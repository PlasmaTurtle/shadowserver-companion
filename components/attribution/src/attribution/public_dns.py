"""Two independently identified public DNS observations within one bounded lookup."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from ipaddress import ip_address

from .cloudflare_dns import CloudflareDnsProvider
from .google_dns import GooglePublicDnsProvider, validated_answers
from .models import LookupFailure, ProviderResult, Settings
from .matching import normalize_domain

PROVIDERS = (GooglePublicDnsProvider, CloudflareDnsProvider)


def compare_answers(answers, *, kinds=("A", "AAAA")):
    """Failures/missing responses are incomplete; only comparable answers disagree."""
    comparisons = []
    for kind in kinds:
        by_source = {
            a.get("source", {}).get("resolver"): a
            for a in answers if a.get("record_type") == kind
        }
        sources = [by_source.get(p.source_name) for p in PROVIDERS]
        if not all(sources):
            state = "incomplete"
        else:
            first, second = sources
            state = "agreement" if (
                set(first.get("addresses", [])) == set(second.get("addresses", []))
                and first.get("status") == second.get("status")
            ) else "disagreement"
        comparisons.append({"record_type": kind, "status": state})
    status = ("disagreement" if any(c["status"] == "disagreement" for c in comparisons)
              else "incomplete" if any(c["status"] == "incomplete" for c in comparisons)
              else "agreement")
    return {"status": status, "records": comparisons}


class DualPublicDnsProvider:
    name = "dns"

    def __init__(self, store, settings=None, *, transport=None, cancel_event=None):
        self.store, self.settings = store, settings or Settings()
        self.providers = tuple(
            p(store, self.settings, transport=transport, cancel_event=cancel_event)
            for p in PROVIDERS
        )

    def close(self):
        for provider in self.providers:
            provider.close()

    def describe(self):
        return {"method": "forward DNS or forward-confirmed reverse DNS",
                "resolver": "Google Public DNS + Cloudflare DNS",
                "resolvers": [p.describe() for p in self.providers],
                "comparison": "Distinct resolver responses; missing responses are incomplete"}

    def _both(self, method, *args, **kwargs):
        # EvidenceStore serializes short SQLite operations. Network waits overlap.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="public-dns") as executor:
            futures = [executor.submit(getattr(p, method), *args, **kwargs) for p in self.providers]
            return [f.result() for f in futures]

    def resolve_addresses(self, hostname, *, refresh=False, offline=False, deadline=None):
        results = self._both("resolve_addresses", hostname, refresh=refresh,
                             offline=offline, deadline=deadline)
        answers = [a for r in results for a in r["answers"]]
        return {"hostname": results[0]["hostname"], "answers": answers,
                "comparison": compare_answers(answers),
                "resolver_results": [{"resolver": p.source_name,
                                      "warnings": r["warnings"],
                                      "answered_types": [a["record_type"] for a in r["answers"]]}
                                     for p, r in zip(self.providers, results)],
                "warnings": list(dict.fromkeys(w for r in results for w in r["warnings"])),
                "network_requests": sum(r["network_requests"] for r in results),
                "cache_hits": sum(r["cache_hits"] for r in results),
                "retry_at": max((r["retry_at"] or 0 for r in results), default=0) or None}

    def collect(self, ip, root_domain, *, hostname=None, refresh=False, offline=False):
        results = self._both("collect", ip, root_domain, hostname=hostname,
                             refresh=refresh, offline=offline)
        selected = next((r for r in results if r.status == "matched" and r.evidence), None)
        snapshots = tuple(dict.fromkeys(s for r in results for s in r.snapshot_ids))
        warnings = list(dict.fromkeys(w for r in results for w in r.warnings))
        summaries, answers = [], []
        kind = "A" if ip_address(ip).version == 4 else "AAAA"
        host = normalize_domain(hostname or root_domain)
        for provider, result in zip(self.providers, results):
            summaries.append({"resolver": provider.source_name, "status": result.status,
                              "reason": result.reason, "snapshot_ids": list(result.snapshot_ids),
                              "warnings": list(result.warnings)})
            url = provider.query_url(host.rstrip(".").lower() + ".", kind)
            for snapshot_id in result.snapshot_ids:
                snapshot = self.store.snapshot(snapshot_id)
                if snapshot.requested_url != url or snapshot.status_code != 200:
                    continue
                try:
                    values, _, _, _ = validated_answers(snapshot.record(), host, kind)
                except (LookupFailure, ValueError, KeyError, TypeError):
                    continue
                answers.append({"record_type": kind, "addresses": [v[0] for v in values],
                                "status": "nxdomain" if snapshot.record()["Status"] == 3
                                          else "answer" if values else "no_answer",
                                "source": {"resolver": provider.source_name}})
                break
        comparison = compare_answers(answers, kinds=(kind,))
        if comparison["status"] == "disagreement":
            warnings.append("dns_resolver_disagreement")
        evidence = None
        if selected:
            evidence = replace(selected.evidence, supporting_snapshot_ids=snapshots,
                details={**selected.evidence.details, "resolver_comparison": comparison,
                         "resolver_results": summaries})
        status = "matched" if evidence else (
            "deferred" if any(r.status == "deferred" for r in results) else results[0].status)
        reason = selected.reason if selected else next(
            (r.reason for r in results if r.status == "deferred"), results[0].reason)
        return ProviderResult(status, evidence, reason, reason.replace("_", " "), snapshots,
            retry_at=max((r.retry_at or 0 for r in results), default=0) or None,
            warnings=tuple(dict.fromkeys(warnings)),
            network_requests=sum(r.network_requests for r in results),
            cache_hits=sum(r.cache_hits for r in results))
