"""Server-side reset routes: reset/all-tagged + baseline snapshot/restore/list.

Phase 5 endpoints. Phase 3+4 endpoints (POST /internal/scenarios/seed, DELETE
/internal/scenarios?run_id=) cover `reset_run`. These cover the remaining
three strategies (`reset_all`, `baseline_snapshot`, `baseline_restore`).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from app.db.session import connection
from app.reset import snapshotter
from app.reset.strategies import FK_INSERT_ORDER

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/reset/all-tagged")
async def reset_all_tagged() -> dict[str, object]:
    """Clear every test_run_id IS NOT NULL row in one transaction.

    Baseline reference rows (test_run_id IS NULL on procedure_code,
    diagnosis_code) are preserved.
    """
    counts: dict[str, int] = {}
    async with connection() as conn, conn.transaction():
        # Reverse FK order so children go first.
        for table in reversed(FK_INSERT_ORDER):
            result = await conn.execute(
                f"DELETE FROM {table} WHERE test_run_id IS NOT NULL"  # noqa: S608
            )
            parts = result.split()
            counts[table] = int(parts[1]) if len(parts) == 2 and parts[0] == "DELETE" else 0
    return {"deleted_counts": counts}


@router.post("/baseline/snapshot", status_code=status.HTTP_201_CREATED)
async def baseline_snapshot(baseline_id: str = Query(..., min_length=1)) -> dict[str, Any]:
    """Capture all 7 tables to Parquet under baselines/{baseline_id}/ in MinIO."""
    manifest = await snapshotter.snapshot_baseline(baseline_id)
    return manifest


@router.post("/baseline/restore")
async def baseline_restore(
    baseline_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Truncate every mutable + reference table and re-insert from baseline.

    If baseline_id is omitted, restores the most-recently-captured baseline.
    Returns 404 if no baselines exist or the named one is missing.
    """
    if baseline_id is None:
        baseline_id = snapshotter.latest_baseline_id()
        if baseline_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "NO_BASELINE",
                        "message": "no baseline snapshots exist yet",
                    }
                },
            )
    try:
        result = await snapshotter.restore_baseline(baseline_id)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "BASELINE_NOT_FOUND",
                    "message": str(e),
                }
            },
        ) from e
    return result


@router.get("/baseline/list")
async def baseline_list() -> dict[str, Any]:
    """Return every known baseline, newest first."""
    return {"baselines": snapshotter.list_baselines()}
