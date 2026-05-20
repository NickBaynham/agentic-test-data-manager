"""Generators for per-run ProcedureCode and DiagnosisCode "invalid" variants.

In MVP, baseline codes (test_run_id IS NULL) come from the migration. These
generators only fire when a scenario needs to attach a per-run code that
isn't in the baseline.
"""

from __future__ import annotations

from typing import Any


def generate_procedure_code(
    _seed: int,
    test_run_id: str,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    constraints = constraints or {}
    return {
        "code": str(constraints.get("procedure_code", f"PC-{test_run_id}")),
        "description": str(
            constraints.get("procedure_code_description", "Per-run synthetic procedure code")
        ),
        "is_valid": bool(constraints.get("procedure_code_is_valid", True)),
        "test_run_id": test_run_id,
    }


def generate_diagnosis_code(
    _seed: int,
    test_run_id: str,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    constraints = constraints or {}
    return {
        "code": str(constraints.get("diagnosis_code", f"DC-{test_run_id}")),
        "description": str(
            constraints.get("diagnosis_code_description", "Per-run synthetic diagnosis code")
        ),
        "is_valid": bool(constraints.get("diagnosis_code_is_valid", True)),
        "test_run_id": test_run_id,
    }
