"""Overview HTTP adapters."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from contextlib import closing
from fastapi import Query
from modules import __version__
from ..release import load_release
from ..search import search_records
from ..workspace_brief import workspace_brief
from ..workspace_queue import workspace_queue
from modules.investigations.components.cases import STAGES
from modules.library.components.content_bank import snapshot_blocks
from modules.ui.components.presentation import presentation_catalog
from modules.investigations.components.package_integrity import verification_operation
from modules.accretion.components.report_profiles import (
    inventory,
    resolve_profile,
    supported_profiles,
)


def register(app, *, store, token, demo):
    release = load_release()

    @app.get("/api/health")
    def health():
        return {
            "app": "notification-workbench",
            "version": __version__,
            "demo": demo,
            "release": release,
        }

    @app.get("/api/bootstrap")
    def bootstrap():
        with closing(store.connect()) as db:
            blocks = snapshot_blocks(db)
        return {
            "token": token,
            "settings": store.settings(),
            "demo": demo,
            "workspace": str(store.root),
            "version": __version__,
            "release": release,
            "explainers": blocks,
            "notification_profiles": sorted(
                (
                    {
                        "id": key,
                        "name": inventory()[key]["name"].replace("-", " "),
                        "notification_mode": resolve_profile({}, configured_type=key)[
                            "notification_mode"
                        ],
                    }
                    for key in supported_profiles()
                ),
                key=lambda profile: profile["name"].casefold(),
            ),
            "presentation": presentation_catalog(store.settings()),
        }

    @app.get("/api/search")
    def search(
        q: str = Query(default="", max_length=120), limit: int = Query(default=6, ge=1, le=10)
    ):
        return search_records(store, q, limit)

    @app.get("/api/workspace/brief")
    def brief(as_of: date | None = None):
        return workspace_brief(store, as_of)

    # Older clients use this URL for the same Workspace queue.
    @app.get("/api/today", include_in_schema=False)
    @app.get("/api/workspace/queue")
    def workspace_priority_queue(as_of: date | None = None):
        return workspace_queue(store, as_of)

    @app.get("/api/dashboard")
    @verification_operation
    def dashboard():
        counts = {
            row["status"]: row["n"]
            for row in store.all(
                "SELECT status,count(*) n FROM leads WHERE merged_into IS NULL GROUP BY status"
            )
        }
        reports = store.all("SELECT * FROM reports ORDER BY created_at DESC")
        report_availability = {r["id"]: store.package_available(r) for r in reports}
        completed = {r["entity_id"] for r in reports if report_availability[r["id"]]}
        locations = Counter()
        tags = Counter()
        for row in store.all("SELECT payload FROM entries"):
            f = json.loads(row["payload"])["source"]["fields"]
            locations[str(f.get("region") or "Not reported")] += 1
            tags[
                "End of life"
                if "eol" in str(f.get("tag", "")).lower()
                else "Reported CVE"
                if "cve-" in str(f.get("tag", "")).lower()
                else "Other finding"
            ] += 1
        imports = store.all("SELECT * FROM imports ORDER BY created_at DESC LIMIT 6")
        totals = store.one("SELECT count(*) observations,count(DISTINCT ip) assets FROM entries")
        stage_counts = {
            r["stage"]: r["n"]
            for r in store.all("SELECT stage,count(*) n FROM cases GROUP BY stage")
        }
        closings = store.all("SELECT * FROM case_closures")
        valid_closings = sum(store.closure_available(c) for c in closings)
        workflow = {
            **{stage: stage_counts.get(stage, 0) for stage in STAGES},
            "closed": valid_closings,
            "scan_validation": store.one(
                "SELECT count(*) n FROM jobs WHERE status IN ('pending','review','deferred')"
            )["n"],
            "unparsed_imports": store.one(
                "SELECT count(*) n FROM imports i WHERE status IN ('queued','running') AND NOT EXISTS(SELECT 1 FROM jobs j WHERE j.import_id=i.id)"
            )["n"],
            "delivered_total": store.one(
                "SELECT count(*) n FROM cases WHERE delivered_at IS NOT NULL"
            )["n"],
            "closed_without_delivery": store.one(
                "SELECT count(*) n FROM cases WHERE stage='closed' AND delivered_at IS NULL"
            )["n"],
            "due": store.one(
                "SELECT count(*) n FROM cases WHERE stage!='closed' AND follow_up_date!='' AND follow_up_date<=?",
                (date.today().isoformat(),),
            )["n"],
        }

        return {
            "workflow": workflow,
            "missing_closings": len(closings) - valid_closings,
            "counts": {
                "new": counts.get("new", 0),
                "in_progress": counts.get("in_progress", 0),
                "completed": len(completed),
                "sent": len({r["entity_id"] for r in reports if r["sent_at"]}),
                **totals,
                "hostnames": store.one("SELECT count(*) n FROM hostnames")["n"],
                "review": store.one("SELECT count(*) n FROM jobs WHERE status='review'")["n"],
            },
            "imports": imports,
            "events": store.all("SELECT * FROM events ORDER BY id DESC LIMIT 8"),
            "locations": dict(locations),
            "finding_types": dict(tags),
            "trend": store.all(
                "SELECT substr(created_at,1,10) day,count(DISTINCT entity_id) total FROM reports GROUP BY day ORDER BY day DESC LIMIT 14"
            ),
            "missing_packages": sum(not value for value in report_availability.values()),
            "units": {
                "scan_validation": "hostname attribution jobs",
                "workflow": "notification cases",
                "assets": "distinct reported IP addresses",
                "observations": "retained source rows",
            },
        }
