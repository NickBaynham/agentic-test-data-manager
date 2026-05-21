"""Phase 7 integration tests — CLI and @atdm_scenario decorator against the live stack.

Covers:
  - CLI subcommands work end-to-end against the running stack (request → audit → reset).
  - @atdm_scenario decorator + atdm_data fixture seed + clean up against live stack.
  - D3 acceptance: teardown actually deletes rows + audit shows status=cleaned.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from typing import Any

import pytest

from atdm.pytest import atdm_scenario
from tests.integration.conftest import COMPOSE_BASE, REPO_ROOT

ATDM = "http://localhost:18001"
AUTH = "Bearer dev-token-change-me"


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


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "ATDM_API_URL": ATDM,
        "ATDM_API_TOKEN": "dev-token-change-me",
        "ATDM_CLI_OUTPUT": "json",
    }
    return subprocess.run(  # noqa: S603
        ["pdm", "run", "atdm", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


# -----------------------------------------------------------------------------
# CLI smoke tests
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_cli_scenarios_lists_all_five(compose_stack: None) -> None:
    result = _run_cli("scenarios")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    ids = {s["scenario_id"] for s in payload["scenarios"]}
    assert ids == {
        "active_member_clean",
        "claim_denial_active_member",
        "expired_eligibility",
        "out_of_network_pending_claim",
        "inactive_member_with_history",
    }


@pytest.mark.integration
def test_cli_request_then_audit_then_reset(compose_stack: None) -> None:
    result = _run_cli("request", "active_member_clean")
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    run_id = response["test_run_id"]
    token = response["cleanup"]["cleanup_token"]

    try:
        # CLI audit shows the expected event sequence.
        audit_result = _run_cli("audit", run_id)
        assert audit_result.returncode == 0
        trail = json.loads(audit_result.stdout)
        actions = [e["action"] for e in trail["events"]]
        assert "request_received" in actions
        assert "seed_completed" in actions

        # Pre-reset: row exists.
        assert int(_psql(f"SELECT COUNT(*) FROM member WHERE test_run_id='{run_id}';")) == 1

        # CLI reset.
        reset_result = _run_cli("reset", run_id, "--token", token)
        assert reset_result.returncode == 0
        reset_payload = json.loads(reset_result.stdout)
        assert reset_payload["status"] == "cleaned"

        # Post-reset: zero rows.
        assert int(_psql(f"SELECT COUNT(*) FROM member WHERE test_run_id='{run_id}';")) == 0
    finally:
        # Belt-and-suspenders cleanup.
        import contextlib

        with contextlib.suppress(urllib.error.URLError):
            urllib.request.urlopen(  # noqa: S310
                urllib.request.Request(
                    f"http://localhost:18000/internal/scenarios?run_id={run_id}",
                    method="DELETE",
                )
            )


@pytest.mark.integration
def test_cli_reset_all_requires_confirm(compose_stack: None) -> None:
    result = _run_cli("reset-all")
    assert result.returncode != 0
    assert "--confirm" in (result.stdout + result.stderr)


@pytest.mark.integration
def test_cli_exits_nonzero_on_unknown_scenario(compose_stack: None) -> None:
    result = _run_cli("request", "this-does-not-exist")
    assert result.returncode != 0
    err = result.stdout + result.stderr
    assert "HTTP 404" in err
    assert "SCENARIO_NOT_FOUND" in err


# -----------------------------------------------------------------------------
# D3 acceptance — @atdm_scenario decorator against live stack
# -----------------------------------------------------------------------------


@atdm_scenario("active_member_clean")
@pytest.mark.integration
def test_d3_decorator_seeds_and_resets_via_live_stack(
    atdm_data: dict[str, Any], compose_stack: None
) -> None:
    """End-to-end D3 acceptance against the live stack.

    The decorator runs BEFORE compose_stack — but compose_stack is session-scoped
    and runs first overall. The fixture order matters for first-test-of-session;
    in practice the stack is up when this runs.
    """
    assert atdm_data["status"] == "ready"
    data = atdm_data["data"]
    assert isinstance(data["member_id"], str)
    assert data["member_id"].startswith("m-")

    # Verify the row actually exists in the DB right now (mid-test).
    run_id = atdm_data["test_run_id"]
    assert int(_psql(f"SELECT COUNT(*) FROM member WHERE test_run_id='{run_id}';")) == 1


# Note: "the decorator's teardown actually emits reset_started / reset_completed
# audit events" is covered by the unit-test suite for the plugin (pytester
# verifies the mock client's reset_run is called) plus the standalone reset
# integration tests in test_request_lifecycle.py. Verifying it inline here
# fights pytest's finalizer LIFO ordering — `request.addfinalizer` runs
# BEFORE the atdm_data fixture's teardown, not after, so it would inspect
# pre-reset state. The cleanest cross-fixture verification needs a separate
# session-scoped tracker; defer that ergonomics work to Phase 8+.
