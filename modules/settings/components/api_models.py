"""Settings request contracts; validation stays with the owning domain."""

from __future__ import annotations

from email.headerregistry import Address
import re
from typing import Literal
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from .profile_catalog import REGION_NAMES, TIMEZONES, agency_for_name, authority_snapshot


class ProfileFields(BaseModel):
    # Only explicitly supplied fields are validated and merged. Old saved
    # profiles remain readable as recorded, including during partial updates.
    regions: list[str] = Field(default_factory=list, min_length=1, max_length=100)
    analyst_name: str = Field(default="", max_length=300)
    analyst_title: str = Field(default="", max_length=300)
    agency: str = Field(default="United States Secret Service", max_length=500)
    department: str = Field(default="U.S. Department of Homeland Security", max_length=500)
    office: str = Field(default="Charlotte, NC Field Office", max_length=500)
    email: str = Field(default="", max_length=254)
    display_timezone: str = Field(default="America/New_York", max_length=100)
    targeted_reason: str = Field(default="", max_length=2000)

    @field_validator("analyst_name", "analyst_title", "agency", "department", "office", "email")
    @classmethod
    def identity_text(cls, value, info):
        if info.field_name == "analyst_title" and not value.strip():
            return ""
        if any(unicodedata.category(char) == "Cc" for char in value):
            raise ValueError(
                "Sender identity fields must be single-line text without control characters"
            )
        value = value.strip()
        if info.field_name in {"analyst_name", "agency", "department", "office"} and not value:
            raise ValueError("Enter a nonblank sender identity value")
        return value

    @field_validator("agency")
    @classmethod
    def known_agency(cls, value):
        agency = agency_for_name(value)
        if agency is None:
            raise ValueError("Select CISA, FBI, or USSS as the sending agency")
        return agency["name"]

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        if not value:
            return value
        try:
            address = Address(addr_spec=value)
            domain = address.domain.encode("idna").decode("ascii")
            labels = domain.split(".")
            if (
                not address.username
                or address.addr_spec != value
                or len(address.username.encode("utf-8")) > 64
                or any(char.isspace() for char in value)
                or len(labels) < 2
                or len(domain) > 253
                or any(
                    not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                    for label in labels
                )
            ):
                raise ValueError
        except (ValueError, UnicodeError) as error:
            raise ValueError("Enter one valid email address, or leave email blank") from error
        return value

    @field_validator("display_timezone")
    @classmethod
    def valid_timezone(cls, value):
        value = value.strip()
        if value not in TIMEZONES:
            raise ValueError("Select a supported display timezone")
        return value

    @field_validator("regions")
    @classmethod
    def known_regions(cls, values):
        result = []
        for raw in values:
            value = REGION_NAMES.get(raw.strip().casefold())
            if value is None:
                raise ValueError("Select a listed U.S. state, district, or territory")
            if value not in result:
                result.append(value)
        if not result:
            raise ValueError("At least one jurisdiction is required")
        return result

    @field_validator("targeted_reason")
    @classmethod
    def reason_text(cls, value):
        if any(unicodedata.category(char) == "Cc" and char not in "\n\r\t" for char in value):
            raise ValueError("The targeted outreach reason must be plain text")
        return value.strip()


class ProfileValues(ProfileFields):
    model_config = ConfigDict(extra="forbid")
    analyst_name: str = Field(min_length=1, max_length=300)
    agency: str = Field(min_length=1, max_length=500)
    office: str = Field(min_length=1, max_length=500)
    regions: list[str] = Field(min_length=1, max_length=100)


class SettingsUpdate(ProfileFields):
    sheet: str = Field(default="", max_length=100)
    timeout: float = Field(default=10, ge=1, le=60, strict=True)
    retries: int = Field(default=1, ge=0, le=3, strict=True)
    interval: float = Field(default=0.25, ge=0, le=10, strict=True)
    watch_inbox: StrictBool = True
    brand_profile: Literal["companion", "usss"] = "companion"
    brand_profile_version: Literal["1"] = "1"
    appearance: Literal["light", "dark", "system"] | None = None
    critical_only: StrictBool = True
    outreach_mode: Literal["critical", "targeted"] = "critical"
    report_type: str = Field(default="auto", max_length=200)
    accretion_priority_cities: list[str] = Field(default_factory=list, max_length=20)
    accretion_priority_products: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("sheet", "report_type")
    @classmethod
    def single_line(cls, value, info):
        if any(unicodedata.category(char) == "Cc" for char in value):
            raise ValueError("Enter single-line text without control characters")
        # Workbook sheet lookup is exact, and spaces are valid title characters.
        return value if info.field_name == "sheet" else value.strip()

    @field_validator("accretion_priority_cities", "accretion_priority_products")
    @classmethod
    def priority_focus(cls, values):
        result, seen = [], set()
        for raw in values:
            value = raw.strip()
            if len(value) > 80 or any(unicodedata.category(char) == "Cc" for char in value):
                raise ValueError(
                    "Each priority focus must be a plain name of at most 80 characters"
                )
            if value and value.casefold() not in seen:
                result.append(value)
                seen.add(value.casefold())
        return result


def merge_settings(previous, changes):
    """Validate related writes against the latest profile inside its transaction."""
    values = {**previous, **changes}
    if {"agency", "department"} & changes.keys():
        agency = agency_for_name(values.get("agency"))
        if agency is None:
            raise ValueError("Select CISA, FBI, or USSS as the sending agency")
        if "department" in changes and changes["department"] != agency["department"]:
            raise ValueError("The department must match the selected agency")
        values["department"] = agency["department"]
    policy_fields = {"agency", "outreach_mode", "critical_only", "targeted_reason"}
    if not policy_fields & changes.keys():
        return values
    if "outreach_mode" not in changes and "critical_only" in changes:
        values["outreach_mode"] = "critical" if changes["critical_only"] else "targeted"
    mode = values.get("outreach_mode", "critical")
    if mode not in {"critical", "targeted"}:
        raise ValueError("Select critical or targeted outreach")
    values["critical_only"] = mode == "critical"
    if mode == "targeted":
        reason = values.get("targeted_reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Targeted outreach requires a recorded reason.")
        if previous.get("agency") != values.get("agency") and "targeted_reason" not in changes:
            raise ValueError("Review the targeted outreach reason for the newly selected agency.")
        agency = agency_for_name(values.get("agency"))
        if agency is None:
            raise ValueError("Select CISA, FBI, or USSS before targeted outreach")
        values["targeted_authority"] = authority_snapshot(agency)
    else:
        values.pop("targeted_authority", None)
        if previous.get("agency") != values.get("agency") and "targeted_reason" not in changes:
            # A reason reviewed for another agency must not silently become
            # active again after switching back from critical to targeted mode.
            values["targeted_reason"] = ""
    return values
