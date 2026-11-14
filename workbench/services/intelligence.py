"""Stable identity for immutable source selections."""

import hashlib
import json


def _json_numbers(value):
    # JSON has one number type. Browsers round-trip 10.0 as 10, including inside
    # retained provider records. Normalize that representation only; never round
    # fractional scores, coerce strings, or equate booleans with numeric values.
    if type(value) is float and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _json_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_numbers(item) for item in value]
    return value


def canonical_selection(record):
    return json.dumps(_json_numbers(record), sort_keys=True, ensure_ascii=False, allow_nan=False)


def same_selection(left, right):
    return canonical_selection(left) == canonical_selection(right)


def selection_key(record):
    return (
        "cve-selection:" + hashlib.sha256(canonical_selection(record).encode("utf-8")).hexdigest()
    )
