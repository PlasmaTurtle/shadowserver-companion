"""RDAP provider: authoritative discovery, IP containment, and bounded entity retrieval."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from ipaddress import IPv6Address, ip_address, ip_network
from typing import Protocol
from urllib.parse import quote, urljoin, urlsplit

from .http import REGISTRIES, RegistryHttpClient, RequestContext, validate_url
from .matching import DomainMatcher
from .name_matching import RegistrationNameMatcher
from .models import AttributionEvidence, LookupFailure, ProviderResult, Settings, VERSION
from .store import EvidenceStore


def normalize_ip(value: str) -> str:
    if not isinstance(value, str) or "%" in value:
        raise ValueError("IP must be a string without a zone identifier")
    address = ip_address(value.strip())
    if isinstance(address, IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.compressed


def eligible_ip(value: str) -> bool:
    address = ip_address(value)
    return address.is_global and not address.is_multicast


class AttributionProvider(Protocol):
    name: str

    def collect(self, ip: str, root_domain: str, *, refresh: bool = False,
                offline: bool = False) -> ProviderResult: ...


@dataclass(frozen=True)
class RegistryRoute:
    urls: tuple[str, ...]
    allowed_hosts: frozenset[str]
    bootstrap_snapshot_id: str


class RegistryResolver:
    def __init__(self, client: RegistryHttpClient):
        self.client = client

    @staticmethod
    def _services(data):
        if not isinstance(data.get("services"), list) or not data["services"]:
            raise ValueError("Bootstrap services are missing")
        services = []
        for service in data["services"]:
            if not isinstance(service, list) or len(service) != 2:
                raise ValueError("Invalid bootstrap service")
            prefixes, bases = service
            if not isinstance(prefixes, list) or not isinstance(bases, list):
                raise ValueError("Invalid bootstrap entry arrays")
            secure = []
            for base in bases:
                if not isinstance(base, str):
                    raise ValueError("Invalid bootstrap URL")
                parts = urlsplit(base)
                if parts.scheme != "https":
                    continue
                if not parts.hostname or "." not in parts.hostname or parts.query:
                    raise ValueError("Invalid bootstrap authority")
                try:
                    ip_address(parts.hostname)
                except ValueError:
                    pass
                else:
                    raise ValueError("Bootstrap service must use a registry hostname")
                validate_url(base, {parts.hostname})
                secure.append(base.rstrip("/") + "/")
            networks = [ip_network(p) for p in prefixes]
            if networks and secure:
                services.append((networks, tuple(secure)))
        if not services:
            raise ValueError("No HTTPS bootstrap services")
        return services

    def resolve(self, ip: str, context: RequestContext, *, offline=False) -> RegistryRoute:
        address = ip_address(ip)
        url = f"https://data.iana.org/rdap/ipv{address.version}.json"
        fetched = self.client.fetch(url, {"data.iana.org", "www.iana.org"}, self._services,
            context, ttl=self.client.settings.bootstrap_ttl, offline=offline)
        if fetched.response.status_code != 200:
            raise LookupFailure("bootstrap_unavailable", "IANA bootstrap data is unavailable")
        services = self._services(fetched.response.record())
        hosts = set(REGISTRIES)
        matches = []
        for networks, urls in services:
            hosts.update(urlsplit(u).hostname for u in urls)
            for network in networks:
                if network.version == address.version and address in network:
                    matches.append((network.prefixlen, urls))
        if not matches:
            raise LookupFailure("no_registry_route", "IANA has no service mapping for this IP", status="incomplete")
        return RegistryRoute(max(matches, key=lambda item: item[0])[1], frozenset(hosts),
                             fetched.response.snapshot_id)


def validate_network(data, ip):
    if data.get("objectClassName") != "ip network":
        raise ValueError("Expected an IP network object")
    start, end, address = ip_address(data["startAddress"]), ip_address(data["endAddress"]), ip_address(ip)
    if start.version != end.version or address.version != start.version or not start <= address <= end:
        raise ValueError("Returned network does not contain the queried IP")


def validate_entity(data, handle):
    if data.get("objectClassName") != "entity" or data.get("handle") != handle:
        raise ValueError("Entity response does not match the referenced handle")


def truncation_warnings(data) -> list[str]:
    warnings = []
    def visit(obj, depth=0):
        if depth > 64:
            warnings.append("Record exceeds the supported nesting depth")
            return
        if isinstance(obj, dict):
            if obj.get("redacted"):
                warnings.append("Registry reports redacted data")
            for field in ("notices", "remarks"):
                items = obj.get(field, [])
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and "truncated" in str(item.get("type", "")).lower():
                            warnings.append(str(item["type"]))
            # Omitted lists of OTHER networks/autnums do not affect this IP's attribution.
            for key, value in obj.items():
                if key not in ("networks", "autnums", "notices", "remarks", "redacted"):
                    visit(value, depth + 1)
        elif isinstance(obj, list):
            for value in obj:
                visit(value, depth + 1)
    visit(data)
    return list(dict.fromkeys(warnings))


def entity_references(data, source_url):
    """Only incomplete embedded entities need a fetch; never traverse their other resources."""
    result, issues = [], []
    def visit(obj, depth=0):
        if depth > 64:
            issues.append("Embedded entity nesting limit reached")
            return
        entities = obj.get("entities", [])
        if not isinstance(entities, list):
            issues.append("Invalid entities member")
            return
        for entity in entities:
            if not isinstance(entity, dict):
                issues.append("Invalid embedded entity")
                continue
            handle = entity.get("handle")
            vcard = entity.get("vcardArray")
            full = (isinstance(vcard, list) and len(vcard) == 2 and isinstance(vcard[1], list)
                    and any(isinstance(p, list) and len(p) >= 4 and p[0] != "version" for p in vcard[1]))
            if not full:
                links = entity.get("links", [])
                links = links if isinstance(links, list) else []
                link = next((l.get("href") for l in links if isinstance(l, dict)
                             and l.get("rel") == "self" and isinstance(l.get("href"), str)
                             and l.get("type", "application/rdap+json").split(";")[0] == "application/rdap+json"), None)
                if isinstance(handle, str) and link:
                    result.append((handle, urljoin(source_url, link)))
                else:
                    issues.append("Incomplete entity has no usable RDAP self link")
            visit(entity, depth + 1)
    visit(data)
    return result, issues


class RdapProvider:
    name = "rdap"

    def __init__(self, store: EvidenceStore, settings: Settings | None = None, *, transport=None,
                 cancel_event=None):
        self.store, self.settings = store, settings or Settings()
        self.cancel_event = cancel_event
        self.client = RegistryHttpClient(store, self.settings, transport=transport)
        self.resolver = RegistryResolver(self.client)
        self.matcher = DomainMatcher()
        self.name_matcher = RegistrationNameMatcher()

    def close(self):
        self.client.close()

    def describe(self):
        return {"version": VERSION, "settings": asdict(self.settings)}

    def collect(self, ip: str, root_domain: str, *, refresh=False, offline=False) -> ProviderResult:
        context = RequestContext(time.monotonic() + self.settings.operation_budget,
                                 cancel_event=self.cancel_event)
        warnings = []
        partials = []

        def result(status, evidence=None, reason="", message="", retry_at=None):
            return ProviderResult(status, evidence, reason, message, tuple(context.snapshot_ids),
                retry_at, tuple(dict.fromkeys(warnings)), context.network_requests, context.cache_hits,
                tuple(partials))

        try:
            ip = normalize_ip(ip)
            if not eligible_ip(ip):
                return result("skipped", reason="nonpublic_ip", message="Public registry lookup skipped")
            route = self.resolver.resolve(ip, context, offline=offline)
            fetched = None
            for index, base in enumerate(route.urls):
                try:
                    fetched = self.client.fetch(base + "ip/" + quote(ip, safe=":"), set(route.allowed_hosts),
                        lambda data: validate_network(data, ip), context, refresh=refresh, offline=offline)
                    break
                except LookupFailure as error:
                    # Do not evade a registry rate limit by using another endpoint.
                    if error.reason not in ("network_error", "service_unavailable") or index == len(route.urls) - 1:
                        raise
            network_response = fetched.response
            if network_response.status_code == 404:
                return result("no_match", reason="not_found", message="Registry returned no IP network record")
            network = network_response.record()
            warnings.extend(truncation_warnings(network))
            queue = [(fetched, 0, ())]
            visited = set()
            entities_fetched = 0
            unresolved = False
            deferred = None
            while queue:
                current, depth, ancestors = queue.pop(0)
                response = current.response
                data = response.record()
                warnings.extend(truncation_warnings(data))
                match = self.matcher.find_match(data, root_domain)
                if match:
                    evidence = AttributionEvidence(self.name, ip,
                        REGISTRIES.get(urlsplit(response.source_url).hostname, urlsplit(response.source_url).hostname),
                        response.source_url, response.retrieved_at, response.snapshot_id,
                        tuple(dict.fromkeys((route.bootstrap_snapshot_id, network_response.snapshot_id,
                                             *ancestors, response.snapshot_id))),
                        match, {"network_handle": network.get("handle"), "network_start": network["startAddress"],
                                "network_end": network["endAddress"]}, current.from_cache)
                    return result("matched", evidence, reason="domain_match")
                for name_match, details in self.name_matcher.find_matches(data, root_domain):
                    partials.append(AttributionEvidence("rdap_keyword", ip,
                        REGISTRIES.get(urlsplit(response.source_url).hostname, urlsplit(response.source_url).hostname),
                        response.source_url, response.retrieved_at, response.snapshot_id,
                        tuple(dict.fromkeys((route.bootstrap_snapshot_id, network_response.snapshot_id,
                                             *ancestors, response.snapshot_id))), name_match,
                        {**details, "network_handle": network.get("handle"),
                         "network_start": network["startAddress"], "network_end": network["endAddress"]},
                        current.from_cache))
                refs, issues = entity_references(data, response.source_url)
                warnings.extend(issues)
                unresolved |= bool(issues)
                # Fetch one reference at a time. Test it before requesting the next.
                pending = []
                for handle, url in refs:
                    key = (urlsplit(url).netloc, handle)
                    if key in visited:
                        continue
                    visited.add(key)
                    if depth >= self.settings.max_entity_depth or entities_fetched >= self.settings.max_entity_requests:
                        unresolved = True
                        warnings.append("Entity retrieval budget reached")
                        continue
                    entities_fetched += 1
                    try:
                        child = self.client.fetch(url, set(route.allowed_hosts),
                            lambda record, h=handle: validate_entity(record, h), context,
                            refresh=refresh, offline=offline)
                    except LookupFailure as error:
                        unresolved = True
                        warnings.append(f"Entity lookup: {error.reason}")
                        if error.status == "deferred":
                            deferred = error
                        continue
                    if child.response.status_code != 200:
                        unresolved = True
                        warnings.append("Referenced entity was not found")
                        continue
                    child_data = child.response.record()
                    warnings.extend(truncation_warnings(child_data))
                    child_match = self.matcher.find_match(child_data, root_domain)
                    chain = (*ancestors, response.snapshot_id)
                    if child_match:
                        evidence = AttributionEvidence(self.name, ip,
                            REGISTRIES.get(urlsplit(child.response.source_url).hostname, urlsplit(child.response.source_url).hostname),
                            child.response.source_url, child.response.retrieved_at, child.response.snapshot_id,
                            tuple(dict.fromkeys((route.bootstrap_snapshot_id, network_response.snapshot_id,
                                                 *chain, child.response.snapshot_id))),
                            child_match, {"network_handle": network.get("handle"), "network_start": network["startAddress"],
                                          "network_end": network["endAddress"]}, child.from_cache)
                        return result("matched", evidence, reason="domain_match")
                    pending.append((child, depth + 1, chain))
                queue.extend(pending)
            if deferred:
                return result("deferred", reason=deferred.reason, message=str(deferred), retry_at=deferred.retry_at)
            if unresolved or warnings:
                return result("incomplete", reason="incomplete_data", message="No match in the available registration data")
            return result("no_match", reason="domain_absent", message="Domain absent from the retrieved registration fields")
        except LookupFailure as error:
            return result(error.status, reason=error.reason, message=str(error), retry_at=error.retry_at)
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            return result("incomplete", reason="invalid_response", message=str(error))

