"""Internal HTTP routes for the Member entity.

These routes are consumed by the ATDM agent's seeder, not by humans. They
intentionally live under `/internal/` to distinguish them from any future
public API.
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, HTTPException, Query, status

from app.models.member import Member
from app.repositories import member as member_repo

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/members", status_code=status.HTTP_201_CREATED)
async def create_member(member: Member) -> dict[str, str]:
    """Insert a Member. The Pydantic model already validates NFR-010 markers;
    the DB CHECKs are the second layer. FK violations on plan_id surface as 422.
    """
    try:
        await member_repo.insert_member(member)
    except asyncpg.UniqueViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "MEMBER_ALREADY_EXISTS",
                    "message": str(e),
                    "details": {"member_id": member.member_id},
                }
            },
        ) from e
    except asyncpg.ForeignKeyViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "FK_VIOLATION",
                    "message": str(e),
                    "details": {"plan_id": member.plan_id},
                }
            },
        ) from e
    except asyncpg.CheckViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "CHECK_VIOLATION",
                    "message": str(e),
                }
            },
        ) from e
    return {"member_id": member.member_id, "status": "created"}


@router.delete("/members")
async def delete_members_by_run(
    run_id: str = Query(..., min_length=1, description="test_run_id to scope the delete"),
) -> dict[str, object]:
    deleted = await member_repo.delete_by_run_id(run_id)
    return {"run_id": run_id, "deleted_count": deleted}
