"""Validator registry — maps the dotted names in scenario YAML to callables."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.validators import ValidationResult
from app.validators.domain import denial_requires_invalid_code
from app.validators.relational import (
    claim_references_existing_member,
    eligibility_status_matches_member,
)
from app.validators.temporal import eligibility_window_contains_claim

ValidatorFn = Callable[[dict[str, Any]], ValidationResult]

VALIDATORS: dict[str, ValidatorFn] = {
    "relational.eligibility_status_matches_member": eligibility_status_matches_member,
    "relational.claim_references_existing_member": claim_references_existing_member,
    "domain.denial_requires_invalid_code": denial_requires_invalid_code,
    "temporal.eligibility_window_contains_claim": eligibility_window_contains_claim,
}


def get_validator(name: str) -> ValidatorFn | None:
    return VALIDATORS.get(name)
