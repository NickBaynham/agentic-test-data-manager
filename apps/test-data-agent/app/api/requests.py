"""POST /test-data/requests — the headline endpoint.

Orchestrates the Phase 3 vertical slice: planner (rule-based) → seeder →
catalog → audit → response. Returns the contract shape required by BRD FR-005.
"""

from __future__ import annotations

import os
import secrets
import uuid
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from ulid import ULID

from app.agents.planner import resolve_plan
from app.audit import writer as audit_writer
from app.catalog import store as catalog_store
from app.scenarios.registry import get_scenario
from app.seeders import healthcare as seeder
from app.seeders.healthcare import SeedError

router = APIRouter()


class DeliveryOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

    seed_target: bool = True
    return_playwright_fixture: bool = False  # Phase 6
    return_pytest_fixture: bool = False  # Phase 6
    cleanup_strategy: Literal["after_test", "leave", "after_suite"] = "after_test"


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    domain: str = Field("healthcare", min_length=1)
    scenario: str = Field(min_length=1)
    constraints: dict[str, Any] = Field(default_factory=dict)
    delivery: DeliveryOptions = Field(default_factory=DeliveryOptions)


def _planner_mode() -> str:
    return os.environ.get("ATDM_PLANNER", "rule")


def _invoker_from(request: Request) -> str:
    # MVP: every authenticated invocation is recorded as agent. Multi-user
    # identity is Phase 4+ (BRD §16 decision #3).
    return "agent:atdm-dev"


@router.post("/test-data/requests")
async def create_request(scenario_request: ScenarioRequest, request: Request) -> dict[str, Any]:
    # ATDM_PLANNER=llm short-circuits to 501 per BRD §16 decision #2.
    if _planner_mode() == "llm":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "error": {
                    "code": "LLM_MODE_NOT_ENABLED",
                    "message": "LLM planner mode is a Phase 2 feature; not enabled in MVP.",
                }
            },
        )

    scenario = get_scenario(scenario_request.scenario)
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "SCENARIO_NOT_FOUND",
                    "message": f"unknown scenario {scenario_request.scenario!r}",
                }
            },
        )

    test_run_id = str(ULID())
    request_id = f"tdr_{uuid.uuid4().hex[:12]}"
    cleanup_token = secrets.token_urlsafe(32)
    invoker = _invoker_from(request)
    minio_client = catalog_store.make_minio_client()

    audit_writer.append_event(
        minio_client,
        test_run_id=test_run_id,
        invoker=invoker,
        action="request_received",
        inputs={
            "request_id": request_id,
            "scenario": scenario_request.scenario,
            "constraints": scenario_request.constraints,
            "delivery": scenario_request.delivery.model_dump(),
            "planner_mode": _planner_mode(),
        },
    )

    plan = resolve_plan(scenario, test_run_id, scenario_request.constraints)
    audit_writer.append_event(
        minio_client,
        test_run_id=test_run_id,
        invoker=invoker,
        action="plan_resolved",
        outputs={
            "scenario_id": plan.scenario_id,
            "steps": [{"generator": s.generator} for s in plan.steps],
        },
    )

    audit_writer.append_event(
        minio_client,
        test_run_id=test_run_id,
        invoker=invoker,
        action="seed_started",
        outputs={"step_count": len(plan.steps)},
    )

    try:
        async with httpx.AsyncClient(
            base_url=seeder.target_sut_base_url(),
            timeout=10.0,
        ) as client:
            seeded = await seeder.execute_plan(plan, client=client)
    except SeedError as e:
        audit_writer.append_event(
            minio_client,
            test_run_id=test_run_id,
            invoker=invoker,
            action="seed_failed",
            outputs={
                "step": e.step,
                "downstream_status": e.downstream_status,
                "message": str(e),
            },
            status="rolled_back",
        )
        # Update catalog with rolled_back status.
        catalog_store.write_run(
            minio_client,
            test_run_id=test_run_id,
            request_id=request_id,
            scenario_id=scenario.scenario_id,
            cleanup_token_plain=cleanup_token,
            invoker=invoker,
            status="rolled_back",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "SEED_FAILED",
                    "message": str(e),
                    "details": {"step": e.step, "downstream_status": e.downstream_status},
                    "test_run_id": test_run_id,
                }
            },
        ) from e

    audit_writer.append_event(
        minio_client,
        test_run_id=test_run_id,
        invoker=invoker,
        action="seed_completed",
        outputs={
            "records_created": [
                {"kind": kind, "primary_key": rec.get(f"{kind}_id")} for kind, rec in seeded.items()
            ]
        },
    )

    catalog_store.write_run(
        minio_client,
        test_run_id=test_run_id,
        request_id=request_id,
        scenario_id=scenario.scenario_id,
        cleanup_token_plain=cleanup_token,
        invoker=invoker,
        status="ready",
    )
    audit_writer.append_event(
        minio_client,
        test_run_id=test_run_id,
        invoker=invoker,
        action="catalog_recorded",
        outputs={"status": "ready"},
    )

    return {
        "request_id": request_id,
        "test_run_id": test_run_id,
        "status": "ready",
        "data": {
            "member_id": seeded.get("member", {}).get("member_id"),
            "plan_id": seeded.get("plan", {}).get("plan_id"),
        },
        "fixtures": {
            # Phase 6 will fill these in.
            "playwright": None,
            "pytest": None,
        },
        "cleanup": {
            "cleanup_token": cleanup_token,
            "endpoint": f"/test-data/runs/{test_run_id}/reset",
        },
    }
