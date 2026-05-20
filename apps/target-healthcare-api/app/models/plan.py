"""Pydantic model for Plan. Schema mirrors migrations/0001_init.sql."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CoverageType = Literal["hmo", "ppo", "epo", "pos"]


class Plan(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    coverage_type: CoverageType
    effective_date: date
    test_run_id: str = Field(min_length=1)
