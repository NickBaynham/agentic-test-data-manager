"""Pydantic models for Member.

Mirrors the schema in migrations/0001_init.sql. All CHECK constraints at the
DB level (FAKE_ prefix, ZZ state, allowed status values) are also validated
here so callers get fast, clear errors before any DB round-trip.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MemberStatus = Literal["active", "inactive"]


class Address(BaseModel):
    model_config = ConfigDict(frozen=True)

    line1: str = Field(min_length=1)
    city: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    zip: str = Field(min_length=1)

    @field_validator("state")
    @classmethod
    def state_must_be_zz(cls, v: str) -> str:
        if v != "ZZ":
            raise ValueError("address state must be 'ZZ' (synthetic data marker, NFR-010)")
        return v


class Member(BaseModel):
    model_config = ConfigDict(frozen=True)

    member_id: str = Field(min_length=1)
    status: MemberStatus
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    date_of_birth: date
    address: Address
    plan_id: str = Field(min_length=1)
    test_run_id: str = Field(min_length=1)

    @field_validator("first_name", "last_name")
    @classmethod
    def must_have_fake_prefix(cls, v: str) -> str:
        if not v.startswith("FAKE_"):
            raise ValueError("name must start with 'FAKE_' (synthetic data marker, NFR-010)")
        return v
