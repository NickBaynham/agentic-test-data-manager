"""POST /test-data/requests — headline endpoint.

Orchestrates the Phase 4 vertical slice:
  request_received → plan_resolved → validators_passed | plan_rejected →
  seed_started → seed_completed | seed_failed → catalog_recorded.
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
from app.seeders.healthcare import SeedError, ValidatorRejected

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


def _invoker_from(_request: Request) -> str:
    return "agent:atdm-dev"


@router.post("/test-data/requests")
async def create_request(scenario_request: ScenarioRequest, request: Request) -> dict[str, Any]:
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

    # Effective constraints = scenario defaults overridden by request.
    effective_constraints = {**scenario.default_constraints, **scenario_request.constraints}

    audit_writer.append_event(
        minio_client,
        test_run_id=test_run_id,
        invoker=invoker,
        action="request_received",
        inputs={
            "request_id": request_id,
            "scenario": scenario_request.scenario,
            "constraints": scenario_request.constraints,
            "effective_constraints": effective_constraints,
            "delivery": scenario_request.delivery.model_dump(),
            "planner_mode": _planner_mode(),
        },
    )

    plan = resolve_plan(scenario, test_run_id, effective_constraints)
    audit_writer.append_event(
        minio_client,
        test_run_id=test_run_id,
        invoker=invoker,
        action="plan_resolved",
        outputs={
            "scenario_id": plan.scenario_id,
            "steps": [{"generator": s.generator} for s in plan.steps],
            "validators": scenario.validators,
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
            bundle, validator_results = await seeder.execute_plan(
                plan, scenario.validators, client=client
            )
    except ValidatorRejected as e:
        audit_writer.append_event(
            minio_client,
            test_run_id=test_run_id,
            invoker=invoker,
            action="plan_rejected",
            outputs={
                "failed_validators": [
                    {
                        "validator": r.validator,
                        "message": r.message,
                        "details": r.details,
                    }
                    for r in e.results
                ]
            },
            status="rejected",
        )
        catalog_store.write_run(
            minio_client,
            test_run_id=test_run_id,
            request_id=request_id,
            scenario_id=scenario.scenario_id,
            cleanup_token_plain=cleanup_token,
            invoker=invoker,
            status="rejected",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "VALIDATOR_REJECTED",
                    "message": "one or more validators rejected the generated plan",
                    "details": {
                        "failed_validators": [r.validator for r in e.results],
                        "messages": [r.message for r in e.results],
                    },
                    "test_run_id": test_run_id,
                }
            },
        ) from e
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
                    "details": {
                        "step": e.step,
                        "downstream_status": e.downstream_status,
                    },
                    "test_run_id": test_run_id,
                }
            },
        ) from e

    # All validators that ran are recorded (passing or not), for traceability.
    audit_writer.append_event(
        minio_client,
        test_run_id=test_run_id,
        invoker=invoker,
        action="validators_passed",
        outputs={"validators": [r.validator for r in validator_results]},
    )

    audit_writer.append_event(
        minio_client,
        test_run_id=test_run_id,
        invoker=invoker,
        action="seed_completed",
        outputs={
            "records_created": [
                {"kind": kind, "primary_key": _pk(bundle.get(kind), kind)}
                for kind in ("plan", "provider", "member", "eligibility", "claim")
                if bundle.get(kind)
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
            "plan_id": _pk(bundle.get("plan"), "plan"),
            "provider_id": _pk(bundle.get("provider"), "provider"),
            "member_id": _pk(bundle.get("member"), "member"),
            "eligibility_id": _pk(bundle.get("eligibility"), "eligibility"),
            "claim_id": _pk(bundle.get("claim"), "claim"),
        },
        "fixtures": {
            "playwright": None,
            "pytest": None,
        },
        "cleanup": {
            "cleanup_token": cleanup_token,
            "endpoint": f"/test-data/runs/{test_run_id}/reset",
        },
    }


def _pk(record: dict[str, Any] | None, kind: str) -> str | None:
    """Pull the primary key out of a record dict by the {kind}_id convention."""
    if not record:
        return None
    key = f"{kind}_id"
    value = record.get(key)
    return None if value is None else str(value)
