"""Claim repository — single SQL surface for the claim table."""

from __future__ import annotations

from app.db.session import DbConn, connection
from app.models.claim import Claim

_INSERT = """
    INSERT INTO claim (
        claim_id, member_id, provider_id, procedure_code, diagnosis_code,
        status, submitted_at, denial_reason, test_run_id
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
"""
_DELETE_BY_RUN = "DELETE FROM claim WHERE test_run_id = $1"


async def insert_claim(
    claim: Claim,
    *,
    conn: DbConn | None = None,
) -> None:
    args = (
        claim.claim_id,
        claim.member_id,
        claim.provider_id,
        claim.procedure_code,
        claim.diagnosis_code,
        claim.status,
        claim.submitted_at,
        claim.denial_reason,
        claim.test_run_id,
    )
    if conn is not None:
        await conn.execute(_INSERT, *args)
        return
    async with connection() as c:
        await c.execute(_INSERT, *args)


async def delete_by_run_id(run_id: str, *, conn: DbConn | None = None) -> int:
    if conn is not None:
        result = await conn.execute(_DELETE_BY_RUN, run_id)
    else:
        async with connection() as c:
            result = await c.execute(_DELETE_BY_RUN, run_id)
    parts = result.split()
    return int(parts[1]) if len(parts) == 2 and parts[0] == "DELETE" else 0
