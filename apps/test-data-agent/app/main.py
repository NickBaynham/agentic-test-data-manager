"""ATDM Agent.

Phase 1: /health, /metrics stubs.
Phase 3: scenario request → seed → audit → reset vertical slice.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from app.api import audit as audit_routes
from app.api import catalog as catalog_routes
from app.api import requests as request_routes
from app.api import reset as reset_routes
from app.api import strategies as strategy_routes
from app.api.middleware import api_token_middleware
from app.audit import metrics as audit_metrics
from app.audit import ui as audit_ui_routes
from app.scenarios.registry import load_scenarios

PLANNER_MODE = os.environ.get("ATDM_PLANNER", "rule")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    load_scenarios()
    yield


app = FastAPI(
    title="ATDM Agent",
    description="Agentic Test Data Manager — intent-to-data scenario provisioning.",
    version="0.3.0",
    lifespan=lifespan,
)

app.middleware("http")(api_token_middleware)

app.include_router(request_routes.router)
app.include_router(reset_routes.router)
app.include_router(strategy_routes.router)
app.include_router(audit_routes.router)
app.include_router(catalog_routes.router)
app.include_router(audit_ui_routes.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by docker compose healthcheck and integration tests."""
    return {
        "status": "ok",
        "service": "test-data-agent",
        "planner_mode": PLANNER_MODE,
    }


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    """Prometheus text exposition. Phase 8 adds audit metrics on top of the
    `atdm_up` heartbeat — see app.audit.metrics."""
    static = "# HELP atdm_up 1 if the agent process is up\n# TYPE atdm_up gauge\natdm_up 1\n"
    return static + audit_metrics.render_prometheus_text()
