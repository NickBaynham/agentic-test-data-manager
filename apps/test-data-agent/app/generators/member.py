"""Deterministic Member generator.

Same seed + test_run_id = same output. All names carry the FAKE_ prefix; the
address state is always `ZZ` (NFR-010).

`plan_id` is derived from `test_run_id` via the f"plan-{test_run_id}"
convention shared across all generators — see app/generators/plan.py.
"""

from __future__ import annotations

import random
from datetime import date
from typing import Any

from app.generators.names import FAKE_CITY_NAMES, FAKE_FIRST_NAMES, FAKE_LAST_NAMES


def generate_member(
    seed: int,
    test_run_id: str,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a Member dict ready to include in a ScenarioBundle."""
    rng = random.Random(seed + 1)
    constraints = constraints or {}

    birth_year = 1970 + (seed % 50)
    birth_month = 1 + (seed % 12)
    birth_day = 1 + (seed % 28)

    return {
        "member_id": f"m-{test_run_id}",
        "status": str(constraints.get("member_status", "active")),
        "first_name": rng.choice(FAKE_FIRST_NAMES),
        "last_name": rng.choice(FAKE_LAST_NAMES),
        "date_of_birth": date(birth_year, birth_month, birth_day).isoformat(),
        "address": {
            "line1": f"{1 + (seed % 999)} FAKE_Main_St",
            "city": rng.choice(FAKE_CITY_NAMES),
            "state": "ZZ",
            "zip": f"{seed % 100000:05d}",
        },
        "plan_id": f"plan-{test_run_id}",
        "test_run_id": test_run_id,
    }
