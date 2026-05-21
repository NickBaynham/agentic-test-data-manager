"""Server-rendered audit UI.

`GET /ui/audit/{run_id}` returns a Pico.css-styled HTML page summarizing one
run's audit trail. Read-only and unauthenticated (NFR-004 — local network
only; no real data ever lives in the audit log).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.audit import writer as audit_writer
from app.catalog import store as catalog_store

router = APIRouter()

# Templates live next to this module so they ship with the package.
_TEMPLATE_DIR = Path(__file__).parent / "templates"
_templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))


def _extract_validator_decisions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pull every validator decision out of `validators_passed` / `plan_rejected`."""
    decisions: list[dict[str, Any]] = []
    for ev in events:
        if ev["action"] == "validators_passed":
            for name in ev.get("outputs", {}).get("validators", []):
                decisions.append({"validator": name, "ok": True, "message": ""})
        elif ev["action"] == "plan_rejected":
            for fv in ev.get("outputs", {}).get("failed_validators", []):
                decisions.append(
                    {
                        "validator": fv.get("validator"),
                        "ok": False,
                        "message": fv.get("message"),
                    }
                )
    return decisions


def _extract_plan_steps(events: list[dict[str, Any]]) -> list[str]:
    for ev in events:
        if ev["action"] == "plan_resolved":
            return [s.get("generator", "?") for s in ev.get("outputs", {}).get("steps", [])]
    return []


def _extract_validators(events: list[dict[str, Any]]) -> list[str]:
    for ev in events:
        if ev["action"] == "plan_resolved":
            vs = ev.get("outputs", {}).get("validators", [])
            if isinstance(vs, list):
                return [str(v) for v in vs]
    return []


def _extract_records_created(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for ev in events:
        if ev["action"] == "seed_completed":
            return list(ev.get("outputs", {}).get("records_created", []))
    return []


def _extract_fixtures(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for ev in events:
        if ev["action"] == "fixtures_emitted":
            fixtures: dict[str, Any] | None = ev.get("outputs", {}).get("fixtures")
            return fixtures
    return None


@router.get("/ui/audit/{run_id}", response_class=HTMLResponse, include_in_schema=False)
async def audit_ui(run_id: str, request: Request) -> HTMLResponse:
    minio_client = catalog_store.make_minio_client()
    events = audit_writer.read_events(minio_client, run_id)
    if not events:
        return _templates.TemplateResponse(
            request,
            "audit_404.html",
            {"run_id": run_id},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    catalog_entry = catalog_store.read_run(minio_client, run_id)

    context: dict[str, Any] = {
        "run_id": run_id,
        "scenario_id": catalog_entry["scenario_id"] if catalog_entry else None,
        "invoker": events[0]["invoker"],
        "planner_mode": events[0]["inputs"].get("planner_mode") if events else "rule",
        "reset_status": catalog_entry["status"] if catalog_entry else None,
        "started_at": events[0]["timestamp"],
        "finished_at": events[-1]["timestamp"],
        "plan_steps": _extract_plan_steps(events),
        "validators": _extract_validators(events),
        "validator_decisions": _extract_validator_decisions(events),
        "records_created": _extract_records_created(events),
        "fixtures": _extract_fixtures(events),
        "events": events,
    }
    return _templates.TemplateResponse(request, "audit_run.html", context)
