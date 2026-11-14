"""Pure canonical asset/source identity helpers shared by ingestion and ownership."""

from datetime import datetime, timezone
import hashlib
from ipaddress import ip_address
from .intake.domains import HOSTNAME
from .intake.versions import entry_fields
from .primitives import dump


def digest(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()


def hostname(value):
    value = str(value or "").strip().rstrip(".").lower()
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    return value if len(value) <= 253 and HOSTNAME.fullmatch(value) else ""


def address(value):
    try:
        return ip_address(str(value or "").strip()).compressed
    except ValueError:
        return ""


def timestamp(value):
    try:
        value = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        return (
            value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
        )
    except ValueError, TypeError:
        return ""


def source_key(entry, source_sha256):
    normalized, source = entry.get("normalized") or {}, entry.get("source") or {}
    if normalized.get("observation_ref"):
        return str(normalized["observation_ref"])
    return hashlib.sha256(
        f"{source_sha256}:{source.get('sheet', '')}:{source.get('row', 0)}".encode()
    ).hexdigest()


def service_scope(entry):
    fields = entry_fields(entry)
    protocol = str(fields.get("protocol") or "").strip().casefold()
    port = str(fields.get("port") or "").strip()
    if port.isdigit():
        port = str(int(port))
    return protocol + ":" + port


def asset_key(entry):
    fields = entry_fields(entry)
    name = hostname(fields.get("hostname") or entry.get("hostname"))
    ip = address(entry.get("ip") or fields.get("ip"))
    return ("hostname:" + name if name else "ip:" + ip if ip else ""), name, ip
