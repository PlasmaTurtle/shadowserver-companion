"""Registration-supplied words generate review candidates, never qualification."""
from __future__ import annotations

import re
import unicodedata

import idna

from .matching import normalize_domain
from .models import DomainMatch


def folded(value):
    return unicodedata.normalize("NFKC", value).casefold()


def name_fields(record):
    """Only network names and organization names; not notices, addresses or prose."""
    def strings(value, path):
        if isinstance(value, str):
            yield value, path
        elif isinstance(value, list):
            for i, child in enumerate(value):
                yield from strings(child, f"{path}/{i}")

    def visit(obj, path="", depth=0):
        if not isinstance(obj, dict) or depth > 64:
            return
        handle = obj.get("handle") if isinstance(obj.get("handle"), str) else None
        roles = tuple(r for r in obj.get("roles", []) if isinstance(r, str)) if isinstance(obj.get("roles", []), list) else ()
        if obj.get("objectClassName") == "ip network" and isinstance(obj.get("name"), str):
            yield obj["name"], path + "/name", handle, roles, "network_name"
        card = obj.get("vcardArray")
        if isinstance(card, list) and len(card) == 2 and isinstance(card[1], list):
            props = [(i, p) for i, p in enumerate(card[1]) if isinstance(p, list) and len(p) >= 4]
            kind = next((str(p[3]).casefold() for _, p in props if p[0] == "kind"), "")
            for i, prop in props:
                field = str(prop[0]).lower()
                # FN is the displayed entity name; explicitly individual cards are excluded.
                if field == "org" or (field == "fn" and kind != "individual"):
                    for value, pointer in strings(prop[3], f"{path}/vcardArray/1/{i}/3"):
                        yield value, pointer, handle, roles, "organization_name" if field == "org" else "entity_name"
        entities = obj.get("entities", [])
        if isinstance(entities, list):
            for i, child in enumerate(entities):
                yield from visit(child, f"{path}/entities/{i}", depth + 1)
    yield from visit(record)


class RegistrationNameMatcher:
    version = "registration-words-v1"

    def find_matches(self, record, root_domain):
        target = normalize_domain(root_domain)
        # Callers supply the registrable root, already derived during intake.
        label = folded(idna.decode(target.split(".")[0]))
        for value, path, handle, roles, field_type in name_fields(record):
            words = tuple(dict.fromkeys(w for w in re.findall(r"[^\W_]+", folded(value))
                                        if any(c.isalpha() for c in w) and w in label))
            if words:
                # No matched domain is asserted by a word match.
                match = DomainMatch(target, "", path, value, handle, roles, field_type)
                yield match, {"matched_words": words, "domain_label": label,
                              "matcher_version": self.version}
