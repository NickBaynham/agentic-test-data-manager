"""Deterministic domain-consistency validators.

Validators run AFTER generators produce a bundle and BEFORE the bundle is
posted to the Target SUT. Any failure → 422 + audit `plan_rejected` + zero
DB writes (the bundle never leaves the agent).

A validator is a callable taking the generated bundle dict (keys: plan,
provider, member, eligibility, claim, procedure_codes, diagnosis_codes) and
returning a ValidationResult.

Per AR-003: validators are deterministic — no LLM, no outbound calls.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    validator: str
    message: str = ""
    details: dict[str, object] | None = None
