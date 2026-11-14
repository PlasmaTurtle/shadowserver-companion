"""Versioned, lossless JSON storage with content-addressed shared strings.

Only newly written report/section snapshots use this format. Historic plain
JSON remains readable and is never rewritten. References live entirely inside
the same document; a backup or certified package needs no external resource
store to reconstruct its original logical model.
"""

from __future__ import annotations

from hashlib import sha256
from base64 import b64encode, b64decode
import json
import re
import zlib

LEGACY_FORMAT = "shadowserver-shared-strings-v1"
FORMAT = "shadowserver-shared-strings-v2"
MIN_STRING_LENGTH = 1024
# Logical repetition is counted even though decoded references share strings
# in memory. Two GiB accommodates long retained review histories while placing
# a finite bound on work performed by downstream logical-model consumers.
MAX_EXPANDED_STRING_BYTES = 2 * 1024 * 1024 * 1024
MAX_UNIQUE_STRING_BYTES = 128 * 1024 * 1024
MAX_DEPTH = 128
REFERENCE = "$ssc_string_sha256"
LITERAL = "$ssc_literal_object"


def pack(document):
    """Build a storage envelope without changing any caller-owned value."""
    strings = {}
    memo = {}
    expanded = 0
    unique_bytes = 0

    def encode(value, depth=0):
        nonlocal expanded, unique_bytes
        if depth > MAX_DEPTH:
            raise ValueError("Snapshot nesting exceeds the supported depth")
        if isinstance(value, str) and len(value) >= MIN_STRING_LENGTH:
            # Frozen models often share Python strings already. Avoid hashing
            # the same multi-megabyte resource for every occurrence.
            cached = memo.get(id(value))
            if cached is not None and cached[0] is value:
                key, size = cached[1:]
            else:
                raw = value.encode("utf-8")
                key, size = sha256(raw).hexdigest(), len(raw)
                memo[id(value)] = (value, key, size)
            expanded += size
            if expanded > MAX_EXPANDED_STRING_BYTES:
                raise ValueError("Compact snapshot expanded content exceeds the supported limit")
            if key not in strings:
                unique_bytes += size
                if unique_bytes > MAX_UNIQUE_STRING_BYTES:
                    raise ValueError("Compact snapshot unique resources exceed the supported limit")
                compressed = b64encode(zlib.compress(value.encode("utf-8"), 6)).decode("ascii")
                strings[key] = (
                    {"encoding": "zlib-base64", "bytes": size, "data": compressed}
                    if len(compressed) + 80 < len(value) * 0.9
                    else value
                )
            return {REFERENCE: key}
        if isinstance(value, list):
            return [encode(item, depth + 1) for item in value]
        if isinstance(value, dict):
            escaped = REFERENCE in value or LITERAL in value
            encoded = {
                key: encode(item, depth + (2 if escaped else 1)) for key, item in value.items()
            }
            # Imported source fields may legitimately use our reserved names.
            # Escape those dictionaries rather than interpreting their data.
            return {LITERAL: encoded} if escaped else encoded
        return value

    encoded = encode(document)
    return {"storage_format": FORMAT, "document": encoded, "strings": strings}


def unpack(value, *, resource_pool=None):
    """Restore a logical document, verifying every shared resource first."""
    if not isinstance(value, dict) or "storage_format" not in value:
        return value
    if value.get("storage_format") not in {LEGACY_FORMAT, FORMAT}:
        raise ValueError("Unsupported snapshot storage format")
    if set(value) != {"storage_format", "document", "strings"}:
        raise ValueError("Invalid compact snapshot envelope")
    stored_strings = value["strings"]
    if not isinstance(stored_strings, dict):
        raise ValueError("Invalid compact snapshot resource table")
    strings = {}
    unique_bytes = 0
    for key, text in stored_strings.items():
        if isinstance(text, dict) and value["storage_format"] == FORMAT:
            if (
                set(text) != {"encoding", "bytes", "data"}
                or text["encoding"] != "zlib-base64"
                or type(text["bytes"]) is not int
                or text["bytes"] < 0
                or not isinstance(text["data"], str)
            ):
                raise ValueError("Invalid compressed snapshot resource")
            if text["bytes"] > MAX_UNIQUE_STRING_BYTES - unique_bytes:
                raise ValueError("Compact snapshot unique resources exceed the supported limit")
            try:
                decoder = zlib.decompressobj()
                raw = decoder.decompress(b64decode(text["data"], validate=True), text["bytes"] + 1)
                if (
                    len(raw) != text["bytes"]
                    or not decoder.eof
                    or decoder.unused_data
                    or decoder.unconsumed_tail
                ):
                    raise ValueError("Invalid compressed snapshot resource length")
                text = raw.decode("utf-8")
            except (ValueError, zlib.error, UnicodeError) as exc:
                raise ValueError("Invalid compressed snapshot resource") from exc
        if (
            not isinstance(key, str)
            or re.fullmatch(r"[0-9a-f]{64}", key) is None
            or not isinstance(text, str)
            or sha256(text.encode("utf-8")).hexdigest() != key
        ):
            raise ValueError("Compact snapshot resource integrity check failed")
        unique_bytes += len(text.encode("utf-8"))
        if unique_bytes > MAX_UNIQUE_STRING_BYTES:
            raise ValueError("Compact snapshot unique resources exceed the supported limit")
        strings[key] = text
        if resource_pool is not None:
            # Caller-owned, short-lived pools let a case history share fonts
            # across independently stored validation records. Always verify
            # this document's bytes before reusing an already parsed string.
            if key in resource_pool and resource_pool[key] != text:
                raise ValueError("Compact snapshot resource pool is inconsistent")
            strings[key] = resource_pool.setdefault(key, text)
    sizes = {key: len(text.encode("utf-8")) for key, text in strings.items()}
    expanded = 0

    def decode(item, depth=0, *, literal=False):
        nonlocal expanded
        if depth > MAX_DEPTH:
            raise ValueError("Snapshot nesting exceeds the supported depth")
        if isinstance(item, list):
            return [decode(child, depth + 1) for child in item]
        if isinstance(item, dict):
            if not literal and set(item) == {REFERENCE}:
                key = item[REFERENCE]
                if not isinstance(key, str) or key not in strings:
                    raise ValueError("Compact snapshot resource is missing")
                expanded += sizes[key]
                if expanded > MAX_EXPANDED_STRING_BYTES:
                    raise ValueError(
                        "Compact snapshot expanded content exceeds the supported limit"
                    )
                return strings[key]
            if not literal and set(item) == {LITERAL}:
                if not isinstance(item[LITERAL], dict):
                    raise ValueError("Invalid escaped snapshot object")
                return decode(item[LITERAL], depth + 1, literal=True)
            if not literal and (REFERENCE in item or LITERAL in item):
                raise ValueError("Invalid compact snapshot reference")
            return {key: decode(child, depth + 1) for key, child in item.items()}
        return item

    return decode(value["document"])


def loads(raw, *, resource_pool=None):
    # Reject ambiguous duplicate names in both legacy and compact documents.
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON property in snapshot")
            result[key] = value
        return result

    return unpack(json.loads(raw, object_pairs_hook=unique), resource_pool=resource_pool)


def dumps(document):
    return json.dumps(pack(document), ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def dump(document, stream):
    # Avoid a second report-sized string and UTF-8 buffer during publication.
    json.dump(pack(document), stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
