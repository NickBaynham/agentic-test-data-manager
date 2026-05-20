"""Deterministic Plan generator.

`generate_plan(seed, test_run_id, constraints)` is a pure function: same
inputs produce identical output. The seed is typically derived from the
test_run_id ULID so runs are reproducible without storing extra state.
"""

from __future__ import annotations

import random
from datetime import date
from typing import Any

from app.generators.names import PLAN_NAMES

COVERAGE_TYPES: tuple[str, ...] = ("hmo", "ppo", "epo", "pos")


def generate_plan(
    seed: int,
    test_run_id: str,
    _constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a Plan dict ready to POST to the Target SUT."""
    rng = random.Random(seed)
    return {
        "plan_id": f"plan-{test_run_id}",
        "name": rng.choice(PLAN_NAMES),
        "coverage_type": rng.choice(COVERAGE_TYPES),
        "effective_date": date(2026, 1, 1).isoformat(),
        "test_run_id": test_run_id,
    }
