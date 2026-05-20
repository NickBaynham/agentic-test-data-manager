"""Internal Plan routes — mirror Member routes."""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, HTTPException, Query, status

from app.models.plan import Plan
from app.repositories import plan as plan_repo

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/plans", status_code=status.HTTP_201_CREATED)
async def create_plan(plan: Plan) -> dict[str, str]:
    try:
        await plan_repo.insert_plan(plan)
    except asyncpg.UniqueViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "PLAN_ALREADY_EXISTS",
                    "message": str(e),
                    "details": {"plan_id": plan.plan_id},
                }
            },
        ) from e
    except asyncpg.CheckViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "CHECK_VIOLATION", "message": str(e)}},
        ) from e
    return {"plan_id": plan.plan_id, "status": "created"}


@router.delete("/plans")
async def delete_plans_by_run(
    run_id: str = Query(..., min_length=1, description="test_run_id to scope the delete"),
) -> dict[str, object]:
    deleted = await plan_repo.delete_by_run_id(run_id)
    return {"run_id": run_id, "deleted_count": deleted}
