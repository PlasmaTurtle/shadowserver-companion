"""Build a report directory using a package-owned copy of the snapshot.

The caller controls staging, publication, and database transactions. This module
copies captured evidence, adjusts only the copy's relative paths, renders all
artifacts, and returns the resulting snapshot and file inventory. If a build
fails, it leaves caller data untouched; the caller removes the staging folder.
"""

from __future__ import annotations

from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Protocol
from attribution import EvidenceRenderer, EvidenceStore
from modules.ui.components.exhibit_rendering import capture_exhibit_masters
from modules.ui.components.print_policy import TLP_EXPLANATION
from .report_contracts import ReportSnapshot
from modules.activity.components.work_log import render_work_log
from modules.workspace.components import compact_json
from .evidence_reader import write_evidence_reader


class PackageRenderer(Protocol):
    def __call__(self, data: ReportSnapshot, destination: Path, evidence_root: Path) -> None: ...


@dataclass(frozen=True)
class PackageRenderers:
    pdf: PackageRenderer
    docx: PackageRenderer


@dataclass(frozen=True)
class BuiltPackage:
    snapshot: ReportSnapshot
    files: dict[str, str]


def _write_snapshot(path: Path, data: ReportSnapshot) -> None:
    # New packages use a lossless shared-resource envelope. Existing certified
    # packages remain untouched and are decoded by the same versioned reader.
    with path.open("w", encoding="utf-8") as stream:
        compact_json.dump(data, stream)


def _file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _provider_capture(store, source, *, cve_id="", publisher=""):
    """Recheck older on-disk provider captures at the new-package boundary."""
    from modules.library.components.intelligence.acquisition import validate_capture_body

    status = source.get("http_status", source.get("status_code"))
    if status is not None and (
        isinstance(status, bool) or not isinstance(status, int) or not 200 <= status < 300
    ):
        raise ValueError("Failed HTTP response omitted from provider evidence")
    if source.get("response_retention") == "metadata-only":
        raise ValueError("Provider response was retained as metadata only")
    path = store.path(source["record_path"])
    maximum = 8 * 1024 * 1024
    if path.stat().st_size > maximum:
        raise ValueError("Saved provider response exceeds the capture limit")
    with path.open("rb") as stream:
        content = stream.read(maximum + 1)
    expected = source.get("body_sha256") or source.get("sha256")
    if expected and hashlib.sha256(content).hexdigest() != expected:
        raise ValueError("Saved provider response failed its integrity check")
    provider = (
        source.get("publisher") or source.get("source") or source.get("provider") or publisher
    )
    if not cve_id:
        cve_id = next(
            (
                value
                for value in [source.get("id", ""), *source.get("referenced_by", [])]
                if isinstance(value, str) and re.fullmatch(r"CVE-\d{4}-\d{4,}", value)
            ),
            "",
        )
    validate_capture_body(
        content,
        provider,
        cve_id=cve_id,
        url=source.get("url") or source.get("source_url") or "",
    )
    return content


def _omit_provider_capture(source, error):
    """Keep the original provenance without copying an unvalidated response."""
    source["original_record_path"] = source.pop("record_path")
    source["availability"] = "omitted"
    source["package_availability"] = "omitted"
    source["package_issue"] = str(error)
    if "record" in source:
        source["record"] = None


def supporting_appendix_snapshot(data: ReportSnapshot) -> ReportSnapshot:
    """Render the retained appendix as its own document without altering evidence."""
    content = data["composition"]
    sections = list(content.get("supporting_appendix_sections", []))
    if content.get("include_appendix", True) is not False or not sections:
        raise ValueError("This report does not have a separately retained appendix")
    while sections and sections[0]["kind"] == "page_break":
        sections.pop(0)
    rendered_ids = {node["exhibit_id"] for node in sections if node.get("exhibit_id")}
    return {
        **data,
        "composition": {
            **content,
            "sections": sections,
            # Backreferences to the front notification remain plain text rather
            # than creating links to absent destinations in this separate file.
            "exhibits": [
                exhibit for exhibit in content["exhibits"] if exhibit["id"] in rendered_ids
            ],
            "appendix_navigation": content.get("supporting_appendix_navigation", {}),
        },
    }


