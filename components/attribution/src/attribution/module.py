"""Provider-independent orchestration and the notification qualification rule."""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable, Protocol
from uuid import uuid4

from .matching import domain_equal_or_below, normalize_domain
from .models import (AttributionEvidence, AttributionResult, Attempt, CandidateIP,
                     LookupFailure, Settings, utc_now)
from .rdap import AttributionProvider, RdapProvider, eligible_ip, normalize_ip
from .store import EvidenceStore
from .public_dns import DualPublicDnsProvider


class QualificationPolicy(Protocol):
    def accepts(self, domain: str, evidence: AttributionEvidence) -> bool: ...
    def describe(self) -> dict: ...


@dataclass(frozen=True)
class RootDomainPolicy:
    allowed_methods: tuple[str, ...] = ("rdap", "dns")

    def accepts(self, domain, evidence):
        return (evidence.method in self.allowed_methods
                and evidence.match.target_domain == domain
                and domain_equal_or_below(evidence.match.matched_domain, domain)
                and (evidence.method != "dns" or evidence.details.get("dns_forward_match") is True))

    def describe(self):
        return {"id": "root-domain-v2", "allowed_methods": list(self.allowed_methods),
                "rule": "Exact root/subdomain in registration content, or a root/subdomain resolving to the reported IP",
                "matcher_version": "registration-domain-v1", "review_matcher": "registration-words-v1",
                "review_rule": "Any registration-name word occurring in the root label requires analyst review"}


