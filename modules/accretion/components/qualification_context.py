"""Read Entities-owned local context before website or attribution work."""

from modules.entities.components.ownership import qualification_context
from .intake.records import observation_payload


def recognize_group(store, group):
    """Read ownership and its proof reference in one Workspace snapshot."""
    entries = [observation_payload(entry) for entry in group.observations]
    with store.read_snapshot() as db:
        return qualification_context(db, group.root_domain, entries)
