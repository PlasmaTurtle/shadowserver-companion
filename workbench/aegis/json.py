"""Dependency-free, bounded JSON validation shared by application boundaries.

This module validates representation and structure. Provider adapters retain
ownership of required fields, identifiers, dates, and domain-specific schemas.
"""

from __future__ import annotations

import json
from itertools import chain
import math

DEFAULT_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_DEPTH = 64


def _limits(max_bytes, max_depth):
    if type(max_bytes) is not int or not 1 <= max_bytes <= 256 * 1024 * 1024:
        raise ValueError("JSON byte limit is invalid")
    if type(max_depth) is not int or not 1 <= max_depth <= 256:
        raise ValueError("JSON nesting limit is invalid")


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("JSON contains duplicate members")
        value[key] = item
    return value


def _finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON contains non-finite numbers")
    return number


def _constant(value):
    raise ValueError("JSON contains non-finite numbers")


def _preflight(text, index, max_bytes, max_depth):
    """Bound one raw_decode value before recursive parsing; respect JSON strings.

    Incomplete input still reaches JSONDecoder, whose JSONDecodeError lets a
    streaming caller obtain another bounded chunk. A complete following value
    is not counted against the first value's byte/depth budget.
    """
    if not isinstance(text, str) or type(index) is not int or not 0 <= index <= len(text):
        raise ValueError("JSON input or offset is invalid")
    depth = 0
    quoted = escaped = False
    root_string = index < len(text) and text[index] == '"'
    container = index < len(text) and text[index] in "{["
    end = index
    for position in range(index, len(text)):
        character = text[position]
        end = position + 1
        if not quoted and not container and not root_string and character in ",]} \t\r\n":
            end = position
            break
        # Every UTF-8 character costs at least one byte, so this cheap check
        # bounds the scan before the exact encoded-length check below.
        if end - index > max_bytes:
            raise ValueError("JSON exceeds its byte limit")
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
                if root_string and depth == 0:
                    break
            continue
        if character == '"':
            quoted = True
        elif character in "{[":
            depth += 1
            if depth > max_depth:
                raise ValueError("JSON exceeds its nesting limit")
        elif character in "}]":
            depth -= 1
            if container and depth <= 0:
                break
        elif not container and not root_string and character in ", \t\r\n":
            end = position
            break
    try:
        if len(text[index:end].encode("utf-8", errors="strict")) > max_bytes:
            raise ValueError("JSON exceeds its byte limit")
    except UnicodeError as error:
        raise ValueError("JSON input is not valid UTF-8") from error


def _valid_unicode(value):
    """Escaped lone surrogates must not survive otherwise valid UTF-8 input."""
    pending = [iter((value,))]
    try:
        while pending:
            try:
                item = next(pending[-1])
            except StopIteration:
                pending.pop()
                continue
            if isinstance(item, str):
                item.encode("utf-8", errors="strict")
            elif isinstance(item, dict):
                pending.append(chain(item.keys(), item.values()))
            elif isinstance(item, list):
                pending.append(iter(item))
    except UnicodeError as error:
        raise ValueError("JSON contains invalid Unicode text") from error


class _StrictJSONDecoder(json.JSONDecoder):
    def __init__(self, max_bytes, max_depth):
        _limits(max_bytes, max_depth)
        self.max_bytes, self.max_depth = max_bytes, max_depth
        super().__init__(object_pairs_hook=_pairs, parse_float=_finite, parse_constant=_constant)

    def decode(self, text, _w=json.decoder.WHITESPACE.match):
        if not isinstance(text, str) or len(text) > self.max_bytes:
            raise ValueError("JSON exceeds its byte limit or is not text")
        try:
            if len(text.encode("utf-8", errors="strict")) > self.max_bytes:
                raise ValueError("JSON exceeds its byte limit")
        except UnicodeError as error:
            raise ValueError("JSON input is not valid UTF-8") from error
        return super().decode(text, _w)

    def raw_decode(self, text, idx=0):
        _preflight(text, idx, self.max_bytes, self.max_depth)
        try:
            value, end = super().raw_decode(text, idx)
        except RecursionError as error:
            raise ValueError("JSON exceeds the decoder nesting limit") from error
        _valid_unicode(value)
        return value, end


def strict_json_decoder(*, max_bytes=DEFAULT_MAX_BYTES, max_depth=DEFAULT_MAX_DEPTH):
    """Return a strict JSONDecoder compatible with bounded streaming raw_decode."""
    return _StrictJSONDecoder(max_bytes, max_depth)


def strict_json_loads(
    body, *, max_bytes=DEFAULT_MAX_BYTES, max_depth=DEFAULT_MAX_DEPTH, require_object=False
):
    """Read bounded UTF-8 JSON, rejecting ambiguous or nonstandard input.

    Bytes/bytearray and decoded str are supported; UTF-16/32 guessing is not.
    The optional root-object constraint is explicit because some providers
    legitimately supply arrays. Domain-specific schemas belong to callers.
    """
    _limits(max_bytes, max_depth)
    if type(require_object) is not bool:
        raise ValueError("JSON object requirement must be boolean")
    try:
        if isinstance(body, (bytes, bytearray)):
            if len(body) > max_bytes:
                raise ValueError("JSON exceeds its byte limit")
            text = bytes(body).decode("utf-8-sig", errors="strict")
        elif isinstance(body, str):
            if len(body) > max_bytes or len(body.encode("utf-8", errors="strict")) > max_bytes:
                raise ValueError("JSON exceeds its byte limit")
            text = body.removeprefix("\ufeff")
        else:
            raise ValueError("JSON input must be bytes or text")
        value = strict_json_decoder(max_bytes=max_bytes, max_depth=max_depth).decode(text)
    except UnicodeError as error:
        raise ValueError("JSON input is not valid UTF-8") from error
    except json.JSONDecodeError as error:
        raise ValueError("JSON input is incomplete or malformed") from error
    if require_object and not isinstance(value, dict):
        raise ValueError("JSON response must be an object")
    return value
