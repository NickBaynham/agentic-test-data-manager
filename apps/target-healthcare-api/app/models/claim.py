"""Pydantic model for Claim. Schema mirrors migrations/0001_init.sql."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ClaimStatus = Literal["paid", "denied", "pending"]


class Claim(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim_id: str = Field(min_length=1)
    member_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    procedure_code: str = Field(min_length=1)
    diagnosis_code: str = Field(min_length=1)
    status: ClaimStatus
    submitted_at: datetime
    denial_reason: str | None = None
    test_run_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _denied_needs_reason(self) -> Claim:
        # Mirrors the DB CHECK: status='denied' requires denial_reason NOT NULL.
        if self.status == "denied" and not self.denial_reason:
            raise ValueError("denial_reason is required when status is 'denied'")
        return self
