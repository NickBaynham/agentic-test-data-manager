"""Provider repository — single SQL surface for the provider table."""

from __future__ import annotations

from app.db.session import DbConn, connection
from app.models.provider import Provider

_INSERT = """
    INSERT INTO provider (provider_id, name, network_status, npi_fake, test_run_id)
    VALUES ($1, $2, $3, $4, $5)
"""
_DELETE_BY_RUN = "DELETE FROM provider WHERE test_run_id = $1"


async def insert_provider(
    provider: Provider,
    *,
    conn: DbConn | None = None,
) -> None:
    if conn is not None:
        await conn.execute(
            _INSERT,
            provider.provider_id,
            provider.name,
            provider.network_status,
            provider.npi_fake,
            provider.test_run_id,
        )
        return
    async with connection() as c:
        await c.execute(
            _INSERT,
            provider.provider_id,
            provider.name,
            provider.network_status,
            provider.npi_fake,
            provider.test_run_id,
        )


async def delete_by_run_id(run_id: str, *, conn: DbConn | None = None) -> int:
    if conn is not None:
        result = await conn.execute(_DELETE_BY_RUN, run_id)
    else:
        async with connection() as c:
            result = await c.execute(_DELETE_BY_RUN, run_id)
    parts = result.split()
    return int(parts[1]) if len(parts) == 2 and parts[0] == "DELETE" else 0
