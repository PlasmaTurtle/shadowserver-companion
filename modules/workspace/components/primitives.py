"""Stable JSON, identifiers and UTC stamps; no workspace or application imports."""

import json
import uuid
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def uid():
    return uuid.uuid4().hex


def dump(value):
    return json.dumps(value, ensure_ascii=False, default=str, allow_nan=False)
