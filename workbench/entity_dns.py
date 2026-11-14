"""Cached root-domain DNS supplements, separate from observed pairs and attribution."""

from contextlib import closing
from copy import deepcopy
import threading
import logging
import math
import sqlite3
import time

from attribution import EvidenceStore
from attribution.google_dns import query_url, validated_answers
from attribution.cloudflare_dns import query_url as cloudflare_query_url
from attribution.public_dns import DualPublicDnsProvider, compare_answers
from attribution.matching import normalize_domain
from attribution.models import Settings
from attribution.rdap import eligible_ip

from .intake.domains import EXTRACT_DOMAIN
from .primitives import now, uid
from .repositories.sources import SourceRepository

MAX_ROOTS_PER_JOB = 24
MAX_VISIBLE_ROOTS = 128
JOB_BUDGET = 35.0
SEMANTICS = (
    "Root domains are derived using the bundled public suffix list. DNS is a current public "
    "resolver observation, not a reported exposure or proof of common ownership."
)


def root_scopes(entity):
    """Derive registrable roots offline, including private PSL suffix boundaries."""
    manual = {
        row.get("name")
        for row in entity.get("hostnames", [])
        if isinstance(row, dict) and row.get("association_basis") == "manual"
    }
    reported = set()
    values = []
    values.extend(
        row.get("name") if isinstance(row, dict) else row for row in entity.get("hostnames", [])
    )
    for row in entity.get("entries", []):
        fields = row.get("source", {}).get("fields") or row.get("normalized") or row
        value = row.get("hostname") or fields.get("hostname")
        values.append(value)
        reported.add(value)
    roots = {}
    try:
        identity_root = EXTRACT_DOMAIN(
            normalize_domain(entity.get("domain"))
        ).top_domain_under_public_suffix
        if identity_root:
            roots[identity_root] = set()
    except ValueError, TypeError:
        pass
    for value in values:
        try:
            host = normalize_domain(value)
            root = EXTRACT_DOMAIN(host).top_domain_under_public_suffix
        except ValueError, TypeError:
            continue
        if not root:
            continue
        roots.setdefault(root, set()).add(host)
    return [
        {
            "root_domain": root,
            "reported_hostnames": sorted(h for h in hosts if h not in manual or h in reported),
            "associated_hostnames": sorted(hosts),
            "kind": "registrable_domain",
        }
        for root, hosts in sorted(roots.items())
    ]


