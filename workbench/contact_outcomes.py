"""Read-only contact usability derived from published evidence and outreach history.

Publication, analyst suitability, and actual delivery are independent facts.  Existing
immutable contact review rows also hold explicit route decisions, so refresh and merge
cannot discard them and no historical report is rewritten.
"""

from datetime import datetime, timezone
import json
import re
from urllib.parse import urlsplit

from .contact_discovery.extract import fax_number, restricted_mailbox

ROUTINE_PURPOSES = {"security", "it", "product_support", "management", "general", "other"}
PURPOSE_ORDER = {
    "security": 0,
    "it": 1,
    "product_support": 2,
    "management": 3,
    "general": 4,
    "other": 5,
    "privacy": 6,
    "hr": 7,
    "media": 8,
    "investor": 9,
    "compliance": 10,
    "physical_emergency": 11,
}


def route_key(kind, value):
    value = (value or "").strip()
    if kind == "email":
        return kind, value.removeprefix("mailto:").casefold()
    if kind == "phone":
        value = re.sub(r"\b(?:ext\.?|extension)\s*", "x", value.casefold())
        value = re.sub(r"[^\dx]", "", value)
        # Equivalent ordinary North American number formatting; extensions stay distinct.
        number, separator, extension = value.partition("x")
        if len(number) == 11 and number.startswith("1"):
            number = number[1:]
        return kind, number + (separator + extension if separator else "")
    return kind, value


def _stamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except ValueError, AttributeError:
        return datetime.min.replace(tzinfo=timezone.utc)


def _route_status(kind, value, attempts, reviews):
    key = route_key(kind, value)
    matching = [
        a
        for a in attempts
        if a["destination"].strip() and route_key(a["channel"], a["destination"]) == key
    ]
    success = [a for a in matching if a["outcome"] in ("delivered", "acknowledged")]
    events = [
        (
            _stamp(a["occurred_at"]),
            _stamp(a["recorded_at"]),
            a["outcome"] != "bounced",
            a["outcome"],
            a["id"],
            a["occurred_at"],
        )
        for a in matching
        if a["outcome"] in ("bounced", "delivered", "acknowledged")
    ]
    for review in reviews:
        if review["action"] in ("route_unusable", "route_restored"):
            detail = json.loads(review["detail"])
            events.append(
                (
                    _stamp(review["created_at"]),
                    _stamp(review["created_at"]),
                    review["action"] == "route_restored",
                    detail.get("reason", ""),
                    review["id"],
                    review["created_at"],
                )
            )
    latest = max(events, default=None, key=lambda event: event[:2])
    successful = max(success, default=None, key=lambda item: _stamp(item["occurred_at"]))
    return {
        "unusable": bool(latest and not latest[2]),
        "usability": "unusable" if latest and not latest[2] else "available",
        "usability_reason": latest[3] if latest else "No adverse delivery outcome recorded",
        "usability_evidence_id": latest[4] if latest else None,
        "usability_updated_at": latest[5] if latest else None,
        "last_successful_use": successful["occurred_at"] if successful else None,
        "last_successful_case_id": successful["case_id"] if successful else None,
        "attempt_count": len(matching),
    }


def contact_summary(store, entity_id, db=None):
    """Return saved readiness facts without fetching or re-verifying website bytes."""
    if db is None:
        with store.read_snapshot() as db:
            return contact_summary(store, entity_id, db)
    entity_id = store.entities.resolve_entity(entity_id, db)
    return contact_summaries(store, [entity_id], db=db)[entity_id]