class AttributionModule:
    def __init__(self, store: EvidenceStore, *, providers: Iterable[AttributionProvider] | None = None,
                 policy: QualificationPolicy | None = None, settings: Settings | None = None,
                 cancel_event=None):
        self.store, self.settings = store, settings or Settings()
        self.cancel_event = cancel_event
        self.policy = policy or RootDomainPolicy()
        self._owns_store = False
        self._owned = []
        if providers is None:
            rdap = RdapProvider(store, self.settings)
            self.providers = (rdap, DualPublicDnsProvider(store, self.settings, cancel_event=cancel_event)) if self.settings.enable_dns else (rdap,)
            self._owned.append(rdap)
        else:
            self.providers = tuple(providers)
        if not self.providers or len({p.name for p in self.providers}) != len(self.providers):
            raise ValueError("Supply at least one provider, with distinct provider names")

    @classmethod
    def open(cls, path: str | Path, **kwargs):
        store = EvidenceStore(path)
        try:
            module = cls(store, **kwargs)
        except Exception:
            store.close()
            raise
        module._owns_store = True
        return module

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        for provider in self._owned:
            provider.close()
        self._owned.clear()
        if self._owns_store:
            self.store.close()
            self._owns_store = False

    def attribute(self, root_domain: str, candidates: Iterable[CandidateIP], *, refresh=False,
                  offline=False) -> AttributionResult:
        if refresh and offline:
            raise ValueError("refresh and offline are mutually exclusive")
        domain = normalize_domain(root_domain)
        entries = tuple(candidates)
        if any(not isinstance(c, CandidateIP) or not isinstance(c.entry_id, str)
               or not c.entry_id.strip() or not isinstance(c.ip, str) for c in entries):
            raise ValueError("Each candidate needs a nonblank string entry_id and a string IP")
        if len({c.entry_id for c in entries}) != len(entries):
            raise ValueError("Candidate entry IDs must be unique within a group")
        attempts, seen, partials = [], set(), []
        evidence, matched = None, None
        eligible = 0
        for candidate in entries:
            if self.cancel_event is not None and self.cancel_event.is_set():
                raise LookupFailure("cancelled", "Attribution cancelled")
            try:
                ip = normalize_ip(candidate.ip)
            except ValueError:
                attempts.append(Attempt(candidate.entry_id, candidate.ip, "input", "incomplete", "invalid_ip"))
                continue
            try:
                host = normalize_domain(candidate.hostname) if candidate.hostname else domain
                if not domain_equal_or_below(host, domain):
                    raise ValueError("Hostname is outside its root-domain group")
            except ValueError:
                attempts.append(Attempt(candidate.entry_id, ip, "input", "incomplete", "invalid_hostname"))
                continue
            key = (ip, host)
            if key in seen:
                attempts.append(Attempt(candidate.entry_id, ip, "input", "skipped", "duplicate_ip"))
                continue
            seen.add(key)
            if not eligible_ip(ip):
                attempts.append(Attempt(candidate.entry_id, ip, "input", "skipped", "nonpublic_ip"))
                continue
            eligible += 1
            for provider in self.providers:
                if self.cancel_event is not None and self.cancel_event.is_set():
                    raise LookupFailure("cancelled", "Attribution cancelled")
                try:
                    options = {"refresh": refresh, "offline": offline}
                    if provider.name == "dns":
                        options["hostname"] = host
                    response = provider.collect(ip, domain, **options)
                except LookupFailure as error:
                    attempts.append(Attempt(candidate.entry_id, ip, provider.name, error.status,
                        error.reason, str(error), error.snapshot_ids, error.retry_at))
                    continue
                status, reason, message = response.status, response.reason, response.message
                for partial in response.partial_evidence:
                    if (provider.name == "rdap" and partial.method == "rdap_keyword"
                            and partial.ip == ip and partial.match.target_domain == domain
                            and partial.details.get("matched_words")):
                        partials.append(replace(partial, details={**partial.details, "entry_id": candidate.entry_id}))
                if status == "matched":
                    supplied = response.evidence
                    # A provider cannot qualify an unrelated input or bypass the module's policy.
                    try:
                        valid = (supplied is not None and normalize_ip(supplied.ip) == ip
                                 and supplied.method == provider.name
                                 and self.policy.accepts(domain, supplied))
                    except ValueError:
                        valid = False
                    if valid:
                        evidence, matched = supplied, candidate
                    else:
                        status, reason, message = "incomplete", "policy_rejected", "Provider evidence did not satisfy the attribution policy"
                elif status not in ("no_match", "incomplete", "deferred", "skipped"):
                    status, reason, message = "incomplete", "provider_contract", "Provider returned an unsupported status"
                attempts.append(Attempt(candidate.entry_id, ip, provider.name, status, reason, message,
                    response.snapshot_ids, response.retry_at, response.warnings,
                    response.network_requests, response.cache_hits))
                if evidence:
                    break
            if evidence:
                break
        if evidence:
            status = "matched"
        elif partials:
            status = "review"
        elif any(a.status == "deferred" for a in attempts):
            status = "deferred"
        elif any(a.status == "incomplete" for a in attempts):
            status = "incomplete"
        elif not eligible:
            status = "no_eligible_ip"
        else:
            status = "no_match"
        result = AttributionResult(uuid4().hex, domain, status, utc_now(), entries,
            matched.entry_id if matched else None, evidence.ip if evidence else None,
            (evidence,) if evidence else (), tuple(attempts), self.policy.describe(),
            {"module": asdict(self.settings), "providers": {
                p.name: p.describe() if callable(getattr(p, "describe", None)) else {} for p in self.providers}},
            partial_evidence=tuple(partials))
        self.store.save_result(result)
        return result

    def attribute_many(self, groups, *, workers=2, refresh=False, offline=False):
        """Yield completed groups, bounded to twice the worker count in flight.

        Input items: (root_domain, iterable_of_CandidateIP). Results arrive in completion order.
        Results are committed individually, so an interrupted batch keeps finished work.
        """
        if type(workers) is not int or not 1 <= workers <= 4:
            raise ValueError("workers must be between 1 and 4")
        groups = iter(groups)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="attribution") as executor:
            pending = set()
            def submit_one():
                try:
                    domain, candidates = next(groups)
                except StopIteration:
                    return False
                pending.add(executor.submit(self.attribute, domain, candidates, refresh=refresh, offline=offline))
                return True
            for _ in range(workers * 2):
                if not submit_one():
                    break
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    yield future.result()
                    submit_one()

