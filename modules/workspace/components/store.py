"""Compatibility facade composing local records and application services.

Database connection/transaction ownership is in Workspace; record projections
are repositories; entity mutations, exports and interrupted-publication recovery
are application services. Existing callers keep the Store API.
"""

import logging
import sqlite3

from .workspace import Workspace
from modules.accretion.components.dark_matter import DarkMatterStore, drain
from modules.entities.components.repositories.entities import EntityRepository
from modules.investigations.components.repositories.artifacts import ArtifactRepository
from modules.entities.components.services.entities import EntityService
from modules.entities.components.services.queries import entity_view
from modules.leads.components.services.lead_exports import LeadExportService
from modules.investigations.components.services.recovery import recover_reports, recover_closings


class Store(Workspace):
    def __init__(self, root):
        super().__init__(root)
        self.dark_matter = DarkMatterStore(self.root)
        drain(self.root, archive=self.dark_matter)
        self.after_commit.append(self._deliver_dark_matter)
        self.entities = EntityRepository(self)
        self.artifacts = ArtifactRepository(self)
        self.recover_reports()
        recover_closings(self)

    def _deliver_dark_matter(self):
        # The committed outbox is authoritative until delivery is acknowledged.
        # Delivery failure must not masquerade as a rolled-back business transaction.
        try:
            with self.lock:
                drain(self.root, archive=self.dark_matter)
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
            logging.getLogger(__name__).exception("Dark Matter delivery pending: %s", error)

    validate_attribution_entry = staticmethod(EntityRepository.validate_attribution_entry)

    def resolve_entity(self, entity_id):
        return self.entities.resolve_entity(entity_id)

    def lead(self, lead_id):
        return entity_view(self, self.entities, lead_id)

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
