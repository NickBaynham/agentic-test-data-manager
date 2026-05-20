"""Phase 3 vertical slice tests.

These exercise the full POST /test-data/requests → seed → audit → reset
lifecycle against the live stack.

Maps to BRD §13 acceptance blocks for FR-001/FR-005, FR-030/FR-035, E1, E2;
and PLAN.md Phase 3 exit criteria.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from typing import Any

import pytest

from tests.integration.conftest import COMPOSE_BASE, REPO_ROOT

ATDM = "http://localhost:18001"
TARGET_SUT = "http://localhost:18000"
AUTH = "Bearer dev-token-change-me"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _request(
    method: str,
    base: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    auth: bool = True,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode() if body is not None else None
    headers: dict[str, str] = {}
    if body is not None:
        headers["content-type"] = "application/json"
    if auth:
        headers["authorization"] = AUTH
    req = urllib.request.Request(  # noqa: S310
        f"{base}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            payload = resp.read()
            return resp.status, (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _psql(sql: str) -> str:
    """Run a SQL statement inside the Postgres container and return stdout."""
    result = subprocess.run(  # noqa: S603
        [
            *COMPOSE_BASE,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "atdm",
            "-d",
            "target_healthcare",
            "-tA",
            "-c",
            sql,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _force_cleanup(run_id: str) -> None:
    """Best-effort: scrub all rows for a run regardless of API state.

    Uses the Phase 4 atomic bundle DELETE so FK ordering is handled
    automatically — Phase 4 scenarios produce all 5 mutable entities, so the
    Phase 3 per-entity helper no longer works.
    """
    import contextlib

    with contextlib.suppress(urllib.error.URLError):
        urllib.request.urlopen(  # noqa: S310
            urllib.request.Request(
                f"http://localhost:18000/internal/scenarios?run_id={run_id}",
                method="DELETE",
            )
        )


# -----------------------------------------------------------------------------
# FR-001 / FR-005 — happy path response contract
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_happy_path_request_contract(compose_stack: None) -> None:
    code, body = _request(
        "POST",
        ATDM,
        "/test-data/requests",
        body={
            "domain": "healthcare",
            "scenario": "active_member_clean",
            "constraints": {},
            "delivery": {"seed_target": True},
        },
    )
    assert code == 200, body

    # Contract shape per FR-005.
    assert body["status"] == "ready"
    assert isinstance(body["request_id"], str) and body["request_id"]
    assert isinstance(body["test_run_id"], str) and body["test_run_id"]
    assert body["data"]["member_id"] is not None
    assert body["data"]["plan_id"] is not None
    assert isinstance(body["cleanup"]["cleanup_token"], str)
    assert body["cleanup"]["endpoint"] == f"/test-data/runs/{body['test_run_id']}/reset"

    run_id = body["test_run_id"]
    try:
        # Database evidence — rows actually landed.
        assert int(_psql(f"SELECT COUNT(*) FROM plan   WHERE test_run_id='{run_id}';")) == 1
        assert int(_psql(f"SELECT COUNT(*) FROM member WHERE test_run_id='{run_id}';")) == 1
    finally:
        _force_cleanup(run_id)


# -----------------------------------------------------------------------------
# FR-030 / FR-035 — reset_run contract
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_reset_with_correct_token_cleans_up(compose_stack: None) -> None:
    _, body = _request(
        "POST",
        ATDM,
        "/test-data/requests",
        body={"scenario": "active_member_clean", "constraints": {}},
    )
    run_id = body["test_run_id"]
    token = body["cleanup"]["cleanup_token"]
    try:
        code, reset_body = _request(
            "POST",
            ATDM,
            f"/test-data/runs/{run_id}/reset",
            body={"cleanup_token": token},
        )
        assert code == 200
        assert reset_body["status"] == "cleaned"
        # Phase 4: bundle DELETE returns deleted_counts for all 7 tables it
        # touched (5 mutable + per-run codes which are 0 in this scenario).
        assert reset_body["deleted_counts"]["member"] == 1
        assert reset_body["deleted_counts"]["plan"] == 1

        assert int(_psql(f"SELECT COUNT(*) FROM member WHERE test_run_id='{run_id}';")) == 0
        assert int(_psql(f"SELECT COUNT(*) FROM plan   WHERE test_run_id='{run_id}';")) == 0
    finally:
        _force_cleanup(run_id)


@pytest.mark.integration
def test_reset_is_idempotent(compose_stack: None) -> None:
    _, body = _request(
        "POST",
        ATDM,
        "/test-data/requests",
        body={"scenario": "active_member_clean", "constraints": {}},
    )
    run_id = body["test_run_id"]
    token = body["cleanup"]["cleanup_token"]
    try:
        _request("POST", ATDM, f"/test-data/runs/{run_id}/reset", body={"cleanup_token": token})

        code, reset_body = _request(
            "POST",
            ATDM,
            f"/test-data/runs/{run_id}/reset",
            body={"cleanup_token": token},
        )
        assert code == 200
        assert reset_body["status"] == "already_cleaned"
    finally:
        _force_cleanup(run_id)


@pytest.mark.integration
def test_reset_with_wrong_token_returns_403_and_no_db_effect(compose_stack: None) -> None:
    _, body = _request(
        "POST",
        ATDM,
        "/test-data/requests",
        body={"scenario": "active_member_clean", "constraints": {}},
    )
    run_id = body["test_run_id"]
    try:
        before = int(_psql(f"SELECT COUNT(*) FROM member WHERE test_run_id='{run_id}';"))
        assert before == 1

        code, _ = _request(
            "POST",
            ATDM,
            f"/test-data/runs/{run_id}/reset",
            body={"cleanup_token": "definitely-wrong"},
        )
        assert code == 403

        after = int(_psql(f"SELECT COUNT(*) FROM member WHERE test_run_id='{run_id}';"))
        assert after == 1
    finally:
        _force_cleanup(run_id)


@pytest.mark.integration
def test_reset_unknown_run_returns_404(compose_stack: None) -> None:
    code, body = _request(
        "POST",
        ATDM,
        "/test-data/runs/01TOTALLYNOTAREALRUN/reset",
        body={"cleanup_token": "anything"},
    )
    assert code == 404
    assert "RUN_NOT_FOUND" in json.dumps(body)


# -----------------------------------------------------------------------------
# E1 / E2 — audit trail
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_audit_events_emitted_for_happy_path(compose_stack: None) -> None:
    """E1 acceptance subset: every documented audit action appears for happy path."""
    _, body = _request(
        "POST",
        ATDM,
        "/test-data/requests",
        body={"scenario": "active_member_clean", "constraints": {}},
    )
    run_id = body["test_run_id"]
    try:
        code, trail = _request("GET", ATDM, f"/audit/runs/{run_id}", auth=False)
        assert code == 200

        actions = [e["action"] for e in trail["events"]]
        # Phase 4 added `validators_passed` between seed_started and seed_completed.
        expected = [
            "request_received",
            "plan_resolved",
            "seed_started",
            "validators_passed",
            "seed_completed",
            "catalog_recorded",
        ]
        assert actions == expected, f"unexpected event order: {actions}"

        # Each event has the required fields.
        for ev in trail["events"]:
            for field in (
                "event_id",
                "timestamp",
                "test_run_id",
                "invoker",
                "action",
                "inputs",
                "outputs",
                "status",
                "schema_version",
            ):
                assert field in ev, f"missing field {field!r} in {ev}"

        assert trail["scenario_id"] == "active_member_clean"
        assert trail["planner_mode"] == "rule"
    finally:
        _force_cleanup(run_id)


@pytest.mark.integration
def test_audit_endpoint_returns_404_for_unknown_run(compose_stack: None) -> None:
    code, body = _request("GET", ATDM, "/audit/runs/01NOTAREALRUN", auth=False)
    assert code == 404
    assert "RUN_NOT_FOUND" in json.dumps(body)


@pytest.mark.integration
def test_audit_endpoint_exposes_x_audit_source_header(compose_stack: None) -> None:
    """E2 contract: audit response includes a pointer to the source Parquet file."""
    _, body = _request(
        "POST",
        ATDM,
        "/test-data/requests",
        body={"scenario": "active_member_clean", "constraints": {}},
    )
    run_id = body["test_run_id"]
    try:
        req = urllib.request.Request(  # noqa: S310
            f"{ATDM}/audit/runs/{run_id}", method="GET"
        )
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            assert resp.status == 200
            assert resp.headers.get("x-audit-source") == f"s3://atdm-audit/runs/{run_id}.parquet"
    finally:
        _force_cleanup(run_id)


# -----------------------------------------------------------------------------
# Authentication and planner mode
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_request_without_auth_returns_401(compose_stack: None) -> None:
    code, body = _request(
        "POST",
        ATDM,
        "/test-data/requests",
        body={"scenario": "active_member_clean"},
        auth=False,
    )
    assert code == 401
    assert "AUTH_REQUIRED" in json.dumps(body)


@pytest.mark.integration
def test_unknown_scenario_returns_404(compose_stack: None) -> None:
    code, body = _request(
        "POST",
        ATDM,
        "/test-data/requests",
        body={"scenario": "this-scenario-does-not-exist"},
    )
    assert code == 404
    assert "SCENARIO_NOT_FOUND" in json.dumps(body)


@pytest.mark.integration
def test_health_endpoint_does_not_require_auth(compose_stack: None) -> None:
    code, body = _request("GET", ATDM, "/health", auth=False)
    assert code == 200
    assert body["status"] == "ok"


# Note: ATDM_PLANNER=llm 501 behavior is exercised as a unit test in
# apps/test-data-agent/tests/test_planner_modes.py — restarting the agent
# container mid-integration-run leaves the stack in a transitional state that
# causes flakes downstream.
