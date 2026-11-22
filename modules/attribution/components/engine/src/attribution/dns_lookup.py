"""Named HTTPS DNS fallback; explicit resolver injection retains legacy evidence."""
from __future__ import annotations

import base64
import time
from ipaddress import ip_address
from urllib.parse import quote

import dns.exception
import dns.resolver
import dns.reversename

from .matching import domain_equal_or_below, normalize_domain
from .models import (AttributionEvidence, DomainMatch, ProviderResult,
                     ResponseSnapshot, Settings, json_bytes)
from .rdap import eligible_ip, normalize_ip
from .google_dns import GooglePublicDnsProvider


class DnsProvider:
    name = "dns"

    def __init__(self, store, settings=None, *, resolver=None, transport=None, cancel_event=None):
        self.store, self.settings, self.resolver = store, settings or Settings(), resolver
        self._google = (GooglePublicDnsProvider(store, self.settings, transport=transport,
                        cancel_event=cancel_event) if resolver is None else None)

    def close(self):
        pass

    def describe(self):
        if self._google is not None:
            return self._google.describe()
        return {"method": "forward DNS or forward-confirmed reverse DNS",
                "resolver": "workstation configuration", "max_ptr_names": 8}

    def collect(self, ip, root_domain, *, hostname=None, refresh=False, offline=False):
        if self._google is not None:
            return self._google.collect(ip, root_domain, hostname=hostname,
                                        refresh=refresh, offline=offline)
        ip, target = normalize_ip(ip), normalize_domain(root_domain)
        host = normalize_domain(hostname or target)
        if not eligible_ip(ip):
            return ProviderResult("skipped", reason="nonpublic_ip")
        if not domain_equal_or_below(host, target):
            return ProviderResult("incomplete", reason="hostname_outside_group")
        deadline = time.monotonic() + self.settings.operation_budget
        snapshots, errors, cached_ids = [], [], set()
        requests = hits = 0
        resolver = self.resolver

        def result(status, reason, evidence=None):
            return ProviderResult(status, evidence, reason, reason.replace("_", " "),
                tuple(s.snapshot_id for s in snapshots), warnings=tuple(dict.fromkeys(errors)),
                network_requests=requests, cache_hits=hits)

        def query(name, kind):
            nonlocal resolver, requests, hits
            # Absolute query names: never append a workstation's search suffix.
            name = name.rstrip(".") + "."
            if resolver is None and not offline:
                try:
                    resolver = dns.resolver.Resolver()
                except (dns.exception.DNSException, OSError) as exc:
                    errors.append("dns_configuration_error")
                    return None
            nameservers = [str(n) for n in resolver.nameservers] if resolver else []
            key = f"dns:v1:{name}:{kind}"
            if not refresh:
                cached = self.store.cached(key)
                if cached and (offline or cached[0].record().get("resolvers") == nameservers):
                    snapshots.extend(cached); hits += 1
                    cached_ids.update(s.snapshot_id for s in cached)
                    return cached[0]
            if offline:
                errors.append("dns_cache_miss")
                return None
            lifetime = min(self.settings.timeout, deadline - time.monotonic())
            if lifetime <= 0:
                errors.append("dns_budget_exhausted")
                return None
            payload = {"query": name, "type": kind, "resolvers": nameservers,
                       "answers": [], "responses": [], "status": "no_answer"}
            ttl = 0.0
            try:
                requests += 1
                answer = resolver.resolve(name, kind, search=False, lifetime=lifetime,
                                          raise_on_no_answer=False)
                payload.update(answers=[r.to_text().rstrip(".") for r in answer],
                               canonical_name=answer.canonical_name.to_text(),
                               responding_resolver=str(answer.nameserver),
                               status="answer" if answer.rrset else "no_answer")
                payload["responses"] = [{"text": answer.response.to_text(),
                    "wire_base64": base64.b64encode(answer.response.to_wire()).decode("ascii")}]
                ttl = max(0, answer.expiration - time.time())
            except dns.resolver.NXDOMAIN as exc:
                payload["status"] = "nxdomain"
                for response in exc.responses().values():
                    payload["responses"].append({"text": response.to_text(),
                        "wire_base64": base64.b64encode(response.to_wire()).decode("ascii")})
                    for rrset in response.authority:
                        for rdata in rrset:
                            if hasattr(rdata, "minimum"):
                                ttl = min(rrset.ttl, rdata.minimum, 30)
            except (dns.exception.DNSException, OSError) as exc:
                payload.update(status="error", error_type=type(exc).__name__, error=str(exc))
                errors.append("dns_" + type(exc).__name__.lower())
            url = f"dns://system/{quote(name, safe='.')}/{kind}"
            snapshot = ResponseSnapshot.create(url, url, 200,
                {"content-type": "application/json", "evidence-protocol": "DNS"}, json_bytes(payload))
            self.store.save_snapshot(snapshot)
            snapshots.append(snapshot)
            if payload["status"] != "error":
                self.store.cache(key, [snapshot], min(ttl, self.settings.cache_ttl))
            return snapshot

        kind = "A" if ip_address(ip).version == 4 else "AAAA"

        def qualifies(snapshot):
            if not snapshot:
                return False
            for value in snapshot.record()["answers"]:
                try:
                    if normalize_ip(value) == ip:
                        return True
                except ValueError:
                    pass
            return False

        def evidence(snapshot, matched_host, basis):
            return AttributionEvidence("dns", ip, "Workstation DNS resolver", snapshot.source_url,
                snapshot.retrieved_at, snapshot.snapshot_id, tuple(s.snapshot_id for s in snapshots),
                DomainMatch(target, matched_host, "/answers", ", ".join(snapshot.record()["answers"]),
                            field_type="dns_address"),
                {"dns_forward_match": True, "basis": basis, "reported_hostname": host,
                 "resolved_hostname": matched_host, "record_type": kind,
                 "observation": "Current DNS association; original reported hostname and IP retained"},
                from_cache=snapshot.snapshot_id in cached_ids)

        forward = query(host, kind)
        if qualifies(forward):
            return result("matched", "dns_forward_match", evidence(forward, host, "forward"))
        reverse = query(dns.reversename.from_address(ip).to_text(), "PTR")
        if reverse:
            names = reverse.record()["answers"]
            if len(names) > 8:
                errors.append("dns_ptr_limit")
            for name in names[:8]:
                try:
                    name = normalize_domain(name)
                except ValueError:
                    continue
                if not domain_equal_or_below(name, target) or name == host:
                    continue
                confirmed = query(name, kind)
                if qualifies(confirmed):
                    return result("matched", "dns_reverse_confirmed", evidence(confirmed, name, "forward_confirmed_reverse"))
        return result("deferred" if errors else "no_match", errors[0] if errors else "dns_no_match")
