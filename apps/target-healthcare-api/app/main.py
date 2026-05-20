"""Target Healthcare API.

Serves as the System Under Test for ATDM. Phase 1: /health stub.
Phase 2: schema landed; Member entity routes available under /internal/.
Remaining six entity routes land in Phase 4.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.session import close_pool, init_pool
from app.routes import member as member_routes
from app.routes import plan as plan_routes
from app.routes import scenarios as scenarios_routes


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await init_pool()
    try:
        yield
    finally:
        await close_pool()


app = FastAPI(
    title="Target Healthcare API",
    description="Synthetic healthcare SUT for the Agentic Test Data Manager.",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(plan_routes.router)
app.include_router(member_routes.router)
app.include_router(scenarios_routes.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by docker compose healthcheck and integration tests."""
    return {"status": "ok", "service": "target-healthcare-api"}
