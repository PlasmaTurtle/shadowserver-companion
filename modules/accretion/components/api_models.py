"""Accretion request contracts; validation stays with the owning domain."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class GroupRetryValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_id: str | None = None


class DeconflictionValues(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    scope: Literal["domain", "host"]
    identifier: str = Field(min_length=1, max_length=254)
    external_reference: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=2000)
