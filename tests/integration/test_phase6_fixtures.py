"""Phase 6 integration tests — fixture delivery.

Maps to BRD acceptance blocks D1 (Playwright JSON) and D2 (pytest module),
exercised against the live stack via POST /test-data/requests with the
relevant delivery flags.

The agent writes fixtures inside its container at /fixtures/...; the host
sees them at ./automation/fixtures/... thanks to the bind-mount configured
in infra/docker-compose.yml. The translation between the two is captured in
`_host_path` below.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from tests.integration.conftest import REPO_ROOT

ATDM = "http://localhost:18001"
SUT = "http://localhost:18000"
AUTH = "Bearer dev-token-change-me"
HOST_FIXTURE_DIR = REPO_ROOT / "automation" / "fixtures"


def _request(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode() if body is not None else None
    headers: dict[str, str] = {"authorization": AUTH}
    if body is not None:
        headers["content-type"] = "application/json"
    req = urllib.request.Request(  # noqa: S310
        f"{ATDM}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            payload = resp.read()
            return resp.status, (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _host_path(container_path: str) -> Path:
    """Translate /fixtures/<file> (container) to host-side <repo>/automation/fixtures/<file>."""
    return HOST_FIXTURE_DIR / Path(container_path).name


def _force_cleanup(run_id: str) -> None:
    with contextlib.suppress(urllib.error.URLError):
        urllib.request.urlopen(  # noqa: S310
            urllib.request.Request(
                f"{SUT}/internal/scenarios?run_id={run_id}",
                method="DELETE",
            )
        )


# -----------------------------------------------------------------------------
# D1 — Playwright JSON fixture
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_playwright_fixture_written_to_disk_and_returned(compose_stack: None) -> None:
    code, body = _request(
        "POST",
        "/test-data/requests",
        body={
            "scenario": "active_member_clean",
            "delivery": {
                "seed_target": True,
                "return_playwright_fixture": True,
                "return_pytest_fixture": False,
            },
        },
    )
    assert code == 200
    run_id = body["test_run_id"]
    try:
        # Response includes the container-side path.
        container_path = body["fixtures"]["playwright"]
        assert container_path is not None
        assert container_path.endswith(".json")
        assert body["fixtures"]["pytest"] is None  # not requested

        # Host-side file actually exists.
        host_file = _host_path(container_path)
        assert host_file.exists(), f"missing host fixture file: {host_file}"

        # Required keys + values.
        payload = json.loads(host_file.read_text())
        assert set(payload.keys()) == {"scenario_id", "test_run_id", "data", "cleanup"}
        assert payload["scenario_id"] == "active_member_clean"
        assert payload["test_run_id"] == run_id
        assert payload["data"]["member_id"].startswith("m-")
        assert payload["cleanup"]["cleanup_token"] == body["cleanup"]["cleanup_token"]
    finally:
        _force_cleanup(run_id)


# -----------------------------------------------------------------------------
# D2 — pytest module fixture
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_pytest_fixture_written_and_importable(compose_stack: None) -> None:
    code, body = _request(
        "POST",
        "/test-data/requests",
        body={
            "scenario": "claim_denial_active_member",
            "delivery": {
                "seed_target": True,
                "return_playwright_fixture": False,
                "return_pytest_fixture": True,
            },
        },
    )
    assert code == 200
    run_id = body["test_run_id"]
    try:
        container_path = body["fixtures"]["pytest"]
        assert container_path is not None
        assert container_path.endswith(".py")
        assert body["fixtures"]["playwright"] is None  # not requested

        host_file = _host_path(container_path)
        assert host_file.exists()

        # Import as a module and call scenario_data().
        spec = importlib.util.spec_from_file_location(f"atdm_fixture_{run_id}", host_file)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        # Register before exec so __spec__ resolves correctly.
        sys.modules[f"atdm_fixture_{run_id}"] = module
        try:
            spec.loader.exec_module(module)
            assert module.SCENARIO_ID == "claim_denial_active_member"
            assert run_id == module.TEST_RUN_ID
            data = module.scenario_data()
            assert data["scenario_id"] == "claim_denial_active_member"
            assert data["test_run_id"] == run_id
            assert data["data"]["claim_id"].startswith("claim-")
        finally:
            sys.modules.pop(f"atdm_fixture_{run_id}", None)
    finally:
        _force_cleanup(run_id)


# -----------------------------------------------------------------------------
# Both at once + audit event
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_both_fixtures_emitted_at_once_with_audit_event(compose_stack: None) -> None:
    code, body = _request(
        "POST",
        "/test-data/requests",
        body={
            "scenario": "active_member_clean",
            "delivery": {
                "seed_target": True,
                "return_playwright_fixture": True,
                "return_pytest_fixture": True,
            },
        },
    )
    assert code == 200
    run_id = body["test_run_id"]
    try:
        assert body["fixtures"]["playwright"] is not None
        assert body["fixtures"]["pytest"] is not None
        assert _host_path(body["fixtures"]["playwright"]).exists()
        assert _host_path(body["fixtures"]["pytest"]).exists()

        # Audit trail records `fixtures_emitted`.
        acode, trail = _request("GET", f"/audit/runs/{run_id}")
        assert acode == 200
        actions = [e["action"] for e in trail["events"]]
        assert "fixtures_emitted" in actions
        ev = next(e for e in trail["events"] if e["action"] == "fixtures_emitted")
        assert "playwright" in ev["outputs"]["fixtures"]
        assert "pytest" in ev["outputs"]["fixtures"]
    finally:
        _force_cleanup(run_id)


@pytest.mark.integration
def test_no_fixtures_emitted_when_flags_false(compose_stack: None) -> None:
    code, body = _request(
        "POST",
        "/test-data/requests",
        body={
            "scenario": "active_member_clean",
            "delivery": {
                "seed_target": True,
                "return_playwright_fixture": False,
                "return_pytest_fixture": False,
            },
        },
    )
    assert code == 200
    run_id = body["test_run_id"]
    try:
        assert body["fixtures"] == {"playwright": None, "pytest": None}

        acode, trail = _request("GET", f"/audit/runs/{run_id}")
        assert acode == 200
        actions = [e["action"] for e in trail["events"]]
        assert "fixtures_emitted" not in actions  # didn't fire
    finally:
        _force_cleanup(run_id)
