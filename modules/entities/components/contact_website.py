"""Reuse a retained qualified website within the contact crawler's existing scope."""

from modules.investigations.components import website_evidence

from .contact_discovery.policy import approved_scope, approved_url


def starting_url(store, scope):
    """Prefer a verified HTTPS apex/www capture; unsupported captures do not widen scope."""
    with store.read_snapshot() as db:
        saved = website_evidence.latest_for_entity(
            db, scope["entity_id"], root_domain=scope["root_domain"]
        )
        if saved is None:
            return None
        try:
            capture = website_evidence.get(store, saved["id"], db=db)
            if not website_evidence.is_usable_capture(capture["capture"]):
                return None
            root, aliases = approved_scope(scope["root_domain"])
            return approved_url(capture["final_url"], {root, *aliases})
        except (OSError, KeyError, TypeError, ValueError):
            return None
