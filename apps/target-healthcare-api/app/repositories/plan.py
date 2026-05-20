"""Plan repository — single SQL surface for the plan table."""

from __future__ import annotations

from app.db.session import connection
from app.models.plan import Plan

_INSERT = """
    INSERT INTO plan (plan_id, name, coverage_type, effective_date, test_run_id)
    VALUES ($1, $2, $3, $4, $5)
"""

_DELETE_BY_RUN = "DELETE FROM plan WHERE test_run_id = $1"

_COUNT_BY_RUN = "SELECT COUNT(*) FROM plan WHERE test_run_id = $1"


async def insert_plan(plan: Plan) -> None:
    async with connection() as conn:
        await conn.execute(
            _INSERT,
            plan.plan_id,
            plan.name,
            plan.coverage_type,
            plan.effective_date,
            plan.test_run_id,
        )


async def delete_by_run_id(run_id: str) -> int:
    async with connection() as conn:
        result = await conn.execute(_DELETE_BY_RUN, run_id)
    parts = result.split()
    return int(parts[1]) if len(parts) == 2 and parts[0] == "DELETE" else 0


async def count_by_run_id(run_id: str) -> int:
    async with connection() as conn:
        row = await conn.fetchrow(_COUNT_BY_RUN, run_id)
    return int(row["count"]) if row is not None else 0
