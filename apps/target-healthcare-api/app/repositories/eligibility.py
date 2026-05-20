"""Eligibility repository — single SQL surface for the eligibility table."""

from __future__ import annotations

from app.db.session import DbConn, connection
from app.models.eligibility import Eligibility

_INSERT = """
    INSERT INTO eligibility (
        eligibility_id, member_id, effective_from, effective_to, status, test_run_id
    )
    VALUES ($1, $2, $3, $4, $5, $6)
"""
_DELETE_BY_RUN = "DELETE FROM eligibility WHERE test_run_id = $1"


async def insert_eligibility(
    eligibility: Eligibility,
    *,
    conn: DbConn | None = None,
) -> None:
    args = (
        eligibility.eligibility_id,
        eligibility.member_id,
        eligibility.effective_from,
        eligibility.effective_to,
        eligibility.status,
        eligibility.test_run_id,
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
