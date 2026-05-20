"""Pydantic model for Eligibility. Schema mirrors migrations/0001_init.sql."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EligibilityStatus = Literal["active", "inactive", "expired"]


class Eligibility(BaseModel):
    model_config = ConfigDict(frozen=True)

    eligibility_id: str = Field(min_length=1)
    member_id: str = Field(min_length=1)
    effective_from: date
    effective_to: date
    status: EligibilityStatus
    test_run_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _to_after_from(self) -> Eligibility:
        if self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self
