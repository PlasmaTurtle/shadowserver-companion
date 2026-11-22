"""Entities request contracts; validation stays with the owning domain."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator


class EntityProfileValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    contact_name: str = Field(default="", max_length=300)
    contact_title: str = Field(default="", max_length=300)
    contact_email: str = Field(default="", max_length=500)
    contact_phone: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=50000)
    address: str = Field(default="", max_length=2000)
    city: str = Field(default="", max_length=300)
    state: str = Field(default="", max_length=300)


class EntityFieldReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Literal["name", "address", "city", "state"]
    action: Literal["confirm", "ignore", "pending"]
    expected_revision: int = Field(ge=0)
    value_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class EntityRename(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    expected_revision: int = Field(ge=0)

    @field_validator("name")
    @classmethod
    def strip_name(cls, name):
        if not name.strip():
            raise ValueError("Entity name cannot be blank")
        return name.strip()


class EntityMerge(BaseModel):
    target_id: str
    source_revision: int = Field(ge=0)
    target_revision: int = Field(ge=0)
