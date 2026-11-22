"""Apply internal case decisions and external referrals to Associate's incoming scope."""

from collections import defaultdict
from urllib.parse import urlsplit

from modules.investigations.components.outreach_policy import entity_hold
from modules.tools.components.network_identity import extract_domain
from .intake.domains import HOSTNAME


def identifier_for(scope, value):
    value = value.strip().casefold().rstrip(".")
    if len(value) > 253 or not HOSTNAME.fullmatch(value):
        raise ValueError("Enter a hostname without a scheme, path or wildcard")
    root = extract_domain(value).top_domain_under_public_suffix
    if not root or (scope == "domain" and value != root):
        raise ValueError("Domain-wide entries require a registrable root domain")
    return value


def exact_host_entries(db, hosts):
    """Use the indexed referral list for the reported hosts or a rendered destination."""
    hosts = sorted(set(hosts) - {""})
    for offset in range(0, len(hosts), 500):
        batch = hosts[offset : offset + 500]
        placeholders = ",".join("?" for _ in batch)
        yield from db.execute(
            f"SELECT * FROM intake_deconfliction WHERE scope='host' AND identifier IN ({placeholders}) ORDER BY identifier",
            batch,
        )


def url_hostname(url):
    return (urlsplit(url or "").hostname or "").casefold().rstrip(".")


class AssociationEvidenceChanged(ValueError):
    """Previously selected evidence no longer supports the admissible source scope."""


def check(db, root, entries, entity_id):
    """Snapshot actual matches so subsequent registry edits cannot rewrite this result."""
    from modules.investigations.components.services.case_queries import completed_notifications

    by_host = defaultdict(list)
    for index, entry in enumerate(entries):
        host = entry["source"]["fields"]["hostname"].casefold().rstrip(".")
        by_host[host].append(index)
    matches, blocked = [], set()
    if entity_id:
        history = completed_notifications(db, entity_id)
        if history["count"]:
            matches.append(
                {
                    "kind": "notification_history",
                    "scope": "entity",
                    "identifier": entity_id,
                    "reference": history["last_case_id"],
                    "count": history["count"],
                    "last_notified_at": history["last_notified_at"],
                    "action": "inform",
                }
            )
        hold = entity_hold(db, entity_id)
        if hold:
            matches.append(
                {
                    "kind": "outreach_" + hold["state"],
                    "scope": "entity",
                    "identifier": entity_id,
                    "reference": hold["case_id"],
                    "reason": hold["reason"],
                    "action": "exclude",
                }
            )
            blocked.update(range(len(entries)))
    hits = list(
        db.execute(
            "SELECT * FROM intake_deconfliction WHERE scope='domain' AND identifier=?", (root,)
        )
    )
    hits.extend(exact_host_entries(db, by_host))
    for row in hits:
        index = range(len(entries)) if row["scope"] == "domain" else by_host[row["identifier"]]
        blocked.update(index)
        matches.append(
            {
                "kind": "external",
                "entry_id": row["id"],
                "scope": row["scope"],
                "identifier": row["identifier"],
                "reference": row["external_reference"],
                "reason": row["reason"],
                "action": "exclude",
            }
        )
    return matches, blocked
