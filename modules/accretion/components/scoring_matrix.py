"""Scoring matrix: bounded weights, base values and explainable report rules.

This owner defines policy only; it performs no evidence reads or workflow work.
"""

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
import math
import re

POLICY_VERSION = 1


TEMPERATURES = ("cool", "warm", "hot", "blazing")


_DEFAULT_POLICY = {
    "version": POLICY_VERSION,
    "quality_weights": {"data": 40, "finding": 40, "entity": 20},
    "urgency_weights": {"severity": 40, "kev": 35, "epss": 15, "priority": 10},
    "aggregate_weights": {"quality": 50, "urgency": 50},
    "temperature_thresholds": [40, 60, 80],
    "priority_cities": [],
    "priority_products": [],
    "provider_outreach_multiplier": 0.1,
    "report_bases": {
        "compromise_indicator": {
            "value": 0.25,
            "reason": "Reported compromise; modest report-type priority, not a CVSS assessment",
        },
    },
}


SEVERITY = {
    "critical": 9.5,
    "high": 8.0,
    "medium": 5.5,
    "low": 2.0,
    "info": 0.0,
    "informational": 0.0,
    "none": 0.0,
}


def policy_defaults():
    """Return an independent copy; weights are provisional, not scientific truth."""
    return deepcopy(_DEFAULT_POLICY)


def is_score_number(value, maximum):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= maximum
    )


def normalize_policy(overrides=None):
    policy = policy_defaults()
    if overrides is None:
        return policy
    if not isinstance(overrides, Mapping) or set(overrides) - set(policy):
        raise ValueError("Unknown Accretion policy setting")
    for key, value in overrides.items():
        if key == "report_bases":
            if not isinstance(value, Mapping):
                raise ValueError("Report bases require named matrix entries")
            policy[key].update(deepcopy(value))
        elif key.endswith("_weights"):
            if not isinstance(value, Mapping) or set(value) - set(policy[key]):
                raise ValueError("Unknown Accretion weight")
            policy[key].update(value)
        else:
            policy[key] = deepcopy(value)
    if type(policy["version"]) is not int or policy["version"] != POLICY_VERSION:
        raise ValueError("Unsupported Accretion policy version")
    for key in ("quality_weights", "urgency_weights", "aggregate_weights"):
        values = list(policy[key].values())
        if not all(is_score_number(v, 100) for v in values) or abs(sum(values) - 100) > 1e-8:
            raise ValueError("Accretion weights must be between 0 and 100 and total 100")
    thresholds = policy["temperature_thresholds"]
    if (
        not isinstance(thresholds, (list, tuple))
        or len(thresholds) != 3
        or not all(is_score_number(v, 100) for v in thresholds)
        or not 0 < thresholds[0] < thresholds[1] < thresholds[2] < 100
    ):
        raise ValueError("Accretion requires three increasing temperature thresholds")
    policy["temperature_thresholds"] = list(thresholds)
    if not is_score_number(policy["provider_outreach_multiplier"], 1):
        raise ValueError("Provider outreach multiplier must be between 0 and 1")
    for name, rule in policy["report_bases"].items():
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z][a-z0-9_]{0,99}", name)
            or not isinstance(rule, Mapping)
            or set(rule) != {"value", "reason"}
            or not is_score_number(rule["value"], 1)
            or not isinstance(rule["reason"], str)
            or not rule["reason"].strip()
            or len(rule["reason"]) > 1000
        ):
            raise ValueError("Report bases require a profile/kind, value from 0 to 1 and reason")
    for key in ("priority_cities", "priority_products"):
        values = policy[key]
        if (
            not isinstance(values, list)
            or len(values) > 100
            or any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in values)
        ):
            raise ValueError("Accretion priorities require at most 100 nonempty names")
        policy[key] = sorted({v.strip().casefold() for v in values})
    return policy


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def policy_hash(policy=None):
    return hashlib.sha256(canonical_json(normalize_policy(policy)).encode()).hexdigest()


def report_base(profile, policy):
    """Match an eligible profile ID first, then its observation kind.

    Entries share the severity weight as independent candidates, never stack
    onto another finding, and remain part of the captured policy/hash.
    """
    if profile.get("capability") != "eligible":
        return None
    for key in (profile.get("id"), profile.get("observation_kind")):
        if key in policy["report_bases"]:
            return {"id": profile.get("id") or key, **policy["report_bases"][key]}
    return None


def factor(identifier, label, value, weight, reason):
    """Retain the exact matrix contribution and its explanation."""
    return {
        "id": identifier,
        "label": label,
        "value": round(value, 6),
        "weight": weight,
        "points": round(value * weight, 3),
        "reason": reason,
    }
