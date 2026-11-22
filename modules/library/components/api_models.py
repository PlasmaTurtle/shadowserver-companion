"""Library request contracts; validation stays with the owning domain."""

from __future__ import annotations
from datetime import datetime
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, ConfigDict, field_validator, ValidationInfo


def citation_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Citation URLs must use HTTP or HTTPS with a hostname")
    parsed.port  # Reject malformed ports using urllib's normal parser.
    return value


class SourceJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cve_ids: list[str] = Field(min_length=1, max_length=1000)
    refresh: bool = False
    local_only: bool = False


class BlockSourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    url: str = Field(min_length=1, max_length=2000)
    publisher: str = Field(default="", max_length=500)
    title: str = Field(default="", max_length=1000)
    retrieved_at: str = Field(default="", max_length=100)
    date_published: str = Field(default="", max_length=100)
    date_updated: str = Field(default="", max_length=100)

    @field_validator("url")
    @classmethod
    def public_url(cls, value):
        return citation_url(value)

    @field_validator("retrieved_at", "date_published", "date_updated")
    @classmethod
    def source_date(cls, value):
        if value:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


class BlockCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    sources: str = Field(default="", max_length=10000)
    source_metadata: list[BlockSourceMetadata] = Field(default_factory=list, max_length=100)

    @field_validator("title", "body")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("This field must not be blank")
        return value

    @field_validator("sources")
    @classmethod
    def source_urls(cls, value):
        for number, line in enumerate(value.splitlines(), 1):
            if line.strip():
                try:
                    citation_url(line.strip())
                except ValueError as error:
                    raise ValueError(f"Source line {number}: {error}") from error
        return value

    @field_validator("source_metadata")
    @classmethod
    def matching_metadata(cls, value, info: ValidationInfo):
        urls = {line.strip() for line in info.data.get("sources", "").splitlines() if line.strip()}
        provided = [item.url for item in value]
        if len(provided) != len(set(provided)) or not set(provided) <= urls:
            raise ValueError("Citation metadata must have one entry per listed source URL")
        return value

    def content_values(self, *, preserve_omitted=False):
        values = self.model_dump(include={"title", "body", "sources", "source_metadata"})
        if preserve_omitted and "source_metadata" not in self.model_fields_set:
            values.pop("source_metadata")
        return values


class BlockUpdate(BlockCreate):
    expected_revision: int = Field(ge=1, strict=True)


class BlockRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1, strict=True)


class BlockArchive(BlockRevisionRequest):
    archived: bool
