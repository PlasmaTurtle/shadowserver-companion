"""Settings request contracts; validation stays with the owning domain."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class SettingsUpdate(BaseModel):
    # An omitted field is not applied by the partial-update adapter. Explicit
    # jurisdiction changes still require a nonempty list of nonblank names.
    regions: list[str] = Field(default_factory=list, min_length=1, max_length=100)
    sheet: str = Field(default="", max_length=100)
    analyst_name: str = Field(default="", max_length=300)
    analyst_title: str = Field(default="", max_length=300)
    agency: str = Field(default="United States Secret Service", max_length=500)
    department: str = Field(default="U.S. Department of Homeland Security", max_length=500)
    office: str = Field(default="Charlotte, NC Field Office", max_length=500)
    email: str = Field(default="", max_length=500)
    timeout: float = Field(default=10, ge=1, le=60)
    retries: int = Field(default=1, ge=0, le=3)
    interval: float = Field(default=0.25, ge=0, le=10)
    watch_inbox: bool = True
    brand_profile: Literal["companion", "usss"] = "companion"
    brand_profile_version: Literal["1"] = "1"
    appearance: Literal["light", "dark", "system"] | None = None
    display_timezone: str = Field(default="America/New_York", max_length=100)
    critical_only: bool = True
    outreach_mode: Literal["critical", "targeted"] = "critical"
    targeted_reason: str = Field(default="", max_length=2000)
    report_type: str = Field(default="auto", max_length=200)
    accretion_priority_cities: list[str] = Field(default_factory=list, max_length=20)
    accretion_priority_products: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("accretion_priority_cities", "accretion_priority_products")
    @classmethod
    def priority_focus(cls, values):
        result, seen = [], set()
        for raw in values:
            value = raw.strip()
            if len(value) > 80 or any(ord(char) < 32 for char in value):
                raise ValueError(
                    "Each priority focus must be a plain name of at most 80 characters"
                )
            if value and value.casefold() not in seen:
                result.append(value)
                seen.add(value.casefold())
        return result

    @field_validator("analyst_name", "analyst_title", "agency", "department", "office", "email")
    @classmethod
    def optional_title(cls, value, info):
        if info.field_name == "analyst_title" and not value.strip():
            return ""
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError(
                "Sender identity fields must be single-line text without control characters"
            )
        # A whitespace-only title must not create a blank signature line.
        return value.strip()

    @field_validator("display_timezone")
    @classmethod
    def valid_timezone(cls, value):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            # Windows embedded Python need not have an IANA database. These
            # supported display zones are resolved by the browser's Intl API;
            # all stored/exported event instants remain explicit UTC.
            if value not in (
                "UTC",
                "America/New_York",
                "America/Chicago",
                "America/Denver",
                "America/Los_Angeles",
                "America/Anchorage",
                "Pacific/Honolulu",
            ):
                raise ValueError("Select a supported IANA timezone") from error
        return value

    @field_validator("regions")
    @classmethod
    def nonblank(cls, values):
        values = list(dict.fromkeys(x.strip() for x in values if x.strip()))
        if not values:
            raise ValueError("At least one region is required")
        return values