def assemble_package(
    store, source: ReportSnapshot, temporary: Path, renderers: PackageRenderers
) -> BuiltPackage:
    """Write package artifacts without mutating the source snapshot or case."""
    data = deepcopy(source)
    (temporary / "evidence").mkdir()
    _package_attribution(store, data["qualified_lead"]["whois"], temporary)
    for cve_id, disposition in data["draft"].get("cve_dispositions", {}).items():
        if disposition.get("action") == "fallback":
            (temporary / "evidence" / ("official-fallback-" + cve_id + ".json")).write_text(
                json.dumps(disposition, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    for record in data["draft"]["cve_records"]:
        if record.get("record_path"):
            # A hash only proves that the old bytes did not change. A primary
            # published source must also match its provider schema now.
            content = _provider_capture(store, record, cve_id=record["id"])
            dest = Path("evidence") / (record["id"] + "-" + record["body_sha256"][:16] + ".json")
            # Write the exact bytes just verified. Reopening the source for a
            # separate copy could package newer, unverified bytes after a sync.
            (temporary / dest).write_bytes(content)
            record["original_record_path"] = record["record_path"]
            record["record_path"] = dest.as_posix()
        for source_info in record.get("sources", []):
            if source_info.get("record_path"):
                try:
                    content = _provider_capture(
                        store, source_info, cve_id=record["id"], publisher=record.get("source", "")
                    )
                except (OSError, ValueError) as error:
                    _omit_provider_capture(source_info, error)
                    continue
                dest = Path("evidence") / ("reference-" + source_info["sha256"] + ".json")
                (temporary / dest).write_bytes(content)
                source_info["original_record_path"] = source_info["record_path"]
                source_info["record_path"] = dest.as_posix()
    # Preserve valid supplementary provider records, including ADP/SSVC and
    # complete shared feeds. Historical HTML/error bodies remain metadata only.
    for source_info in data.get("source_snapshots", []):
        if source_info.get("record_path") and source_info.get("availability") not in {
            "unavailable",
            "omitted",
        }:
            original_path = source_info["record_path"]
            try:
                raw = _provider_capture(store, source_info)
            except (OSError, ValueError) as error:
                _omit_provider_capture(source_info, error)
                continue
            digest = hashlib.sha256(raw).hexdigest()
            dest = Path("evidence") / ("captured-" + digest + ".json")
            (temporary / dest).write_bytes(raw)
            source_info["original_record_path"] = original_path
            source_info["record_path"] = dest.as_posix()
    for item in data["evidence"]:
        for key in ("path", "preview_path"):
            source = store.path(item[key])
            dest = Path("evidence") / (
                item["id"] + ("-preview.png" if key == "preview_path" else ".original.bin")
            )
            content = source.read_bytes()
            if hashlib.sha256(content).hexdigest() != item["file_integrity"][key + "_sha256"]:
                raise ValueError("Screenshot evidence changed during certification")
            (temporary / dest).write_bytes(content)
            item[key] = dest.as_posix()
    if data.get("contact_research"):
        research = data["contact_research"]
        _package_contact_research(store, research, temporary)
        (temporary / "evidence" / "contact-research.json").write_text(
            json.dumps(research, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    for citation in data["composition"]["citations"]:
        if citation.get("record_path"):
            for record in data["draft"]["cve_records"]:
                for proof in [record, *record.get("sources", [])]:
                    if proof.get("original_record_path") == citation["record_path"]:
                        citation["original_record_path"] = citation["record_path"]
                        citation["record_path"] = proof.get("record_path", "")
                        if proof.get("package_availability") == "omitted":
                            citation["package_availability"] = "omitted"
                        break
    from .package_exhibits import export_gallery

    data["package_format"] = "shadowserver-report-package-v2"
    capture_exhibit_masters(data["composition"])
    data["exhibit_artifacts"] = export_gallery(
        data["composition"], temporary / "exhibits", data.get("document_policy")
    )
    (temporary / "appendix-index.json").write_text(
        json.dumps(
            data["composition"].get("appendix", {}).get("index", []), ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    (temporary / "handling-notice.txt").write_text(TLP_EXPLANATION + "\n", encoding="utf-8")
    renderers.pdf(data, temporary / "notification.pdf", temporary)
    renderers.docx(data, temporary / "notification.docx", temporary)
    if data["composition"].get("full_edition_sections"):
        from .recipient_edition import full_report_snapshot

        full_data = full_report_snapshot(data)
        renderers.pdf(full_data, temporary / "complete-report.pdf", temporary)
        renderers.docx(full_data, temporary / "complete-report.docx", temporary)
    if data["composition"].get("include_appendix", True) is False and data["composition"].get(
        "supporting_appendix_sections"
    ):
        appendix_data = supporting_appendix_snapshot(data)
        renderers.pdf(appendix_data, temporary / "supporting-appendix.pdf", temporary)
        renderers.docx(appendix_data, temporary / "supporting-appendix.docx", temporary)
    render_work_log(data, data["chronology"], temporary / "work-log.pdf")
    (temporary / "chronology.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "case_id": data["case_id"],
                "report_id": data["certification"]["report_id"],
                "revision": data["report_revision"],
                "events": data["chronology"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_snapshot(temporary / "snapshot.json", data)
    write_evidence_reader(data, temporary)
    hashes = {
        p.relative_to(temporary).as_posix(): _file_sha256(p)
        for p in temporary.rglob("*")
        if p.is_file()
    }
    return BuiltPackage(snapshot=data, files=hashes)


def _package_attribution(store, proofs, destination):
    """Export each result once, with decisions attached only to their source result."""
    saved = [proof for proof in proofs if proof.get("result_id")]
    if not saved:
        return
    from modules.attribution.components.attribution_approval_evidence import valid_approval_reuse
    from modules.ui.components.presentation import mark_attribution_bundle

    with closing(EvidenceStore(store.root / "attribution.sqlite3")) as evidence_store:
        exports = {}
        for proof in saved:
            inherited = proof.get("approval_reuse")
            if "approval_reuse" in proof:
                root = (proof.get("attribution") or {}).get("root_domain")
                if not valid_approval_reuse(proof, root, evidence_store):
                    raise ValueError("The prior registrant approval failed evidence verification")
                source = inherited["source_proof"]
                exports.setdefault(source["result_id"], {})[source["review"]["id"]] = source[
                    "review"
                ]
            decisions = exports.setdefault(proof["result_id"], {})
            if proof.get("review") and not inherited:
                review = proof["review"]
                decisions[review.get("id") or proof["result_id"]] = review
        for result_id, decisions in exports.items():
            path = destination / "registration" / result_id
            EvidenceRenderer(evidence_store).export(
                result_id, path, review_decisions=list(decisions.values())
            )
            mark_attribution_bundle(path)


def _package_contact_research(store, research, destination):
    """Copy validated contact extracts, never previously retained website bodies.

    This operates on the package-owned snapshot. Historical captures and already
    certified packages remain unchanged; their source metadata still explains
    which response supported the original contact finding.
    """
    from modules.entities.components.contact_evidence import is_derived_snapshot, snapshot_content

    for run in research.get("runs", []):
        for captured in run.get("snapshots", []):
            original_path = captured.pop("path", "")
            if original_path:
                captured["original_path"] = original_path
            if not is_derived_snapshot(captured):
                captured["package_availability"] = "omitted"
                captured["package_issue"] = (
                    "Original webpage response omitted by contact evidence policy; "
                    "source metadata and extracted contact findings are retained."
                )
                continue
            try:
                content = snapshot_content(store, run["id"], {**captured, "path": original_path})
            except (ValueError, OSError) as error:
                # Optional contact evidence must not become a certification
                # gate or silently recreate a quarantined/missing artifact.
                captured["package_availability"] = "unavailable"
                captured["package_issue"] = str(error)
                continue
            digest = hashlib.sha256(content).hexdigest()
            dest = Path("evidence") / ("contact-" + digest + ".contact.json")
            (destination / dest).write_bytes(content)
            captured["path"] = dest.as_posix()
            captured["package_availability"] = "available"
            captured.pop("package_issue", None)