def contact_summaries(store, entity_ids, *, db=None):
    """Bulk current-owner contact readiness; six queries per bounded ID batch.

    Callers supply canonical entity IDs from cases/entities, not unresolved aliases.
    All routes use the exact same pure usability projection as the single view.
    """
    if db is None:
        with store.read_snapshot() as db:
            return contact_summaries(store, entity_ids, db=db)
    identities = list(dict.fromkeys(entity_ids))
    result = {}
    for start in range(0, len(identities), 400):
        batch = identities[start : start + 400]
        marks = ",".join("?" for _ in batch)
        facts = {
            identity: {
                "candidates": [],
                "attempts": [],
                "reviews": [],
                "latest_sources": {},
                "profile": {},
                "plans": [],
            }
            for identity in batch
        }
        for row in db.execute(
            f"SELECT * FROM contact_candidates WHERE entity_id IN ({marks})", batch
        ):
            facts[row["entity_id"]]["candidates"].append(dict(row))
        for row in db.execute(
            f"SELECT a.*,c.entity_id owner_entity_id FROM contact_attempts a JOIN cases c ON c.id=a.case_id WHERE c.entity_id IN ({marks})",
            batch,
        ):
            facts[row["owner_entity_id"]]["attempts"].append(dict(row))
        for row in db.execute(
            f"SELECT r.*,c.entity_id owner_entity_id FROM contact_reviews r JOIN contact_candidates c ON c.id=r.candidate_id WHERE c.entity_id IN ({marks}) ORDER BY r.rowid",
            batch,
        ):
            facts[row["owner_entity_id"]]["reviews"].append(dict(row))
        for row in db.execute(
            f"SELECT s.candidate_id,s.payload,c.entity_id FROM contact_sources s JOIN contact_candidates c ON c.id=s.candidate_id AND c.latest_run_id=s.run_id WHERE c.entity_id IN ({marks})",
            batch,
        ):
            facts[row["entity_id"]]["latest_sources"][row["candidate_id"]] = json.loads(
                row["payload"]
            )
        for row in db.execute(
            f"SELECT entity_id,payload FROM entity_profiles WHERE entity_id IN ({marks})", batch
        ):
            facts[row["entity_id"]]["profile"] = json.loads(row["payload"])
        for row in db.execute(
            f"SELECT id,entity_id,contact_name,contact_role,contact_email,contact_phone FROM cases WHERE entity_id IN ({marks})",
            batch,
        ):
            facts[row["entity_id"]]["plans"].append(dict(row))
        for identity, values in facts.items():
            result[identity] = _contact_summary(identity, **values)
    return result


def _contact_summary(entity_id, candidates, attempts, reviews, latest_sources, profile, plans):
    preference = next((r for r in reversed(reviews) if r["action"] == "route_preferred"), None)
    preferred_id = preference["candidate_id"] if preference else None
    statuses, routes, known = {}, [], {}
    for row in candidates:
        payload = json.loads(row["payload"])
        # All decisions about the same destination apply across attributed roots.
        key = route_key(payload["kind"], payload["value"])
        related_ids = {
            other["id"]
            for other in candidates
            if route_key(
                json.loads(other["payload"])["kind"], json.loads(other["payload"])["value"]
            )
            == key
        }
        status = _route_status(
            payload["kind"],
            payload["value"],
            attempts,
            [r for r in reviews if r["candidate_id"] in related_ids],
        )
        current = not row["missing_from_latest"] and not payload.get("source_changed")
        fax = payload["kind"] == "phone" and any(
            fax_number(payload["value"], source.get("excerpt", ""))
            for source in latest_sources.get(row["id"], [])
        )
        recruiting = payload["kind"] == "email" and restricted_mailbox(payload["value"])
        status.update(
            usable=not status["unusable"]
            and not fax
            and row["decision"] != "ignored"
            and payload["kind"] in ("email", "phone", "form")
            and payload.get("purpose") != "physical_emergency",
            can_adopt=not status["unusable"]
            and not fax
            and row["decision"] != "ignored"
            and payload["kind"] in ("email", "phone", "person")
            and payload.get("purpose") != "physical_emergency",
            routine_suggestion=payload.get("purpose", "other") in ROUTINE_PURPOSES
            and not fax
            and not recruiting
            and payload.get("recommended_for_outreach") is not False
            and not payload.get("purpose_conflict"),
            reviewed_at=row.get("reviewed_at"),
            reviewed_by=row.get("reviewed_by"),
            publication_current=current,
            preferred=row["id"] == preferred_id,
        )
        # Interpret legacy discoveries without changing their saved evidence or
        # decisions. A retained fax is not a voice route; recruiting is explicit.
        if fax:
            status.update(fax=True, routing_label="Fax number · retained source")
        if recruiting:
            status.update(purpose="hr", routing_label="Recruiting / employment address")
        statuses[row["id"]] = status
        known.setdefault(key, []).append((row, payload, status))
        routes.append(
            {
                "candidate_id": row["id"],
                "kind": payload["kind"],
                "value": payload["value"],
                "purpose": payload.get("purpose", "other"),
                "source": "published",
                **status,
            }
        )
    manual = {
        route_key(kind, profile.get("contact_" + kind)): {
            "value": profile.get("contact_" + kind, ""),
            "name": profile.get("contact_name", ""),
            "role": profile.get("contact_title", ""),
        }
        for kind in ("email", "phone")
    }
    if profile.get("contact_name", "").strip() and not any(
        profile.get("contact_" + kind, "").strip() for kind in ("email", "phone")
    ):
        manual[route_key("person", profile["contact_name"])] = {
            "value": profile["contact_name"],
            "name": profile["contact_name"],
            "role": profile.get("contact_title", ""),
        }
    for plan in plans:
        for kind in ("email", "phone"):
            value = plan["contact_" + kind]
            manual.setdefault(
                route_key(kind, value),
                {
                    "value": value,
                    "name": plan["contact_name"],
                    "role": plan["contact_role"],
                },
            )
        if plan["contact_name"].strip() and not any(
            plan["contact_" + kind].strip() for kind in ("email", "phone")
        ):
            manual.setdefault(
                route_key("person", plan["contact_name"]),
                {
                    "value": plan["contact_name"],
                    "name": plan["contact_name"],
                    "role": plan["contact_role"],
                },
            )
    for key, details in manual.items():
        value = details["value"]
        if not value or not value.strip():
            continue
        associated = known.get(key, [])
        status = _route_status(
            key[0],
            value,
            attempts,
            [r for r in reviews if any(row["id"] == r["candidate_id"] for row, _, _ in associated)],
        )
        # A manual plan remains intact. It cannot silently bypass a known adverse
        # result or a later evidence-change/ignore decision for that exact route.
        evidence_warning = any(
            item[0]["decision"] == "ignored"
            or item[1].get("purpose") == "physical_emergency"
            or item[2].get("fax")
            for item in associated
        )
        routes.append(
            {
                "candidate_id": None,
                "kind": key[0],
                "value": value,
                "name": details["name"],
                "role": details["role"],
                "source": "manual",
                "preferred": False,
                **status,
                "usable": key[0] in ("email", "phone")
                and not status["unusable"]
                and not evidence_warning,
                "publication_current": not evidence_warning,
            }
        )
    warnings = list(
        dict.fromkeys(
            f"{route['value']}: {route['usability_reason'] if route['unusable'] else 'Not present in the most recent source'}"
            for route in routes
            if route["unusable"] or not route["publication_current"]
        )
    )
    return {
        "entity_id": entity_id,
        "has_usable_contact": any(r["usable"] for r in routes),
        "candidate_status": statuses,
        "routes": routes,
        "warnings": warnings,
        "preferred_candidate_id": preferred_id,
    }


