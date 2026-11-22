"""Lossless source values and cheap field normalization for the report archive.

This is a field contract, not an admission gate. Missing or malformed values are
retained with diagnostics. Software versions and unknown fields remain text;
their meaning is never guessed from a different report's similarly named field.
"""

from datetime import date, datetime, time, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from ipaddress import ip_address
import math
import re

from .intake.domains import HOSTNAME, root_domain
from .report_profiles import inventory, inventory_metadata

NORMALIZATION_VERSION = 1
_BOOLEAN_FIELDS = frozenset({"cert_expired", "cert_valid", "anonymous_access", "anon_login"})
_TIMESTAMP_FIELDS = frozenset({"timestamp", "http_date", "cert_issue_date", "cert_expiration_date"})


def json_value(value):
    """Represent input values without clipping or silently dropping non-JSON data."""
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return {"$type": "nonfinite_number", "value": str(value)}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported report value type: {type(value).__name__}")


def field_type(name):
    if name not in known_fields():
        return "text"
    if name == "ip" or name.endswith("_ip"):
        return "ip"
    if name == "hostname":
        return "hostname"
    if name == "port" or name.endswith("_port"):
        return "port"
    if name == "asn" or name.endswith("_asn"):
        return "asn"
    if name in _TIMESTAMP_FIELDS:
        return "timestamp"
    if name in _BOOLEAN_FIELDS:
        return "boolean"
    if name in {"latitude", "longitude"}:
        return "number"
    if name in {"http_code", "count", "naics", "sic"}:
        return "integer"
    return "text"


@lru_cache(maxsize=1)
def known_fields():
    fields = {}
    for report_type, definition in inventory().items():
        for name in definition.get("fields", ()):
            fields.setdefault(name, []).append(report_type)
    return fields


def normalize_fields(fields):
    """Normalize JSON-safe source fields once without rewriting their original tree."""
    original = fields
    normalized, errors = {}, {}
    for name, raw in fields.items():
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            normalized[name] = None
            continue
        kind = field_type(name)
        value = raw.strip() if isinstance(raw, str) else raw
        try:
            if isinstance(raw, dict) and raw.get("$type") == "nonfinite_number":
                raise ValueError("Non-finite number")
            if isinstance(raw, float) and not math.isfinite(raw):
                raise ValueError("Non-finite number")
            if kind == "ip":
                value = ip_address(str(value)).compressed
            elif kind == "hostname":
                value = str(value).rstrip(".").encode("idna").decode("ascii").lower()
                if len(value) > 253 or not HOSTNAME.fullmatch(value):
                    raise ValueError("Invalid hostname")
            elif kind in {"integer", "port", "asn"}:
                if isinstance(value, bool):
                    raise ValueError("Boolean is not an integer")
                text = str(value)
                if kind == "asn" and text.upper().startswith("AS"):
                    text = text[2:]
                if not re.fullmatch(r"[+-]?\d+", text):
                    raise ValueError("Invalid integer")
                value = int(text)
                if kind == "port" and not 0 <= value <= 65535:
                    raise ValueError("Port outside 0..65535")
                if kind == "asn" and not 0 <= value <= 4294967295:
                    raise ValueError("ASN outside 0..4294967295")
            elif kind == "number":
                if isinstance(value, bool):
                    raise ValueError("Boolean is not a number")
                value = float(value)
                bound = 90 if name == "latitude" else 180
                if not math.isfinite(value) or not -bound <= value <= bound:
                    raise ValueError("Coordinate outside valid range")
            elif kind == "boolean":
                token = str(value).lower()
                if token not in {"true", "false", "yes", "no", "y", "n", "1", "0"}:
                    raise ValueError("Invalid boolean")
                value = token in {"true", "yes", "y", "1"}
            elif kind == "timestamp":
                if name == "http_date":
                    try:
                        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                    except ValueError:
                        parsed = parsedate_to_datetime(str(value))
                else:
                    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                value = (
                    parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
                    .astimezone(timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z")
                )
            elif name in {"protocol", "severity"}:
                value = str(value).lower()
            elif name == "region" and not isinstance(value, str):
                raise ValueError("Expected region text")
        except (ValueError, TypeError, UnicodeError, OverflowError) as error:
            value = None
            errors[name] = str(error)
        normalized[name] = value
    hostname = normalized.get("hostname")
    domain = root_domain(hostname) if isinstance(hostname, str) and hostname else ""
    return original, normalized, errors, domain or ""


def catalogue(observed=(), report_type=None):
    definitions = known_fields()
    names = (
        set(inventory().get(report_type, {}).get("fields", ())) if report_type else set(definitions)
    )
    observed_reports = {}
    for report, name in observed:
        observed_reports.setdefault(name, set()).add(report)
        if not report_type or report == report_type:
            names.add(name)
    return {
        "fields": [
            {
                "name": name,
                "type": field_type(name),
                "known": name in definitions,
                "reports": sorted(
                    set(definitions.get(name, ())) | observed_reports.get(name, set())
                ),
            }
            for name in sorted(names)
        ],
        "report_types": sorted(inventory()),
        "version": inventory_metadata()["sha256"],
        "normalization_version": NORMALIZATION_VERSION,
    }
