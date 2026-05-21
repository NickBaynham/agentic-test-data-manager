"""`atdm` CLI.

Subcommands wrap each ATDM agent HTTP endpoint:

  atdm request <scenario>          → POST /test-data/requests
  atdm reset <run_id> --token T    → POST /test-data/runs/<run_id>/reset
  atdm reset-all --confirm         → POST /test-data/reset/all (X-Confirm: yes)
  atdm baseline-snapshot           → POST /test-data/baseline/snapshot
  atdm baseline-restore            → POST /test-data/baseline/restore
  atdm baseline-list               → GET  /test-data/baseline/list
  atdm audit <run_id>              → GET  /audit/runs/<run_id>
  atdm scenarios                   → GET  /catalog/scenarios

Global flag `--output (human|json)` selects the print format.
Non-zero exit on any API error.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Annotated, Any

import typer

from atdm.client import AtdmClient, AtdmClientError

app = typer.Typer(
    name="atdm",
    help="Agentic Test Data Manager - CLI for the local stack.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Output handling
# ---------------------------------------------------------------------------


def _output() -> str:
    return os.environ.get("ATDM_CLI_OUTPUT", "human")


def _print(payload: Any) -> None:
    """Print payload according to ATDM_CLI_OUTPUT mode."""
    if _output() == "json":
        typer.echo(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return

    if isinstance(payload, dict):
        for k, v in payload.items():
            if isinstance(v, dict | list):
                typer.echo(f"{k}: {json.dumps(v, default=str)}")
            else:
                typer.echo(f"{k}: {v}")
    elif isinstance(payload, list):
        for item in payload:
            typer.echo(json.dumps(item, default=str))
    else:
        typer.echo(str(payload))


def _emit_error(e: AtdmClientError) -> None:
    typer.echo(f"error: HTTP {e.status_code}", err=True)
    typer.echo(json.dumps(e.body, indent=2, default=str), err=True)


# ---------------------------------------------------------------------------
# Global options
# ---------------------------------------------------------------------------


@app.callback()
def _root(
    output: Annotated[
        str,
        typer.Option(
            "--output",
            "-o",
            help="Output format: human or json.",
            envvar="ATDM_CLI_OUTPUT",
        ),
    ] = "human",
) -> None:
    """Set the output format for all subcommands."""
    os.environ["ATDM_CLI_OUTPUT"] = output


# ---------------------------------------------------------------------------
# Scenario lifecycle commands
# ---------------------------------------------------------------------------


@app.command()
def request(
    scenario: Annotated[str, typer.Argument(help="Scenario ID to request.")],
    constraint: Annotated[
        list[str] | None,
        typer.Option(
            "--constraint",
            "-c",
            help="Per-constraint override, format key=value. Repeatable.",
        ),
    ] = None,
    playwright: Annotated[
        bool,
        typer.Option("--playwright/--no-playwright", help="Emit a Playwright JSON fixture."),
    ] = False,
    pytest_fixture: Annotated[
        bool,
        typer.Option("--pytest/--no-pytest", help="Emit a pytest module fixture."),
    ] = False,
) -> None:
    """POST a scenario request."""
    constraints: dict[str, Any] = {}
    for kv in constraint or []:
        if "=" not in kv:
            typer.echo(f"bad --constraint value (need key=value): {kv}", err=True)
            raise typer.Exit(code=2)
        k, v = kv.split("=", 1)
        constraints[k] = v

    client = AtdmClient()
    try:
        response = client.request_scenario(
            scenario,
            constraints=constraints,
            return_playwright_fixture=playwright,
            return_pytest_fixture=pytest_fixture,
        )
    except AtdmClientError as e:
        _emit_error(e)
        raise typer.Exit(code=1) from e
    _print(response)


@app.command()
def reset(
    run_id: Annotated[str, typer.Argument(help="Test run ID to reset.")],
    token: Annotated[str, typer.Option("--token", "-t", help="Cleanup token from the request.")],
) -> None:
    """POST a cleanup-token-gated reset for one run."""
    client = AtdmClient()
    try:
        response = client.reset_run(run_id, token)
    except AtdmClientError as e:
        _emit_error(e)
        raise typer.Exit(code=1) from e
    _print(response)


@app.command("reset-all")
def reset_all(
    confirm: Annotated[
        bool,
        typer.Option(
            "--confirm/--no-confirm",
            help="REQUIRED. Deletes every test_run_id-tagged row.",
        ),
    ] = False,
) -> None:
    """Clear every test_run_id-tagged row across all tables."""
    if not confirm:
        typer.echo("reset-all requires --confirm (destructive).", err=True)
        raise typer.Exit(code=2)
    client = AtdmClient()
    try:
        response = client.reset_all()
    except AtdmClientError as e:
        _emit_error(e)
        raise typer.Exit(code=1) from e
    _print(response)


# ---------------------------------------------------------------------------
# Baseline commands
# ---------------------------------------------------------------------------


@app.command("baseline-snapshot")
def baseline_snapshot(
    baseline_id: Annotated[
        str | None,
        typer.Option("--baseline-id", "-b", help="Optional ID. Auto-generated if omitted."),
    ] = None,
) -> None:
    """Capture every mutable + reference table to Parquet in MinIO."""
    client = AtdmClient()
    try:
        response = client.baseline_snapshot(baseline_id)
    except AtdmClientError as e:
        _emit_error(e)
        raise typer.Exit(code=1) from e
    _print(response)


@app.command("baseline-restore")
def baseline_restore(
    baseline_id: Annotated[
        str | None,
        typer.Option("--baseline-id", "-b", help="ID to restore. Latest if omitted."),
    ] = None,
) -> None:
    """Truncate everything and re-insert from the named (or latest) baseline."""
    client = AtdmClient()
    try:
        response = client.baseline_restore(baseline_id)
    except AtdmClientError as e:
        _emit_error(e)
        raise typer.Exit(code=1) from e
    _print(response)


@app.command("baseline-list")
def baseline_list() -> None:
    """List every captured baseline, newest first."""
    client = AtdmClient()
    try:
        response = client.baseline_list()
    except AtdmClientError as e:
        _emit_error(e)
        raise typer.Exit(code=1) from e
    _print(response)


# ---------------------------------------------------------------------------
# Read commands
# ---------------------------------------------------------------------------


@app.command()
def audit(
    run_id: Annotated[str, typer.Argument(help="Test run ID to look up.")],
) -> None:
    """Print the audit trail for a run."""
    client = AtdmClient()
    try:
        response = client.get_audit(run_id)
    except AtdmClientError as e:
        _emit_error(e)
        raise typer.Exit(code=1) from e
    _print(response)


@app.command()
def scenarios() -> None:
    """List the loaded scenario definitions."""
    client = AtdmClient()
    try:
        response = client.get_scenarios()
    except AtdmClientError as e:
        _emit_error(e)
        raise typer.Exit(code=1) from e
    _print(response)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Console script entry point."""
    app()


if __name__ == "__main__":
    main()
    sys.exit(0)
