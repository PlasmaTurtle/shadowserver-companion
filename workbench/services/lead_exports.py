"""Compatibility JSON projections; preserve grouped full rows and primary proof."""

import json


class LeadExportService:
    def __init__(self, store):
        self.store = store

    def export_lead(self, lead_id, case_id=None, *, lead_override=None):
        from ..cases import Cases
        from ..contact_records import ContactRecords

        lead = lead_override or (
            Cases(self.store).view(case_id) if case_id else self.store.lead(lead_id)
        )
        root_by_id = {
            r["id"]: r["root_domain"]
            for r in self.store.all(
                "SELECT id,root_domain FROM entries WHERE lead_id=?", (lead["id"],)
            )
        }
        from ..lead_export_model import qualified_export

        exported = qualified_export(lead, root_by_id, case_id)
        if not case_id:
            exported["contact_discovery"] = ContactRecords(self.store).export_projection(lead["id"])
        return exported

    def export_all(self):
        with self.store.lock:
            values = [
                self.store.export_lead(row["id"])
                for row in self.store.all(
                    "SELECT id FROM leads WHERE merged_into IS NULL ORDER BY created_at"
                )
            ]
            destination = self.store.root / "exports" / "qualified-leads.json"
            temporary = destination.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(values, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            temporary.replace(destination)
