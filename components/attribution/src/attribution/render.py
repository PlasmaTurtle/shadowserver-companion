"""Portable evidence export; HTML is built only from saved snapshots and escaped text."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import tempfile
from pathlib import Path

from .models import json_bytes
from .store import EvidenceStore


def atomic_write(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".attribution-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    except BaseException:
        if os.path.exists(name):
            os.unlink(name)
        raise


def exportable_snapshot(snapshot):
    """Do not redistribute historical non-JSON or rejected response bodies."""
    if snapshot.body_retention != "original":
        return snapshot
    media = snapshot.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if snapshot.status_code not in (200, 404) or media not in (
        "application/json", "application/rdap+json", "application/dns-json", "application/x-javascript"
    ):
        return snapshot.without_body("legacy_unvalidated_response")
    try:
        snapshot.record()
    except ValueError:
        return snapshot.without_body("legacy_unvalidated_response")
    return snapshot


def render_html(result: dict, snapshots: dict, review_decisions=()) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    matches = []
    for evidence in result["evidence"]:
        match = evidence["match"]
        details = evidence.get("details", {})
        extra = "".join(f"<dt>{esc(k.replace('_', ' ').capitalize())}</dt><dd>{esc(v)}</dd>" for k, v in details.items())
        matches.append(f'''<section><h2>Qualifying attribution</h2>
        <dl><dt>IP address</dt><dd>{esc(evidence['ip'])}</dd>
        <dt>Source / method</dt><dd>{esc(evidence['source_name'])} / {esc(evidence['method'].upper())}</dd>
        <dt>Retrieved (UTC)</dt><dd>{esc(evidence['retrieved_at'])}</dd>
        <dt>Matched domain</dt><dd><mark>{esc(match['matched_domain'])}</mark></dd>
        <dt>Complete field value</dt><dd class="mono">{esc(match['value'])}</dd>
        <dt>JSON Pointer</dt><dd class="mono">{esc(match['field_path'])}</dd>
        <dt>Entity / roles</dt><dd>{esc(match.get('entity_handle') or 'Not specified')} / {esc(', '.join(match.get('entity_roles', [])) or 'Not specified')}</dd>
        {extra}
        <dt>Source URL</dt><dd class="mono">{esc(evidence['source_url'])}</dd>
        <dt>Snapshot</dt><dd class="mono">{esc(evidence['snapshot_id'])}</dd></dl></section>''')
    decision_html = ''.join(f'''<section><h2>Analyst decision: {esc(r['decision'])}</h2>
        <p>{esc(r['reviewer'])} · {esc(r['reviewed_at'])}</p><p>{esc(r.get('note', ''))}</p>
        <p>Selected partial-match index: {esc(r.get('evidence_index'))}</p>
        <p class="subtitle">The original automated result below remains unchanged.</p></section>'''
        for r in review_decisions)
    partial_html = []
    for evidence in result.get("partial_evidence", []):
        match, details = evidence["match"], evidence["details"]
        words = details["matched_words"]
        parts, end = [], 0
        for found in re.finditer("|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)), match["value"], re.IGNORECASE):
            parts += [esc(match["value"][end:found.start()]), "<mark>" + esc(found.group()) + "</mark>"]
            end = found.end()
        parts.append(esc(match["value"][end:]))
        partial_html.append(f'''<section><h2>Partial name match — analyst review required</h2>
        <p>{''.join(parts)}</p><dl><dt>Matching words</dt><dd>{esc(', '.join(words))}</dd>
        <dt>Reported root / IP</dt><dd>{esc(result['root_domain'])} / {esc(evidence['ip'])}</dd>
        <dt>Original entry</dt><dd>{esc(details.get('entry_id', ''))}</dd>
        <dt>Source field</dt><dd class="mono">{esc(match['field_path'])}</dd>
        <dt>Source</dt><dd>{esc(evidence['source_name'])} · {esc(evidence['source_url'])}</dd>
        <dt>Retrieved (UTC)</dt><dd>{esc(evidence['retrieved_at'])}</dd>
        <dt>Registered range</dt><dd>{esc(details.get('network_start', ''))} – {esc(details.get('network_end', ''))}</dd>
        <dt>Snapshot</dt><dd class="mono">{esc(evidence['snapshot_id'])}</dd></dl></section>''')
    records = []
    for sid, snapshot in snapshots.items():
        snapshot = exportable_snapshot(snapshot)
        try:
            raw = json.dumps(snapshot.record(), ensure_ascii=False, indent=2)
        except ValueError:
            raw = json.dumps({
                "body_retention": snapshot.body_retention,
                "received_body_sha256": snapshot.received_body_sha256,
                "received_body_size": snapshot.received_body_size,
                "note": "Response body omitted; only retrieval metadata is retained in this export.",
            }, ensure_ascii=False, indent=2)
        transport = "DNS observation" if snapshot.source_url.startswith("dns:") else f"HTTP {snapshot.status_code}"
        records.append(f'''<details><summary>{esc(snapshot.source_url)} · {esc(transport)}</summary>
          <p>Retrieved: {esc(snapshot.retrieved_at)}<br>SHA-256: <span class="mono">{esc(snapshot.body_sha256)}</span></p>
          <pre>{esc(raw)}</pre></details>''')
    attempts = "".join(f"<tr><td>{esc(a['entry_id'])}</td><td>{esc(a['ip'])}</td><td>{esc(a['status'])}</td><td>{esc(a['reason'])}</td></tr>" for a in result["attempts"])
    warnings = sorted({w for a in result["attempts"] for w in a.get("warnings", [])})
    warning_html = "<section><h2>Record limitations</h2><ul>" + "".join(f"<li>{esc(w)}</li>" for w in warnings) + "</ul></section>" if warnings else ""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; base-uri 'none'; form-action 'none'">
    <title>Attribution evidence — {esc(result['root_domain'])}</title><style>
    :root{{color-scheme:light;font-family:Segoe UI,Arial,sans-serif;color:#182e39;background:#eef2f4}}
    *{{box-sizing:border-box}}body{{margin:0;padding:44px 20px}}main{{max-width:960px;margin:auto;background:#fff;padding:48px 54px;border-top:6px solid #216565;border-radius:4px;box-shadow:0 8px 40px #162e3910}}
    .eyebrow{{font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#48717a;font-weight:700}}h1{{font-size:32px;margin:14px 0 8px;font-weight:650}}h2{{font-size:18px;color:#216565;margin:0 0 18px}}p{{line-height:1.6}}.subtitle{{color:#5b6e77}}.status{{display:inline-block;padding:6px 12px;background:#e6f1ef;border:1px solid #c2ddd8;border-radius:5px;font-weight:600}}
    section{{margin-top:30px;border-top:1px solid #dee6e9;padding-top:26px}}dl{{display:grid;grid-template-columns:175px minmax(0,1fr);gap:12px 20px;font-size:14px}}dt{{color:#5b6e77}}dd{{margin:0;overflow-wrap:anywhere;line-height:1.5}}mark{{background:#def3cd;padding:2px 4px}}.mono,pre{{font-family:Consolas,monospace;font-size:12px;overflow-wrap:anywhere}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{text-align:left;border-bottom:1px solid #e2e9ec;padding:10px;overflow-wrap:anywhere}}th{{background:#f2f6f7}}details{{margin:12px 0;border:1px solid #dce6e9;border-radius:4px;padding:14px;font-size:13px;overflow-wrap:anywhere}}summary{{cursor:pointer;font-weight:600}}pre{{white-space:pre-wrap;max-height:500px;overflow:auto;background:#f5f7f8;padding:14px}}footer{{margin-top:32px;color:#647982;font-size:12px;line-height:1.6}}@media(max-width:640px){{body{{padding:12px}}main{{padding:24px}}dl{{grid-template-columns:1fr;gap:4px}}dd{{margin-bottom:12px}}}}@media print{{body{{padding:0;background:white}}main{{box-shadow:none;padding:12mm;border-radius:0}}section{{break-inside:avoid}}details{{break-inside:avoid}}pre{{max-height:none}}}}
    </style></head><body><main><div class="eyebrow">Attribution Module · Evidence record</div>
    <h1>{esc(result['root_domain'])}</h1><p class="subtitle">Registration attribution for a notification lead</p>
    <span class="status">{esc(result['status'].replace('_',' ').upper())}</span>
    <p>Evaluated: {esc(result['evaluated_at'])}<br>Result ID: <span class="mono">{esc(result['result_id'])}</span></p>
    {decision_html}{''.join(matches)}{''.join(partial_html)}{warning_html}<section><h2>Lookup attempts</h2><table><thead><tr><th>Entry</th><th>IP</th><th>Outcome</th><th>Reason</th></tr></thead><tbody>{attempts}</tbody></table>
    <p class="subtitle">{len(result['candidates'])} candidate observations retained. Processing stops after the first qualifying match.</p></section>
    <section><h2>Saved source responses</h2><p class="subtitle">Expand a response to inspect preserved registry data. Rejected and unsupported bodies are omitted; their retrieval receipts identify the omission and received checksum.</p>{''.join(records)}</section>
    <footer>Policy: {esc(result['policy']['id'])} · Module {esc(result['module_version'])}<br>
    This exhibit records registration and DNS observations. Partial name matches require an analyst decision. Current DNS does not establish the hostname's historical address. Retrieval times are the workstation's UTC timestamps. SHA-256 checks detect changed bytes; they do not independently authenticate the source or timestamp.</footer>
    </main></body></html>'''


class EvidenceRenderer:
    def __init__(self, store: EvidenceStore):
        self.store = store

    def export(self, result_id: str, destination: str | Path, *, review_decisions=()) -> Path:
        result = self.store.result(result_id)
        if any(r.get('result_id') != result_id for r in review_decisions):
            raise ValueError('A review decision belongs to a different attribution result')
        destination = Path(destination)
        if destination.exists() and any(destination.iterdir()):
            raise ValueError("Export directory must be empty; existing evidence will not be overwritten")
        destination.mkdir(parents=True, exist_ok=True)
        ids = list(dict.fromkeys(sid for a in result["attempts"] for sid in a["snapshot_ids"]))
        ids.extend(sid for e in [*result["evidence"], *result.get("partial_evidence", [])] for sid in e["supporting_snapshot_ids"] if sid not in ids)
        if any(not re.fullmatch(r"[a-f0-9]{32}", sid) for sid in ids):
            raise ValueError("Invalid snapshot identifier")
        snapshots = {sid: exportable_snapshot(self.store.snapshot(sid)) for sid in ids}
        outputs = {"attribution.json": json_bytes(result),
                   "evidence.html": render_html(result, snapshots, review_decisions).encode("utf-8")}
        if review_decisions:
            outputs['analyst-reviews.json'] = json_bytes(review_decisions)
        metadata = []
        for sid, snapshot in snapshots.items():
            name = None
            if snapshot.body_retention == "original":
                name = f"responses/{sid}.json"
                outputs[name] = snapshot.body
            metadata.append({**snapshot.metadata(), "body_file": name})
        outputs["responses.json"] = json_bytes(metadata)
        outputs["manifest.json"] = json_bytes({"schema_version": 1, "result_id": result_id,
            "files": {name: hashlib.sha256(body).hexdigest() for name, body in outputs.items()}})
        for name, content in outputs.items():
            atomic_write(destination / name, content)
        return destination / "evidence.html"


def verify_export(directory: str | Path) -> dict:
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_bytes())
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or not isinstance(manifest.get("files"), dict)
            or not {"attribution.json", "responses.json", "evidence.html"} <= manifest["files"].keys()):
        raise ValueError("Unsupported or incomplete evidence manifest")
    verified, changed = [], []
    for name, expected in manifest["files"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory):
            raise ValueError("Manifest path escapes the evidence directory")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            changed.append(name)
        else:
            verified.append(name)
    return {"valid": not changed, "checked_files": len(verified) + len(changed), "changed_or_missing": changed}

