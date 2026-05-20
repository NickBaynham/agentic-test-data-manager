"""Async Postgres connection pool for the Target Healthcare API.

The pool is created at FastAPI startup (`lifespan`) and closed at shutdown.
Connection parameters come from POSTGRES_* env vars.

All SQL execution flows through the pool via repository methods. No raw SQL
runs outside `app/repositories/` (architectural rule that will be enforced by
the AR-003 fitness test in Phase 8 — but agents respect it from Phase 2 on).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import asyncpg.pool

# Either a raw Connection or a PoolConnectionProxy can be passed into a repo
# method. Both expose execute/fetchrow/etc. Pool.acquire() yields the proxy
# form; passing it to repo methods that accept Connection requires this alias
# (mypy strict otherwise rejects the assignment).
type DbConn = asyncpg.Connection[Any] | asyncpg.pool.PoolConnectionProxy[Any]

_pool: asyncpg.Pool[Any] | None = None


def _dsn_from_env() -> str:
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "atdm")
    password = os.environ.get("POSTGRES_PASSWORD", "atdm-dev-only")
    database = os.environ.get("POSTGRES_DB", "target_healthcare")
    return f"postgres://{user}:{password}@{host}:{port}/{database}"


async def init_pool(min_size: int = 1, max_size: int = 10) -> asyncpg.Pool[Any]:
    """Create the module-level pool. Call once at startup."""
    global _pool  # noqa: PLW0603
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=_dsn_from_env(),
            min_size=min_size,
            max_size=max_size,
        )
    return _pool


async def close_pool() -> None:
    """Close the module-level pool. Call once at shutdown."""
    global _pool  # noqa: PLW0603
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool[Any]:
    """Return the active pool. Raises if init_pool() has not been called."""
    if _pool is None:
        raise RuntimeError(
            "Database pool is not initialized. "
            "init_pool() must be called at startup (see app.main lifespan)."
        )
    return _pool


@asynccontextmanager
async def connection() -> AsyncIterator[DbConn]:
    """Yield a pooled connection. Use inside repository methods."""
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn
