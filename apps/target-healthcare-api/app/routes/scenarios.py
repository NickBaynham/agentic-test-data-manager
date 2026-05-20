"""Atomic scenario bundle endpoints.

`POST /internal/scenarios/seed` accepts a bundle of entities and inserts them
all in one Postgres transaction. Any FK / CHECK / unique violation rolls the
whole bundle back automatically — no need for application-level saga
compensation.

`DELETE /internal/scenarios?run_id=...` deletes all entities for the run in
FK-safe reverse order, in one transaction.

These endpoints are the Phase 4 successor to the per-entity routes used in
Phase 2/3. Per-entity routes (POST /internal/members, POST /internal/plans)
remain for direct-entity testing and backward compatibility.
"""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.db.session import connection
from app.models.claim import Claim
from app.models.codes import DiagnosisCode, ProcedureCode
from app.models.eligibility import Eligibility
from app.models.member import Member
from app.models.plan import Plan
from app.models.provider import Provider
from app.repositories import claim as claim_repo
from app.repositories import codes as codes_repo
from app.repositories import eligibility as eligibility_repo
from app.repositories import member as member_repo
from app.repositories import plan as plan_repo
from app.repositories import provider as provider_repo

router = APIRouter(prefix="/internal", tags=["internal"])


class ScenarioBundle(BaseModel):
    model_config = ConfigDict(frozen=True)

    procedure_codes: list[ProcedureCode] = Field(default_factory=list)
    diagnosis_codes: list[DiagnosisCode] = Field(default_factory=list)
    plan: Plan | None = None
    provider: Provider | None = None
    member: Member | None = None
    eligibility: Eligibility | None = None
    claim: Claim | None = None


@router.post("/scenarios/seed", status_code=status.HTTP_201_CREATED)
async def seed_scenario(bundle: ScenarioBundle) -> dict[str, object]:
    """Insert every entity in the bundle in one Postgres transaction.

    Order respects FKs: codes → plan → provider → member → eligibility → claim.
    """
    counts: dict[str, int] = {}
    try:
        async with connection() as conn, conn.transaction():
            for pc in bundle.procedure_codes:
                await codes_repo.insert_procedure_code(pc, conn=conn)
            counts["procedure_codes"] = len(bundle.procedure_codes)

            for dc in bundle.diagnosis_codes:
                await codes_repo.insert_diagnosis_code(dc, conn=conn)
            counts["diagnosis_codes"] = len(bundle.diagnosis_codes)

            if bundle.plan is not None:
                await plan_repo.insert_plan(bundle.plan, conn=conn)
                counts["plan"] = 1

            if bundle.provider is not None:
                await provider_repo.insert_provider(bundle.provider, conn=conn)
                counts["provider"] = 1

            if bundle.member is not None:
                await member_repo.insert_member(bundle.member, conn=conn)
                counts["member"] = 1

            if bundle.eligibility is not None:
                await eligibility_repo.insert_eligibility(bundle.eligibility, conn=conn)
                counts["eligibility"] = 1

            if bundle.claim is not None:
                await claim_repo.insert_claim(bundle.claim, conn=conn)
                counts["claim"] = 1
    except asyncpg.UniqueViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "ALREADY_EXISTS", "message": str(e)}},
        ) from e
    except asyncpg.ForeignKeyViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "FK_VIOLATION", "message": str(e)}},
        ) from e
    except asyncpg.CheckViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "CHECK_VIOLATION", "message": str(e)}},
        ) from e

    return {"status": "seeded", "counts": counts}


@router.delete("/scenarios")
async def delete_scenario_by_run(
    run_id: str = Query(..., min_length=1, description="test_run_id to scope the delete"),
) -> dict[str, object]:
    """Delete every entity for the run in FK-safe reverse order, atomically.

    Order: claim → eligibility → member → plan → provider → per-run codes.
    Shared (test_run_id IS NULL) baseline reference rows are untouched.
    """
    counts: dict[str, Any] = {}
    async with connection() as conn, conn.transaction():
        counts["claim"] = await claim_repo.delete_by_run_id(run_id, conn=conn)
        counts["eligibility"] = await eligibility_repo.delete_by_run_id(run_id, conn=conn)
        counts["member"] = await member_repo.delete_by_run_id(run_id, conn=conn)
        counts["plan"] = await plan_repo.delete_by_run_id(run_id, conn=conn)
        counts["provider"] = await provider_repo.delete_by_run_id(run_id, conn=conn)
        counts["procedure_codes"] = await codes_repo.delete_procedure_codes_by_run(
            run_id, conn=conn
        )
        counts["diagnosis_codes"] = await codes_repo.delete_diagnosis_codes_by_run(
            run_id, conn=conn
        )
    return {"run_id": run_id, "deleted_counts": counts}
