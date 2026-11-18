"""Current narrative: the notification's start date, independent of intake."""

from datetime import datetime

from .introduction_model import office_timezone
from .notification_narrative import MONTHS, scan_date
from .notification_narrative_v2 import joined
from .notification_narrative_v4 import (
    REPORT_STARTED_REVISION,
    _included,
    generate_narrative as generate_v4,
)


REVISION = REPORT_STARTED_REVISION


def report_started_date(lead, draft):
    """Use the immutable case timestamp in office time, never a source date.

    Standalone or historical documents without a case timestamp may use their
    saved report date. Rendering never substitutes today's date.
    """
    stamp = lead.get("case", {}).get("created_at")
    if stamp:
        try:
            parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(office_timezone()).date()
            return parsed.date()
        except ValueError:
            pass
    return scan_date(draft.get("report_date"))


def generate_narrative(lead, draft):
    _, groups = _included(lead, draft)
    if not groups:
        return ""
    started = report_started_date(lead, draft)
    prefix = f"On {MONTHS[started.month - 1]} {started.day}, {started.year}, " if started else ""
    opening = (
        prefix
        + ("the" if prefix else "The")
        + " United States Secret Service, Charlotte Cyber Fraud Task Force, began reviewing "
        + "Shadowserver observations associated with "
        + joined(ip for group in groups for ip in group["ips"])
        + "."
    )
    from .sender_identity import apply_identity_copy

    result = {**draft, "narrative": generate_v4(lead, draft, opening_text=opening)}
    return apply_identity_copy(result)["narrative"]
