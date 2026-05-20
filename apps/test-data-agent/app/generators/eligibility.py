"""Deterministic Eligibility generator.

Constraints understood:
  eligibility_status: "active" | "inactive" | "expired" (default: "active")
  eligibility_window: "current" | "expired_last_year" | "future" (default: "current")
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def generate_eligibility(
    seed: int,
    test_run_id: str,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    constraints = constraints or {}
    status = str(constraints.get("eligibility_status", "active"))
    window = str(constraints.get("eligibility_window", "current"))

    today = date(2026, 6, 1)
    if window == "expired_last_year":
        # Window ended a year ago.
        effective_from = today - timedelta(days=730)
        effective_to = today - timedelta(days=365)
        if status == "active":
            # Window says expired but caller asked active — caller's contradiction.
            # Pydantic accepts, validators will catch.
            pass
    elif window == "future":
        effective_from = today + timedelta(days=30)
        effective_to = today + timedelta(days=395)
    else:
        # current — covers today.
        effective_from = today - timedelta(days=180)
        effective_to = today + timedelta(days=185)

    return {
        "eligibility_id": f"elig-{test_run_id}",
        "member_id": f"m-{test_run_id}",
        "effective_from": effective_from.isoformat(),
        "effective_to": effective_to.isoformat(),
        "status": status,
        "test_run_id": test_run_id,
    }