def verification_route(settings):
    """Only an explicitly configured public route is used in the introduction."""
    return (settings.get("outreach_verification_route") or "").strip()


def validate_verification_route(value):
    if len(value) > 1000 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Use a single public verification URL or office telephone line")
    value = value.strip()
    if value.startswith(("http:", "https:")):
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Use a public HTTPS verification URL without credentials")
    return value


def directory_contact(store, entity_id, db=None):
    """Compact current contact facts; never reads captured pages or starts a lookup."""
    if db is None:
        with store.read_snapshot() as db:
            return directory_contact(store, entity_id, db)
    summary = contact_summary(store, entity_id, db)
    routes = [
        r
        for r in summary["routes"]
        if r["usable"]
        and r["publication_current"]
        and (r.get("routine_suggestion", True) or r.get("preferred"))
    ]
    routes.sort(
        key=lambda r: (
            not r.get("preferred", False),
            r.get("source") != "manual",
            PURPOSE_ORDER.get(r.get("purpose"), 99),
        )
    )
    chosen = {
        kind: next((r for r in routes if r["kind"] == kind), None)
        for kind in ("email", "phone", "form")
    }
    run = db.execute(
        "SELECT status,finished_at FROM contact_runs WHERE entity_id=? ORDER BY rowid DESC LIMIT 1",
        (entity_id,),
    ).fetchone()
    queued = db.execute(
        "SELECT status FROM entity_contact_queue WHERE entity_id=?", (entity_id,)
    ).fetchone()
    profile = db.execute(
        "SELECT payload FROM entity_profiles WHERE entity_id=?", (entity_id,)
    ).fetchone()
    profile = json.loads(profile[0]) if profile else {}
    return {
        "name": profile.get("contact_name")
        or next((r.get("name") for r in routes if r.get("name")), ""),
        "role": profile.get("contact_title", ""),
        **{kind: (route["value"] if route else "") for kind, route in chosen.items()},
        "sources": {kind: route.get("source") for kind, route in chosen.items() if route},
        "status": "found" if any(chosen.values()) else run["status"] if run else "not_checked",
        "checked_at": run["finished_at"] if run else None,
        "queue_status": queued["status"] if queued else None,
    }


def complete_entity_details(store, entity, summary, profile, db=None):
    """Enough information for entity lookup/contact, without claiming verification."""
    name = str(entity.get("company") or "").strip().casefold()
    root = str(entity["domain"]).casefold()
    if (
        not name
        or name == root
        or name.endswith("." + root)
        or not profile.get("address", "").strip()
    ):
        return summary
    contact = directory_contact(store, entity["id"], db)
    if contact["email"] or contact["phone"]:
        return {**summary, "required": False, "complete": True}
    return summary
