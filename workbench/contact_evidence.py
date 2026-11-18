"""Contact evidence stores typed extracts; original responses remain transient."""

import hashlib
import json
import re
from pathlib import Path
from datetime import datetime

from .contact_discovery.policy import MAX_PAGE_BYTES, MAX_CANDIDATES
from .contact_input import plain_text, validate_candidate_input
from .contact_discovery.extract import candidate_key, review_url
from .aegis.json import strict_json_loads
from .aegis import validate_scan_receipt

MAX_CAPTURE_BYTES = MAX_PAGE_BYTES
RETENTION = "contact-extract-v1"
SOURCE_FIELDS = (
    "url",
    "retrieved_at",
    "status_code",
    "content_type",
    "sha256",
    "hash_scope",
    "captured_bytes",
    "truncated",
    "content_scan",
)
CONTACT_FIELDS = (
    "kind",
    "value",
    "name",
    "role",
    "purpose",
    "route_type",
    "routing_label",
    "routing_options",
)


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def is_derived_snapshot(snapshot):
    if snapshot.get("retention") not in (None, "", RETENTION):
        raise ValueError("Unknown contact evidence retention format")
    return snapshot.get("retention") == RETENTION


def prepare_snapshot(snapshot, candidates):
    """Construct an allowlisted derivative; source digest is never its file digest."""
    source = {key: snapshot[key] for key in SOURCE_FIELDS if key in snapshot}
    if review_url(source.get("url", "")) != source.get("url"):
        raise ValueError("Contact evidence URL is not canonical")
    if type(source.get("status_code")) is not int or not 100 <= source["status_code"] <= 599:
        raise ValueError("Contact HTTP status is invalid")
    original_hash = source.get("sha256")
    if not isinstance(original_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", original_hash):
        raise ValueError("Contact response SHA-256 is invalid")
    body = snapshot.get("body")
    if body is not None:
        if not isinstance(body, bytes) or len(body) > MAX_CAPTURE_BYTES:
            raise ValueError("Contact response exceeds its capture limit")
        if hashlib.sha256(body).hexdigest() != original_hash:
            raise ValueError("Contact response failed its SHA-256 integrity check")
        # Compatibility for internal callers still supplying transient responses.
        # Validate before extracting or persisting; never write these bytes.
        if 200 <= source["status_code"] < 300:
            from .contact_discovery.validation import decode_response_text

            decoded = decode_response_text(
                body,
                source.get("content_type", ""),
                security_source=source.get("content_type", "").split(";", 1)[0].strip().lower()
                == "text/plain",
                partial=bool(source.get("truncated")),
            )
            from .aegis import scan_text

            source["content_scan"] = scan_text(decoded, context="contact-response")
        source["captured_bytes"] = len(body)
    if (
        type(source.get("captured_bytes", 0)) is not int
        or not 0 <= source.get("captured_bytes", 0) <= MAX_CAPTURE_BYTES
    ):
        raise ValueError("Contact capture size is invalid")
    source.setdefault(
        "content_scan",
        {
            "status": "not_recorded",
            "provider": "none",
            "representation": "none",
            "verdict": "not_recorded",
        },
    )
    source["content_scan"] = validate_scan_receipt(
        source["content_scan"], allow_unrecorded=True, representation="utf-16-le"
    )
    source.setdefault("captured_bytes", 0)
    source.setdefault("truncated", False)
    if type(source["truncated"]) is not bool:
        raise ValueError("Contact truncation flag is invalid")
    source.setdefault("hash_scope", "captured_prefix" if source["truncated"] else "captured_body")
    if source["hash_scope"] != ("captured_prefix" if source["truncated"] else "captured_body"):
        raise ValueError("Contact source digest scope is invalid")
    for key in ("url", "retrieved_at", "content_type"):
        plain_text(source.get(key, ""), 2048)
    try:
        stamp = datetime.fromisoformat(source["retrieved_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError()
    except (ValueError, KeyError):
        raise ValueError("Contact retrieval date must include its timezone") from None
    contacts = []
    for candidate in candidates:
        for citation in candidate["sources"]:
            if citation["snapshot_id"] == snapshot["id"]:
                contacts.append(
                    {
                        **{key: candidate[key] for key in CONTACT_FIELDS if key in candidate},
                        "excerpt": citation.get("excerpt", ""),
                    }
                )
    if contacts and source["content_scan"]["status"] in {"blocked", "unavailable"}:
        raise ValueError("Blocked contact content cannot establish contact evidence")
    title = plain_text(snapshot.get("title", ""), 2000) if contacts else ""
    artifact = {
        "schema": 1,
        "retention": RETENTION,
        "source": source,
        "title": title,
        "contacts": contacts,
        "notice": "Derived contact evidence. Original response bytes were not retained; source SHA-256 identifies the received response.",
    }
    content = (json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    if len(content) > MAX_CAPTURE_BYTES:
        raise ValueError("Derived contact evidence exceeds its capture limit")
    saved = {
        "id": snapshot["id"],
        **source,
        "title": title,
        "retention": RETENTION,
        "artifact_sha256": hashlib.sha256(content).hexdigest(),
        "artifact_bytes": len(content),
    }
    return saved, content


def _snapshot_file(store, run_id, snapshot):
    relative = Path(snapshot["path"])
    expected = Path("evidence") / "contact-discovery" / run_id
    if relative.is_absolute() or relative.parent != expected:
        raise ValueError("Contact snapshot path is outside its saved run")
    original = store.root / relative
    if any(part.is_symlink() for part in (original, *original.parents) if part != store.root):
        raise ValueError("Contact snapshot path contains a symbolic link")
    path = store.path(relative)
    if not path.is_file():
        raise ValueError("Saved contact response is missing")
    return path


def snapshot_content(store, run_id, snapshot):
    path = _snapshot_file(store, run_id, snapshot)
    with path.open("rb") as source:
        body = source.read(MAX_CAPTURE_BYTES + 1)
    if len(body) > MAX_CAPTURE_BYTES:
        raise ValueError("Saved contact response exceeds its capture limit")
    digest = (
        snapshot.get("artifact_sha256") if is_derived_snapshot(snapshot) else snapshot["sha256"]
    )
    if hashlib.sha256(body).hexdigest() != digest:
        raise ValueError("Saved contact response failed its SHA-256 integrity check")
    if is_derived_snapshot(snapshot):
        try:
            value = strict_json_loads(body, max_bytes=MAX_CAPTURE_BYTES, require_object=True)
            if (
                set(value) != {"schema", "retention", "source", "title", "contacts", "notice"}
                or value["schema"] != 1
                or value["retention"] != RETENTION
            ):
                raise ValueError("Unexpected contact evidence fields")
            if value["source"] != {key: snapshot[key] for key in SOURCE_FIELDS}:
                raise ValueError("Contact evidence differs from its source provenance")
            if (
                not isinstance(value["contacts"], list)
                or len(value["contacts"]) > MAX_CANDIDATES * 50
            ):
                raise ValueError("Contact evidence has invalid extracts")
            prepare_snapshot({**snapshot, "body": None}, [])
            if value["title"] != snapshot.get("title", ""):
                raise ValueError("Contact evidence title differs from its metadata")
            plain_text(value["title"], 2000)
            plain_text(value["notice"], 500)
            if value["contacts"] and snapshot["content_scan"]["status"] in {
                "blocked",
                "unavailable",
            }:
                raise ValueError("Blocked contact content cannot establish contact evidence")
            for contact in value["contacts"]:
                if not isinstance(contact, dict) or set(contact) - {*CONTACT_FIELDS, "excerpt"}:
                    raise ValueError("Unexpected contact evidence fields")
                validate_candidate_input(
                    {
                        **{key: item for key, item in contact.items() if key != "excerpt"},
                        "key": candidate_key(contact.get("kind"), contact.get("value", "")),
                        "sources": [
                            {
                                "snapshot_id": snapshot["id"],
                                "url": snapshot["url"],
                                "excerpt": contact.get("excerpt", ""),
                            }
                        ],
                    },
                    {snapshot["id"]: snapshot},
                )
        except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Saved contact extract is invalid") from error
    return body


def snapshot_path(store, run_id, snapshot):
    snapshot_content(store, run_id, snapshot)
    return _snapshot_file(store, run_id, snapshot)
