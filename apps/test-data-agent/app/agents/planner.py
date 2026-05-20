"""Rule-based planner (Phase 3).

Translates `{scenario_id, constraints}` to a deterministic `Plan` of ordered
generator invocations. No LLM. No outbound calls.

The LLM planner stub (Phase 2 work, deferred to Phase 4+) lives in
`llm_planner.py` and is only reachable when `ATDM_PLANNER=llm` — in MVP it
returns 501 from the API layer before this module ever loads.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.scenarios.registry import ScenarioDefinition


class PlanStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    generator: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_id: str
    test_run_id: str
    constraints: dict[str, Any]
    steps: list[PlanStep]


def resolve_plan(
    scenario: ScenarioDefinition,
    test_run_id: str,
    constraints: dict[str, Any],
) -> Plan:
    """Build a Plan by translating the scenario's generator list into ordered
    PlanSteps. Constraints propagate to every step; each generator picks the
    fields it cares about.
    """
    steps = [PlanStep(generator=name, args=dict(constraints)) for name in scenario.generators]
    return Plan(
        scenario_id=scenario.scenario_id,
        test_run_id=test_run_id,
        constraints=constraints,
        steps=steps,
    )
