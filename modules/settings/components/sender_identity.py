"""Pinned sender identity and versioned copy for newly adopted report profiles.

Workspace preferences are not a substitute for a report snapshot. Older drafts
without this profile keep their established wording until explicit adoption.
"""

from copy import deepcopy
import re

REVISION = "sender-profile-2026-11-13-v1"
FIELDS = (
    "analyst_name",
    "analyst_title",
    "agency",
    "department",
    "office",
    "email",
    "outreach_verification_route",
)
LIMITS = {key: 300 if key in {"analyst_name", "analyst_title"} else 500 for key in FIELDS}
LIMITS["outreach_verification_route"] = 1000
DEFAULT_AGENCY = "United States Secret Service"
DEFAULT_OFFICE = "Charlotte, NC Field Office"


def _text(profile, key):
    value = profile.get(key)
    return value if isinstance(value, str) else ""


def capture_profile(settings):
    return {
        "revision": REVISION,
        **{key: str(settings.get(key) or "").strip() for key in FIELDS},
    }


def effective_settings(settings, draft):
    """Overlay only saved identity; keep operational preferences current."""
    value = draft.get("sender_profile")
    profile = value if isinstance(value, dict) else {}
    return {
        **settings,
        **{key: profile[key] for key in FIELDS if isinstance(profile.get(key), str)},
    }


def update_available(settings, draft):
    return draft.get("sender_profile") != capture_profile(settings)


def _profile_shape_issue(profile):
    if profile is None or profile == {}:
        return None
    if not isinstance(profile, dict):
        return "Adopt the current report format to repair the sender profile."
    if profile.get("revision") != REVISION:
        return "Adopt the current report format to update the sender profile."
    if any(not isinstance(profile.get(key), str) for key in FIELDS):
        return "Adopt the current report format to repair the sender profile."
    if set(profile) != {*FIELDS, "revision"} or any(
        len(profile[key]) > LIMITS[key] for key in FIELDS
    ):
        return "Adopt the current report format to repair the sender profile."
    if any(any(ord(c) < 32 or ord(c) == 127 for c in profile[key]) for key in FIELDS):
        return "Sender identity must use single-line text without control characters."
    return None


def validate_saved_profile(draft):
    """Allow unfinished/legacy drafts, reject malformed authoritative identity."""
    issue = _profile_shape_issue(draft.get("sender_profile"))
    if issue:
        raise ValueError("Saved sender profile is invalid: " + issue)


def profile_issue(draft, settings=None):
    profile = draft.get("sender_profile")
    if profile is None or profile == {}:
        if settings is not None and not _default_profile(
            {"sender_profile": capture_profile(settings)}
        ):
            return "Adopt the current report format to reconcile the sender settings with this draft's legacy agency wording."
        return None  # A legacy draft must be deliberately adopted, not rewritten.
    issue = _profile_shape_issue(profile)
    if issue:
        return issue
    if not profile["agency"].strip():
        return "Set the sending organization in Settings, then adopt the current report format."
    if not profile["analyst_name"].strip():
        return "Set the sender name in Settings, then adopt the current report format."
    return None


def _default_profile(draft):
    value = draft.get("sender_profile")
    profile = value if isinstance(value, dict) else {}
    return (
        _text(profile, "agency").casefold() == DEFAULT_AGENCY.casefold()
        and _text(profile, "office").casefold() == DEFAULT_OFFICE.casefold()
    )


def _organization(draft):
    value = draft.get("sender_profile")
    profile = value if isinstance(value, dict) else {}
    agency = _text(profile, "agency").strip() or "reporting organization"
    office = _text(profile, "office").strip()
    name = ", ".join(
        [agency, office] if office and office.casefold() != agency.casefold() else [agency]
    )
    return re.sub(r"^the\s+", "", name, flags=re.I)


def identity_copy(text, draft):
    """Change controlled sender insertions, never source descriptions or evidence."""
    if (
        not isinstance(draft.get("sender_profile"), dict)
        or not draft["sender_profile"]
        or _default_profile(draft)
    ):
        return text
    name = _organization(draft)
    for literal in (
        "United States Secret Service Charlotte Cyber Fraud Task Force (CFTF)",
        "United States Secret Service, Charlotte Cyber Fraud Task Force",
        "United States Secret service, Charlotte Cyber Fraud Task Force",
        "United States Secret Service, Charlotte Field Office",
    ):
        text = text.replace(literal, name)
    for purpose in ("cyber-enabled financial crime", "cyber incidents"):
        text = text.replace(
            "This notification is part of our ongoing effort to help organizations safeguard "
            f"their infrastructure and prevent {purpose}.",
            "This notification aims to help your organization review reported exposures "
            "and protect its systems.",
        )
    return text


def security_intro(text, draft):
    if (
        not isinstance(draft.get("sender_profile"), dict)
        or not draft["sender_profile"]
        or _default_profile(draft)
    ):
        return text
    return (
        "This voluntary advisory shares reported cybersecurity concerns with your organization. "
        "We recommend prompt review with the person or company responsible for the technology "
        "identified in this notice."
    )


def responsibility(text, draft):
    if not isinstance(draft.get("sender_profile"), dict) or not draft["sender_profile"]:
        return text
    agency = _text(draft["sender_profile"], "agency").strip() or "reporting organization"
    if agency.casefold() == DEFAULT_AGENCY.casefold():
        return text
    return (
        "This notification does not authorize its sender to access or modify your systems. "
        "Remediation decisions and actions remain the responsibility of your organization. "
        "This notification is provided for informational purposes only and does not constitute "
        "a requirement or mandate for remediation."
    )


def apply_identity_copy(draft, *, narrative=True):
    if not draft.get("sender_profile"):
        return draft
    for field in ("intro", "narrative") if narrative else ("intro",):
        draft[field] = identity_copy(draft.get(field, ""), draft)
    if not narrative:
        return draft
    # Human-readable labels are taken only from the pinned reviewed snippet bank.
    # Technical/source records retain their original tags unchanged.
    text = draft.get("narrative", "")
    for snippet in draft.get("finding_explainer_snapshots", []):
        title = snippet.get("title")
        if not title or snippet.get("category") != "lifecycle":
            continue
        for rule in snippet.get("match_rules", []):
            for tag in rule.get("tags", []):
                if not tag.startswith("eol-"):
                    continue
                text = re.sub(
                    r"(?<![\w-])" + re.escape(tag) + r"(?![\w-])", lambda _: title, text, flags=re.I
                )
    if not re.search(r"CVE-\d{4}-\d{4,}", text, re.I):
        text = text.replace("The identified vulnerability is ", "The reported condition is ")
        text = text.replace("The identified vulnerabilities are ", "The reported conditions are ")
    draft["narrative"] = text
    return draft


def pin_submitted(data, prior):
    profile = prior.get("sender_profile")
    submitted = data.get("sender_profile")
    if submitted and submitted != profile:
        raise ValueError(
            "Sender identity is read-only. Adopt the current report format to update it."
        )
    if profile:
        data["sender_profile"] = deepcopy(profile)
    else:
        data.pop("sender_profile", None)


def approved_copy(draft):
    from modules.investigations.components import approved_template as approved

    return {
        "attribution": approved.ATTRIBUTION,
        "security_intro": security_intro(approved.SECURITY_INTRO, draft),
        "fraud_intro": approved.FRAUD_INTRO,
        "fraud_risks": approved.FRAUD_RISKS,
        "fraud_stats_intro": approved.FRAUD_STATS_INTRO,
        "fraud_stats": approved.FRAUD_STATS,
        "responsibility": responsibility(approved.RESPONSIBILITY, draft),
    }
