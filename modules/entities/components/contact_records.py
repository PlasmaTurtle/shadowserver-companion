"""Saved contact evidence, attribution scope, review decisions and explicit adoption."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from attribution import EvidenceStore
from attribution.matching import normalize_domain

from modules.attribution.components.asset_attribution import _verify_snapshots
from modules.attribution.components.attribution_bridge import checked_result
from modules.attribution.components.attribution_display import attribution_summaries
from modules.workspace.components.primitives import dump, now, uid
from .contact_discovery.policy import (
    approved_scope,
    MAX_TOTAL_BYTES,
    MAX_REQUESTS,
    MAX_CANDIDATES,
)
from .contact_discovery import candidate_key
from .contact_evidence import (
    fingerprint as fingerprint,
    snapshot_path as snapshot_path,
    is_derived_snapshot,
    prepare_snapshot,
    snapshot_content,
)
from .contact_input import clean_result
from .contact_outcomes import (
    ROUTINE_PURPOSES,
    PURPOSE_ORDER,
    contact_summary,
    route_key,
    verification_route,
    validate_verification_route,
)


class ContactConflict(ValueError):
    """The review or contact plan changed since the operator opened it."""


class ContactRecords:
    def __init__(self, store):
        self.store = store

    def _entity(self, entity_id, db=None):
        identity = self.store.entities.resolve_entity(entity_id, db)
        if not identity:
            raise ValueError("Business entity not found")
        return identity

    def scope(self, entity_id, root_domain=None):
        """Use an associated entity domain; attribution evidence is optional context."""
        entity_id = self._entity(entity_id)
        roots = self._associated_roots(entity_id)
        if root_domain is None:
            entity = self.store.one("SELECT domain FROM leads WHERE id=?", (entity_id,))
            primary = normalize_domain(entity["domain"]) if entity else ""
            if primary in roots:
                root_domain = primary
            elif len(roots) == 1:
                root_domain = roots[0]
            else:
                raise ValueError("Select one website hostname for this entity")
        root, _ = approved_scope(normalize_domain(root_domain))
        if root not in roots:
            raise ValueError("This hostname is outside the entity's associated websites")
        try:
            return self._attributed_scope(entity_id, root)
        except (ValueError, OSError, sqlite3.Error, KeyError, TypeError):
            # A contact search is useful before a notification or attribution exists.
            # Never imply that the website association establishes network ownership.
            scope = {
                "schema": 2,
                "basis": "entity_domain",
                "entity_id": entity_id,
                "root_domain": root,
                "attribution_entry_id": None,
                "attribution_ref": None,
                "attribution": None,
                "snapshots": [],
                "match_summary": "Website associated with this entity",
                "reported_ip": "",
            }
            scope["fingerprint"] = fingerprint(scope)
            return scope

    def _associated_roots(self, entity_id):
        roots = {
            row["root_domain"]
            for row in self.store.all(
                "SELECT root_domain FROM domain_groups WHERE entity_id=?", (entity_id,)
            )
        }
        entity = self.store.one("SELECT domain FROM leads WHERE id=?", (entity_id,))
        if entity and entity["domain"]:
            roots.add(entity["domain"])
        valid = set()
        for root in roots:
            try:
                valid.add(approved_scope(normalize_domain(root))[0])
            except ValueError:
                continue
        return sorted(valid)

    def _attributed_scope(self, entity_id, root_domain=None):
        """Derive and verify the network boundary from a saved attribution decision."""
        entity_id = self._entity(entity_id)
        groups = self.store.all("SELECT * FROM domain_groups WHERE entity_id=?", (entity_id,))
        if root_domain is None:
            eligible = []
            for group in groups:
                try:
                    eligible.append(self.scope(entity_id, group["root_domain"]))
                except (ValueError, OSError, sqlite3.Error, KeyError):
                    continue
            if len(eligible) != 1:
                raise ValueError("Select one eligible attributed root hostname for this business")
            return eligible[0]
        root = normalize_domain(root_domain)
        group = next((g for g in groups if g["root_domain"] == root), None)
        if not group:
            raise ValueError("This root hostname is outside the business attribution scope")
        entry = self.store.one(
            "SELECT * FROM entries WHERE id=? AND lead_id=? AND root_domain=?",
            (group["attribution_entry_id"], entity_id, root),
        )
        if not entry:
            raise ValueError("The attribution observation no longer belongs to this business")
        proof = json.loads(group["attribution"])
        lead = {
            "entries": [{**json.loads(entry["payload"]), "id": entry["id"]}],
            "domain_groups": [{**group, "attribution": proof}],
        }
        summary = attribution_summaries(self.store, lead)[0]
        if not summary["supported"]:
            raise ValueError(summary["match_summary"])
        result_id, snapshot_id = proof.get("result_id"), proof.get("snapshot_id")
        if not result_id or not snapshot_id or not proof.get("body_sha256"):
            raise ValueError(
                "This legacy attribution has no retained response proof; save a new attribution before discovering contacts"
            )
        path = self.store.root / "attribution.sqlite3"
        if not path.is_file():
            raise ValueError("Saved attribution database is unavailable")
        with EvidenceStore(path) as evidence_store:
            result = checked_result(evidence_store, result_id, root)
            _verify_snapshots(evidence_store, result)
            evidence = proof.get("evidence") or {}
            accepted = proof.get("review", {}).get("decision") == "accept"
            available = (
                result.get("partial_evidence", []) if accepted else result.get("evidence", [])
            )
            if evidence not in available or (not accepted and result.get("status") != "matched"):
                raise ValueError(
                    "Saved attribution decision does not identify its retained evidence"
                )
            if evidence.get("ip") != entry["ip"] or evidence.get("snapshot_id") != snapshot_id:
                raise ValueError("Saved attribution evidence does not match this observation")
            snapshot = evidence_store.snapshot(snapshot_id)
            if snapshot.body_sha256 != proof["body_sha256"]:
                raise ValueError("Saved attribution response differs from its recorded SHA-256")
            ids = {snapshot_id, *evidence.get("supporting_snapshot_ids", [])}
            snapshots = [evidence_store.snapshot(sid).metadata() for sid in sorted(ids)]
        scope = {
            "entity_id": entity_id,
            "root_domain": root,
            "attribution_entry_id": entry["id"],
            "attribution_ref": {
                "result_id": result_id,
                "snapshot_id": snapshot_id,
                "body_sha256": proof["body_sha256"],
            },
            "attribution": proof,
            "snapshots": snapshots,
            "match_summary": summary["match_summary"],
            "reported_ip": entry["ip"],
        }
        scope["fingerprint"] = fingerprint(scope)
        return scope

    def roots(self, entity_id):
        result = []
        for root in self._associated_roots(entity_id):
            item = {"root_domain": root, "eligible": False, "attribution_ref": None}
            try:
                scope = self.scope(entity_id, root)
                item.update(eligible=True, attribution_ref=scope["attribution_ref"])
            except (ValueError, OSError, sqlite3.Error, KeyError, TypeError) as error:
                item["reason"] = str(error)
            result.append(item)
        return result

    def _run(self, row):
        return {
            **json.loads(row["payload"]),
            "id": row["id"],
            "entity_id": row["entity_id"],
            "original_entity_id": row["original_entity_id"],
            "attribution_ref": json.loads(row["scope"])["attribution_ref"],
            "scope_fingerprint": json.loads(row["scope"])["fingerprint"],
            "limits": json.loads(row["limits_json"]),
        }

    def export_projection(self, entity_id):
        entity_id = self._entity(entity_id)
        with self.store.read_snapshot() as db:
            runs = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM contact_runs WHERE entity_id=? ORDER BY rowid DESC", (entity_id,)
                )
            ]
            candidates = []
            for row in db.execute(
                "SELECT * FROM contact_candidates WHERE entity_id=? ORDER BY first_seen,id",
                (entity_id,),
            ):
                item = {**dict(row), **json.loads(row["payload"])}
                item.pop("payload", None)
                item["key"] = item.pop("candidate_key")
                item["missing_from_latest"] = bool(item["missing_from_latest"])
                item["sources"] = [
                    source
                    for source_row in db.execute(
                        "SELECT payload FROM contact_sources WHERE candidate_id=? ORDER BY rowid DESC",
                        (row["id"],),
                    )
                    for source in json.loads(source_row["payload"])
                ]
                item["reviews"] = [
                    dict(review)
                    for review in db.execute(
                        "SELECT * FROM contact_reviews WHERE candidate_id=? ORDER BY rowid",
                        (row["id"],),
                    )
                ]
                item["review_required"] = False
                item["provenance_text"] = self._explanation(item, runs)
                candidates.append(item)
        outcomes = contact_summary(self.store, entity_id)
        for candidate in candidates:
            candidate.update(outcomes["candidate_status"].get(candidate["id"], {}))
        contacts = {}
        # One visible route, with all its saved provenance. Prefer a current,
        # explicitly preferred record over an arbitrary first-created duplicate.
        ordered = sorted(
            candidates,
            key=lambda c: (
                c.get("decision") == "ignored",
                not c.get("preferred", False),
                c.get("missing_from_latest", False),
                PURPOSE_ORDER.get(c.get("purpose"), 99),
            ),
        )
        for candidate in ordered:
            key = route_key(candidate["kind"], candidate["value"])
            if key not in contacts:
                contacts[key] = {
                    **candidate,
                    "source": "published",
                    "known": False,
                    "sources": list(candidate["sources"]),
                }
            else:
                for source in candidate["sources"]:
                    if source not in contacts[key]["sources"]:
                        contacts[key]["sources"].append(source)
        for route in outcomes["routes"]:
            if route.get("source") != "manual":
                continue
            key = route_key(route["kind"], route["value"])
            if key in contacts:
                contacts[key]["known"] = True
                for field in ("name", "role"):
                    if not contacts[key].get(field) and route.get(field):
                        contacts[key][field] = route[field]
                continue
            contacts[key] = {
                **route,
                "id": "known-" + candidate_key(route["kind"], route["value"]),
                "name": route.get("name", ""),
                "role": route.get("role", ""),
                "purpose": route.get("purpose", "general"),
                "known": True,
                "sources": [],
                "review_required": False,
                "provenance_text": "Saved entity or notification contact.",
            }
        return {
            "schema": 1,
            "entity_id": entity_id,
            "runs": [self._run(row) for row in runs],
            "candidates": candidates,
            "contacts": list(contacts.values()),
            "latest_run": self._run(runs[0]) if runs else None,
            "contact_readiness": outcomes,
        }

    @staticmethod
    def _explanation(candidate, runs):
        source = next(
            (s for s in candidate["sources"] if s["run_id"] == candidate["latest_run_id"]), None
        )
        run = next((r for r in runs if r["id"] == candidate["latest_run_id"]), None)
        if not source or not run:
            return "The saved contact source is unavailable."
        scope = json.loads(run["scope"])
        attribution = (
            f"Saved attribution associated reported IP {scope['reported_ip']} with {candidate['root_domain']}. "
            f"{scope['match_summary']} "
            if scope.get("attribution_ref")
            else f"The website {candidate['root_domain']} is associated with this entity. "
        )
        return (
            attribution + f"The business website published {candidate['value']} at "
            f"{source['url']} (retrieved {source['retrieved_at']}; SHA-256 {source['sha256']}). "
            + (
                f"Attribution result: {scope['attribution_ref']['result_id']}. "
                if scope.get("attribution_ref")
                else ""
            )
            + f"Published purpose: {candidate.get('purpose', 'other').replace('_', ' ')}. "
            + (
                f"Routing instruction: {candidate['routing_label']}. "
                if candidate.get("routing_label")
                else ""
            )
            + ("This source was partially captured. " if source.get("truncated") else "")
            + "Publication does not establish delivery or responsibility for the reported systems."
        )

    def state(self, entity_id):
        result = self.export_projection(entity_id)
        result["roots"] = self.roots(result["entity_id"])
        entity = self.store.one("SELECT domain FROM leads WHERE id=?", (result["entity_id"],))
        result["default_root"] = normalize_domain(entity["domain"]) if entity else ""
        result["active_job"] = None
        result["summary"] = {
            decision: sum(c["decision"] == decision for c in result["candidates"])
            for decision in ("pending", "confirmed", "ignored")
        }
        result["summary"]["review_required"] = sum(
            c["review_required"] for c in result["candidates"]
        )
        result["summary"]["usable"] = sum(c.get("usable", False) for c in result["candidates"])
        choices = [
            c
            for c in result["candidates"]
            if c.get("purpose", "other") in ROUTINE_PURPOSES
            and c.get("recommended_for_outreach") is not False
            and not c.get("purpose_conflict")
            and c["decision"] != "ignored"
            and not c.get("unusable")
            and not c.get("missing_from_latest")
        ]
        choices.sort(
            key=lambda c: (
                not bool(c.get("preferred") and c.get("usable")),
                not bool(c.get("usable") and c.get("purpose") in {"security", "it"}),
                PURPOSE_ORDER.get(c.get("purpose"), 99),
                not bool(c.get("usable")),
                c.get("value", "").casefold(),
            )
        )
        result["best_route_id"] = choices[0]["id"] if choices else None
        result["summary"]["security_routes"] = sum(
            c.get("purpose") == "security" for c in result["candidates"]
        )
        result["summary"]["referral_routes"] = sum(
            c.get("purpose") in {"it", "product_support"} for c in result["candidates"]
        )
        return result

    def save_run(self, scope, result, limits=None):
        """Persist a complete capture atomically after rechecking the attribution boundary."""
        run_id, folder = uid(), None
        if result.get("root_hostname") != scope["root_domain"]:
            raise ValueError("Contact result belongs to another root hostname")
        aliases = result.get("aliases", [])
        if any(alias not in approved_scope(scope["root_domain"])[1] for alias in aliases):
            raise ValueError("Contact result includes an unapproved hostname")
        allowed = {scope["root_domain"], *aliases}
        result = clean_result(result, allowed)
        snapshots, snapshot_ids = [], set()
        candidates = result.get("candidates", [])
        prepared = [prepare_snapshot(saved, candidates) for saved in result["snapshots"]]
        if (
            result.get("status")
            not in ("relevant_found", "general_only", "not_found", "partial", "cancelled", "failed")
            or not 0 <= result.get("request_count", 0) <= MAX_REQUESTS
            or len(result.get("snapshots", [])) > MAX_REQUESTS
            or len(candidates) > MAX_CANDIDATES
        ):
            raise ValueError("Contact result exceeded its capture budget")
        try:
            with self.store.transaction() as db:
                current = self.scope(scope["entity_id"], scope["root_domain"])
                if current["fingerprint"] != scope["fingerprint"]:
                    raise ContactConflict(
                        "Business attribution changed during discovery; retry with its current scope"
                    )
                folder = self.store.root / "evidence" / "contact-discovery" / run_id
                if any(part.is_symlink() for part in folder.parents if part != self.store.root):
                    raise ValueError("Contact evidence directory contains a symbolic link")
                self.store.path(folder.relative_to(self.store.root))
                folder.mkdir(parents=True)
                total_bytes = 0
                for index, (saved, content) in enumerate(prepared):
                    total_bytes += saved["captured_bytes"]
                    if total_bytes > MAX_TOTAL_BYTES:
                        raise ValueError("Contact response exceeded its total capture budget")
                    snapshot_ids.add(saved["id"])
                    path = folder / f"{index + 1:02d}-{saved['artifact_sha256']}.contact.json"
                    path.write_bytes(content)
                    snapshots.append(
                        {**saved, "path": path.relative_to(self.store.root).as_posix()}
                    )
                payload = {**result, "snapshots": snapshots}
                created = result.get("started_at") or now()
                finished = result.get("finished_at") or now()
                limits = asdict(limits) if is_dataclass(limits) else limits or {}
                db.execute(
                    "INSERT INTO contact_runs VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        scope["entity_id"],
                        scope["entity_id"],
                        scope["root_domain"],
                        result["status"],
                        dump(scope),
                        dump(limits),
                        dump(payload),
                        created,
                        finished,
                    ),
                )
                checked_urls = {
                    row["url"]
                    for row in result.get("coverage", [])
                    if row.get("state") in {"checked", "checked_empty", "not_found"}
                }
                # A focused or incomplete lookup says nothing about sources it
                # did not read. Only invalidate contacts whose whole prior
                # publication footprint was actually checked in this run.
                for prior in db.execute(
                    "SELECT c.id,s.payload FROM contact_candidates c JOIN contact_sources s ON s.candidate_id=c.id AND s.run_id=c.latest_run_id WHERE c.entity_id=? AND c.root_domain=? AND c.missing_from_latest=0",
                    (scope["entity_id"], scope["root_domain"]),
                ).fetchall():
                    source_urls = {item["url"] for item in json.loads(prior["payload"])}
                    if source_urls and source_urls <= checked_urls:
                        db.execute(
                            "UPDATE contact_candidates SET missing_from_latest=1,revision=revision+1 WHERE id=?",
                            (prior["id"],),
                        )
                by_snapshot = {s["id"]: s for s in snapshots}
                for candidate in candidates:
                    if (
                        candidate["kind"] not in ("email", "phone", "form", "person")
                        or not candidate["sources"]
                    ):
                        raise ValueError("Contact candidate has no supported type or source")
                    if (
                        len(candidate["value"])
                        > {"email": 500, "phone": 100, "form": 2048, "person": 300}[
                            candidate["kind"]
                        ]
                        or len(candidate.get("name", "")) > 300
                        or len(candidate.get("role", "")) > 300
                    ):
                        raise ValueError("Published contact exceeds supported field length")
                    if candidate_key(candidate["kind"], candidate["value"]) != candidate["key"]:
                        raise ValueError(
                            "Contact candidate key does not identify its published value"
                        )
                    sources = []
                    for source in candidate["sources"]:
                        snapshot = by_snapshot.get(source["snapshot_id"])
                        if not snapshot or source["url"] != snapshot["url"]:
                            raise ValueError("Contact candidate does not identify its saved source")
                        sources.append(
                            {
                                **source,
                                "run_id": run_id,
                                "retrieved_at": snapshot["retrieved_at"],
                                "sha256": snapshot["sha256"],
                            }
                        )
                    existing = db.execute(
                        "SELECT * FROM contact_candidates WHERE entity_id=? AND root_domain=? AND candidate_key=?",
                        (scope["entity_id"], scope["root_domain"], candidate["key"]),
                    ).fetchone()
                    clean = {
                        k: v
                        for k, v in candidate.items()
                        if k not in ("sources", "review_required", "key")
                    }
                    clean["source_changed"] = False
                    if existing:
                        old = json.loads(existing["payload"])
                        if candidate_key(old["kind"], old["value"]) != candidate["key"]:
                            raise ValueError("Contact candidate identity changed without a new key")
                        prior = db.execute(
                            "SELECT payload FROM contact_sources WHERE candidate_id=? AND run_id=?",
                            (existing["id"], existing["latest_run_id"]),
                        ).fetchone()

                        def signature(ss):
                            return sorted((s["url"], s.get("excerpt", "")) for s in ss)

                        clean["source_changed"] = (
                            old.get("source_changed", False)
                            or signature(json.loads(prior["payload"])) != signature(sources)
                            or any(
                                old.get(k, "") != clean.get(k, "")
                                for k in (
                                    "name",
                                    "role",
                                    "purpose",
                                    "routing_label",
                                    "routing_options",
                                    "route_type",
                                    "original_url",
                                    "external_destination",
                                    "purpose_conflict",
                                    "recommended_for_outreach",
                                )
                            )
                        )
                        identity = existing["id"]
                        db.execute(
                            "UPDATE contact_candidates SET payload=?,revision=revision+1,last_seen=?,latest_run_id=?,missing_from_latest=0 WHERE id=?",
                            (dump(clean), finished, run_id, identity),
                        )
                    else:
                        identity = uid()
                        db.execute(
                            """INSERT INTO contact_candidates(id,entity_id,root_domain,candidate_key,payload,first_seen,last_seen,latest_run_id)
                                      VALUES(?,?,?,?,?,?,?,?)""",
                            (
                                identity,
                                scope["entity_id"],
                                scope["root_domain"],
                                candidate["key"],
                                dump(clean),
                                finished,
                                finished,
                                run_id,
                            ),
                        )
                    db.execute(
                        "INSERT INTO contact_sources VALUES(?,?,?)",
                        (identity, run_id, dump(sources)),
                    )
                self.store.log(
                    db,
                    "contact_discovery",
                    f"Contact discovery for {scope['root_domain']}: {result['status']}; {len(candidates)} published contacts; run {run_id}",
                    scope["entity_id"],
                )
            return self._run(self.store.one("SELECT * FROM contact_runs WHERE id=?", (run_id,)))
        except Exception:
            if folder:
                shutil.rmtree(folder, ignore_errors=True)
            raise

    def _verified_candidate(self, db, entity_id, candidate_id, expected_revision):
        row = db.execute(
            "SELECT * FROM contact_candidates WHERE id=? AND entity_id=?", (candidate_id, entity_id)
        ).fetchone()
        if not row:
            raise ValueError("Contact candidate does not belong to this business")
        if row["revision"] != expected_revision:
            raise ContactConflict("This contact changed. Reload before reviewing or using it.")
        return row

    def _verify_candidate_evidence(self, row):
        from modules.entities.components.contact_validation import validate_candidate

        validate_candidate(self.store, row)
        run = self.store.one("SELECT * FROM contact_runs WHERE id=?", (row["latest_run_id"],))
        for snapshot in json.loads(run["payload"])["snapshots"]:
            if is_derived_snapshot(snapshot):
                snapshot_path(self.store, run["id"], snapshot)

    def review(self, entity_id, candidate_id, action, expected_revision):
        actions = {"confirm": "confirmed", "ignore": "ignored", "pending": "pending"}
        if action not in actions:
            raise ValueError("Unknown contact review action")
        actor = self.store.settings().get("analyst_name") or "Local operator"
        with self.store.transaction() as db:
            entity_id = self._entity(entity_id, db)
            row = self._verified_candidate(db, entity_id, candidate_id, expected_revision)
            payload = json.loads(row["payload"])
            if action == "confirm":
                self._verify_candidate_evidence(row)
                if row["missing_from_latest"]:
                    raise ContactConflict(
                        "This contact was not found in the latest complete lookup; refresh before confirming"
                    )
                payload["source_changed"] = False
            stamp = now()
            db.execute(
                "UPDATE contact_candidates SET decision=?,payload=?,revision=revision+1,reviewed_by=?,reviewed_at=? WHERE id=?",
                (actions[action], dump(payload), actor, stamp, candidate_id),
            )
            db.execute(
                "INSERT INTO contact_reviews VALUES(?,?,?,?,?,?,?)",
                (
                    uid(),
                    candidate_id,
                    row["revision"] + 1,
                    action,
                    actor,
                    stamp,
                    row["latest_run_id"],
                ),
            )
            self.store.log(
                db,
                "contact_reviewed",
                f"{row['root_domain']}: contact {candidate_id} {actions[action]}",
                entity_id,
            )
        return self.state(entity_id)

    def use(self, cases, case_id, candidate_id, expected_version, expected_revision):
        with self.store.transaction() as db:
            case = cases.require(db, case_id)
            if case["version"] != expected_version or case["stage"] == "closed":
                raise ContactConflict(
                    "This case changed or is closed. Reload before using a contact."
                )
            row = self._verified_candidate(db, case["entity_id"], candidate_id, expected_revision)
            payload = json.loads(row["payload"])
            usability = contact_summary(self.store, case["entity_id"], db)["candidate_status"][
                candidate_id
            ]
            if payload.get("purpose") == "physical_emergency":
                raise ContactConflict(
                    "A physical-emergency line is not a routine cyber outreach route"
                )
            if usability.get("fax"):
                raise ContactConflict("A published fax number is not a voice contact")
            if usability["unusable"]:
                raise ContactConflict(
                    "This route has an adverse contact outcome. Review its usability or choose another contact."
                )
            self._verify_candidate_evidence(row)
            keys = {"email": "contact_email", "phone": "contact_phone", "person": "contact_name"}
            key = keys.get(payload["kind"])
            if not key:
                raise ValueError("A published form is a reference link, not a contact-plan address")
            if not usability["can_adopt"]:
                raise ContactConflict(
                    "This contact is ignored or unavailable. Review its status before using it."
                )
            changes = {key: payload["value"]}
            if payload.get("name"):
                changes["contact_name"] = payload["name"]
            if payload.get("role"):
                changes["contact_role"] = payload["role"]
            profile = self.store.entities.profile(db, case["entity_id"])
            profile_keys = {"contact_role": "contact_title"}
            filled = {
                k: v
                for k, v in changes.items()
                if not (case[k] or profile.get(profile_keys.get(k, k), "")).strip()
            }
            if filled:
                db.execute(
                    "UPDATE cases SET "
                    + ",".join(k + "=?" for k in filled)
                    + ",version=version+1,updated_at=? WHERE id=?",
                    (*filled.values(), now(), case_id),
                )
                actor = self.store.settings().get("analyst_name") or "Local operator"
                self.store.log(
                    db,
                    "contact_used",
                    f"{actor} selected contact {candidate_id}; source run {row['latest_run_id']}; filled {', '.join(filled)}",
                    case["entity_id"],
                    case_id,
                )
            updated = dict(db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone())
        return {
            "case_id": case_id,
            "version": updated["version"],
            "filled_fields": list(filled),
            "contact_plan": {
                k: updated[k]
                for k in ("contact_name", "contact_role", "contact_email", "contact_phone")
            },
        }

    def automatic_default(self, entity_id):
        """Save a sourced default without claiming a human confirmed the contact."""
        state = self.state(entity_id)
        candidate = next(
            (c for c in state["candidates"] if c["id"] == state["best_route_id"]), None
        )
        if not candidate:
            return None
        with self.store.transaction() as db:
            summary = contact_summary(self.store, entity_id, db)
            status = summary["candidate_status"].get(candidate["id"], {})
            profile = self.store.entities.profile(db, entity_id)
            if summary["preferred_candidate_id"] or any(
                profile.get(k) for k in ("contact_email", "contact_phone", "contact_name")
            ):
                return None
            if not (
                status.get("usable")
                and status.get("routine_suggestion")
                and status.get("publication_current")
            ):
                return None
            row = self._verified_candidate(db, entity_id, candidate["id"], candidate["revision"])
            self._verify_candidate_evidence(row)
            stamp = now()
            db.execute(
                "UPDATE contact_candidates SET revision=revision+1 WHERE id=?", (candidate["id"],)
            )
            db.execute(
                "INSERT INTO contact_reviews VALUES(?,?,?,?,?,?,?)",
                (
                    uid(),
                    candidate["id"],
                    row["revision"] + 1,
                    "route_preferred",
                    "Automatic discovery",
                    stamp,
                    dump(
                        {
                            "reason": "Discovered default; pending human confirmation",
                            "source_run_id": row["latest_run_id"],
                            "automatic": True,
                        }
                    ),
                ),
            )
            field = {"email": "contact_email", "phone": "contact_phone"}.get(candidate["kind"])
            if field:
                profile[field] = candidate["value"]
                self.store.entities.save_profile(db, entity_id, profile)
                self.store.entities.touch_profile(db, entity_id)
            self.store.log(
                db,
                "contact_default_discovered",
                "Saved a published contact as the default, pending confirmation",
                entity_id,
            )
        return candidate["id"]

    def route_decision(self, entity_id, candidate_id, action, reason, expected_revision):
        """Record preference/usability without rewriting publication or delivery history."""
        if action not in ("prefer", "unusable", "restore"):
            raise ValueError("Unknown contact-route decision")
        reason = reason.strip()
        if not reason or len(reason) > 2000:
            raise ValueError("Record a reason for this contact-route decision")
        actor = self.store.settings().get("analyst_name") or "Local operator"
        with self.store.transaction() as db:
            entity_id = self._entity(entity_id, db)
            row = self._verified_candidate(db, entity_id, candidate_id, expected_revision)
            status = contact_summary(self.store, entity_id, db)["candidate_status"][candidate_id]
            if action == "prefer":
                if not status["usable"]:
                    raise ContactConflict("Choose an available contact as the preferred route")
                self._verify_candidate_evidence(row)
            stamp = now()
            saved_action = {
                "prefer": "route_preferred",
                "unusable": "route_unusable",
                "restore": "route_restored",
            }[action]
            db.execute(
                "UPDATE contact_candidates SET revision=revision+1 WHERE id=?", (candidate_id,)
            )
            db.execute(
                "INSERT INTO contact_reviews VALUES(?,?,?,?,?,?,?)",
                (
                    uid(),
                    candidate_id,
                    row["revision"] + 1,
                    saved_action,
                    actor,
                    stamp,
                    dump({"reason": reason, "source_run_id": row["latest_run_id"]}),
                ),
            )
            self.store.log(
                db, saved_action, f"{actor}: contact {candidate_id}; {reason}", entity_id
            )
        return self.state(entity_id)

    def configure_verification(self, value, expected_value):
        value = validate_verification_route(value)
        with self.store.transaction() as db:
            settings = json.loads(
                db.execute("SELECT value FROM settings WHERE key='profile'").fetchone()["value"]
            )
            if verification_route(settings) != expected_value:
                raise ContactConflict("The verification route changed. Reload before saving.")
            settings["outreach_verification_route"] = value
            db.execute("UPDATE settings SET value=? WHERE key='profile'", (dump(settings),))
            self.store.log(
                db,
                "outreach_verification_updated",
                "Updated the configured public verification route",
            )
        return {"verification_route": value}

    def handoff(self, case_id):
        """Prepare a deterministic introduction; never send, certify, or change a plan."""
        case = self.store.one("SELECT * FROM cases WHERE id=?", (case_id,))
        if not case:
            raise ValueError("Notification case not found")
        entity = self.store.one("SELECT * FROM leads WHERE id=?", (case["entity_id"],))
        projection = self.export_projection(case["entity_id"])
        summary = projection["contact_readiness"]
        profile_row = self.store.one(
            "SELECT payload FROM entity_profiles WHERE entity_id=?", (case["entity_id"],)
        )
        profile = json.loads(profile_row["payload"]) if profile_row else {}
        destinations = [
            ("email", case["contact_email"] or profile.get("contact_email", "")),
            ("phone", case["contact_phone"] or profile.get("contact_phone", "")),
        ]
        selected = None
        for kind, value in destinations:
            if value.strip():
                matching = [
                    r
                    for r in summary["routes"]
                    if route_key(r["kind"], r["value"]) == route_key(kind, value)
                ]
                selected = next(
                    (r for r in matching if r["usable"]), matching[0] if matching else None
                )
                if selected and selected["usable"]:
                    break
        if not any(value.strip() for _, value in destinations):
            selected = next((r for r in summary["routes"] if r["preferred"] and r["usable"]), None)
        source = next(
            (
                c
                for c in projection["candidates"]
                if selected
                and route_key(c["kind"], c["value"])
                == route_key(selected["kind"], selected["value"])
            ),
            None,
        )
        report = (
            self.store.one(
                "SELECT * FROM reports WHERE id=? AND case_id=?",
                (case["certified_report_id"], case_id),
            )
            if case["certified_report_id"]
            else None
        )
        available = bool(report and self.store.package_available(report))
        from modules.investigations.components.observation_scope import legacy_scope_warning
        from modules.investigations.components.repositories.cases import CaseRepository

        scope_warning = (
            legacy_scope_warning(CaseRepository(self.store).view(case_id)) if available else None
        )
        settings = self.store.settings()
        verify = verification_route(settings)
        from modules.settings.components.sender_identity import effective_settings

        settings = effective_settings(settings, json.loads(case["draft"]))
        blockers = []
        from modules.investigations.components.outreach_policy import get_policy

        with self.store.read_snapshot() as db:
            policy = get_policy(db, case_id)
        if policy["state"] != "active":
            reason = policy["reason"].rstrip().rstrip(".")
            blockers.append(
                f"Outreach is {policy['state'].replace('_', ' ')}: {reason}. Review the outreach decision before proceeding."
            )
        if case["stage"] == "closed":
            blockers.append(
                "This case is closed; reconsider it through the case workflow before preparing new outreach."
            )
        if not selected or not selected["usable"]:
            blockers.append(
                "Choose a usable contact in the plan or select a preferred published route."
            )
        if not available:
            blockers.append(
                "A current certified report must be available before this handoff is ready."
            )
        if scope_warning:
            blockers.append(scope_warning["message"])
        if not settings.get("analyst_name", "").strip():
            blockers.append("Set your sender name in Settings.")
        if not verify:
            blockers.append("Configure a public verification URL or office telephone route.")
        company = entity["company"] or entity["domain"]
        identity = ", ".join(
            v
            for v in (
                settings.get("analyst_name", ""),
                settings.get("analyst_title", ""),
                settings.get("agency", ""),
            )
            if v
        )
        reference = case["title"] or case_id
        publication = (
            "Your organization published this contact route on its website."
            if source
            else "This contact route was selected from our recorded business-contact research."
        )
        opening = (
            f"My name is {identity}."
            if settings.get("analyst_name", "").strip()
            else "[Enter your name and organization before using this introduction.]"
        )
        verification = (
            f"You can independently verify this outreach through: {verify}."
            if verify
            else "[Add an independently accessible official verification route before outreach.]"
        )
        report_offer = (
            "[Revise and recertify the report scope before offering this notification.]"
            if scope_warning
            else "A supporting notification report is available for review."
            if available
            else "[Complete report certification before offering the notification report.]"
        )
        message = f"Hello,\n\n{opening}\n\nWe are contacting {company} about a reported vulnerability associated with a service attributed to your organization. The finding comes from a Shadowserver report and does not by itself establish that exploitation occurred.\n\n{publication} Could you direct this notification to the person responsible for the affected systems?\n\n{verification}\n\nNotification reference: {reference}. {report_offer}\n\nThank you,\n{settings.get('analyst_name', '')}"
        return {
            "case_id": case_id,
            "case_version": case["version"],
            "ready": not blockers,
            "blockers": blockers,
            "warnings": summary["warnings"] + ([scope_warning["message"]] if scope_warning else []),
            "scope_warning": scope_warning,
            "contact": selected,
            "contact_plan": {
                "contact_name": case["contact_name"] or profile.get("contact_name", ""),
                "contact_role": case["contact_role"] or profile.get("contact_title", ""),
                "contact_email": case["contact_email"] or profile.get("contact_email", ""),
                "contact_phone": case["contact_phone"] or profile.get("contact_phone", ""),
            },
            "source_explanation": source["provenance_text"]
            if source
            else "Manually recorded contact plan; no published-source citation is attached.",
            "report": {
                "id": report["id"],
                "revision": report["revision"],
                "url": f"/api/reports/{report['id']}/pdf",
            }
            if available
            else None,
            "subject": f"Vulnerability notification for {company} — {reference}",
            "message": message,
            "verification_route": verify,
            "outreach_policy": policy,
            "call_outline": f"1. Identify yourself: {identity or '[configured sender required]'}.\n2. Ask for the person responsible for the reported systems.\n3. Explain that this is a proactive notification based on a Shadowserver report.\n4. Offer independent verification: {verify or '[configure public verification route]'}.\n5. Agree on a suitable delivery route and record the actual outcome.\nReference: {reference}",
        }

    def export(self, entity_id, run_id=None):
        from modules.entities.components.contact_validation import validate_contact_data

        projection = self.export_projection(entity_id)
        validate_contact_data(self.store, projection["entity_id"], allow_unavailable_legacy=True)
        rows = self.store.all(
            "SELECT * FROM contact_runs WHERE entity_id=? ORDER BY rowid",
            (projection["entity_id"],),
        )
        if run_id is not None:
            rows = [row for row in rows if row["id"] == run_id]
        if not rows:
            raise ValueError("No saved contact discovery evidence was found")
        handle, filename = tempfile.mkstemp(suffix=".zip")
        os.close(handle)
        path = Path(filename)
        try:
            with ZipFile(path, "w", ZIP_DEFLATED) as archive:
                archive.writestr("provenance.json", dump(projection))
                archive.writestr(
                    "README.txt",
                    "Published contact extracts and source provenance. Original webpage bodies are not included. Source SHA-256 values identify received responses; artifact hashes identify the derived contact JSON. Historical webpage bodies are omitted even when present locally. Attribution references and contact review decisions are in provenance.json. Publication does not establish delivery or system responsibility.\n",
                )
                for row in rows:
                    run = json.loads(row["payload"])
                    archive.writestr(
                        f"runs/{row['id']}/run.json",
                        dump({**run, "attribution_scope": json.loads(row["scope"])}),
                    )
                    for snapshot in run["snapshots"]:
                        if not is_derived_snapshot(snapshot):
                            continue
                        content = snapshot_content(self.store, row["id"], snapshot)
                        archive.writestr(
                            f"runs/{row['id']}/" + Path(snapshot["path"]).name, content
                        )
                    scope = json.loads(row["scope"])
                    expected = scope.pop("fingerprint")
                    if fingerprint(scope) != expected:
                        raise ValueError("Contact attribution scope failed its fingerprint check")
                    if not scope.get("attribution_ref"):
                        continue
                    with EvidenceStore(self.store.root / "attribution.sqlite3") as evidence:
                        original = checked_result(
                            evidence, scope["attribution_ref"]["result_id"], row["root_domain"]
                        )
                        _verify_snapshots(evidence, original)
                        archive.writestr(
                            f"runs/{row['id']}/attribution/result.json", dump(original)
                        )
                        # Registration result and its referenced digests are sufficient
                        # context here. Contact exports never distribute raw responses.
            return path
        except Exception:
            path.unlink(missing_ok=True)
            raise
