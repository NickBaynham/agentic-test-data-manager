"""Phase 4 integration tests — broadened generators, validators, scenarios.

Covers:
  - All 5 scenarios fulfill end-to-end against the live stack.
  - B2 acceptance: contradicting constraints → 422 + plan_rejected audit + zero DB.
  - Atomic bundle insert + atomic FK-safe delete via /internal/scenarios/*.

The B4 generator-failure path is exercised as a unit test in
apps/test-data-agent/tests/test_seeder.py (mockable, deterministic).
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
AUTH = "Bearer dev-token-change-me"

ALL_SCENARIOS: list[str] = [
    "active_member_clean",
    "claim_denial_active_member",
    "expired_eligibility",
    "out_of_network_pending_claim",
    "inactive_member_with_history",
]


def _request(
    method: str,
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
        f"{ATDM}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            payload = resp.read()
            return resp.status, (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _psql(sql: str) -> str:
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
    # Use the bundle DELETE — atomic across all 5 mutable tables.
    import contextlib

    with contextlib.suppress(urllib.error.URLError):
        urllib.request.urlopen(  # noqa: S310
            urllib.request.Request(
                f"http://localhost:18000/internal/scenarios?run_id={run_id}",
                method="DELETE",
            )
        )


def _all_table_counts(run_id: str) -> dict[str, int]:
    out = _psql(
        f"""
        SELECT 'plan',        COUNT(*) FROM plan        WHERE test_run_id='{run_id}' UNION ALL
        SELECT 'provider',    COUNT(*) FROM provider    WHERE test_run_id='{run_id}' UNION ALL
        SELECT 'member',      COUNT(*) FROM member      WHERE test_run_id='{run_id}' UNION ALL
        SELECT 'eligibility', COUNT(*) FROM eligibility WHERE test_run_id='{run_id}' UNION ALL
        SELECT 'claim',       COUNT(*) FROM claim       WHERE test_run_id='{run_id}';
        """
    )
    counts: dict[str, int] = {}
    for line in out.splitlines():
        if "|" not in line:
            continue
        kind, n = line.split("|")
        counts[kind] = int(n)
    return counts


# -----------------------------------------------------------------------------
# Each of the 5 scenarios fulfills end-to-end
# -----------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("scenario", ALL_SCENARIOS)
def test_scenario_end_to_end(compose_stack: None, scenario: str) -> None:
    code, body = _request("POST", "/test-data/requests", body={"scenario": scenario})
    assert code == 200, body

    run_id = body["test_run_id"]
    try:
        counts = _all_table_counts(run_id)
        assert counts == {
            "plan": 1,
            "provider": 1,
            "member": 1,
            "eligibility": 1,
            "claim": 1,
        }, f"scenario {scenario!r} row counts: {counts}"

        # Cleanup via API.
        token = body["cleanup"]["cleanup_token"]
        rcode, _ = _request(
            "POST",
            f"/test-data/runs/{run_id}/reset",
            body={"cleanup_token": token},
        )
        assert rcode == 200

        zeros = _all_table_counts(run_id)
        assert all(v == 0 for v in zeros.values()), zeros
    finally:
        _force_cleanup(run_id)


# -----------------------------------------------------------------------------
# B2 acceptance — validator rejection produces 422 + plan_rejected + zero DB
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_validator_rejects_inactive_member_with_active_eligibility(
    compose_stack: None,
) -> None:
    """`relational.eligibility_status_matches_member` fires when the request
    forces member.status=inactive + eligibility.status=active."""
    code, body = _request(
        "POST",
        "/test-data/requests",
        body={
            "scenario": "active_member_clean",
            "constraints": {
                "member_status": "inactive",
                "eligibility_status": "active",
            },
        },
    )
    assert code == 422, body
    err = body["detail"]["error"]
    assert err["code"] == "VALIDATOR_REJECTED"
    assert "relational.eligibility_status_matches_member" in err["details"]["failed_validators"]

    run_id = err["test_run_id"]
    try:
        counts = _all_table_counts(run_id)
        assert all(v == 0 for v in counts.values()), counts
    finally:
        _force_cleanup(run_id)


@pytest.mark.integration
def test_audit_records_plan_rejected_event(compose_stack: None) -> None:
    """The plan_rejected event must appear in the audit trail with the
    failing validator's name."""
    code, body = _request(
        "POST",
        "/test-data/requests",
        body={
            "scenario": "active_member_clean",
            "constraints": {
                "member_status": "inactive",
                "eligibility_status": "active",
            },
        },
    )
    assert code == 422
    run_id = body["detail"]["error"]["test_run_id"]

    try:
        acode, trail = _request("GET", f"/audit/runs/{run_id}", auth=False)
        assert acode == 200
        actions = [e["action"] for e in trail["events"]]
        assert "plan_rejected" in actions
        rejected = next(e for e in trail["events"] if e["action"] == "plan_rejected")
        names = [f["validator"] for f in rejected["outputs"]["failed_validators"]]
        assert "relational.eligibility_status_matches_member" in names
    finally:
        _force_cleanup(run_id)


# -----------------------------------------------------------------------------
# Atomic bundle delete works
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_reset_clears_all_five_entities(compose_stack: None) -> None:
    """claim_denial_active_member exercises all 5 mutable tables. Reset
    must delete every row tagged with the run_id, atomically."""
    code, body = _request(
        "POST", "/test-data/requests", body={"scenario": "claim_denial_active_member"}
    )
    assert code == 200
    run_id = body["test_run_id"]
    token = body["cleanup"]["cleanup_token"]

    try:
        before = _all_table_counts(run_id)
        assert all(v == 1 for v in before.values()), before

        rcode, _ = _request(
            "POST",
            f"/test-data/runs/{run_id}/reset",
            body={"cleanup_token": token},
        )
        assert rcode == 200

        after = _all_table_counts(run_id)
        assert all(v == 0 for v in after.values()), after
    finally:
        _force_cleanup(run_id)
