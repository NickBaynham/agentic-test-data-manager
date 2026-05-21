"""Catalog read endpoints.

Phase 7 ships GET /catalog/scenarios (FR-041). Phase 7+ can add /catalog/runs
(FR-042) for prior-run discovery.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.scenarios.registry import all_scenarios

router = APIRouter()


@router.get("/catalog/scenarios")
async def list_scenarios() -> dict[str, Any]:
    """Return every loaded scenario definition."""
    return {
        "scenarios": [s.model_dump() for s in all_scenarios()],
    }
