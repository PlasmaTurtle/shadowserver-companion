"""Entity edits and merges; each operation owns one cross-record transaction."""

import json
from ..repositories.entities import EntityRepository
from ..entity_review import REVIEW_FIELDS, field_values, value_hash


class EntityService:
    def __init__(self, store):
        self.store = store
        self.repository = EntityRepository(store)

    def rename_entity(self, entity_id, name, expected_revision):
        actor = self.store.settings().get("analyst_name") or "Local operator"
        with self.store.transaction() as db:
            row = self.repository.active(db, entity_id)
            if not row:
                raise ValueError("Active entity not found")
            if row["draft_revision"] != expected_revision:
                raise ValueError("This entity changed. Reload before renaming it.")
            draft = json.loads(row["draft"])
            draft.update(company=name, reviewed=False)
            self.repository.rename(db, entity_id, name, draft)
            if name != (row["company"] or row["domain"]):
                self.repository.save_field_review(db, entity_id, "name", name, "confirmed", actor)
            self.store.log(
                db,
                "entity_renamed",
                f"Entity renamed from {row['company'] or row['domain']} to {name}",
                entity_id,
            )
        self.store.export_all()

    def update_entity_profile(self, entity_id, values, expected_revision):
        actor = self.store.settings().get("analyst_name") or "Local operator"
        with self.store.transaction() as db:
            row = self.repository.active(db, entity_id)
            if not row or row["draft_revision"] != expected_revision:
                raise ValueError("This entity changed. Reload before saving its details.")
            previous = self.repository.profile(db, entity_id)
            from ..entity_validation import validate_profile

            values = validate_profile(values, previous=previous)
            self.repository.save_profile(db, entity_id, values)
            for field in REVIEW_FIELDS:
                if field == "name":
                    continue
                value = str(values.get(field) or "")
                if value != str(previous.get(field) or ""):
                    self.repository.save_field_review(
                        db,
                        entity_id,
                        field,
                        value,
                        "confirmed" if value.strip() else "pending",
                        actor,
                    )
            self.repository.touch_profile(db, entity_id)
            self.store.log(
                db,
                "entity_profile_saved",
                "Updated business contact and address details",
                entity_id,
            )
        self.store.export_all()

    def associate_asset(self, entity_id, hostname, expected_revision):
        from ..awareness import link_asset

        with self.store.transaction() as db:
            row = self.repository.active(db, entity_id)
            if not row or row["draft_revision"] != expected_revision:
                raise ValueError("This entity changed. Reload before associating an asset.")
            asset = link_asset(db, hostname, entity_id, basis="manual")
            self.repository.touch_profile(db, entity_id)
            self.store.log(
                db, "entity_asset_associated", f"Associated hostname {asset['hostname']}", entity_id
            )
        self.store.export_all()
        return asset

    def review_entity_field(self, entity_id, field, action, expected_revision, expected_hash):
        """Resolve a reminder without changing drafts, certifications or case revisions."""
        if field not in REVIEW_FIELDS or action not in ("confirm", "ignore", "pending"):
            raise ValueError("Unknown business field review action")
        actor = self.store.settings().get("analyst_name") or "Local operator"
        with self.store.transaction() as db:
            row = self.repository.active(db, entity_id)
            if not row or row["draft_revision"] != expected_revision:
                raise ValueError("This entity changed. Reload before reviewing its details.")
            profile = self.repository.profile(db, entity_id)
            value = field_values(row, profile)[field]
            if value_hash(value) != expected_hash:
                raise ValueError("This field changed. Reload before reviewing it.")
            if action == "confirm" and not value.strip():
                raise ValueError(
                    "Enter this business detail before confirming it, or choose Ignore."
                )
            status = {"confirm": "confirmed", "ignore": "ignored", "pending": "pending"}[action]
            self.repository.save_field_review(db, entity_id, field, value, status, actor)
            self.store.log(
                db, "entity_field_reviewed", f"{REVIEW_FIELDS[field]}: {status}", entity_id
            )
            return {
                "entity_revision": row["draft_revision"],
                "entity_review": self.repository.field_review(db, row, profile),
            }

    def merge_entities(self, source_id, target_id, source_revision, target_revision):
        """Keep target draft; retain source draft and completed packages on archived entity."""
        if source_id == target_id:
            raise ValueError("Select a different entity")
        with self.store.transaction() as db:
            source = self.repository.active(db, source_id)
            target = self.repository.active(db, target_id)
            if not source or not target:
                raise ValueError("Both entities must still be active")
            if (source["draft_revision"], target["draft_revision"]) != (
                source_revision,
                target_revision,
            ):
                raise ValueError("An entity changed. Reload before combining them.")
            if source["demo"] != target["demo"]:
                raise ValueError("Demonstration and working entities cannot be combined")
            profiles = self.repository.profiles(db, source_id, target_id)
            from ..entity_validation import merge_profiles

            merged_profile = merge_profiles(
                profiles.get(source_id, {}), profiles.get(target_id, {})
            )
            self.repository.save_profile(db, target_id, merged_profile)
            for field in REVIEW_FIELDS:
                if field != "name" and merged_profile.get(field, "") != profiles.get(
                    target_id, {}
                ).get(field, ""):
                    self.repository.save_field_review(
                        db,
                        target_id,
                        field,
                        merged_profile.get(field, ""),
                        "pending",
                        "Entity merge",
                    )
                    self.repository.copy_profile_source(db, source_id, target_id, field)
            count = self.repository.transfer_records(db, source_id, target_id)
            from ..lead_frontier import merge_entity_memory

            merge_entity_memory(db, source_id, target_id)
            from ..awareness import merge_entities as merge_awareness_entities

            merge_awareness_entities(db, source_id, target_id)
            draft = json.loads(target["draft"])
            draft["reviewed"] = False
            draft["cve_reviewed"] = False
            # Union source reference records, while retaining the target's narrative/contact.
            records = {r["id"]: r for r in json.loads(source["draft"]).get("cve_records", [])}
            records.update({r["id"]: r for r in draft.get("cve_records", [])})
            draft["cve_records"] = list(records.values())
            self.repository.update_merge_target(db, target_id, draft, count)
            self.store.log(
                db,
                "entity_merged",
                f"Combined {source['company'] or source['domain']} into {target['company'] or target['domain']}; retained all observations and report history",
                target_id,
            )
            self.store.validate_attribution_entry(db, target_id)
            # Business identity merges do not merge notification scopes or
            # invalidate their pinned content. Add findings explicitly in Leads.
        self.store.export_all()
        return self.store.lead(target_id)
