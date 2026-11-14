"""Stable finding identity and observation time; no persistence or workflow."""

from datetime import datetime, timezone
import hashlib
import ipaddress
import re
from .versions import entry_fields
import json


def signature(entry):
    """Compare findings, excluding scan date, file name and catalog refreshes."""
    fields = entry_fields(entry)
    address = str(entry.get("ip") or fields.get("ip") or "")
    try:
        address = ipaddress.ip_address(address).compressed
    except ValueError:
        pass

    def tokens(value):
        return sorted(set(re.split(r"[;,\s]+", str(value or "").strip().casefold())) - {""})

    values = [
        str(fields.get("hostname") or "").casefold().rstrip("."),
        address,
        str(fields.get("protocol") or "").casefold(),
        str(fields.get("port") or ""),
        tokens(fields.get("tag")),
        tokens(fields.get("version")),
        *[
            str(fields.get(k) or "").casefold()
            for k in ("product", "application", "service", "severity", "region", "city")
        ],
    ]
    return hashlib.sha256(
        json.dumps(values, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def observed(entry, fallback):
    value = entry.get("source", {}).get("fields", {}).get("timestamp") or fallback
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (
            stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
        )
    except ValueError, TypeError:
        return fallback
