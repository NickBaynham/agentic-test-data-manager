"""Pydantic model for Provider. Schema mirrors migrations/0001_init.sql."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NetworkStatus = Literal["in_network", "out_of_network"]


class Provider(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    network_status: NetworkStatus
    npi_fake: str = Field(min_length=1)
    test_run_id: str = Field(min_length=1)
