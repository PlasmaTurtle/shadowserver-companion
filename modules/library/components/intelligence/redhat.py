"""Red Hat Security Data API CVE records and their product-scoped statements."""

import re
from datetime import datetime
from itertools import islice
from typing import Annotated

from pydantic import BaseModel, Field, ValidationError


PUBLISHER = "Red Hat Product Security"
API = "https://access.redhat.com/hydra/rest/securitydata/cve/"
PORTAL = "https://access.redhat.com/security/cve/"
CVE = re.compile(r"CVE-[0-9]{4}-[0-9]{4,}")
ScopeText = Annotated[str, Field(min_length=1, max_length=4096)]


def identifier(value):
    if not isinstance(value, str) or len(value) > 80 or not CVE.fullmatch(value.upper()):
        raise ValueError("Invalid CVE identifier")
    return value.upper()


def source_url(cve_id):
    return API + identifier(cve_id) + ".json"


class PackageState(BaseModel):
    product_name: ScopeText
    fix_state: ScopeText
    cpe: ScopeText | None = None
    package_name: ScopeText | None = None


class AffectedRelease(BaseModel):
    product_name: ScopeText
    advisory: ScopeText
    cpe: ScopeText | None = None
    package: ScopeText | None = None
    release_date: ScopeText | None = None


class Record(BaseModel):
    name: ScopeText
    public_date: ScopeText
    statement: Annotated[str, Field(max_length=64 * 1024)] | None = None
    package_state: list[PackageState] | None = None
    affected_release: list[AffectedRelease] | None = None


def record(cve_id, raw):
    if raw.get("name") != identifier(cve_id):
        raise ValueError("Red Hat response identifier differs from the requested CVE")
    try:
        value = Record.model_validate(raw, strict=True)
        datetime.fromisoformat(value.public_date)
        for release in value.affected_release or ():
            if release.release_date is not None:
                datetime.fromisoformat(release.release_date)
    except (ValidationError, ValueError):
        # Validation messages may contain arbitrary input from a rejected body.
        raise ValueError("Red Hat response has invalid statement, date, or scope fields") from None
    return value


def product_page(value, offset, limit):
    states = value.package_state or []
    releases = value.affected_release or []

    def rows():
        for index, item in enumerate(states):
            yield {
                "product": item.product_name,
                "package": item.package_name,
                "cpe": item.cpe,
                "status": item.fix_state,
                "advisory": None,
                "release_date": None,
                "source_pointer": f"/package_state/{index}",
            }
        for index, item in enumerate(releases):
            yield {
                "product": item.product_name,
                "package": item.package,
                "cpe": item.cpe,
                "status": "Fixed",
                "advisory": item.advisory,
                "release_date": item.release_date,
                "source_pointer": f"/affected_release/{index}",
            }

    return len(states) + len(releases), list(islice(rows(), offset, offset + limit))
