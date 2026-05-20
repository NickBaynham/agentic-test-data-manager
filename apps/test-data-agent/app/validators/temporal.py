"""Temporal validators."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.validators import ValidationResult


def _to_date(value: object) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _to_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def eligibility_window_contains_claim(bundle: dict[str, Any]) -> ValidationResult:
    """For denied or pending claims, the claim's submitted_at shall fall within
    the eligibility's effective window (or the window shall otherwise justify
    the denial — e.g., expired eligibility is a legitimate reason for denial).

    Paid claims with submitted_at outside the window are a different problem
    domain (back-billing) and not flagged here.
    """
    name = "temporal.eligibility_window_contains_claim"
    claim = bundle.get("claim")
    eligibility = bundle.get("eligibility")
    if not claim or not eligibility:
        return ValidationResult(ok=True, validator=name)
    if claim["status"] not in ("denied", "pending"):
        return ValidationResult(ok=True, validator=name)

    submitted = _to_datetime(claim["submitted_at"])
    eff_from = _to_date(eligibility["effective_from"])
    eff_to = _to_date(eligibility["effective_to"])
    if submitted is None or eff_from is None or eff_to is None:
        return ValidationResult(
            ok=False,
            validator=name,
            message="unparseable date(s) on claim or eligibility",
            details={
                "submitted_at": claim["submitted_at"],
                "effective_from": eligibility["effective_from"],
                "effective_to": eligibility["effective_to"],
            },
        )

    submitted_date = submitted.date()
    if eligibility["status"] == "expired":
        # Expired eligibility legitimately produces denied/pending claims out
        # of window — that's the SCENARIO. Permit.
        return ValidationResult(ok=True, validator=name)

    if not (eff_from <= submitted_date <= eff_to):
        return ValidationResult(
            ok=False,
            validator=name,
            message="claim submitted outside eligibility window",
            details={
                "submitted_date": submitted_date.isoformat(),
                "window": f"{eff_from.isoformat()}..{eff_to.isoformat()}",
            },
        )
    return ValidationResult(ok=True, validator=name)