class EntityDNS:
    """Background, bounded DNS lookups whose display does not alter an entity or case."""

    def __init__(self, store, *, provider_factory=DualPublicDnsProvider):
        self.store = store
        self.provider_factory = provider_factory
        self.lock = threading.RLock()
        self.semaphore = threading.Semaphore(2)
        self.stop = threading.Event()
        self.jobs = {}
        self.root_locks = {}

    def _cached(self, root):
        try:
            value = SourceRepository(self.store).payload("entity-dns:v1:" + root)
            if not isinstance(value, dict) or value.get("hostname") != root:
                return None
            if any(
                type(value.get(key)) not in (int, float) or not math.isfinite(value[key])
                for key in ("expires_at", "next_attempt_at")
            ):
                return None
            # Do not trust a derived summary if its original response has changed.
            answers = []
            with closing(EvidenceStore(self.store.root / "attribution.sqlite3")) as evidence:
                for answer in value.get("answers", []):
                    kind = answer["record_type"]
                    if kind not in ("A", "AAAA"):
                        return None
                    snapshot = evidence.snapshot(answer["source"]["snapshot_id"])
                    resolver = answer.get("source", {}).get("resolver", "Google Public DNS")
                    if resolver not in ("Google Public DNS", "Cloudflare DNS"):
                        return None
                    make_url = cloudflare_query_url if resolver == "Cloudflare DNS" else query_url
                    url = make_url(root + ".", kind)
                    if (
                        snapshot.requested_url != url
                        or snapshot.source_url != url
                        or snapshot.status_code != 200
                    ):
                        return None
                    parsed, ttl, chain, authenticated = validated_answers(
                        snapshot.record(), root, kind
                    )
                    public = sorted({address for address, _, _ in parsed if eligible_ip(address)})
                    answers.append(
                        {
                            **answer,
                            "addresses": public,
                            "cname_chain": chain,
                            "ttl": ttl,
                            "dnssec_authenticated_data": authenticated,
                            "source": {**answer["source"], **snapshot.metadata()},
                        }
                    )
            if self.provider_factory is DualPublicDnsProvider and not value.get("resolver_results"):
                return None
            comparison = compare_answers(answers)
            if value.get("retained_previous_answers"):
                comparison = {**comparison, "status": "incomplete"}
            return {
                **value,
                "answers": answers,
                "comparison": comparison,
                "stale": value.get("expires_at", 0) <= time.time(),
            }
        except OSError, ValueError, KeyError, TypeError, AttributeError, sqlite3.Error:
            return None

    def status(self, entity):
        # Capture progress before loading results. If a worker commits and
        # finishes during those reads, this response remains running; the next
        # poll can then pair completion with the newly committed lookup.
        with self.lock:
            job = deepcopy(self.jobs.get(entity["id"], {"status": "idle"}))
        scopes = root_scopes(entity)
        records = []
        missing = 0
        for scope in scopes:
            cached = self._cached(scope["root_domain"])
            if cached is None or cached.get("next_attempt_at", 0) <= time.time():
                missing += 1
            if len(records) < MAX_VISIBLE_ROOTS:
                records.append({**scope, "lookup": cached})
        disabled = bool(entity.get("demo"))
        return {
            "entity_id": entity["id"],
            "roots": records,
            "total_roots": len(scopes),
            "roots_remaining": missing,
            "truncated": len(scopes) > len(records),
            "running": job["status"] in ("queued", "running"),
            "job": job,
            "needs_lookup": bool(missing)
            and not disabled
            and job.get("next_attempt_at", 0) <= time.time(),
            "disabled": disabled,
            "semantics": SEMANTICS,
        }

    def busy(self):
        with self.lock:
            return any(job.get("status") in ("queued", "running") for job in self.jobs.values())

    def start(self, entity, *, refresh=False):
        if self.stop.is_set():
            raise ValueError("DNS connections are closing")
        if entity.get("demo"):
            return self.status(entity)
        with self.lock:
            if getattr(self.store, "maintenance", threading.Event()).is_set():
                raise ValueError("A workspace data operation or update is in progress")
            if (
                not refresh
                and self.jobs.get(entity["id"], {}).get("next_attempt_at", 0) > time.time()
            ):
                return self.status(entity)
            if self.jobs.get(entity["id"], {}).get("status") in ("queued", "running"):
                return self.status(entity)
            if sum(j.get("status") in ("queued", "running") for j in self.jobs.values()) >= 16:
                raise ValueError("DNS lookups are busy; try again shortly")
            due = []
            for scope in root_scopes(entity):
                cached = self._cached(scope["root_domain"])
                if refresh or cached is None or cached.get("next_attempt_at", 0) <= time.time():
                    due.append((cached is not None, scope["root_domain"]))
            # Resolve previously unseen roots before rechecking stale roots on large entities.
            roots = [root for _, root in sorted(due)[:MAX_ROOTS_PER_JOB]]
            if not roots:
                return self.status(entity)
            self.jobs[entity["id"]] = {
                "status": "queued",
                "completed": 0,
                "total": len(roots),
                "started_at": now(),
                "message": "Resolving root domains",
                "error": None,
            }
            threading.Thread(
                target=self._run,
                args=(entity["id"], roots, refresh),
                daemon=True,
                name="entity-root-dns",
            ).start()
        return self.status(entity)

    def _run(self, entity_id, roots, refresh):
        acquired = False
        try:
            while not self.stop.is_set():
                if self.semaphore.acquire(timeout=0.1):
                    acquired = True
                    break
            if not acquired:
                return
            with self.lock:
                self.jobs[entity_id]["status"] = "running"
            deadline = time.monotonic() + JOB_BUDGET
            with closing(EvidenceStore(self.store.root / "attribution.sqlite3")) as evidence:
                provider = self.provider_factory(
                    evidence,
                    Settings(
                        timeout=5, operation_budget=12, max_response_bytes=262144, cache_ttl=3600
                    ),
                    cancel_event=self.stop,
                )
                try:
                    for root in roots:
                        if self.stop.is_set() or time.monotonic() >= deadline:
                            break
                        with self.lock:
                            root_lock = self.root_locks.setdefault(root, threading.Lock())
                        if not root_lock.acquire(timeout=max(0.01, deadline - time.monotonic())):
                            break
                        try:
                            cached = self._cached(root)
                            if (
                                not refresh
                                and cached
                                and cached.get("next_attempt_at", 0) > time.time()
                            ):
                                continue
                            result = provider.resolve_addresses(
                                root, refresh=refresh, deadline=deadline
                            )
                            moment = time.time()
                            ttls = [
                                answer["ttl"] for answer in result["answers"] if answer["addresses"]
                            ]
                            ttl = min(min(ttls), 3600) if ttls else 300
                            failed = bool(result["warnings"])
                            result.update(
                                revision_id=uid(),
                                checked_at=now(),
                                expires_at=moment + ttl,
                                next_attempt_at=max(
                                    moment + (300 if failed else max(60, ttl)),
                                    result.get("retry_at") or 0,
                                ),
                                resolver="Google Public DNS + Cloudflare DNS"
                                if self.provider_factory is DualPublicDnsProvider
                                else "Google Public DNS",
                                resolver_kind="public recursive resolver",
                            )
                            # A failed refresh keeps previous good answers visible with their original times.
                            if (
                                failed
                                and not result["answers"]
                                and cached
                                and cached.get("answers")
                            ):
                                result["answers"] = cached["answers"]
                                result["expires_at"] = cached.get("expires_at", moment)
                                result["retained_previous_answers"] = True
                            with self.store.transaction() as db:
                                SourceRepository.put(db, "entity-dns:v1:" + root, result)
                                SourceRepository.put(
                                    db,
                                    "entity-dns-revision:" + result["revision_id"],
                                    result,
                                    immutable=True,
                                )
                        finally:
                            root_lock.release()
                            with self.lock:
                                self.jobs[entity_id]["completed"] += 1
                finally:
                    provider.close()
            with self.lock:
                self.jobs[entity_id].update(
                    status="complete", completed_at=now(), message="Root DNS updated"
                )
        except Exception as error:
            logging.getLogger(__name__).warning("Root DNS job failed: %s", type(error).__name__)
            with self.lock:
                self.jobs[entity_id].update(
                    status="error",
                    completed_at=now(),
                    next_attempt_at=time.time() + 300,
                    error="Root DNS lookup could not finish. Existing observations are unchanged.",
                )
        finally:
            if acquired:
                self.semaphore.release()

    def close(self):
        self.stop.set()
