"""Accretion request contracts; validation stays with the owning domain."""

from __future__ import annotations
from pydantic import BaseModel, ConfigDict


class GroupRetryValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_id: str | None = None
