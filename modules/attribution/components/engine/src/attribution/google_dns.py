"""Google Public DNS JSON-over-HTTPS with preserved responses and strict matching.

Google Public DNS is a recursive resolver, not an authoritative name server.
The fixed service URL identifies the provider; saved bytes identify the actual
observation used, even when a later lookup returns a different answer.
"""
from __future__ import annotations

import threading
import time
from ipaddress import ip_address
from urllib.parse import urlencode, urlsplit

import dns.reversename
import httpx

from .bounded_http import CaptureCancelled, capture_response
from .http import SAVED_HEADERS, response_ttl, retry_delay
from .matching import domain_equal_or_below, normalize_domain
from .models import AttributionEvidence, DomainMatch, LookupFailure, ProviderResult, ResponseSnapshot, Settings, VERSION
from .rdap import eligible_ip, normalize_ip

ENDPOINT = "https://dns.google/resolve"
DOCUMENTATION = "https://developers.google.com/speed/public-dns/docs/doh/json"
SOURCE_NAME = "Google Public DNS"
TYPES = {"A": 1, "AAAA": 28, "PTR": 12}


def query_url(name, kind):
    return ENDPOINT + "?" + urlencode({"name": name, "type": kind, "cd": "false",
                                       "edns_client_subnet": "0.0.0.0/0"})


def _name(value):
    if not isinstance(value, str) or value != value.strip() or not value.isascii():
        raise ValueError("Invalid DNS name")
    return normalize_domain(value)


def validated_answers(data, name, kind):
    """Return only records reachable from the exact question by one CNAME chain."""
    number = TYPES[kind]
    status = data.get("Status")
    if type(status) is not int or not 0 <= status <= 65535:
        raise ValueError("Invalid DNS status")
    for flag in ("TC", "RD", "RA", "AD", "CD"):
        if type(data.get(flag)) is not bool:
            raise ValueError("Missing or invalid DNS response flag")
    if data["TC"] or data["CD"] or not data["RD"] or not data["RA"]:
        raise ValueError("Truncated or conflicting DNS response")
    question = data.get("Question")
    if (not isinstance(question, list) or len(question) != 1
            or not isinstance(question[0], dict)
            or type(question[0].get("type")) is not int
            or question[0]["type"] != number
            or _name(question[0].get("name")) != _name(name)):
        raise ValueError("DNS response question differs from the request")
    if status not in (0, 3):
        raise LookupFailure("dns_service_error", f"Public DNS returned DNS status {status}")
    rows = data.get("Answer", [])
    if not isinstance(rows, list) or len(rows) > 1024:
        raise ValueError("Invalid DNS answer section")
    records = []
    for index, row in enumerate(rows):
        if (not isinstance(row, dict) or type(row.get("type")) is not int
                or type(row.get("TTL")) is not int or not 0 <= row["TTL"] <= 2147483647
                or not isinstance(row.get("data"), str)):
            raise ValueError("Malformed DNS answer")
        if row["type"] in (5, number):
            records.append((index, row, _name(row.get("name"))))
    if status == 3:
        # A negative response cannot qualify an address, even if it contains one.
        if any(row["type"] == number for _, row, _ in records):
            raise ValueError("NXDOMAIN contains address answers")
        return [], 0.0, [], data["AD"]
    current, chain, seen, ttls = _name(name), [], set(), []
    for _ in range(17):
        if current in seen:
            raise ValueError("DNS alias loop")
        seen.add(current)
        aliases = [row for _, row, owner in records if owner == current and row["type"] == 5]
        values = [(index, row) for index, row, owner in records if owner == current and row["type"] == number]
        if aliases:
            targets = {_name(row["data"]) for row in aliases}
            if values or len(targets) != 1:
                raise ValueError("Conflicting DNS alias answers")
            current = targets.pop()
            chain.append(current)
            ttls.extend(row["TTL"] for row in aliases)
            continue
        output = []
        for index, row in values:
            value = _name(row["data"]) if kind == "PTR" else normalize_ip(row["data"])
            if kind != "PTR" and ip_address(value).version != (4 if kind == "A" else 6):
                raise ValueError("DNS address family differs from requested record type")
            output.append((value, index, row["data"]))
            ttls.append(row["TTL"])
        return output, min(ttls) if output else 0.0, chain, data["AD"]
    raise ValueError("DNS alias limit exceeded")


