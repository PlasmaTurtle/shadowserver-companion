"""Compatibility facade composing local records and application services.

Database connection/transaction ownership is in Workspace; record projections
are repositories; entity mutations, exports and interrupted-publication recovery
are application services. Existing callers keep the Store API.
"""

from .workspace import Workspace
from .workspace_defaults import DEFAULT_SETTINGS as DEFAULT_SETTINGS, EXPLAINERS as EXPLAINERS
from .primitives import now as now, uid as uid, dump as dump
from .repositories.entities import EntityRepository
from .repositories.artifacts import ArtifactRepository
from .services.entities import EntityService
from .services.lead_exports import LeadExportService
from .services.recovery import recover_reports, recover_closings


class Store(Workspace):
    def __init__(self, root):
        super().__init__(root)
        self.entities = EntityRepository(self)
        self.artifacts = ArtifactRepository(self)
        self.recover_reports()
        recover_closings(self)

    validate_attribution_entry = staticmethod(EntityRepository.validate_attribution_entry)

    def resolve_entity(self, entity_id):
        return self.entities.resolve_entity(entity_id)

    def lead(self, lead_id):
        from .contact_outcomes import complete_entity_details

        entity = self.entities.lead(lead_id)
        if entity:
            entity["entity_review"] = complete_entity_details(
                self, entity, entity["entity_review"], entity["entity_profile"]
            )
        return entity

    def rename_entity(self, entity_id, name, expected_revision):
        return EntityService(self).rename_entity(entity_id, name, expected_revision)

    def update_entity_profile(self, entity_id, values, expected_revision):
        return EntityService(self).update_entity_profile(entity_id, values, expected_revision)

    def review_entity_field(self, entity_id, field, action, expected_revision, expected_hash):
        return EntityService(self).review_entity_field(
            entity_id, field, action, expected_revision, expected_hash
        )

    def merge_entities(self, source_id, target_id, source_revision, target_revision):
        return EntityService(self).merge_entities(
            source_id, target_id, source_revision, target_revision
        )

    def recover_reports(self):
        return recover_reports(self)

    def package_available(self, report):
        return self.artifacts.package_available(report)

    def package_inventory(self, report):
        return self.artifacts.package_inventory(report)

    def closure_available(self, record):
        return self.artifacts.closure_available(record)

    def closure_inventory(self, record):
        return self.artifacts.closure_inventory(record)

    def work_log_available(self, report):
        return self.artifacts.work_log_available(report)

    def export_lead(self, lead_id, case_id=None):
        return LeadExportService(self).export_lead(lead_id, case_id)

    def export_all(self):
        return LeadExportService(self).export_all()
