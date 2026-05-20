"""ATDM Agent — Phase 1 stub.

Serves /health and /metrics only. Real scenario request, validator, seeder,
audit, and reset surfaces land in Phase 3 onward.
"""

import os

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

PLANNER_MODE = os.environ.get("ATDM_PLANNER", "rule")

app = FastAPI(
    title="ATDM Agent",
    description="Agentic Test Data Manager — intent-to-data scenario provisioning.",
    version="0.1.0",
)


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
    """Prometheus text exposition. Phase 1 emits only `atdm_up`."""
    return "# HELP atdm_up 1 if the agent process is up\n# TYPE atdm_up gauge\natdm_up 1\n"
