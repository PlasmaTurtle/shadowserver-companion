"""Bounded background enrichment; fetching never adopts evidence into a case."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import threading
from .primitives import now, uid


class SourceJobs:
    def __init__(self, store, fetch):
        self.store, self.fetch = store, fetch
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="companion-sources")
        self.lock = threading.RLock()
        self.jobs = {}

    def start(self, cve_ids, refresh=False, *, local_only=False):
        ids = list(dict.fromkeys(cve_ids))
        if not ids or len(ids) > 1000:
            raise ValueError("Select between 1 and 1,000 CVEs")
        with self.lock:
            if sum(j["status"] in ("queued", "running") for j in self.jobs.values()) >= 4:
                raise ValueError("Four source jobs are already queued or running")
            # Bounded in-memory progress. Immutable evidence stays in the bank.
            for old in [
                k for k, j in self.jobs.items() if j["status"] not in ("queued", "running")
            ][:-20]:
                self.jobs.pop(old, None)
            identity = uid()
            self.jobs[identity] = {
                "id": identity,
                "created_at": now(),
                "status": "queued",
                "total": len(ids),
                "completed": 0,
                "current_cve": None,
                "results": [],
                "errors": [],
                "cancel": threading.Event(),
            }
            self.pool.submit(self._run, identity, ids, refresh, local_only)
        return self.get(identity)

    def _run(self, identity, ids, refresh, local_only=False):
        job = self.jobs[identity]
        with self.lock:
            job.update(status="running", started_at=now())
        try:
            for cve_id in ids:
                if job["cancel"].is_set():
                    break
                with self.lock:
                    job["current_cve"] = cve_id
                try:
                    result = self.fetch(
                        self.store,
                        cve_id,
                        refresh=refresh,
                        cancel_event=job["cancel"],
                        **({"local_only": True} if local_only else {}),
                    )
                    with self.lock:
                        job["results"].append(result)
                except Exception as error:
                    with self.lock:
                        job["errors"].append(
                            {"cve_id": cve_id, "error": str(error), "attempted_at": now()}
                        )
                with self.lock:
                    job["completed"] += 1
            with self.lock:
                job["status"] = "cancelled" if job["cancel"].is_set() else "completed"
        finally:
            with self.lock:
                job.update(finished_at=now(), current_cve=None)

    def get(self, identity):
        with self.lock:
            if identity not in self.jobs:
                raise ValueError(
                    "Source job is unavailable; saved evidence remains in the CVE bank"
                )
            return deepcopy({k: v for k, v in self.jobs[identity].items() if k != "cancel"})

    def cancel(self, identity):
        with self.lock:
            if identity not in self.jobs:
                raise ValueError("Source job not found")
            self.jobs[identity]["cancel"].set()
        return self.get(identity)

    def close(self):
        with self.lock:
            for job in self.jobs.values():
                job["cancel"].set()
        self.pool.shutdown(wait=False, cancel_futures=True)

    def busy(self):
        with self.lock:
            return any(j["status"] in ("queued", "running") for j in self.jobs.values())
