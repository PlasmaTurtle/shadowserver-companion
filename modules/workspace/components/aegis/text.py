"""Bounded media parsing and strict text decoding at external-input boundaries.

Callers choose supported media, size and character sets. These helpers validate
representation; they do not establish source trust or replace a provider schema.
This module has no dependency on a workflow, storage layer or network client.
"""

import codecs
import re

from .errors import InputValidationError

_CHARSETS = {
    "utf-8": "utf-8-sig",
    "utf8": "utf-8-sig",
    "us-ascii": "ascii",
    "ascii": "ascii",
    "iso-8859-1": "iso-8859-1",
    "windows-1252": "cp1252",
}
_MEDIA = re.compile(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+", re.I)
_PARAMETER = re.compile(
    r"([a-z0-9!#$&^_.+-]+)\s*=\s*(?:\"([^\"\r\n]*)\"|'([^'\r\n]*)'|([^\s;\"']+))", re.I
)
_CONTROLS = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f-\x9f]")
_BINARY_PREFIXES = (
    b"MZ",
    b"\x7fELF",
    b"%PDF-",
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"PK\x07\x08",
    b"\x89PNG",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"RIFF",
    b"BM",
    b"\x1f\x8b",
    b"7z\xbc\xaf\x27\x1c",
    b"Rar!",
    b"\xd0\xcf\x11\xe0",
)


def parse_media_type(content_type, *, max_length=512):
    """Return normalized media and bounded, unambiguous parameters.

    Missing media, malformed parameters, duplicate names and header control
    characters are rejected. The accepted media allowlist belongs to the caller.
    """
    if type(max_length) is not int or max_length <= 0:
        raise ValueError("The media header limit must be a positive integer")
    if (
        not isinstance(content_type, str)
        or len(content_type) > max_length
        or any(ord(c) < 32 or ord(c) == 127 for c in content_type)
    ):
        raise InputValidationError("unsupported_content", "The response has an invalid media type.")
    segments = content_type.split(";")
    media = segments[0].strip().lower()
    if not _MEDIA.fullmatch(media):
        raise InputValidationError("unsupported_content", "The response has an invalid media type.")
    parameters = {}
    for segment in segments[1:]:
        match = _PARAMETER.fullmatch(segment.strip())
        if not match:
            raise InputValidationError(
                "unsupported_content", "The response has malformed media parameters."
            )
        name = match[1].lower()
        if name in parameters:
            raise InputValidationError(
                "unsupported_content", "The response has ambiguous media parameters."
            )
        parameters[name] = next(v for v in match.groups()[1:] if v is not None)
    return media, parameters


def decode_bounded_text(
    body,
    content_type,
    *,
    allowed_media,
    max_bytes,
    partial=False,
    allowed_charsets=None,
):
    """Decode supported text without replacement or encoding inference.

    ``partial`` permits an unfinished codepoint only at the capture boundary.
    Callers must still mark a truncated capture incomplete. ``allowed_charsets``
    can narrow the supported encodings; it cannot enable arbitrary codecs.
    """
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("The text byte limit must be a positive integer")
    if type(partial) is not bool:
        raise ValueError("The partial text flag must be a boolean")
    if not isinstance(body, bytes) or len(body) > max_bytes:
        raise InputValidationError("invalid_response", "The response exceeds its text byte limit.")
    media, parameters = parse_media_type(content_type)
    if media not in allowed_media:
        raise InputValidationError(
            "unsupported_content", "The source did not return a supported text format."
        )
    charset = parameters.get("charset", "utf-8").lower()
    if charset not in _CHARSETS or (
        allowed_charsets is not None and charset not in allowed_charsets
    ):
        raise InputValidationError(
            "unsupported_charset", "The source uses an unsupported text encoding."
        )
    prefix = body.lstrip()
    if prefix.startswith(codecs.BOM_UTF8):
        prefix = prefix[len(codecs.BOM_UTF8) :].lstrip()
    if prefix.startswith(_BINARY_PREFIXES) or b"\x00" in body:
        raise InputValidationError(
            "nontext_response", "The source returned binary content instead of text."
        )
    try:
        decoder = codecs.getincrementaldecoder(_CHARSETS[charset])(errors="strict")
        text = decoder.decode(body, final=not partial)
    except UnicodeError:
        raise InputValidationError(
            "invalid_text", "The source contains invalid bytes for its declared text encoding."
        ) from None
    if _CONTROLS.search(text):
        raise InputValidationError(
            "nontext_response", "The source contains unsupported binary control characters."
        )
    return text
