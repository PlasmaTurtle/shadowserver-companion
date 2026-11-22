"""HTTP field parsing without requests, provider pacing or application state."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import re


def parse_retry_after(value: str | None, *, now: datetime) -> float | None:
    """Return server delay in seconds, or None for absent/invalid guidance.

    RFC 9110 permits decimal integers and HTTP dates (including obsolete asctime
    dates in GMT). The caller supplies an aware clock and owns fallback, minimum
    waits and operation deadlines. No sleeping or network work happens here.
    """
    if now.utcoffset() is None:
        raise ValueError("Retry-After requires a timezone-aware current instant")
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        return None
    value = value.strip()
    try:
        if value.isascii() and value.isdecimal():
            delay = float(value)
        else:
            deadline = parsedate_to_datetime(value)
            if deadline.tzinfo is None:
                # email.utils also accepts zone-less mail dates. Only HTTP's
                # asctime form has an implicit GMT zone in this contract.
                if not re.fullmatch(
                    r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) "
                    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
                    r"[ 0-9][0-9] [0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4}",
                    value,
                ):
                    return None
                deadline = deadline.replace(tzinfo=timezone.utc)
            delay = (deadline - now).total_seconds()
        return max(0.0, delay) if math.isfinite(delay) else None
    except (ValueError, TypeError, OverflowError):
        return None
