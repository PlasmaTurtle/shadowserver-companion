"""Regenerate distributable PDF/DOCX examples from explicit synthetic fixtures.

Run from the source checkout: python modules/investigations/tools/generate_examples.py
Uses the production layout defaults and deterministic narrative generator.
No case workspace, external service, AI provider or live source is consulted.
"""

from pathlib import Path
from hashlib import sha256
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "modules/attribution/components/engine/src")]

from modules.investigations.tools.preview_attribution import evidence_fixture
from attribution.google_dns import DOCUMENTATION, SOURCE_NAME, query_url
from attribution.models import json_bytes
from modules.investigations.tools.preview_vulnerabilities import specimen as vulnerability_specimen
from modules.investigations.components.outreach_template import apply_outreach_template
from modules.investigations.components.report_composition import compose
from modules.investigations.components.report_layouts import adopt_current_layouts
from modules.investigations.components.report_renderers import render_pdf, render_docx
from modules.ui.components.presentation import document_policy
from modules.investigations.components.report_explainers import select_report_explainers
from modules.settings.components.sender_identity import capture_profile


def _synthetic_google_dns(entry, root_domain):
    """Current provider shape, using fictional answers without a network request."""
    proof = evidence_fixture("DNS", entry, root_domain)
    hostname = entry["source"]["fields"]["hostname"]
    source_url = query_url(hostname + ".", "A")
    note = "Synthetic saved response for layout review; no live DNS request was made."
    record = {
        "Status": 0,
        "TC": False,
        "RD": True,
        "RA": True,
        "AD": False,
        "CD": False,
        "Question": [{"name": hostname + ".", "type": 1}],
        "Answer": [{"name": hostname + ".", "type": 1, "TTL": 300, "data": entry["ip"]}],
        "fixture_note": note,
    }
    proof.update(
        registry=SOURCE_NAME,
        source_url=source_url,
        record=record,
        body_sha256=sha256(json_bytes(record)).hexdigest(),
        hash_scope="Canonical JSON bytes of the synthetic response fixture.",
        fixture_note=note,
    )
    proof["attribution"]["field"] = "/Answer/0/data"
    proof["evidence"].update(source_name=SOURCE_NAME, source_url=source_url)
    proof["evidence"]["match"]["field_path"] = "/Answer/0/data"
    proof["evidence"]["details"].update(
        record_type="A",
        resolver_kind="public recursive resolver",
        provider_documentation=DOCUMENTATION,
        fixture_note=note,
    )
    return proof


def synthetic_example(*, multiple=False):
    data = vulnerability_specimen("Multiple_CVEs" if multiple else "Two_Assets")
    group = data["qualified_lead"]["validated_leads"][0]
    for entry in group["entries"]:
        entry["normalized"] = {"profile": {"id": "scan_http_vulnerable"}}
    data["qualified_lead"]["whois"] = [
        _synthetic_google_dns(group["entries"][0], group["hostname"])
    ]
    data["draft"]["sender_profile"] = capture_profile(data["profile"])
    adopt_current_layouts(data["draft"])
    # These are newly generated examples, not historical saved artwork. Adopt
    # current paragraph presentation while retaining their selected branding.
    brand = data.get("document_policy", {}).get("brand_profile", {}).get("id", "companion")
    data["document_policy"] = document_policy({**data["profile"], "brand_profile": brand})
    data["draft"]["document_policy"] = data["document_policy"]
    lead = {
        "entries": group["entries"],
        "company": data["entity_name"],
        "domain": data["domain"],
        "entity_profile": {"city": "Greensboro", "state": "North Carolina"},
    }
    data["draft"]["report_explainer_snapshots"] = select_report_explainers(lead)
    apply_outreach_template(lead, data["draft"])
    data["composition"] = compose(data)
    assert data["demo"] is True
    assert data["draft"]["narrative"].count("began reviewing Shadowserver observations") == 1
    assert not data["composition"]["citation_integrity_issues"]
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "examples")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for name, multiple in (("Sample_Notification", False), ("Multiple_CVE_Notification", True)):
        data = synthetic_example(multiple=multiple)
        render_pdf(data, args.output / (name + ".pdf"), args.output, draft=True)
        render_docx(data, args.output / (name + ".docx"), args.output, draft=True)
        results.append(
            {
                "name": name,
                "cves": len(data["cves"]),
                "narrative_revision": data["draft"]["narrative_revision"],
                "narratives": 1,
                "synthetic": True,
            }
        )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
