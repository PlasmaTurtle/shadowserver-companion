"""Lock reviewed content without rendering; recheck dependencies at atomic commit."""

from ..cases import Cases
from ..report_snapshot import snapshot
from ..report_operations import check_deadline, publication, phase
from ..attribution_display import attribution_summaries
from ..reviews.queries import SectionReviewQueries
from ..reviews.policy import check_key, check_revision, fingerprints


class SectionReviewService:
    def __init__(self, store, reviews=None):
        self.store = store
        self.reviews = reviews or SectionReviewQueries(store)
        self.repository = self.reviews.repository

    def validate(self, case_id, key, expected_revision):
        check_key(key)

        # Assemble content outside the writer lock. No page layout, artwork,
        # renderer process, or network request belongs in a section freeze.
        with self.store.read_snapshot() as db:
            case = Cases(self.store).require(db, case_id, editable=True)
            check_revision(case, expected_revision)
            self._assert_open(case_id, key, db)
        lead = self._lead(case_id)
        data = snapshot(
            self.store,
            case["entity_id"],
            case_id,
            include_reviews=False,
            capture_sections=(),
        )
        self._assert_ready(data, lead, key)
        phase("Rechecking the reviewed section")
        frozen = fingerprints(data, lead, sections=(key,))[key]

        with self.store.transaction() as db:
            case = Cases(self.store).require(db, case_id, editable=True)
            check_revision(case, expected_revision)
            self._assert_open(case_id, key, db)
            # The source selection, sender settings or evidence could change
            # during preparation without changing this draft's revision. Rebuild a
            # read-only model under the writer lock and compare all dependencies.
            current_lead = self._lead(case_id)
            current = snapshot(
                self.store,
                case["entity_id"],
                case_id,
                include_reviews=False,
                capture_sections=(),
            )
            self._assert_ready(current, current_lead, key)
            verified = fingerprints(current, current_lead, sections=(key,))[key]
            if frozen["content_hash"] != verified["content_hash"] or (
                frozen["frozen_fields"] != verified["frozen_fields"]
            ):
                raise ValueError(
                    "This section changed while its content was being checked. "
                    "Refresh the draft, review the changes, and validate again."
                )
            actor = self.store.settings()["analyst_name"].strip()
            check_deadline()
            with publication():
                stamp = self.repository.save_validation(db, case_id, key, actor, frozen)
            db.execute(
                "UPDATE cases SET draft_revision=draft_revision+1,version=version+1,updated_at=? WHERE id=?",
                (stamp, case_id),
            )

    def _lead(self, case_id):
        lead = Cases(self.store).view(case_id)
        lead["attribution_summaries"] = attribution_summaries(self.store, lead)
        return lead

    def _assert_open(self, case_id, key, db):
        if key in self.repository.active(case_id, db):
            raise ValueError(
                "This section is frozen. Reopen it with a reason before validating another revision."
            )

    def _assert_ready(self, data, lead, key):
        review = next(
            r for r in self.reviews.describe(data, lead, record_changes=False) if r["key"] == key
        )
        if review["issues"]:
            raise ValueError("Complete this section: " + "; ".join(review["issues"]))

    def reopen(self, case_id, key, expected_revision, reason):
        check_key(key)
        if not reason.strip():
            raise ValueError("A reason is required to reopen a validated section")

        with self.store.transaction() as db:
            case = Cases(self.store).require(db, case_id, editable=True)
            check_revision(case, expected_revision)
            prior = self.repository.active(case_id, db).get(key)
            if not prior:
                raise ValueError("This section is already open for editing")
            actor = self.store.settings().get("analyst_name", "").strip()
            if not actor:
                raise ValueError("Set the analyst name in Settings before reopening a section")
            # A NULL validation_id ends the active freeze; the old snapshot stays.
            stamp = self.repository.event(
                db, case_id, key, "reopened", actor, reason.strip(), prior["revision"]
            )
            db.execute(
                "UPDATE cases SET draft_revision=draft_revision+1,version=version+1,updated_at=? WHERE id=?",
                (stamp, case_id),
            )
