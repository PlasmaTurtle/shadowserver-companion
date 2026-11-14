"""Review status, freeze guards and stale-dependency chronology.

Describe can record a newly observed stale dependency; record_changes=False is
the explicit read-only path used inside validation and startup recovery.
"""

import workbench.compact_json as compact_json
from ..repositories.reviews import SectionReviewRepository
from .policy import SECTIONS, PREREQUISITES, fingerprints, changed_paths, content_projection


class SectionReviewQueries:
    def __init__(self, store):
        self.store = store
        self.repository = SectionReviewRepository(store)

    def history(self, case_id):
        return self.repository.history(case_id)

    def snapshots(self, case_id):
        return self.repository.snapshots(case_id)

    def describe(self, data, lead, *, record_changes=True):
        active = self.repository.active(lead["case_id"])
        # Editable sections have no prior fingerprint to compare. Their
        # readiness still comes from the same evidence and citation checks.
        resources = {}
        saved_records = {
            key: compact_json.loads(row["snapshot_json"], resource_pool=resources)
            for key, row in active.items()
        }
        actual = self._fingerprints(data, lead, saved_records)
        reviews = []
        actor = self.store.settings().get("analyst_name", "").strip()
        editable = lead.get("case", {}).get("stage") == "in_progress"
        for key, label in SECTIONS.items():
            prior = active.get(key)
            previously_stale = bool(
                prior
                and self.store.one(
                    "SELECT 1 FROM section_events WHERE validation_id=? AND action='stale' LIMIT 1",
                    (prior["id"],),
                )
            )
            changed = bool(
                prior and (previously_stale or prior["content_hash"] != actual[key]["content_hash"])
            )
            status = "stale" if changed else "validated" if prior else "draft"
            issues = [
                r["label"]
                for r in data["readiness"]
                if r["key"]
                in (PREREQUISITES[key] | {"source_integrity", "citation_integrity", "handling"})
                and not r["ok"]
            ]
            if not actor:
                issues.append("Set the analyst name in Settings before validating")
            if changed:
                issues.append(
                    "Supporting content changed. Reopen this section with a reason, review, and validate again."
                )
                if record_changes:
                    with self.store.transaction() as db:
                        if not db.execute(
                            "SELECT 1 FROM section_events WHERE validation_id=? AND action=? AND dependency_hash=?",
                            (prior["id"], "stale", actual[key]["content_hash"]),
                        ).fetchone():
                            self.repository.event(
                                db,
                                lead["case_id"],
                                key,
                                "stale",
                                "System",
                                "Dependency change detected; the previously validated snapshot is retained.",
                                prior["revision"],
                                prior["id"],
                                actual[key]["content_hash"],
                            )
            saved = saved_records.get(key, {})
            differences = (
                changed_paths(saved.get("snapshot", {}), actual[key]["snapshot"]) if changed else []
            )
            reviews.append(
                {
                    "key": key,
                    "label": label,
                    "status": status,
                    "revision": prior["revision"]
                    if prior
                    else self.repository.last_revision(lead["case_id"], key),
                    "validated_at": prior["validated_at"] if prior else None,
                    "validated_by": prior["validated_by"] if prior else None,
                    "validation_id": prior["id"] if prior else None,
                    "can_validate": editable and not prior and not issues,
                    "issues": issues,
                    "changed": changed,
                    "changed_dependencies": differences,
                    "content_hash": prior["content_hash"] if prior else None,
                    "frozen_fields": saved.get("frozen_fields", {}),
                    "frozen_context": saved.get("frozen_context", {}),
                    "snapshot": saved.get("snapshot"),
                    "fingerprint_version": saved.get("fingerprint_version", 1) if prior else None,
                }
            )
        return reviews

    @staticmethod
    def _fingerprints(data, lead, saved_records):
        result = {}
        versions = {saved.get("fingerprint_version", 1) for saved in saved_records.values()}
        for version in versions:
            sections = [
                key
                for key, saved in saved_records.items()
                if saved.get("fingerprint_version", 1) == version
            ]
            result.update(
                fingerprints(
                    data, lead, sections=sections, version=version, prior_snapshots=saved_records
                )
            )
            if version == 1:
                # Historical validation rows and their artwork hashes stay
                # intact. A working draft may change output presentation while
                # every originally reviewed content dependency remains equal.
                current_content = fingerprints(data, lead, sections=sections)
                for key in sections:
                    saved = saved_records[key]
                    if content_projection(saved) == current_content[key]["snapshot"]:
                        result[key]["content_hash"] = saved["content_hash"]
        return result

    def assert_editable(self, db, case_id, keys):
        active = self.repository.active(case_id, db)
        locked = [SECTIONS[key] for key in keys if key in active]
        if locked:
            raise ValueError(
                "Reopen these frozen sections with a reason before editing: " + ", ".join(locked)
            )

    def guard_draft(self, db, before, after, lead):
        active = self.repository.active(lead["case_id"], db)
        if not active:
            return
        # Editing applies the current content policy to both sides. Old saved
        # rows keep their hash; presentation choices do not mutate either lock.
        current = fingerprints(before, lead, sections=active)
        proposed = fingerprints(after, lead, sections=active)
        self.assert_editable(
            db,
            lead["case_id"],
            [
                key
                for key in active
                if current[key]["content_hash"] != proposed[key]["content_hash"]
                # A declared frozen field remains locked even if a particular
                # layout does not display it (for example the report date).
                # Keep historical rendered-content hashes unchanged.
                or current[key]["frozen_fields"] != proposed[key]["frozen_fields"]
            ],
        )
