"""Preview and atomically adopt current business identity into a working case.

The plan contains both revisions the analyst reviewed. Reopening a validation
and repinning identity happen in the same transaction; historical snapshots
remain append-only.
"""

import json

from .primitives import dump
from .repositories.cases import CaseRepository
from .repositories.reviews import SectionReviewRepository
from .reviews.policy import SECTIONS


def _changes(case, entity, profile):
    prior = json.loads(case["entity_snapshot"] or "{}")
    draft = json.loads(case["draft"])
    previous_profile = prior.get("entity_profile", {})
    fields = [
        (
            "company",
            "Business name",
            draft.get("company", prior.get("company", "")),
            entity["company"],
        ),
        ("domain", "Root domain", prior.get("domain", ""), entity["domain"]),
        (
            "address",
            "Mailing address",
            draft.get("address", previous_profile.get("address", "")),
            profile.get("address", ""),
        ),
        ("city", "City", previous_profile.get("city", ""), profile.get("city", "")),
        ("state", "State", previous_profile.get("state", ""), profile.get("state", "")),
    ]
    changes = [
        {"key": key, "label": label, "before": before or "", "after": after or ""}
        for key, label, before, after in fields
        if (before or "") != (after or "")
    ]
    affected = set()
    keys = {item["key"] for item in changes}
    if "company" in keys:
        affected.update({"introduction", "vulnerabilities", "attribution"})
    if "address" in keys:
        affected.update({"introduction", "attribution"})
    if keys & {"city", "state"}:
        affected.add("vulnerabilities")
    if "domain" in keys:
        affected.update(SECTIONS)
    return changes, affected


def _plan(store, db, case):
    repository = CaseRepository(store)
    entity = repository.entities.active(db, case["entity_id"])
    if not entity:
        raise ValueError("Business entity not found")
    profile = repository.entities.profile(db, case["entity_id"])
    changes, affected = _changes(case, entity, profile)
    active = SectionReviewRepository(store).active(case["id"], db)
    plan = {
        "case_id": case["id"],
        "expected_version": case["version"],
        "expected_entity_revision": entity["draft_revision"],
        "changed": bool(changes),
        "changes": changes,
        "affected_sections": [key for key in SECTIONS if key in affected],
        "reopen_sections": [key for key in SECTIONS if key in affected and key in active],
    }
    return plan, entity, profile, active


def adoption_plan(cases, case_id):
    with cases.store.read_snapshot() as db:
        case = cases.require(db, case_id, editable=True)
        return _plan(cases.store, db, case)[0]


def adopt(
    cases,
    case_id,
    expected_version,
    *,
    expected_entity_revision=None,
    reopen_affected=False,
    reason="",
):
    store = cases.store
    with store.transaction() as db:
        case = cases.require(db, case_id, expected_version, editable=True)
        plan, entity, profile, active = _plan(store, db, case)
        if (
            expected_entity_revision is not None
            and entity["draft_revision"] != expected_entity_revision
        ):
            raise ValueError(
                "Entity details changed. Review the updated adoption plan before saving."
            )
        if reopen_affected and expected_entity_revision is None:
            raise ValueError(
                "Review the current entity details before reopening affected sections."
            )
        locked = plan["reopen_sections"]
        if locked and not reopen_affected:
            raise ValueError(
                "Reopen "
                + ", ".join(SECTIONS[key] for key in locked)
                + " before adopting changed entity details"
            )
        if locked:
            if not reason.strip():
                raise ValueError("A reason is required to reopen affected sections")
            actor = store.settings(db=db).get("analyst_name", "").strip()
            if not actor:
                raise ValueError("Set the analyst name in Settings before reopening a section")
            reviews = SectionReviewRepository(store)
            for key in locked:
                reviews.event(
                    db,
                    case_id,
                    key,
                    "reopened",
                    actor,
                    "Entity details adoption: " + reason.strip(),
                    active[key]["revision"],
                )
        if plan["changed"]:
            cases.repository.pin_entity(db, case_id, dict(entity), profile)
            draft = json.loads(case["draft"])
            draft.update(
                company=entity["company"], address=profile.get("address", ""), reviewed=False
            )
            cases.repository.replace_working_draft(db, case_id, draft)
            store.log(
                db,
                "entity_details_adopted",
                dump(
                    {
                        "changes": plan["changes"],
                        "reopened_sections": locked,
                        "reason": reason.strip(),
                    }
                ),
                case["entity_id"],
                case_id,
            )
    return cases.view(case_id)