class GooglePublicDnsProvider:
    name = "dns"
    source_name = SOURCE_NAME
    endpoint = ENDPOINT
    documentation = DOCUMENTATION
    accept = "application/json"
    query_url = staticmethod(query_url)

    def __init__(self, store, settings=None, *, transport=None, cancel_event=None):
        self.store, self.settings = store, settings or Settings()
        self.transport, self.cancel_event = transport, cancel_event
        self._lock = threading.Lock()
        self._next_request = 0.0

    def close(self):
        pass

    def describe(self):
        return {"method": "forward DNS or forward-confirmed reverse DNS", "resolver": self.source_name,
                "resolver_kind": "public recursive resolver", "transport": "DNS over HTTPS",
                "endpoint": self.endpoint, "documentation_url": self.documentation,
                "dnssec_validation_requested": True, "edns_client_subnet": "0.0.0.0/0",
                "max_ptr_names": 8, "max_cname_links": 16}

    def _remaining(self, deadline):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise LookupFailure("dns_cancelled", "DNS lookup cancelled")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LookupFailure("dns_budget_exhausted", "DNS lookup time budget exhausted")
        return remaining

    def _query(self, state, name, kind, *, refresh, offline, deadline):
        name = _name(name) + "."
        url = self.query_url(name, kind)
        try:
            self._remaining(deadline)
            cached = None if refresh else self.store.cached(url)
            if cached:
                if (len(cached) != 1 or cached[0].requested_url != url or cached[0].source_url != url
                        or cached[0].status_code != 200):
                    raise ValueError("Cached DNS response has a different source")
                parsed = validated_answers(cached[0].record(), name, kind)
                state["snapshots"].extend(cached)
                state["hits"] += 1
                state["cached_ids"].add(cached[0].snapshot_id)
                return cached[0], parsed
            if offline:
                raise LookupFailure("dns_cache_miss", f"No fresh {self.source_name} response is cached")
            while not self._lock.acquire(timeout=min(.05, self._remaining(deadline))):
                pass
            try:
                self._remaining(deadline)
                cooldown = self.store.cooldown(urlsplit(self.endpoint).hostname)
                if cooldown > time.time():
                    state["retry_at"] = cooldown
                    raise LookupFailure("dns_rate_limited", f"{self.source_name} cooldown is active")
                while self._next_request > time.monotonic():
                    time.sleep(max(0, min(.05, self._next_request - time.monotonic(), self._remaining(deadline))))
                state["requests"] += 1
                response = capture_response(url, budget=self._remaining(deadline),
                    timeout=min(self.settings.timeout, self._remaining(deadline)),
                    cancel_event=self.cancel_event, limit=self.settings.max_response_bytes,
                    decode=False, transport=self.transport,
                    headers={"Accept": self.accept, "Accept-Encoding": "identity",
                             "User-Agent": f"AttributionModule/{VERSION}"})
                snapshot = ResponseSnapshot.create(url, response.url, response.status_code,
                    {k: v for k, v in response.headers.items() if k in SAVED_HEADERS}, response.body)
                try:
                    parsed = self._validate_response(snapshot, response, url, name, kind, state)
                except (LookupFailure, ValueError, KeyError, TypeError, RecursionError):
                    snapshot = snapshot.without_body("rejected_response")
                    self.store.save_snapshot(snapshot)
                    state["snapshots"].append(snapshot)
                    raise
                self.store.save_snapshot(snapshot)
                state["snapshots"].append(snapshot)
                self.store.cache(url, [snapshot], response_ttl(snapshot.headers,
                    min(parsed[1], self.settings.cache_ttl)))
                return snapshot, parsed
            finally:
                self._next_request = time.monotonic() + self.settings.interval
                self._lock.release()
        except CaptureCancelled:
            state["errors"].append("dns_cancelled")
        except LookupFailure as error:
            state["errors"].append(error.reason)
        except httpx.HTTPError:
            # Do not retain exception messages, which can contain proxy credentials.
            state["errors"].append("dns_network_error")
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            message = str(error)
            state["errors"].append("dns_response_too_large" if "size limit" in message else
                          "dns_budget_exhausted" if "time budget" in message or "budget exhausted" in message
                          else "dns_invalid_response")
        return None

    def _validate_response(self, snapshot, response, url, name, kind, state):
        if response.status_code == 429 or (response.status_code == 503 and "retry-after" in response.headers):
            state["retry_at"] = time.time() + max(self.settings.interval, retry_delay(response.headers.get("retry-after")))
            self.store.set_cooldown(urlsplit(self.endpoint).hostname, state["retry_at"])
            raise LookupFailure("dns_rate_limited", f"{self.source_name} requested a cooldown")
        if response.status_code != 200:
            raise LookupFailure("dns_http_error", f"{self.source_name} returned HTTP {response.status_code}")
        if response.url != url:
            raise ValueError("DNS response URL differs from the fixed service request")
        if response.headers.get("content-encoding", "identity").lower() not in ("", "identity"):
            raise ValueError("Unexpected DNS response compression")
        media = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media not in ("application/json", "application/x-javascript", "application/dns-json"):
            raise ValueError("DNS response is not JSON")
        return validated_answers(snapshot.record(), name, kind)

    def resolve_addresses(self, hostname, *, refresh=False, offline=False, deadline=None):
        """Capture forward A/AAAA records without making an attribution assertion."""
        host = normalize_domain(hostname)
        deadline = min(deadline, time.monotonic() + self.settings.operation_budget) if deadline is not None else time.monotonic() + self.settings.operation_budget
        state = {"snapshots": [], "errors": [], "cached_ids": set(), "requests": 0, "hits": 0, "retry_at": None}
        answers = []
        for kind in ("A", "AAAA"):
            response = self._query(state, host, kind, refresh=refresh, offline=offline, deadline=deadline)
            if response:
                snapshot, (values, ttl, chain, authenticated) = response
                answers.append({"record_type": kind, "addresses": [value for value, _, _ in values if eligible_ip(value)],
                    "nonpublic_addresses_omitted": sum(not eligible_ip(value) for value, _, _ in values),
                    "cname_chain": chain, "ttl": ttl, "dnssec_authenticated_data": authenticated,
                    "status": "nxdomain" if snapshot.record()["Status"] == 3 else "answer" if values else "no_answer",
                    "source": {**snapshot.metadata(), "resolver": self.source_name, "resolver_kind": "public recursive resolver",
                               "transport": "DNS over HTTPS", "from_cache": snapshot.snapshot_id in state["cached_ids"]}})
            if any(error in state["errors"] for error in ("dns_cancelled", "dns_budget_exhausted", "dns_rate_limited")):
                break
        return {"hostname": host, "answers": answers, "warnings": list(dict.fromkeys(state["errors"])),
                "network_requests": state["requests"], "cache_hits": state["hits"], "retry_at": state["retry_at"]}

    def collect(self, ip, root_domain, *, hostname=None, refresh=False, offline=False):
        ip, target = normalize_ip(ip), normalize_domain(root_domain)
        host = normalize_domain(hostname or target)
        if not eligible_ip(ip):
            return ProviderResult("skipped", reason="nonpublic_ip")
        if not domain_equal_or_below(host, target):
            return ProviderResult("incomplete", reason="hostname_outside_group")
        deadline = time.monotonic() + self.settings.operation_budget
        state = {"snapshots": [], "errors": [], "cached_ids": set(), "requests": 0, "hits": 0, "retry_at": None}
        snapshots, errors, cached_ids = state["snapshots"], state["errors"], state["cached_ids"]

        def result(status, reason, evidence=None):
            return ProviderResult(status, evidence, reason, reason.replace("_", " "),
                tuple(s.snapshot_id for s in snapshots), retry_at=state["retry_at"],
                warnings=tuple(dict.fromkeys(errors)), network_requests=state["requests"], cache_hits=state["hits"])

        def query(name, kind):
            return self._query(state, name, kind, refresh=refresh, offline=offline, deadline=deadline)

        kind = "A" if ip_address(ip).version == 4 else "AAAA"

        def evidence(response, matched_host, basis):
            if not response:
                return None
            snapshot, (values, _, chain, authenticated) = response
            for value, index, original in values:
                if value == ip:
                    return AttributionEvidence("dns", ip, self.source_name, snapshot.source_url,
                        snapshot.retrieved_at, snapshot.snapshot_id, tuple(s.snapshot_id for s in snapshots),
                        DomainMatch(target, matched_host, f"/Answer/{index}/data", original, field_type="dns_address"),
                        {"dns_forward_match": True, "basis": basis, "reported_hostname": host,
                         "resolved_hostname": matched_host, "record_type": kind, "cname_chain": chain,
                         "resolver_kind": "public recursive resolver", "transport": "DNS over HTTPS",
                         "dnssec_authenticated_data": authenticated, "documentation_url": self.documentation,
                         "observation": "Current DNS association; original reported hostname and IP retained"},
                        from_cache=snapshot.snapshot_id in cached_ids)
            return None

        forward = query(host, kind)
        matched = evidence(forward, host, "forward")
        if matched:
            return result("matched", "dns_forward_match", matched)
        if any(e in errors for e in ("dns_cancelled", "dns_budget_exhausted", "dns_rate_limited")):
            return result("deferred", errors[0])
        reverse = query(dns.reversename.from_address(ip).to_text(), "PTR")
        if reverse:
            names = reverse[1][0]
            if len(names) > 8:
                errors.append("dns_ptr_limit")
            for name, _, _ in names[:8]:
                if not domain_equal_or_below(name, target) or name == host:
                    continue
                confirmed = query(name, kind)
                matched = evidence(confirmed, name, "forward_confirmed_reverse")
                if matched:
                    return result("matched", "dns_reverse_confirmed", matched)
                if any(e in errors for e in ("dns_cancelled", "dns_budget_exhausted", "dns_rate_limited")):
                    break
        return result("deferred" if errors else "no_match", errors[0] if errors else "dns_no_match")
