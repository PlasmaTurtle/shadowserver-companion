"""Shared reference freshness and risk-schema rules; no storage or transport setup."""

from datetime import datetime, timezone

SCHEMA_VERSION = 1


class UnsupportedRiskSchema(ValueError):
    pass


def date(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (
        parsed.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None
        else parsed.astimezone(timezone.utc)
    )


def check_schema(db, *, attached=False):
    version = db.execute(
        "PRAGMA risk.user_version" if attached else "PRAGMA user_version"
    ).fetchone()[0]
    if version not in (0, SCHEMA_VERSION):
        raise UnsupportedRiskSchema("Risk catalog was created by a newer application")


def freshness(provider, state, current):
    checked = state.get("last_success_at")
    score_age = None
    try:
        if provider == "epss" and state.get("score_date"):
            score_age = (
                current.date() - datetime.strptime(state["score_date"], "%Y-%m-%d").date()
            ).days
        stale = (
            not checked
            or (current - date(checked)).total_seconds() > 172800
            or score_age is not None
            and score_age > 2
        )
    except (ValueError, TypeError, AttributeError):
        stale = True
    return {"score_age_days": score_age, "stale": bool(stale)}
