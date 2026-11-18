"""Conservative geography hints for account-authorized subscriptions.

reports/subscribed returns names, not a geographic entitlement schema. Recognize
only whole geographic names and explicit prefixes, never state substrings inside
an organization name. National/custom subscriptions remain available with a
visible note. Accretion still filters each observation by configured region.
"""

import re
from .entity_validation import STATE_NAMES
from .shadowserver_reports.errors import ConfigurationError


def _token(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value).strip().casefold()).strip("-")


_STATE_ALIASES = {
    alias: code for code, name in STATE_NAMES.items() for alias in (_token(code), _token(name))
}
_STATE_ALIASES.update(
    {
        "gu": "GU",
        "guam": "GU",
        "vi": "VI",
        "us-virgin-islands": "VI",
        "u-s-virgin-islands": "VI",
        "virgin-islands": "VI",
        "as": "AS",
        "american-samoa": "AS",
        "mp": "MP",
        "northern-mariana-islands": "MP",
    }
)
_NATIONAL = {"us", "usa", "united-states", "united-states-of-america", "us-national", "national-us"}
_PREFIXES = ("united-states-", "usa-", "us-", "state-", "region-", "geo-")


def state_scope(name):
    """Recognize explicit whole-name selectors, never arbitrary name substrings."""
    token = _token(name)
    if token in _STATE_ALIASES:
        return _STATE_ALIASES[token]
    for _ in range(2):
        prefix = next((p for p in _PREFIXES if token.startswith(p)), None)
        if prefix is None:
            break
        token = token[len(prefix) :]
        if token in _STATE_ALIASES:
            return _STATE_ALIASES[token]
    return None


def jurisdiction(regions):
    values = [str(region).strip() for region in regions if str(region).strip()]
    return {
        "regions": list(dict.fromkeys(values)),
        "states": {code for value in values if (code := state_scope(value))},
        "names": {_token(value) for value in values},
    }


def classify(subscription, scope):
    token = _token(subscription)
    state = state_scope(subscription)
    if state:
        return "matched" if state in scope["states"] else "outside"
    if token in scope["names"]:
        return "matched"
    if token in _NATIONAL:
        return "national"
    return "unclassified"


def require_subscription(subscription, regions):
    if classify(subscription, jurisdiction(regions)) == "outside":
        raise ConfigurationError(
            "This report subscription is outside your configured jurisdiction. "
            "Select an available subscription or update Jurisdiction in Settings."
        )


def available_subscriptions(subscriptions, regions):
    scope = jurisdiction(regions)
    groups = {name: [] for name in ("matched", "national", "unclassified", "outside")}
    available = []
    for name in dict.fromkeys(subscriptions):
        kind = classify(name, scope)
        groups[kind].append(name)
        if kind != "outside":
            available.append(name)
    notice = "Report choices follow your configured jurisdiction."
    if groups["outside"]:
        count = len(groups["outside"])
        notice += f" {count} other-state subscription{'s' if count != 1 else ''} hidden."
    if groups["national"] or groups["unclassified"]:
        notice += (
            " National or organization-specific subscriptions may cover more than these regions; "
            "individual observations still pass the jurisdiction filter."
        )
    return available, {
        "regions": scope["regions"],
        "hidden_subscriptions": len(groups["outside"]),
        "unclassified_subscriptions": groups["unclassified"],
        "matched_subscriptions": groups["matched"],
        "national_subscriptions": groups["national"],
        "notice": notice,
    }
