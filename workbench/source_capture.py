"""Capture case-selected saved evidence for report assembly; never performs I/O online."""

from __future__ import annotations

from copy import deepcopy
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from attribution import EvidenceStore
from .attribution_bridge import checked_result, domain_identity, same_domain
from .source_references import cve_response_sources as cve_response_sources
from .intelligence.acquisition import validate_capture_body


def _snapshots(value):
    result = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "snapshot_id" and isinstance(item, str):
                result.add(item)
            elif key in ("snapshot_ids", "supporting_snapshot_ids") and isinstance(item, list):
                result.update(x for x in item if isinstance(x, str))
            else:
                result.update(_snapshots(item))
    elif isinstance(value, list):
        for item in value:
            result.update(_snapshots(item))
    return result


def _case_record(raw, cve_ids):
    # Retain the matched entries and full catalog metadata, not unrelated clients.
    if (
        isinstance(raw, dict)
        and isinstance(raw.get("vulnerabilities"), list)
        and ("catalogVersion" in raw or "count" in raw)
    ):
        return {
            **{k: v for k, v in raw.items() if k != "vulnerabilities"},
            "vulnerabilities": [
                item
                for item in raw["vulnerabilities"]
                if isinstance(item, dict) and item.get("cveID") in cve_ids
            ],
            "selection_scope": "Matching case CVEs; full captured catalog retained in internal evidence package",
        }
    return raw


