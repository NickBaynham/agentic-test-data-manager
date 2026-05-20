"""Pydantic models for ProcedureCode and DiagnosisCode reference tables.

Baseline reference rows (shared across runs) have test_run_id=None.
Per-run "invalid" variants carry the run's test_run_id so they're cleaned up
along with the run.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProcedureCode(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str = Field(min_length=1)
    description: str = Field(min_length=1)
    is_valid: bool = True
    test_run_id: str | None = None


class DiagnosisCode(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str = Field(min_length=1)
    description: str = Field(min_length=1)
    is_valid: bool = True
    test_run_id: str | None = None
