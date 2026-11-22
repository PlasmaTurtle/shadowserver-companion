"""Entities HTTP adapters."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import closing
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask
from modules.workspace.components.primitives import dump
from attribution import EvidenceRenderer, EvidenceStore
from modules.ui.components.presentation import mark_attribution_bundle
from modules.library.components.intelligence_index import decorate_rows
from modules.entities.components.api_models import (
    EntityProfileValues,
    EntityRename,
    EntityMerge,
    EntityFieldReview,
)
from modules.investigations.components.api_models import (
    CaseVersion,
)
from modules.investigations.components.services.case_queries import (
    completed_notifications,
    list_cases,
    notification_histories,
)
from modules.leads.components.lead_queue import LeadQueue, save_ip_association
from ..repositories.entities import EntityRepository
from modules.attribution.components.attribution_display import attribution_summaries
from ..entity_dns import EntityDNS


class PendingLeadStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    case_id: str | None = None
    expected_case_version: int | None = Field(default=None, ge=0)


class PendingLeadDisposition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    status: Literal["pending", "deferred", "dismissed"]


class PendingLeadAssociation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    entity_id: str = Field(min_length=1, max_length=100)


class OwnershipTransfer(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    hostname: str = Field(min_length=1, max_length=253)
    target_entity_id: str = Field(min_length=1, max_length=100)
    source_revision: int = Field(ge=0)
    target_revision: int = Field(ge=0)
    review_token: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=1, max_length=5000)


class FindingReactivation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(ge=0)
    review_token: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=1, max_length=5000)


class EntityDNSRefresh(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh: bool = False


class EntityAssetAssociation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    hostname: str = Field(min_length=1, max_length=253)


class EntityIPAssociation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    ip: str = Field(min_length=1, max_length=45)


class EntityDetailsAdoption(CaseVersion):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_entity_revision: int | None = Field(default=None, ge=0)
    reopen_affected: bool = False
    reason: str = Field(default="", max_length=5000)


def register(app, *, store, cases, get_lead):
    queue = LeadQueue(store)
    dns_connections = EntityDNS(store)
    app.state.entity_dns = dns_connections

    @app.get("/api/pending-leads")
    def pending_leads(status: str = "pending", q: str = ""):
        return queue.list(status, q)

    @app.get("/api/pending-leads/{pending_id}")
    def pending_lead(pending_id: str):
        return queue.detail(pending_id)

    @app.get("/api/website-evidence/{capture_id}/image")
    def website_evidence_image(capture_id: str, original: bool = False):
        from modules.investigations.components.website_evidence import preview

        try:
            content = preview(store, capture_id, original=original)
        except KeyError as error:
            raise HTTPException(404, "Website screenshot not found") from error
        except (OSError, ValueError) as error:
            raise HTTPException(409, "Website screenshot failed its integrity check") from error
        return Response(content, media_type="image/png")

    @app.post("/api/pending-leads/{pending_id}/start")
    def start_pending(pending_id: str, body: PendingLeadStart):
        return queue.start(
            pending_id,
            body.expected_revision,
            case_id=body.case_id,
            expected_case_version=body.expected_case_version,
        )

    @app.post("/api/pending-leads/{pending_id}/disposition")
    def disposition(pending_id: str, body: PendingLeadDisposition):
        return queue.disposition(pending_id, body.expected_revision, body.status)

    @app.post("/api/pending-leads/{pending_id}/associate")
    def associate(pending_id: str, body: PendingLeadAssociation):
        return queue.associate(pending_id, body.expected_revision, body.entity_id)

    @app.get("/api/entities")
    def entities(q: str = "", review_required: bool = False):
        rows = leads(q=q)
        repository = EntityRepository(store)
        with store.read_snapshot() as db:
            histories = notification_histories(db, (row["id"] for row in rows))
            for row in rows:
                row["notification_history"] = histories[row["id"]]
                entity = db.execute("SELECT * FROM leads WHERE id=?", (row["id"],)).fetchone()
                row["entity_profile"] = repository.profile(db, row["id"])
                row["entity_review"] = repository.field_review(db, entity, row["entity_profile"])
                from ..contact_outcomes import complete_entity_details

                row["entity_review"] = complete_entity_details(
                    store, row, row["entity_review"], row["entity_profile"], db
                )
                row["review_required"] = row["entity_review"]["required"]
                row["entity_revision"] = row["draft_revision"]
        return [r for r in rows if not review_required or r["review_required"]]

    @app.get("/api/navigation-counts")
    def navigation_counts():
        return {
            "entities_review": len(entities(review_required=True)),
            "leads": len(queue.list()),
            "attribution_review": store.one("SELECT count(*) n FROM jobs WHERE status='review'")[
                "n"
            ],
        }

    @app.get("/api/entity-locations")
    def entity_locations(state: str = "", q: str = ""):
        from ..entity_validation import locations, STATE_NAMES

        if len(q) > 300 or len(state) > 300:
            raise ValueError("Location search is too long")
        try:
            cities = locations(state, q)
        except ValueError:
            cities = []
        return {
            "states": [{"code": k, "name": v} for k, v in STATE_NAMES.items()],
            "cities": cities,
        }

    @app.get("/api/entities/{entity_id}/ownership-transfer")
    def ownership_transfer_review(entity_id: str, hostname: str, target_entity_id: str):
        from ..services.entity_lifecycle import EntityLifecycle

        return EntityLifecycle(store).transfer_plan(entity_id, hostname, target_entity_id)

    @app.post("/api/entities/{entity_id}/ownership-transfer")
    def transfer_entity_ownership(entity_id: str, body: OwnershipTransfer):
        from ..services.entity_lifecycle import EntityLifecycle

        return EntityLifecycle(store).transfer(
            entity_id,
            body.hostname,
            body.target_entity_id,
            body.source_revision,
            body.target_revision,
            body.review_token,
            body.reason,
        )

    @app.get("/api/entities/{entity_id}/findings/{finding_id}/reactivation")
    def finding_reactivation_review(entity_id: str, finding_id: str):
        from ..services.entity_lifecycle import EntityLifecycle

        return EntityLifecycle(store).reactivation_plan(entity_id, finding_id)

    @app.post("/api/entities/{entity_id}/findings/{finding_id}/reactivation")
    def reactivate_finding(entity_id: str, finding_id: str, body: FindingReactivation):
        from ..services.entity_lifecycle import EntityLifecycle

        return EntityLifecycle(store).reactivate(
            entity_id, finding_id, body.expected_revision, body.review_token, body.reason
        )

    @app.post("/api/entities/{entity_id}/assets")
    def associate_entity_asset(entity_id: str, body: EntityAssetAssociation):
        from ..services.entities import EntityService

        EntityService(store).associate_asset(entity_id, body.hostname, body.expected_revision)
        return entity_detail(entity_id)

    @app.get("/api/entities/{entity_id}")
    def entity_detail(entity_id: str):
        from modules.library.components.catalog_outreach import decorate_entity

        entity = store.lead(store.resolve_entity(entity_id))
        if not entity:
            raise HTTPException(404, "Business entity not found")
        with store.read_snapshot() as db:
            entity["cases"] = list_cases(store, entity_id=entity["id"], db=db)
            entity["notification_history"] = completed_notifications(
                db, entity["id"], include_cases=True
            )
        entity["entity_revision"] = entity["draft_revision"]
        entity["review_required"] = entity["entity_review"]["required"]
        entity["attribution_summaries"] = attribution_summaries(store, entity)
        entity["ip_associations"] = store.all(
            "SELECT ip,recorded_by,recorded_at FROM entity_ip_associations WHERE entity_id=? ORDER BY ip",
            (entity["id"],),
        )
        entity["dns_connections"] = dns_connections.status(entity)
        entity["observation_dates"] = {
            "first_seen": entity["awareness"]["first_seen"],
            "last_seen": entity["awareness"]["last_seen"],
        }
        return decorate_entity(store.root, entity)

    @app.get("/api/entities/{entity_id}/connections/dns")
    def entity_dns_status(entity_id: str):
        return entity_detail(entity_id)["dns_connections"]

    @app.post("/api/entities/{entity_id}/connections/dns")
    def entity_dns_start(entity_id: str, body: EntityDNSRefresh):
        return dns_connections.start(entity_detail(entity_id), refresh=body.refresh)

    @app.get("/api/leads")
    def leads(status: str = "", q: str = ""):
        if status and status not in ("new", "in_progress", "completed", "deferred"):
            raise HTTPException(400, "Unknown status")
        clauses, args = ["l.merged_into IS NULL"], []
        if status:
            clauses.append("l.status=?")
            args.append(status)
        if q:
            clauses.append(
                "(l.domain LIKE ? OR l.company LIKE ? OR l.id IN (SELECT g.entity_id FROM hostnames h JOIN domain_groups g ON g.root_domain=h.root_domain WHERE h.name LIKE ?) OR l.id IN (SELECT entity_id FROM awareness_assets WHERE hostname LIKE ?))"
            )
            args.extend(["%" + q + "%"] * 4)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = store.all(
            "SELECT l.id,l.domain,l.company,l.status,l.updated_at,l.created_at,l.new_observations,l.demo,l.draft_revision, "
            "(SELECT count(*) FROM cases WHERE entity_id=l.id) case_count, "
            "(SELECT count(*) FROM cases WHERE entity_id=l.id AND stage!='closed') open_cases, "
            "(SELECT group_concat(DISTINCT version) FROM entries WHERE lead_id=l.id) versions, "
            "0 unassigned_observations "
            "FROM leads l" + where + " ORDER BY l.updated_at DESC",
            args,
        )
        from modules.leads.components.repositories.lead_scopes import pending_counts

        with store.read_snapshot() as db:
            current = pending_counts(db)
            from ..repositories.entity_awareness import directory as awareness_directory

            awareness = awareness_directory(db)
        for row in rows:
            summary = awareness.get(row["id"], {})
            row.update(
                observations=summary.get("observations", 0),
                approved_observations=summary.get("approved_observations", 0),
                dark_matter_observations=summary.get("dark_matter_observations", 0),
                finding_count=summary.get("findings", 0),
                observation_days=summary.get("observation_days", 0),
                assets=summary.get("ips", 0),
                hostname_count=summary.get("hostname_count", 0),
                tags=summary.get("tags", ""),
            )
            row["unassigned_observations"] = current.get(row["id"], 0)
            row["new_observations"] = current.get(row["id"], 0) if row["case_count"] else 0
        return decorate_rows(store, rows, kind="leads")

    @app.put("/api/entities/{entity_id}/profile")
    def entity_profile(entity_id: str, body: EntityProfileValues):
        store.update_entity_profile(
            entity_id, body.model_dump(exclude={"expected_revision"}), body.expected_revision
        )
        return entity_detail(entity_id)

    @app.post("/api/entities/{entity_id}/field-review")
    def review_entity_field(entity_id: str, body: EntityFieldReview):
        return store.review_entity_field(
            entity_id, body.field, body.action, body.expected_revision, body.value_hash
        )

    @app.put("/api/entities/{entity_id}/name")
    def rename_entity(entity_id: str, body: EntityRename):
        entity_detail(entity_id)
        store.rename_entity(entity_id, body.name, body.expected_revision)
        return entity_detail(entity_id)

    @app.post("/api/entities/{entity_id}/merge")
    def merge_entity(entity_id: str, body: EntityMerge):
        store.merge_entities(entity_id, body.target_id, body.source_revision, body.target_revision)
        return entity_detail(body.target_id)

    @app.get("/api/entities/{entity_id}/ip-associations")
    def ip_associations(entity_id: str):
        return entity_detail(entity_id)["ip_associations"]

    @app.post("/api/entities/{entity_id}/ip-associations")
    def add_ip_association(entity_id: str, body: EntityIPAssociation):
        save_ip_association(store, entity_id, body.ip, body.expected_revision)
        return entity_detail(entity_id)

    @app.get("/api/leads/{lead_id}")
    def lead(lead_id: str, case_id: str | None = None):
        entity_id = store.resolve_entity(lead_id) or lead_id
        if case_id is None and cases.default_id(entity_id) is None:
            return entity_detail(entity_id)
        return get_lead(entity_id, case_id)

    @app.get("/api/cases/{case_id}/entity-details")
    def entity_details_adoption_plan(case_id: str):
        from modules.investigations.components.entity_adoption import adoption_plan

        return adoption_plan(cases, case_id)

    @app.post("/api/cases/{case_id}/entity-details")
    def adopt_entity_details(case_id: str, body: EntityDetailsAdoption):
        lead = cases.adopt_entity_details(case_id, **body.model_dump())
        return get_lead(lead["id"], case_id)

    @app.get("/api/entities/{entity_id}/archived-draft.json")
    def archived_draft(entity_id: str):
        row = store.one("SELECT * FROM leads WHERE id=? AND merged_into IS NOT NULL", (entity_id,))
        if not row:
            raise HTTPException(404, "Archived entity not found")
        return Response(
            dump(
                {
                    "entity_id": entity_id,
                    "entity_name": row["company"],
                    "merged_into": row["merged_into"],
                    "draft_revision": row["draft_revision"],
                    "draft": json.loads(row["draft"]),
                }
            ),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="prior-draft-{entity_id[:8]}.json"'
            },
        )

    @app.post("/api/leads/{lead_id}/start")
    def start(lead_id: str, case_id: str | None = None):
        if case_id is None and cases.default_id(lead_id) is None:
            opened = cases.create(lead_id)
            return get_lead(lead_id, opened["case_id"])
        lead = get_lead(lead_id, case_id)
        case = lead.get("case")
        if case is None:
            lead = cases.create(lead_id)
        elif case["stage"] == "pending_notification":
            raise HTTPException(
                409, "Use Revise report and record a reason to reopen a certified notification."
            )
        elif case["stage"] in ("notification_completed", "closed"):
            lead = cases.create(lead_id)
        return get_lead(lead_id, lead["case_id"])

    @app.get("/api/leads/{lead_id}/json")
    def export_lead(lead_id: str, case_id: str | None = None):
        if case_id is None:
            entity_detail(lead_id)
        else:
            get_lead(lead_id, case_id)
        return Response(
            json.dumps(store.export_lead(lead_id, case_id), indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="lead-{lead_id[:8]}.json"'},
        )

    @app.get("/api/leads/{lead_id}/attribution.zip")
    def export_attribution(lead_id: str, case_id: str | None = None):
        lead = entity_detail(lead_id) if case_id is None else get_lead(lead_id, case_id)
        proofs = [g["attribution"] for g in lead["domain_groups"]]
        results = {proof.get("result_id") for proof in proofs} - {None}
        if not results:
            raise HTTPException(
                409,
                "This legacy or demonstration attribution has no raw response bundle. Its saved record is in Lead JSON.",
            )
        handle, path = tempfile.mkstemp(suffix=".zip")
        os.close(handle)
        try:
            with (
                tempfile.TemporaryDirectory() as temp,
                closing(EvidenceStore(store.root / "attribution.sqlite3")) as evidence_store,
            ):
                from modules.attribution.components.attribution_approval_evidence import (
                    valid_approval_reuse,
                )

                inherited = {}
                for proof in proofs:
                    if "approval_reuse" not in proof:
                        continue
                    root = (proof.get("attribution") or {}).get("root_domain")
                    if not valid_approval_reuse(proof, root, evidence_store):
                        raise ValueError(
                            "Inherited attribution approval failed its integrity check"
                        )
                    reuse = proof["approval_reuse"]
                    results.add(reuse["source_result_id"])
                    inherited[proof["result_id"]] = {
                        **{key: value for key, value in reuse.items() if key != "source_proof"},
                        "analyst_review": proof["review"],
                    }
                renderer = EvidenceRenderer(evidence_store)
                for result_id in results:
                    reviews = store.all(
                        "SELECT * FROM attribution_reviews WHERE result_id=? ORDER BY reviewed_at",
                        (result_id,),
                    )
                    renderer.export(result_id, Path(temp) / result_id, review_decisions=reviews)
                    mark_attribution_bundle(Path(temp) / result_id)
                    if result_id in inherited:
                        (Path(temp) / result_id / "approval-reuse.json").write_text(
                            dump(inherited[result_id]), encoding="utf-8"
                        )
                with ZipFile(path, "w", ZIP_DEFLATED) as archive:
                    for file in Path(temp).rglob("*"):
                        if file.is_file():
                            archive.write(file, file.relative_to(temp))
        except Exception:
            Path(path).unlink(missing_ok=True)
            raise
        return FileResponse(
            path,
            filename=f"attribution-{lead_id[:8]}.zip",
            background=BackgroundTask(Path(path).unlink, missing_ok=True),
        )
