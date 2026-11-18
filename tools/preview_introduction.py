"""Generate three offline introduction candidates with synthetic case records.

Run from the repository: python tools/preview_introduction.py OUTPUT_DIRECTORY
No workspace is opened, no provider is queried, and no draft is migrated.
The fictional CVE identifiers and KEV assertions test layout only.
"""

from copy import deepcopy
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "components" / "attribution" / "src"))

from workbench.report_composition import compose
from workbench.report_renderers import render_pdf, render_docx
from workbench.report_drafts import default_draft
from workbench.report_layouts import CURRENT_LAYOUTS
from workbench.workspace_defaults import DEFAULT_SETTINGS
from workbench.introduction_model import REVISION, INTRO, SUBJECT
from workbench.introduction_layout import layout_introduction
from workbench.exhibit_rendering import svg


def specimen(ip_count, product_count=1, repeats=1):
    profile = deepcopy(DEFAULT_SETTINGS)
    profile.update(analyst_name="Example Analyst", analyst_title="Special Agent")
    products = [
        "Example VPN 7.0.1",
        "Example Mail Server 3.2",
        "Example Web Server 2.4",
        "Example Portal 8.1",
        "Example Gateway 6.0",
        "Example Exchange 4.2",
        "Example Document Server 5.1",
        "Example Control Panel 2.0",
    ][:product_count]
    cves = [f"CVE-2099-{10001 + i}" for i in range(product_count)]
    entries, assets = [], []
    for index in range(ip_count):
        product_index = index % product_count
        fields = {
            "ip": f"192.0.2.{index + 14}",
            "hostname": "gateway.harborhealth.example"
            if ip_count == 1
            else f"service{index + 1:02}.harborhealth.example",
            "protocol": "TCP",
            "port": [10443, 443, 8443][product_index % 3],
            "version": products[product_index],
            "tag": cves[product_index],
            "asn": 64496,
            "city": "Greensboro",
            "region": "North Carolina",
            "geo": "US",
            "severity": "critical",
            "timestamp": "2026-11-05T05:58:00Z",
        }
        assets.append(
            {
                **fields,
                "private_ip": False,
                "location": "Greensboro, North Carolina, US",
                "first_seen": fields["timestamp"],
                "last_seen": fields["timestamp"],
            }
        )
        for repeat in range(repeats):
            entries.append(
                {
                    "id": f"synthetic-{index}-{repeat}",
                    "ip": fields["ip"],
                    "private_ip": False,
                    "report_type": "scan_http_vulnerable",
                    "source": {
                        "fields": deepcopy(fields),
                        "row": len(entries) + 2,
                        "workbook": "synthetic-layout-example.xlsx",
                    },
                }
            )
    lead = {
        "entries": entries,
        "company": "Harbor Example Health, P.A.",
        "domain": "harborhealth.example",
        "entity_profile": {
            "address": "100 Example Way, Suite 200\nGreensboro, NC 27401",
            "city": "Greensboro",
            "state": "North Carolina",
        },
    }
    draft = default_draft(lead, profile)
    # This page-specific fixture intentionally enables only the introduction;
    # successive preview modules select their own reviewed page revisions.
    draft.update({key: "legacy" for key in CURRENT_LAYOUTS})
    draft.update(
        introduction_revision=REVISION,
        intro=INTRO,
        subject=SUBJECT,
        report_date="2026-11-07",
        severity="Critical",
    )
    draft["cve_records"] = [
        {
            "id": cve,
            "verification_status": "published",
            "source": "Synthetic CNA fixture",
            "description": "Fictional record for layout testing. No real vulnerability is represented.",
            "public_url": "https://sources.example/" + cve,
            "revision_id": "fixture-" + cve,
            "retrieved_at": "2026-11-07T14:00:00Z",
            "kev": True if i == 0 else None,
            "kev_retrieved_at": "2026-11-07T14:00:00Z",
            "kev_date": "2026-11-07",
            "sources": [
                {
                    "publisher": "CISA fixture",
                    "public_url": "https://sources.example/kev-fixture",
                    "retrieved_at": "2026-11-07T14:00:00Z",
                }
            ],
        }
        for i, cve in enumerate(cves)
    ]
    data = {
        "schema_version": 7,
        "demo": True,
        "report_revision": 1,
        "draft_revision": 1,
        "domain": lead["domain"],
        "entity_name": lead["company"],
        "profile": profile,
        "draft": draft,
        "cves": cves,
        "assets": assets,
        "evidence": [],
        "explainers": [],
        "references": [],
        "document_policy": {"brand_profile": {"id": "usss", "version": "1"}},
        "qualified_lead": {
            "validated_leads": [{"hostname": lead["domain"], "entries": entries}],
            "whois": [
                {
                    "ip": entries[0]["ip"],
                    "registry": "Synthetic registry",
                    "source_url": "https://sources.example/rdap-fixture",
                    "retrieved_at": "2026-11-07T14:00:00Z",
                    "protocol": "SYNTHETIC",
                    "attribution": {"value": "harborhealth.example"},
                }
            ],
        },
    }
    data["composition"] = compose(data)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for label, ips, products, observations in [
        ("Single_Asset", 1, 1, 1),
        ("Eight_Assets", 8, 3, 3),
        ("Seventy_Assets", 70, 8, 3),
    ]:
        data = specimen(ips, products, observations)
        intro = data["composition"]["sections"][0]
        assert intro["kind"] == "introduction"
        plan = layout_introduction(intro["model"])
        # The review contains only page one, while its full source model retains
        # every appendix entry and citation for integration/inspection.
        (args.output / (label + "_Source.json")).write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        data["composition"]["sections"] = [intro]
        stem = args.output / ("Introduction_" + label)
        render_pdf(data, stem.with_suffix(".pdf"), args.output, draft=True)
        render_docx(data, stem.with_suffix(".docx"), args.output)
        stem.with_suffix(".svg").write_bytes(svg(plan.summary))
        results.append(
            {
                "name": label,
                "ips": ips,
                "observations": ips * observations,
                "products": products,
                "summary_height_pt": plan.summary.height,
                "revision": REVISION,
            }
        )
    (args.output / "review.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
