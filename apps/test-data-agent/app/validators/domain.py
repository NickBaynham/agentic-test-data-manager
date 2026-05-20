"""Domain-rule validators (healthcare-specific)."""

from __future__ import annotations

from typing import Any

from app.validators import ValidationResult

# Baseline invalid codes from the migration. Per-run "invalid" codes also
# satisfy the rule (they're flagged is_valid=false in the bundle).
BASELINE_INVALID_PROCEDURE_CODES: frozenset[str] = frozenset({"00000"})
BASELINE_INVALID_DIAGNOSIS_CODES: frozenset[str] = frozenset({"ZZZ.99"})


def denial_requires_invalid_code(bundle: dict[str, Any]) -> ValidationResult:
    """A denied claim shall reference an invalid code OR carry a denial_reason.

    "Invalid code" means: the referenced procedure_code or diagnosis_code is
    either a known baseline invalid code, or carried `is_valid: false` in the
    bundle's per-run codes.
    """
    name = "domain.denial_requires_invalid_code"
    claim = bundle.get("claim")
    if not claim or claim["status"] != "denied":
        return ValidationResult(ok=True, validator=name)

    # Per-run codes flagged invalid?
    per_run_invalid_procs = {
        c["code"] for c in bundle.get("procedure_codes", []) if not c.get("is_valid", True)
    }
    per_run_invalid_diags = {
        c["code"] for c in bundle.get("diagnosis_codes", []) if not c.get("is_valid", True)
    }

    referenced_proc = claim["procedure_code"]
    referenced_diag = claim["diagnosis_code"]
    proc_is_invalid = (
        referenced_proc in BASELINE_INVALID_PROCEDURE_CODES
        or referenced_proc in per_run_invalid_procs
    )
    diag_is_invalid = (
        referenced_diag in BASELINE_INVALID_DIAGNOSIS_CODES
        or referenced_diag in per_run_invalid_diags
    )
    has_denial_reason = bool(claim.get("denial_reason"))

    if not (proc_is_invalid or diag_is_invalid or has_denial_reason):
        return ValidationResult(
            ok=False,
            validator=name,
            message=("denied claim must reference an invalid code or carry a denial_reason"),
            details={
                "procedure_code": referenced_proc,
                "diagnosis_code": referenced_diag,
                "denial_reason": claim.get("denial_reason"),
            },
        )
    return ValidationResult(ok=True, validator=name)
