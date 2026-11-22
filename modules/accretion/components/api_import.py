"""Offline handoff from the independent Shadowserver API downloader.

This adapter accepts an already downloaded report and its public receipt. It
does not hold credentials, call the API, trust a receipt instead of hashing the
bytes, or claim that the account/catalog has passed live acceptance.
"""

from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re

MAX_API_DOWNLOAD = 256 * 1024 * 1024
MAX_RECEIPT_JSON = 64 * 1024
RECEIPT_FIELDS = frozenset(
    (
        "path",
        "original_filename",
        "subscription",
        "report_type",
        "report_date",
        "retrieved_at",
        "size_bytes",
        "sha256",
        "source_fingerprint",
        "logical_id",
        "schema_reference",
        "validation",
        "reused",
    )
)


def receipt_acquisition(receipt, *, narrative_date_basis=None):
    """Validate only the downloader's public receipt, with no bearer secrets.

    Source report and retrieval dates are provenance only. The legacy
    narrative_date_basis argument is accepted for compatibility and ignored;
    the report builder owns its narrative date independently of acquisition.
    """
    if hasattr(receipt, "public_dict"):
        receipt = receipt.public_dict()
    if not isinstance(receipt, dict) or set(receipt) - RECEIPT_FIELDS:
        raise ValueError("Supply the API module's public download receipt only")
    receipt = dict(receipt)
    # A local downloader path is not a portable identity or an import instruction.
    receipt.pop("path", None)
    for key in ("original_filename", "subscription", "report_type", "report_date", "retrieved_at"):
        value = receipt.get(key)
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 1024
            or any(ord(c) < 32 for c in value)
        ):
            raise ValueError(f"Download receipt has an invalid {key}")
    name = receipt["original_filename"]
    if Path(name.replace("\\", "/")).name != name or not name.lower().endswith((".csv", ".csv.gz")):
        raise ValueError("API receipt filename must name a CSV or CSV.gz report")
    for key in ("sha256", "source_fingerprint", "logical_id"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get(key, ""))):
            raise ValueError(f"Download receipt has an invalid {key}")
    size = receipt.get("size_bytes")
    if type(size) is not int or not 0 < size <= MAX_API_DOWNLOAD:
        raise ValueError("API download must be between 1 byte and 256 MiB")
    if receipt.get("validation") != "csv_valid":
        raise ValueError("API download receipt must record completed CSV validation")
    if "reused" in receipt and type(receipt["reused"]) is not bool:
        raise ValueError("Download receipt has an invalid reused flag")
    if receipt.get("schema_reference") is not None and (
        not isinstance(receipt["schema_reference"], str) or len(receipt["schema_reference"]) > 2048
    ):
        raise ValueError("Download receipt has an invalid schema reference")
    try:
        parsed_date = date.fromisoformat(receipt["report_date"])
        retrieved = datetime.fromisoformat(receipt["retrieved_at"].replace("Z", "+00:00"))
        if parsed_date.isoformat() != receipt["report_date"] or retrieved.tzinfo is None:
            raise ValueError
    except ValueError:
        raise ValueError(
            "Receipt report date and timezone-aware retrieval time are required"
        ) from None
    identity_parts = [
        receipt[k] for k in ("subscription", "report_type", "report_date", "original_filename")
    ]
    expected = hashlib.sha256(
        json.dumps(identity_parts, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()
    if receipt["logical_id"] != expected:
        raise ValueError("Receipt logical identity does not match its report selection")
    encoded = json.dumps(
        receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    if len(encoded) > MAX_RECEIPT_JSON:
        raise ValueError("API receipt exceeds the 64 KiB limit")
    return {
        "kind": "shadowserver_api_receipt",
        "report_date": receipt["report_date"],
        "retrieved_at": receipt["retrieved_at"],
        "catalog_coverage": "unknown",
        "receipt_sha256": hashlib.sha256(encoded).hexdigest(),
        "receipt": receipt,
        "live_api_acceptance": "not_performed_by_companion",
    }


def enqueue_download(intake, path, receipt, *, narrative_date_basis=None):
    """Library entry point; accepts a file path supplied by the local caller."""
    acquisition = receipt_acquisition(receipt)
    with Path(path).open("rb") as stream:
        return intake.enqueue_stream(
            acquisition["receipt"]["original_filename"],
            stream,
            max_bytes=MAX_API_DOWNLOAD,
            acquisition=acquisition,
        )
