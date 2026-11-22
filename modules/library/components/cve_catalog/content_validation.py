"""Bounded format checks before network feed bytes reach staging files.

These checks reject HTML/error documents and mismatched containers. Complete
record, checksum and schema validation still happens before catalog publication.
"""

import codecs
import json
import re
import zlib

from modules.workspace.components.aegis.json import strict_json_decoder
from modules.workspace.components.aegis.text import parse_media_type

PREFIX_LIMIT = 64 * 1024


def validate_feed_media(headers, kind):
    """Honor an explicit publisher media type; content checks remain mandatory."""
    value = next((str(v) for k, v in headers.items() if str(k).lower() == "content-type"), "")
    if not value:
        # Some mirrors omit the header. A valid container/structured document
        # must still be proved before staging; absence is not format approval.
        return
    try:
        media, _ = parse_media_type(value)
    except ValueError as error:
        raise ValueError("Reference feed has an invalid content type") from error
    allowed = {
        "gzip": {
            "application/gzip",
            "application/x-gzip",
            "application/octet-stream",
            "application/x-compressed",
        },
        "json": {"application/json", "text/json", "text/plain"},
        "meta": {"text/plain", "application/octet-stream"},
    }[kind]
    if media not in allowed and not (
        kind == "json" and re.fullmatch(r"application/[a-z0-9.+-]+\+json", media)
    ):
        raise ValueError("Reference feed returned an unsupported content type")


def _nvd_prefix(text):
    """Recognize the real top-level vulnerabilities array, never a string match."""
    decoder = strict_json_decoder(max_bytes=PREFIX_LIMIT)
    position = len(text) - len(text.lstrip())
    if position == len(text):
        return False
    if text[position] != "{":
        raise ValueError("NVD compressed feed does not contain a JSON object")
    position += 1
    seen = set()
    while True:
        position += len(text[position:]) - len(text[position:].lstrip())
        if position == len(text):
            return False
        try:
            key, position = decoder.raw_decode(text, position)
        except json.JSONDecodeError:
            return False
        if not isinstance(key, str) or key in seen:
            raise ValueError("NVD feed contains invalid or duplicate header fields")
        seen.add(key)
        position += len(text[position:]) - len(text[position:].lstrip())
        if position == len(text):
            return False
        if text[position] != ":":
            raise ValueError("NVD feed has invalid JSON framing")
        position += 1
        position += len(text[position:]) - len(text[position:].lstrip())
        if position == len(text):
            return False
        if key == "vulnerabilities":
            if text[position] != "[":
                raise ValueError("NVD feed has no vulnerability array")
            return True
        try:
            value, position = decoder.raw_decode(text, position)
        except json.JSONDecodeError:
            return False
        if key == "format" and value != "NVD_CVE" or key == "version" and value != "2.0":
            raise ValueError("NVD feed has an unsupported format or version")
        position += len(text[position:]) - len(text[position:].lstrip())
        if position == len(text):
            return False
        if text[position] != ",":
            raise ValueError("NVD feed is missing its vulnerability array")
        position += 1


def _epss_prefix(text):
    lines = text.splitlines()
    if not lines:
        return False
    if not lines[0].startswith("#"):
        raise ValueError("EPSS compressed feed does not contain CSV metadata")
    if len(lines) < 2 or not text.endswith(("\n", "\r")) and len(lines) == 2:
        return False
    if not re.search(r"model_version\s*:\s*[^,\s]+", lines[0]) or not re.search(
        r"score_date\s*:\s*\d{4}-\d{2}-\d{2}(?:,|\s|$)", lines[0]
    ):
        raise ValueError("EPSS feed is missing its model version or score date")
    if lines[1] != "cve,epss,percentile":
        raise ValueError("EPSS feed has unexpected columns")
    return True


def validated_gzip_chunks(chunks, kind):
    """Release compressed bytes only after bounded inflation proves feed framing.

    At most 64 KiB of compressed prefix and 64 KiB of expanded prefix are held.
    Remaining input remains streaming; callers retain full size/checksum/schema
    checks and never treat this prefix check as complete record validation.
    """
    pending, expanded = [], bytearray()
    compressed_size = 0
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    check = {"nvd": _nvd_prefix, "epss": _epss_prefix}[kind]
    valid = False
    for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise ValueError("Reference feed transport returned non-byte data")
        if not chunk:
            continue
        if valid:
            yield chunk
            continue
        # Large network chunks are split for bounded prefix validation. The
        # uninspected remainder is yielded only after the prefix was accepted.
        offset = 0
        while offset < len(chunk) and not valid:
            piece = chunk[offset : offset + min(4096, PREFIX_LIMIT - compressed_size)]
            if not piece:
                raise ValueError("Compressed feed header exceeds its validation budget")
            pending.append(piece)
            compressed_size += len(piece)
            offset += len(piece)
            try:
                expanded.extend(inflater.decompress(piece, PREFIX_LIMIT - len(expanded)))
            except zlib.error as error:
                raise ValueError("Reference feed is not a valid gzip document") from error
            try:
                text = codecs.getincrementaldecoder("utf-8-sig")(errors="strict").decode(
                    bytes(expanded), final=False
                )
            except UnicodeError as error:
                raise ValueError("Reference feed prefix is not valid UTF-8") from error
            valid = check(text)
            if not valid and (len(expanded) >= PREFIX_LIMIT or inflater.eof):
                raise ValueError("Reference feed does not contain the expected document header")
        if valid:
            yield from pending
            pending.clear()
            if offset < len(chunk):
                yield chunk[offset:]
    if not valid:
        raise ValueError("Reference feed is empty or has an incomplete document header")


def verify_gzip_prefix(path, kind):
    """Check a cache file before expanding any of its bytes to another file."""
    with path.open("rb") as source:
        stream = validated_gzip_chunks(iter(lambda: source.read(128 * 1024), b""), kind)
        next(stream)
        stream.close()
