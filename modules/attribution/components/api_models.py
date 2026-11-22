"""Attribution request contracts; validation stays with the owning domain."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class AttributionReviewValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_id: str = Field(min_length=32, max_length=32)
    evidence_index: int | None = Field(default=None, ge=0)
    decision: Literal["accept", "dismiss"]
    note: str = Field(default="", max_length=2000)