def capture_sources(store, data):
    """Sources are selected by pinned case proof/result IDs and pinned CVE revisions."""
    sources = {}
    history = []
    issues = []
    # Import settings contain workstation/analyst preferences as well as parsing
    # policy. Only case-relevant source identity and parsing policy belong in a
    # recipient appendix; no arbitrary settings or complete workbook rows.
    import_sources = {}
    case_id = data.get("case_id")
    if case_id:
        rows = store.all(
            """SELECT i.id,i.name,i.sha256,i.fingerprint,i.created_at,i.config,
                                   e.id AS entry_id
                            FROM case_entries ce JOIN entries e ON e.id=ce.entry_id
                            JOIN imports i ON i.id=e.import_id
                            WHERE ce.case_id=? ORDER BY i.created_at,i.id,e.id""",
            (case_id,),
        )
        policy_keys = (
            "regions",
            "sheet",
            "com_only",
            "exclude_numeric_roots",
            "critical_only",
            "outreach_mode",
            "report_type",
            "report_profiles",
            "profile_inventory",
        )
        selected_entry_ids = {
            entry["id"]
            for group in data["qualified_lead"].get("validated_leads", [])
            for entry in group.get("entries", [])
        }
        for row in rows:
            if row["entry_id"] not in selected_entry_ids:
                continue
            if row["id"] not in import_sources:
                config = json.loads(row["config"])
                import_sources[row["id"]] = {
                    "id": row["id"],
                    "filename": row["name"],
                    "sha256": row["sha256"],
                    "import_fingerprint": row["fingerprint"],
                    "imported_at": row["created_at"],
                    "parsing_policy": {
                        key: deepcopy(config[key]) for key in policy_keys if key in config
                    },
                    "scope": "Metadata for the original import. Only this notification's selected observations are reproduced.",
                    "referenced_by": [],
                }
            import_sources[row["id"]]["referenced_by"].append(row["entry_id"])
    data["import_sources"] = list(import_sources.values())
    cve_ids = set(data.get("cves", []))

    def add(metadata, record, refs):
        identity = {
            k: metadata.get(k)
            for k in (
                "snapshot_id",
                "revision_id",
                "provider",
                "publisher",
                "url",
                "source_url",
                "retrieved_at",
                "body_sha256",
                "sha256",
                "record_path",
                "id",
            )
        }
        key = str(
            metadata.get("snapshot_id")
            or hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        )
        if key in sources:
            current = sources[key]
            current["referenced_by"] = sorted(set(current["referenced_by"] + refs))
            if metadata.get("acquisition_outcomes"):
                outcomes = current.setdefault("acquisition_outcomes", [])
                for outcome in metadata["acquisition_outcomes"]:
                    if outcome not in outcomes:
                        outcomes.append(deepcopy(outcome))
                current["source_status"] = (
                    "captured_failed_response"
                    if any(item.get("outcome") != "success" for item in outcomes)
                    else "captured_response"
                )
            return
        sources[key] = {
            **deepcopy(metadata),
            "id": key,
            "record": record,
            "referenced_by": list(refs),
        }

    records = data.get("draft", {}).get("cve_records", [])
    for record in records:
        for source in cve_response_sources(record):
            if not isinstance(source, dict):
                continue
            path = source.get("record_path")
            metadata = {
                k: deepcopy(source[k])
                for k in (
                    "id",
                    "revision_id",
                    "provider",
                    "publisher",
                    "source",
                    "title",
                    "public_url",
                    "url",
                    "requested_url",
                    "source_url",
                    "retrieved_at",
                    "published_at",
                    "updated_at",
                    "date_published",
                    "date_updated",
                    "body_sha256",
                    "sha256",
                    "record_path",
                    "status",
                    "http_status",
                    "source_restrictions",
                    "acquisition_outcomes",
                    "source_status",
                    "adapter_version",
                    "retry_after",
                    "response_retention",
                    "validation_error",
                    "content_type",
                    "captured_bytes",
                )
                if k in source
            }
            metadata.setdefault(
                "provider",
                source.get("provider")
                or source.get("publisher")
                or source.get("source")
                or record.get("source")
                or "Captured source",
            )
            if source.get("response_retention") == "metadata-only" or (
                path and source.get("http_status") not in (None, 200)
            ):
                metadata.update(
                    availability="omitted",
                    response_retention="metadata-only",
                    reason=source.get("validation_error")
                    or "Unsuccessful provider response body omitted by input policy",
                )
                if path:
                    metadata["original_record_path"] = metadata.pop("record_path")
                add(metadata, None, [record["id"]])
                continue
            if not path:
                continue
            try:
                with store.path(path).open("rb") as captured:
                    raw = captured.read(8 * 1024 * 1024 + 1)
                digest = hashlib.sha256(raw).hexdigest()
                expected = source.get("body_sha256") or source.get("sha256")
                if expected and expected != digest:
                    raise ValueError("Saved source response failed its integrity check")
                publisher = source.get("publisher") or source.get("source") or metadata["provider"]
                parsed = validate_capture_body(
                    raw, publisher, cve_id=record["id"], url=source.get("url", "")
                )
                metadata["body_sha256"] = digest
                metadata["response_retention"] = "validated-provider-json"
                add(metadata, _case_record(parsed, cve_ids), [record["id"]])
            except (OSError, ValueError) as error:
                issues.append(str(path) + ": " + str(error))
                metadata["availability"] = "unavailable"
                metadata["reason"] = str(error)
                metadata["id"] = "missing:" + str(path)
                add(metadata, None, [record["id"]])
    proofs = data.get("qualified_lead", {}).get("whois", [])
    selected_ids = {p["result_id"] for p in proofs if p.get("result_id")}

    def clock(value):
        try:
            instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return instant.astimezone(timezone.utc) if instant.tzinfo else None
        except ValueError, TypeError:
            return None

    if selected_ids:
        with closing(EvidenceStore(store.root / "attribution.sqlite3")) as evidence_store:
            selected = {}
            for result_id in sorted(selected_ids):
                try:
                    result = evidence_store.result(result_id)
                    roots = {
                        p.get("attribution", {}).get("root_domain")
                        for p in proofs
                        if p.get("result_id") == result_id
                    }
                    if result.get("result_id") != result_id or not any(
                        same_domain(result.get("root_domain"), root) for root in roots
                    ):
                        raise ValueError(
                            "Attribution result does not belong to the case domain group"
                        )
                    selected[result_id] = result
                except (KeyError, ValueError, OSError) as error:
                    issues.append(result_id + ": " + str(error))
                    history.append(
                        {
                            "result_id": result_id,
                            "availability": "unavailable",
                            "reason": str(error),
                        }
                    )
            included = dict(selected)
            inherited_ids = set()
            for proof in proofs:
                if "approval_reuse" not in proof:
                    continue
                from .attribution_approval_evidence import valid_approval_reuse

                try:
                    root = (proof.get("attribution") or {}).get("root_domain")
                    if not valid_approval_reuse(proof, root, evidence_store):
                        raise ValueError(
                            "Inherited attribution approval failed its integrity check"
                        )
                    source_id = proof["approval_reuse"]["source_result_id"]
                    included[source_id] = checked_result(evidence_store, source_id, root)
                    inherited_ids.add(source_id)
                except (KeyError, ValueError, OSError) as error:
                    issues.append(str(proof.get("result_id", "")) + ": " + str(error))
            # Only look at jobs belonging to the case's original observation
            # imports, and never adopt a later retry or later analyst decision.
            case_id = data.get("case_id")
            jobs = (
                store.all(
                    """SELECT DISTINCT j.id,j.domain,j.attempts FROM jobs j JOIN entries e
              ON e.import_id=j.import_id AND e.root_domain=j.domain
              JOIN case_entries ce ON ce.entry_id=e.id WHERE ce.case_id=?""",
                    (case_id,),
                )
                if case_id
                else []
            )
            cutoffs = {}
            for proof in proofs:
                result = selected.get(proof.get("result_id"))
                if result:
                    cutoff = clock(result.get("evaluated_at"))
                    if cutoff:
                        identity = domain_identity(result["root_domain"])
                        cutoffs[identity] = max(cutoffs.get(identity, cutoff), cutoff)
            for job in jobs:
                cutoff = cutoffs.get(domain_identity(job["domain"]))
                if not cutoff:
                    continue
                for attempt in json.loads(job["attempts"] or "[]"):
                    result_id = attempt.get("result_id")
                    if not result_id or result_id in included:
                        continue
                    try:
                        result = checked_result(evidence_store, result_id, job["domain"])
                        timestamp = clock(result.get("evaluated_at"))
                        if timestamp and timestamp <= cutoff:
                            included[result_id] = result
                    except (KeyError, ValueError, OSError) as error:
                        # A historical reference is retained visibly; no future
                        # or unverifiable response is silently substituted.
                        history.append(
                            {
                                "result_id": result_id,
                                "availability": "unavailable",
                                "reason": str(error),
                            }
                        )
            for result_id, result in sorted(
                included.items(), key=lambda row: (row[1].get("evaluated_at", ""), row[0])
            ):
                item = deepcopy(result)
                item["case_evidence_status"] = (
                    "selected supporting result"
                    if result_id in selected
                    else "source of reused analyst approval"
                    if result_id in inherited_ids
                    else "prior case-relevant result"
                )
                roots = [
                    p
                    for p in proofs
                    if same_domain(
                        p.get("attribution", {}).get("root_domain"), result.get("root_domain")
                    )
                ]
                clocks = [
                    clock(p.get("review", {}).get("reviewed_at"))
                    or clock(result.get("evaluated_at"))
                    for p in roots
                ]
                review_cutoff = max((value for value in clocks if value), default=None)
                reviews = store.all(
                    "SELECT * FROM attribution_reviews WHERE result_id=? ORDER BY reviewed_at",
                    (result_id,),
                )
                item["analyst_reviews"] = [
                    r
                    for r in reviews
                    if clock(r.get("reviewed_at"))
                    and review_cutoff
                    and clock(r["reviewed_at"]) <= review_cutoff
                ]
                history.append(item)
                try:
                    for snapshot_id in sorted(_snapshots(result)):
                        snap = evidence_store.snapshot(snapshot_id)
                        meta = snap.metadata()
                        meta.update(provider="Registration/DNS source", id=snapshot_id)
                        try:
                            record = snap.record()
                        except ValueError:
                            record = None
                            meta.update(
                                availability="omitted",
                                response_retention="metadata-only",
                                reason="Unvalidated registration response body omitted by input policy",
                            )
                        add(meta, record, [result_id])
                except (KeyError, ValueError, OSError) as error:
                    issues.append(result_id + ": " + str(error))
                    item["source_availability"] = "unavailable"
                    item["source_error"] = str(error)
    data["source_snapshots"] = list(sources.values())
    data["attribution_history"] = history
    data["source_integrity_issues"] = issues
    return data
