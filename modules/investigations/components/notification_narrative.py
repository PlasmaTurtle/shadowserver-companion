"""Deterministic narrative with the established next-day receipt date.

The v2 wording after the opening is retained. Dates come only from source-row
timestamps plus one calendar day, following the user's next-day receipt rule;
never from document or source-retrieval dates. Saved v2 drafts continue to use
the unchanged generator in notification_narrative_v2.
"""

from modules.accretion.components.intake.versions import entry_fields
from datetime import date, datetime, timedelta

from .notification_narrative_v2 import (
    REVISION as V2_REVISION,
    findings,
    generate_narrative as generate_v2,
    joined,
    presentation_groups as presentation_groups,
    scopes,
    unique,
)

REVISION = "consolidated-2026-11-08-v3"
PRESENTATION_REVISIONS = frozenset(
    (V2_REVISION, REVISION, "source-aware-2026-11-10-v4", "report-start-2026-11-12-v5")
)
GROUP_FIELDS = ("hostname", "protocol", "port", "tag", "version")
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def scan_date(value):
    """Read supported source dates without shifting to another time zone.

    Native ISO timestamps and US month/day/year exports are accepted. Numeric
    spreadsheet serials and malformed text are not guessed. The original value
    is retained unchanged in the source evidence.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for pattern in (
        "%m/%d/%Y %H:%M:%S.%f",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def dated_groups(lead, groups):
    """Keep dates attached to included row findings and their own IPs."""
    included = {tuple(group[key] for key in GROUP_FIELDS): group for group in groups}
    by_date = {}
    for entry in lead["entries"]:
        fields = entry_fields(entry)
        key = tuple(str(fields.get(field, "") or "") for field in GROUP_FIELDS)
        group = included.get(key)
        if group is None:
            continue
        observed = scan_date(fields.get("timestamp"))
        if observed == date.max:
            observed = None  # The next-day receipt date is not representable.
        rows = by_date.setdefault(observed, {})
        member = rows.setdefault(group["key"], {**group, "ips": []})
        if entry["ip"] not in member["ips"]:
            member["ips"].append(entry["ip"])
    return {day: list(members.values()) for day, members in by_date.items()}


def finding_phrase(groups):
    labels = unique(label for group in groups for label in findings(group))
    return "a critical security finding" if len(labels) == 1 else "critical security findings"


def opening(lead, groups):
    by_date = dated_groups(lead, groups)
    days = sorted(day for day in by_date if day is not None)
    dated = [group for day in days for group in by_date[day]]
    undated = by_date.get(None, [])
    if days:
        receipt_days = [day + timedelta(days=1) for day in days]
        dates = joined(f"{MONTHS[day.month - 1]} {day.day}, {day.year}" for day in receipt_days)
        ips = joined(ip for group in dated for ip in group["ips"])
        text = (
            f"On {dates}, the United States Secret Service, Charlotte Cyber Fraud Task Force, "
            f"received a Shadowserver Notification related to {finding_phrase(dated)} detected on {ips}."
        )
    else:
        ips = joined(ip for group in groups for ip in group["ips"])
        text = (
            "The United States Secret Service, Charlotte Cyber Fraud Task Force, "
            f"received a Shadowserver Notification related to {finding_phrase(groups)} detected on {ips}."
        )
    if undated:
        if not days:
            text += " The supplied observations do not include a valid scan date."
        else:
            scope = "; ".join(
                joined(findings(group)) + " on " + scopes([group], detailed=True)
                for group in undated
            )
            text += " A valid scan date was not supplied for " + scope + "."
    return text


def generate_narrative(lead, draft, *, opening_text=None):
    groups = [group for group in presentation_groups(lead, draft) if not group.get("excluded")]
    if not groups:
        return ""
    historical = generate_v2(lead, draft)
    ips = joined(ip for group in groups for ip in group["ips"])
    previous_opening = (
        "The United States Secret Service, Charlotte Cyber Fraud Task Force, received a "
        f"Shadowserver Notification related to {finding_phrase(groups)} detected on {ips}."
    )
    if not historical.startswith(previous_opening):
        raise ValueError("Historical narrative opening does not match its pinned template")
    return (opening_text if opening_text is not None else opening(lead, groups)) + historical[
        len(previous_opening) :
    ]
