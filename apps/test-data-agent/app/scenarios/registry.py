"""Scenario registry.

Loads every `*.yaml` file in this directory at startup and exposes lookup by
scenario_id. Schema is intentionally simple in Phase 3 — Phase 4 may extend
with a constraints schema reference.

Per BRD §16 decision #6 (FR-044), every scenario YAML declares
linked_requirement_ids: list[str] (may be empty).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

SCENARIO_DIR = Path(__file__).parent


class ScenarioDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_id: str = Field(min_length=1)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    generators: list[str] = Field(min_length=1)
    validators: list[str] = Field(default_factory=list)
    linked_requirement_ids: list[str] = Field(default_factory=list)
    # Scenario-level constraint defaults. Caller's `constraints` override these.
    default_constraints: dict[str, Any] = Field(default_factory=dict)


_registry: dict[str, ScenarioDefinition] = {}


def load_scenarios(directory: Path | None = None) -> dict[str, ScenarioDefinition]:
    """Read every *.yaml in `directory` (defaults to this module's directory)
    and return a dict keyed by scenario_id. Idempotent — caches into _registry.
    """
    global _registry  # noqa: PLW0603
    target_dir = directory or SCENARIO_DIR
    loaded: dict[str, ScenarioDefinition] = {}
    for path in sorted(target_dir.glob("*.yaml")):
        raw: dict[str, Any] = yaml.safe_load(path.read_text())
        scenario = ScenarioDefinition.model_validate(raw)
        if scenario.scenario_id in loaded:
            raise ValueError(f"duplicate scenario_id {scenario.scenario_id!r} in {path}")
        loaded[scenario.scenario_id] = scenario
    _registry = loaded
    return _registry


def get_scenario(scenario_id: str) -> ScenarioDefinition | None:
    return _registry.get(scenario_id)


def all_scenarios() -> list[ScenarioDefinition]:
    return list(_registry.values())
