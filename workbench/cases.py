"""Case ownership, scoped observations and notification workflow transitions."""

from __future__ import annotations

import json
from .primitives import now, uid
from .content_bank import snapshot_blocks
from .repositories.cases import CaseRepository

STAGES = {
    "in_progress": "Work in progress",
    "pending_notification": "Pending notification",
    "notification_completed": "Notification completed",
    "closed": "Closing report completed",
}


class Cases:
    def __init__(self, store):
        self.store = store
        self.repository = CaseRepository(store)

    def default_id(self, entity_id, db=None):
        return self.repository.default_id(entity_id, db)

    def require(self, db, case_id, expected_version=None, editable=False):
        row = self.repository.get(db, case_id)
        if not row:
            raise ValueError("Notification case not found")
        if expected_version is not None and row["version"] != expected_version:
            raise ValueError("This case changed. Reload before saving.")
        if editable and row["stage"] != "in_progress":
            raise ValueError(
                "Revise the certified report before changing its content. Delivered or closed cases require a new notification."
            )
        return row

    def create(self, entity_id, title=""):
        entity_id = self.store.resolve_entity(entity_id)
        with self.store.transaction() as db:
            if self.repository.open_for_entity(db, entity_id):
                raise ValueError(
                    "This business already has an open notification. Use its existing case."
                )
            case_id = self._create(db, entity_id, title)
        return self.view(case_id)

    def _create(self, db, entity_id, title="", *, entry_ids=None, intake_lead_id=None):
        entity = self.repository.entities.active(db, entity_id)
        if not entity:
            raise ValueError("Business entity not found")
        case_id, stamp = uid(), now()
        # Prefer observations not yet assigned to a notification; include the
        # group's supporting attribution entry even if a prior case used it.
        rows = self.repository.creation_entries(db, entity_id)
        if entry_ids is not None:
            selected = set(entry_ids)
            rows = [r for r in rows if r["id"] in selected]
            if {r["id"] for r in rows} != selected:
                raise ValueError("Selected observations changed or belong to another entity")
        if not rows:
            raise ValueError("A case needs qualified observations")
        draft = {
            "cve_records": json.loads(entity["draft"]).get("cve_records", []),
            "explainer_snapshots": snapshot_blocks(db),
        }
        from .presentation import document_policy
        from .report_layouts import CURRENT_REVISIONS
        from .sender_identity import capture_profile

        draft["document_policy"] = document_policy(self.store.settings())
        draft["sender_profile"] = capture_profile(self.store.settings())
        draft.update(CURRENT_REVISIONS)
        from .notification_narrative_v5 import report_started_date

        draft["report_date"] = report_started_date({"case": {"created_at": stamp}}, {}).isoformat()
        self.repository.create_scope(
            db,
            case_id,
            entity_id,
            title.strip()
            or f"Notification · {entity['company'] or entity['domain']} · {stamp[:10]}",
            stamp,
            draft,
            rows,
            intake_lead_id=intake_lead_id,
        )
        profile = self.repository.entities.profile(db, entity_id)
        self.repository.pin_entity(db, case_id, dict(entity), profile)
        # A new case must not silently bypass a prior reasoned outreach hold.
        held_from = self.repository.inherit_outreach_hold(db, entity_id, case_id)
        if held_from:
            self.store.log(
                db,
                "outreach_hold_inherited",
                "Retained outreach hold from notification " + held_from,
                entity_id,
                case_id,
            )
        # Entity-level caches may contain findings from older notifications.
        # Only carry source records for observations actually assigned here.
        from .intelligence.identifiers import identifiers

        tags = self.repository.reported_tags(db, case_id)
        reported = set(identifiers(tags))
        from .intelligence.local import initial_records

        draft["cve_records"] = initial_records(self.store, reported, draft["cve_records"], db)
        self.repository.set_initial_draft(db, case_id, draft)
        self.store.log(db, "case_opened", "Opened notification case", entity_id, case_id)
        return case_id

    def adopt_entity_details(self, case_id, expected_version, **options):
        from .entity_adoption import adopt

        return adopt(self, case_id, expected_version, **options)

    def absorb(self, db, entity_id, group, entry_ids, records):
        case = self.repository.open_for_group(db, entity_id, group.hostname)
        if not case:
            if not self.repository.has_cases(db, entity_id):
                return self._create(db, entity_id)
            # Later observations remain available to start another case.
            return None
        if case["stage"] == "pending_notification":
            # The certified case is an immutable scope. Later observations stay
            # on the entity for an explicit revision or a new notification.
            return None
        added = self.repository.extend_scope(db, case["id"], group.hostname, entry_ids)
        if not added:
            return case["id"]
        draft = json.loads(case["draft"])
        draft.update(reviewed=False, cve_reviewed=False)
        cves = {r["id"]: r for r in draft.get("cve_records", [])}
        # New observations may add references, but never silently replace a selected source revision.
        for record in records or []:
            cves.setdefault(record["id"], record)
        draft["cve_records"] = list(cves.values())
        self.repository.replace_working_draft(db, case["id"], draft)
        self.store.log(
            db,
            "case_observations",
            f"{added} new observations attached; report requires review",
            entity_id,
            case["id"],
        )
        return case["id"]

    def combine_unworked(self, db, entity_id, preferred_case_id):
        """Absorb pristine intake placeholders; keep cases with analyst work intact."""
        rows = self.repository.open_for_entity(db, entity_id)
        if len(rows) < 2:
            return

        def pristine(case):
            return case["version"] == case["draft_revision"] == 0 and not self.repository.has_work(
                db, case["id"]
            )

        untouched = [c for c in rows if pristine(c)]
        worked = [c for c in rows if c not in untouched]
        # Several distinct histories require an explicit analyst choice; leave
        # them separate rather than guessing which notification should gain rows.
        if not untouched or len(worked) > 1:
            return
        target = (
            worked[0]
            if worked
            else next((c for c in rows if c["id"] == preferred_case_id), rows[0])
        )
        if target["stage"] != "in_progress":
            return
        draft = json.loads(target["draft"])
        records = {r["id"]: r for r in draft.get("cve_records", [])}
        for source in untouched:
            if source["id"] == target["id"]:
                continue
            self.repository.combine_scope(db, target["id"], source["id"])
            for record in json.loads(source["draft"]).get("cve_records", []):
                records.setdefault(record["id"], record)
            self.store.log(
                db,
                "lead_group_combined",
                "Combined untouched lead group from " + source["title"],
                entity_id,
                target["id"],
            )
        draft.update(reviewed=False, cve_reviewed=False, cve_records=list(records.values()))
        self.repository.replace_working_draft(db, target["id"], draft)

    def view(self, case_id):
        return self.repository.view(case_id)

    def revise(self, case_id, version, reason):
        if not reason.strip():
            raise ValueError("A reason is required to revise a certified report")
        actor = self.store.settings().get("analyst_name", "").strip()
        if not actor:
            raise ValueError("Set the analyst name in Settings before revising a report")
        with self.store.transaction() as db:
            case = self.require(db, case_id, version)
            if case["stage"] != "pending_notification":
                raise ValueError(
                    "Only an undelivered certified report can be revised. Start a new notification for delivered work."
                )
            draft = json.loads(case["draft"])
            draft["reviewed"] = False
            self.repository.replace_working_draft(db, case_id, draft)
            from .repositories.reviews import SectionReviewRepository

            SectionReviewRepository(self.store).event(
                db, case_id, "", "report_reopened", actor, reason.strip(), case["draft_revision"]
            )
            self.store.log(
                db,
                "case_revised",
                f"Opened a new report revision by {actor}; previous package retained. Reason: {reason.strip()}",
                case["entity_id"],
                case_id,
            )
        return self.view(case_id)

    def plan(self, case_id, values):
        with self.store.transaction() as db:
            case = self.require(db, case_id, values["expected_version"])
            if case["stage"] == "closed":
                raise ValueError("Closed cases cannot be edited")
            self.repository.save_plan(db, case_id, values)
            self.store.log(
                db,
                "follow_up_updated",
                "Updated contact details and next action",
                case["entity_id"],
                case_id,
            )
        return self.view(case_id)

    def attempt(self, case_id, values):
        with self.store.transaction() as db:
            case = self.require(db, case_id, values["expected_version"])
            if case["stage"] == "closed":
                raise ValueError("Closed cases cannot receive new activity")
            report_id = values.get("report_id")
            report = self.repository.report(db, case_id, report_id)
            if report_id and not report:
                raise ValueError("The report revision does not belong to this case")
            success = values["outcome"] in ("delivered", "acknowledged")
            if success:
                if (
                    not values["recipient"].strip()
                    or not report
                    or report_id != case["certified_report_id"]
                    or case["stage"] == "in_progress"
                ):
                    raise ValueError(
                        "Successful delivery requires a recipient and the current certified report revision"
                    )
                if not self.store.package_available(dict(report)):
                    raise ValueError(
                        "Restore the certified report package before recording successful delivery"
                    )
            self.repository.record_contact(db, case_id, report_id, values, success)
            self.store.log(
                db,
                "contact_attempt",
                f"{values['outcome'].replace('_', ' ')} · {values['channel']} · {values['recipient']}",
                case["entity_id"],
                case_id,
            )
        return self.view(case_id)
