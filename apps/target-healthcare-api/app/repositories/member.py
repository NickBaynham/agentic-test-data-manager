"""Member repository — the single SQL surface for the Member table.

Every write to the `member` table flows through one of these functions.
Parameterized queries only; no string-formatted SQL. This is enforced
architecturally — AR-003 fitness test in Phase 8 will assert that the agent
module never imports asyncpg, sqlalchemy, or any raw-SQL surface.
"""

from __future__ import annotations

import asyncpg

from app.db.session import connection
from app.models.member import Address, Member

_INSERT_MEMBER = """
    INSERT INTO member (
        member_id, status, first_name, last_name, date_of_birth,
        address_line1, address_city, address_state, address_zip,
        plan_id, test_run_id
    )
    VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
    )
"""

_DELETE_BY_RUN = "DELETE FROM member WHERE test_run_id = $1"

_COUNT_BY_RUN = "SELECT COUNT(*) FROM member WHERE test_run_id = $1"

_SELECT_BY_ID = """
    SELECT member_id, status, first_name, last_name, date_of_birth,
           address_line1, address_city, address_state, address_zip,
           plan_id, test_run_id
    FROM member WHERE member_id = $1
"""


async def insert_member(member: Member) -> None:
    """Insert a single Member. Raises asyncpg.IntegrityConstraintViolationError
    if the FK to plan, the FAKE_ CHECK, or the ZZ CHECK fails.
    """
    async with connection() as conn:
        await conn.execute(
            _INSERT_MEMBER,
            member.member_id,
            member.status,
            member.first_name,
            member.last_name,
            member.date_of_birth,
            member.address.line1,
            member.address.city,
            member.address.state,
            member.address.zip,
            member.plan_id,
            member.test_run_id,
        )


async def delete_by_run_id(run_id: str) -> int:
    """Delete every Member with the given test_run_id. Returns deleted count."""
    async with connection() as conn:
        result = await conn.execute(_DELETE_BY_RUN, run_id)
    # asyncpg returns a tag like "DELETE 3"; parse the count out.
    parts = result.split()
    return int(parts[1]) if len(parts) == 2 and parts[0] == "DELETE" else 0


async def count_by_run_id(run_id: str) -> int:
    """Return the number of Members with the given test_run_id."""
    async with connection() as conn:
        row = await conn.fetchrow(_COUNT_BY_RUN, run_id)
    if row is None:
        return 0
    return int(row["count"])


async def get_by_id(member_id: str) -> Member | None:
    """Fetch a Member by primary key. Returns None if absent."""
    async with connection() as conn:
        row: asyncpg.Record | None = await conn.fetchrow(_SELECT_BY_ID, member_id)
    if row is None:
        return None
    return Member(
        member_id=row["member_id"],
        status=row["status"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        date_of_birth=row["date_of_birth"],
        address=Address(
            line1=row["address_line1"],
            city=row["address_city"],
            state=row["address_state"],
            zip=row["address_zip"],
        ),
        plan_id=row["plan_id"],
        test_run_id=row["test_run_id"],
    )
