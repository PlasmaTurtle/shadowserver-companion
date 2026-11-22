"""Entity finding history API backed by canonical observation memberships."""

from .awareness_history import entity_history


def entity_finding_history(db, entity_id, *, limit=250):
    """Return approved finding history and immutable notification coverage."""
    return entity_history(db, entity_id, limit=limit)
