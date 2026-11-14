"""Seed entity identity from the accepted registration object, with field provenance."""

import json
import re

from attribution.matching import domain_equal_or_below, normalize_domain
from .entity_review import value_hash
from .primitives import dump, now


def text(value, limit=300):
    if isinstance(value, list):
        value = ", ".join(text(part, limit) for part in value[:20])
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _card(entity):
    card = entity.get("vcardArray")
    if not isinstance(card, list) or len(card) != 2 or not isinstance(card[1], list):
        return {}
    return {
        str(prop[0]).lower(): (index, prop)
        for index, prop in enumerate(card[1][:100])
        if isinstance(prop, list) and len(prop) >= 4
    }


def _organization(entity, path):
    props = _card(entity)
    kind = text(props.get("kind", (None, [None] * 4))[1][3]).casefold()
    roles = entity.get("roles", [])
    if not isinstance(roles, (list, tuple)):
        roles = []
    if kind == "individual":
        return None
    name_key = "org" if "org" in props else "fn"
    if name_key not in props or (name_key == "fn" and kind != "org" and "registrant" not in roles):
        return None
    index, prop = props[name_key]
    name = text(prop[3])
    if (
        not name
        or re.search(r"redacted|not disclosed|privacy protected", name, re.I)
        or name.casefold()
        in {
            "private",
            "private customer",
            "abuse",
            "abuse desk",
            "noc",
            "network operations",
            "technical support",
            "unknown",
        }
    ):
        return None
    values = {"name": name}
    pointers = {"name": f"{path}/vcardArray/1/{index}/3"}
    if "adr" in props:
        index, adr = props["adr"]
        parts = adr[3]
        params = adr[1] if isinstance(adr[1], dict) else {}
        label = params.get("label")
        if isinstance(label, str) and label.strip():
            values["address"] = "\n".join(
                line.strip() for line in label.splitlines() if line.strip()
            )[:2000]
            pointers["address"] = f"{path}/vcardArray/1/{index}/1/label"
        if isinstance(parts, list) and len(parts) >= 7:
            street = [text(part, 500) for part in parts[:3]]
            city, state, postal, country = [text(part) for part in parts[3:7]]
            if not values.get("address"):
                lines = [*street, " ".join(v for v in (city, state, postal) if v), country]
                values["address"] = "\n".join(line for line in lines if line)[:2000]
                pointers["address"] = f"{path}/vcardArray/1/{index}/3"
            for field, value, number in (("city", city, 3), ("state", state, 4)):
                if value:
                    values[field] = value
                    pointers[field] = f"{path}/vcardArray/1/{index}/3/{number}"
    return {
        "values": {key: value for key, value in values.items() if value},
        "pointers": pointers,
        "entity_handle": text(entity.get("handle")),
    }


def extract(attribution, root):
    evidence = attribution.get("evidence") or {}
    method = evidence.get("method")
    match = evidence.get("match") or {}
    if method not in {"rdap", "rdap_keyword"}:
        return None
    if method == "rdap_keyword":
        if attribution.get("review", {}).get("decision") != "accept":
            return None
    else:
        try:
            if not domain_equal_or_below(
                normalize_domain(match.get("matched_domain", "")), normalize_domain(root)
            ):
                return None
        except ValueError:
            return None
    record = attribution.get("record")
    pointer = match.get("field_path")
    if (
        not isinstance(record, dict)
        or not isinstance(pointer, str)
        or not pointer.startswith("/")
        or len(pointer.split("/")) > 65
    ):
        return None
    # Only ancestors of the exact matched field are candidates. Never pick an
    # unrelated registrant or an arbitrary contact elsewhere in a network record.
    candidates, current, path = [], record, ""
    if "vcardArray" in current:
        candidates.append((current, path))
    try:
        for part in pointer.split("/")[1:65]:
            part = part.replace("~1", "/").replace("~0", "~")
            current = current[int(part)] if isinstance(current, list) else current[part]
            path += "/" + part.replace("~", "~0").replace("/", "~1")
            if isinstance(current, dict) and "vcardArray" in current:
                candidates.append((current, path))
    except ValueError, TypeError, KeyError, IndexError:
        return None
    for entity, path in reversed(candidates):
        details = _organization(entity, path)
        if details:
            return {
                **details,
                "source_url": attribution.get("source_url", ""),
                "retrieved_at": attribution.get("retrieved_at", ""),
                "snapshot_id": attribution.get("snapshot_id", ""),
                "result_id": attribution.get("result_id", ""),
                "method": method,
            }
    return None


def seed_entity(db, entity_id, attribution):
    entity = db.execute(
        "SELECT * FROM leads WHERE id=? AND merged_into IS NULL", (entity_id,)
    ).fetchone()
    if not entity:
        return []
    details = extract(attribution, entity["domain"])
    if not details:
        return []
    row = db.execute(
        "SELECT payload FROM entity_profiles WHERE entity_id=?", (entity_id,)
    ).fetchone()
    profile = json.loads(row[0]) if row else {}
    hostnames = {
        entity["domain"].casefold(),
        *(
            r[0].casefold()
            for r in db.execute(
                "SELECT h.name FROM hostnames h JOIN domain_groups g ON h.root_domain=g.root_domain WHERE g.entity_id=?",
                (entity_id,),
            )
        ),
    }
    applied = []
    for field, value in details["values"].items():
        if db.execute(
            "SELECT 1 FROM entity_field_reviews WHERE entity_id=? AND field=?", (entity_id, field)
        ).fetchone():
            continue
        prior = entity["company"] if field == "name" else profile.get(field, "")
        if prior and (field != "name" or prior.casefold() not in hostnames):
            continue
        # A manually supplied address must not be paired with a registry city.
        if field in {"city", "state"} and profile.get("address") and "address" not in applied:
            continue
        if field == "name":
            db.execute("UPDATE leads SET company=? WHERE id=?", (value, entity_id))
        else:
            profile[field] = value
        source = {
            key: details[key]
            for key in (
                "source_url",
                "retrieved_at",
                "snapshot_id",
                "result_id",
                "method",
                "entity_handle",
            )
        }
        source.update(
            field_path=details["pointers"][field], value_hash=value_hash(value), value=value
        )
        db.execute(
            "INSERT INTO entity_profile_sources(entity_id,field,payload) VALUES(?,?,?) ON CONFLICT(entity_id,field) DO UPDATE SET payload=excluded.payload",
            (entity_id, field, dump(source)),
        )
        db.execute(
            "INSERT INTO entity_field_reviews VALUES(?,?,?,?,?,?)",
            (entity_id, field, "pending", value_hash(value), "Registry import", now()),
        )
        applied.append(field)
    if applied:
        db.execute(
            "INSERT INTO entity_profiles VALUES(?,?) ON CONFLICT(entity_id) DO UPDATE SET payload=excluded.payload",
            (entity_id, dump(profile)),
        )
        db.execute(
            "UPDATE leads SET draft_revision=draft_revision+1,updated_at=? WHERE id=?",
            (now(), entity_id),
        )
    return applied


def migrate(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS entity_profile_sources(entity_id TEXT NOT NULL REFERENCES leads(id),field TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(entity_id,field))"
    )
    for entity in db.execute(
        "SELECT id,attribution FROM leads WHERE merged_into IS NULL"
    ).fetchall():
        seed_entity(db, entity["id"], json.loads(entity["attribution"]))
