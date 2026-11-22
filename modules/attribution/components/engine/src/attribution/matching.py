"""Deterministic domain matching over registration fields, with exact evidence paths."""
from __future__ import annotations

import re
from email.utils import parseaddr
from ipaddress import ip_address
from urllib.parse import unquote, urlsplit

import idna

from .models import DomainMatch

TOKEN = re.compile(r"(?<![\w@.-])(?:[^\W_](?:[\w-]{0,61}[^\W_])?\.)+"
                   r"[^\W_](?:[\w-]{0,61}[^\W_])?(?![\w-]|\.[\w-])", re.UNICODE)
URL = re.compile(r"(?:https?://|mailto:)[^\s<>\"']+", re.IGNORECASE)
EMAIL = re.compile(r"[^\s<>\"'(),;]+@[^\s<>\"'(),;]+")
# Protocol/service metadata and unrelated resources are preserved, but not attribution.
EXCLUDED = {"links", "notices", "events", "rdapConformance", "port43", "lang",
            "objectClassName", "status", "roles", "redacted", "networks", "autnums"}


def normalize_domain(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("root_domain must be a string")
    value = value.strip()
    try:
        value = idna.uts46_remap(value, std3_rules=True, transitional=False)
    except idna.IDNAError as error:
        raise ValueError("Invalid domain name") from error
    if value.endswith(".."):
        raise ValueError("Invalid empty domain label")
    if value.endswith("."):
        value = value[:-1]
    if not value or any(c in value for c in "/:@?#\\"):
        raise ValueError("Supply a domain name, without a URL, email address, or port")
    try:
        domain = idna.encode(value, uts46=True, std3_rules=True).decode("ascii").lower()
    except idna.IDNAError as error:
        raise ValueError("Invalid domain name") from error
    if len(domain) > 253 or len(domain.split(".")) < 2:
        raise ValueError("Supply a fully qualified domain name")
    try:
        ip_address(domain)
    except ValueError:
        return domain
    raise ValueError("A domain name cannot be an IP address")


def domain_equal_or_below(found: str, target: str) -> bool:
    return found == target or found.endswith("." + target)


def _canonical(value):
    try:
        return normalize_domain(value)
    except ValueError:
        return None


def _email_domain(value):
    if value.lower().startswith("mailto:"):
        value = unquote(value[7:].split("?", 1)[0])
    address = parseaddr(value)[1]
    if address.count("@") != 1:
        return None
    return _canonical(address.rsplit("@", 1)[1].rstrip(".,;"))


def _url_domain(value):
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() in ("https", "http") and parts.hostname:
            return _canonical(parts.hostname)
    except ValueError:
        pass
    return None


def text_domains(value):
    # Remove whole URLs/emails before searching prose. A target in an unrelated
    # URL's path, query, or userinfo must not masquerade as that URL's hostname.
    remaining = value
    for pattern, extractor in ((URL, lambda s: _email_domain(s) if s.lower().startswith("mailto:") else _url_domain(s)),
                               (EMAIL, _email_domain)):
        for match in list(pattern.finditer(remaining)):
            found = extractor(match.group().rstrip(".,;)]}"))
            if found:
                yield found
        remaining = pattern.sub(" ", remaining)
    for match in TOKEN.finditer(remaining):
        found = _canonical(match.group())
        if found:
            yield found


def pointer_part(value):
    return str(value).replace("~", "~0").replace("/", "~1")


class DomainMatcher:
    version = "registration-domain-v1"

    def candidates(self, record: dict):
        """Yield domain occurrences; unknown registration fields remain searchable."""
        def visit(value, path="", handle=None, roles=(), depth=0):
            if depth > 64:
                raise ValueError("Registration record exceeds the supported nesting depth")
            if isinstance(value, dict):
                if value.get("objectClassName") == "entity":
                    handle = value.get("handle") if isinstance(value.get("handle"), str) else None
                    raw_roles = value.get("roles", [])
                    roles = tuple(r for r in raw_roles if isinstance(r, str)) if isinstance(raw_roles, list) else ()
                for key, child in value.items():
                    child_path = path + "/" + pointer_part(key)
                    if key in EXCLUDED:
                        continue
                    if key == "vcardArray":
                        if not isinstance(child, list) or len(child) != 2 or not isinstance(child[1], list):
                            continue
                        for i, prop in enumerate(child[1]):
                            if not isinstance(prop, list) or len(prop) < 4:
                                continue
                            name = str(prop[0]).lower()
                            if name in ("version", "prodid", "uid", "rev", "source"):
                                continue
                            values = prop[3:]
                            for j, item in enumerate(values, 3):
                                p = f"{child_path}/1/{i}/{j}"
                                if name in ("email", "url") and isinstance(item, str):
                                    domain = _email_domain(item) if name == "email" else _url_domain(item)
                                    if domain:
                                        yield domain, p, item, handle, roles, name
                                else:
                                    yield from visit(item, p, handle, roles, depth + 1)
                    else:
                        yield from visit(child, child_path, handle, roles, depth + 1)
            elif isinstance(value, list):
                for i, child in enumerate(value):
                    yield from visit(child, path + "/" + str(i), handle, roles, depth + 1)
            elif isinstance(value, str):
                for domain in text_domains(value):
                    yield domain, path, value, handle, roles, "text"
        yield from visit(record)

    def find_match(self, record: dict, root_domain: str) -> DomainMatch | None:
        target = normalize_domain(root_domain)
        for domain, path, value, handle, roles, kind in self.candidates(record):
            if domain_equal_or_below(domain, target):
                return DomainMatch(target, domain, path, value, handle, roles, kind)
        return None

