"""Durable contact work requests accepted within an entity's publication transaction."""

from modules.leads.components.provider_policy import is_provider


def queue_initial(db, entity_id, root_domain):
    """Request one initial lookup; repeated sightings retain existing work state."""
    if is_provider(root_domain):
        return False
    return bool(
        db.execute(
            "INSERT OR IGNORE INTO entity_contact_queue(entity_id) VALUES(?)", (entity_id,)
        ).rowcount
    )
