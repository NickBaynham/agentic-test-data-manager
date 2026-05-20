"""GET /audit/runs/{run_id} — return full audit trail as JSON.

Read-only — there is no mutation surface for audit events (NFR-011).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from app.audit import writer as audit_writer
from app.catalog import store as catalog_store

router = APIRouter()


@router.get("/audit/runs/{run_id}")
async def get_audit_trail(run_id: str, response: Response) -> dict[str, object]:
    minio_client = catalog_store.make_minio_client()
    events = audit_writer.read_events(minio_client, run_id)
    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RUN_NOT_FOUND",
                    "message": f"no audit trail for run_id {run_id!r}",
                }
            },
        )

    catalog_entry = catalog_store.read_run(minio_client, run_id)
    response.headers["x-audit-source"] = f"s3://atdm-audit/runs/{run_id}.parquet"

    return {
        "run_id": run_id,
        "scenario_id": catalog_entry["scenario_id"] if catalog_entry else None,
        "invoker": events[0]["invoker"] if events else None,
        "planner_mode": events[0]["inputs"].get("planner_mode") if events else None,
        "reset_status": catalog_entry["status"] if catalog_entry else None,
        "started_at": events[0]["timestamp"] if events else None,
        "finished_at": events[-1]["timestamp"] if events else None,
        "events": events,
    }
