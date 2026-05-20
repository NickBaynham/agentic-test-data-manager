"""Deterministic Claim generator.

Constraints understood:
  claim_status: "paid" | "denied" | "pending" (default: "paid")
  procedure_code: explicit code (default: "99213" — valid baseline)
  diagnosis_code: explicit code (default: "Z00.00" — valid baseline)
  denial_reason: free-text (default: "invalid_procedure_code" when status='denied')
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

DEFAULT_VALID_PROC = "99213"
DEFAULT_INVALID_PROC = "00000"  # baseline invalid code from migration
DEFAULT_VALID_DIAG = "Z00.00"
DEFAULT_INVALID_DIAG = "ZZZ.99"


def generate_claim(
    _seed: int,
    test_run_id: str,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    constraints = constraints or {}
    status = str(constraints.get("claim_status", "paid"))
    if status not in ("paid", "denied", "pending"):
        status = "paid"

    if status == "denied":
        procedure_code = str(constraints.get("procedure_code", DEFAULT_INVALID_PROC))
        diagnosis_code = str(constraints.get("diagnosis_code", DEFAULT_INVALID_DIAG))
        denial_reason: str | None = str(constraints.get("denial_reason", "invalid_procedure_code"))
    else:
        procedure_code = str(constraints.get("procedure_code", DEFAULT_VALID_PROC))
        diagnosis_code = str(constraints.get("diagnosis_code", DEFAULT_VALID_DIAG))
        denial_reason = None

    return {
        "claim_id": f"claim-{test_run_id}",
        "member_id": f"m-{test_run_id}",
        "provider_id": f"prov-{test_run_id}",
        "procedure_code": procedure_code,
        "diagnosis_code": diagnosis_code,
        "status": status,
        "submitted_at": datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC).isoformat(),
        "denial_reason": denial_reason,
        "test_run_id": test_run_id,
    }
