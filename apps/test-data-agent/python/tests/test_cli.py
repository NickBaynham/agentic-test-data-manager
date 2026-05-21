"""Unit tests for the `atdm` CLI.

Uses Typer's CliRunner and patches AtdmClient to avoid network calls.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from atdm.cli import app
from atdm.client import AtdmClientError

runner = CliRunner()


def _ok_response(test_run_id: str = "01TESTRUN") -> dict[str, Any]:
    return {
        "request_id": "tdr_abc",
        "test_run_id": test_run_id,
        "status": "ready",
        "data": {"member_id": f"m-{test_run_id}", "plan_id": f"plan-{test_run_id}"},
        "fixtures": {"playwright": None, "pytest": None},
        "cleanup": {
            "cleanup_token": "tok",
            "endpoint": f"/test-data/runs/{test_run_id}/reset",
        },
    }


def test_help_runs() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "request" in result.stdout
    assert "reset" in result.stdout
    assert "baseline-snapshot" in result.stdout


def test_request_happy_path() -> None:
    with patch("atdm.cli.AtdmClient") as MockClient:
        MockClient.return_value.request_scenario.return_value = _ok_response()
        result = runner.invoke(app, ["request", "active_member_clean"])
    assert result.exit_code == 0
    assert "01TESTRUN" in result.stdout


def test_request_with_json_output() -> None:
    with patch("atdm.cli.AtdmClient") as MockClient:
        MockClient.return_value.request_scenario.return_value = _ok_response()
        result = runner.invoke(app, ["--output", "json", "request", "active_member_clean"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert payload["test_run_id"] == "01TESTRUN"


def test_request_with_constraints() -> None:
    with patch("atdm.cli.AtdmClient") as MockClient:
        MockClient.return_value.request_scenario.return_value = _ok_response()
        result = runner.invoke(
            app,
            [
                "request",
                "claim_denial_active_member",
                "-c",
                "provider_network=out_of_network",
                "-c",
                "member_status=active",
            ],
        )
    assert result.exit_code == 0
    MockClient.return_value.request_scenario.assert_called_once()
    call_kwargs = MockClient.return_value.request_scenario.call_args.kwargs
    assert call_kwargs["constraints"] == {
        "provider_network": "out_of_network",
        "member_status": "active",
    }


def test_request_bad_constraint_format() -> None:
    result = runner.invoke(app, ["request", "scenario", "-c", "no-equals-sign"])
    assert result.exit_code == 2
    assert "bad --constraint" in result.stderr or "bad --constraint" in result.stdout


def test_request_exits_non_zero_on_api_error() -> None:
    with patch("atdm.cli.AtdmClient") as MockClient:
        MockClient.return_value.request_scenario.side_effect = AtdmClientError(
            "POST /test-data/requests returned 422",
            status_code=422,
            body={"error": {"code": "VALIDATOR_REJECTED"}},
        )
        result = runner.invoke(app, ["request", "active_member_clean"])
    assert result.exit_code == 1
    err_combined = result.stdout + (result.stderr or "")
    assert "HTTP 422" in err_combined
    assert "VALIDATOR_REJECTED" in err_combined


def test_reset_calls_client() -> None:
    with patch("atdm.cli.AtdmClient") as MockClient:
        MockClient.return_value.reset_run.return_value = {"status": "cleaned"}
        result = runner.invoke(app, ["reset", "01RUN", "--token", "T"])
    assert result.exit_code == 0
    MockClient.return_value.reset_run.assert_called_once_with("01RUN", "T")


def test_reset_all_requires_confirm() -> None:
    result = runner.invoke(app, ["reset-all"])
    assert result.exit_code == 2
    assert "--confirm" in (result.stderr or result.stdout)


def test_reset_all_with_confirm_proceeds() -> None:
    with patch("atdm.cli.AtdmClient") as MockClient:
        MockClient.return_value.reset_all.return_value = {
            "strategy": "reset_all",
            "deleted_counts": {"member": 0},
        }
        result = runner.invoke(app, ["reset-all", "--confirm"])
    assert result.exit_code == 0
    assert "reset_all" in result.stdout


def test_baseline_snapshot_passes_id_through() -> None:
    with patch("atdm.cli.AtdmClient") as MockClient:
        MockClient.return_value.baseline_snapshot.return_value = {"baseline_id": "bl-x"}
        result = runner.invoke(app, ["baseline-snapshot", "--baseline-id", "bl-test"])
    assert result.exit_code == 0
    MockClient.return_value.baseline_snapshot.assert_called_once_with("bl-test")


def test_baseline_restore_defaults_to_latest() -> None:
    with patch("atdm.cli.AtdmClient") as MockClient:
        MockClient.return_value.baseline_restore.return_value = {"baseline_id": "latest"}
        result = runner.invoke(app, ["baseline-restore"])
    assert result.exit_code == 0
    MockClient.return_value.baseline_restore.assert_called_once_with(None)


def test_audit_prints_events() -> None:
    with patch("atdm.cli.AtdmClient") as MockClient:
        MockClient.return_value.get_audit.return_value = {
            "run_id": "01R",
            "events": [{"action": "request_received"}, {"action": "seed_completed"}],
        }
        result = runner.invoke(app, ["--output", "json", "audit", "01R"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    actions = [e["action"] for e in payload["events"]]
    assert "request_received" in actions


def test_scenarios_lists_loaded() -> None:
    with patch("atdm.cli.AtdmClient") as MockClient:
        MockClient.return_value.get_scenarios.return_value = {
            "scenarios": [{"scenario_id": "active_member_clean", "generators": ["generate_plan"]}]
        }
        result = runner.invoke(app, ["--output", "json", "scenarios"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["scenarios"][0]["scenario_id"] == "active_member_clean"


# CliRunner's mix_stderr is removed in Click 8.2+; on older versions we'd
# need to access result.stderr separately. The asserts above use both.
del pytest  # silence unused import (pytest comes in via the fixture below).
