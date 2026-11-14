"""Offline review specimens for the opt-in Vulnerabilities page revision.

All identifiers, addresses, scores, descriptions and source assessments in
these fixtures are fictional. They exercise layout, not vulnerability facts.
The finding narrative uses the approved prose once for the whole notification.
"""

from copy import deepcopy
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "components" / "attribution" / "src"))

from tools.preview_introduction import specimen as introduction_specimen
from workbench.outreach_template import apply_outreach_template
from workbench.report_composition import compose
from workbench.report_renderers import render_pdf, render_docx
from workbench.exhibit_rendering import capture_exhibit_masters, prepared_pages
from workbench.vulnerability_model import REVISION
from workbench.notification_narrative import REVISION as REVIEW_NARRATIVE_REVISION


def specimen(scenario="Short_Narrative"):
    count = 6 if scenario == "Multiple_CVEs" else 1
    data = introduction_specimen(2 if scenario == "Two_Assets" else 1)
    data["cves"] = [f"CVE-2099-{10001 + i}" for i in range(count)]
    draft = data["draft"]
    draft["vulnerability_revision"] = REVISION
    # This specimen tests the historical reviewed page, not a new source-family
    # import. Pin its generator so future defaults cannot rewrite the baseline.
    draft["narrative_revision"] = REVIEW_NARRATIVE_REVISION
    records = []
    for index, cve in enumerate(data["cves"]):
        record = deepcopy(draft["cve_records"][0])
        record.update(
            id=cve,
            public_url="https://sources.example/" + cve,
            revision_id="fixture-" + cve,
            description="In this fictional example, an unauthenticated request to the Example VPN service can disclose configuration data. Exploitation requires the affected administrative interface to be reachable. This description and all scores are synthetic layout fixtures.",
            cvss_assessments=[
                {
                    "score": 9.1,
                    "severity": "Critical",
                    "version": "3.1",
                    "source": "Example CNA",
                    "publisher": "Example CNA",
                }
            ],
            epss=0.8421,
            epss_percentile=0.9923,
            epss_date="2026-11-07",
            epss_retrieved_at="2026-11-07T14:00:00Z",
            kev=True if index % 2 == 0 else False,
        )
        record["sources"].append(
            {
                "publisher": "FIRST fixture",
                "public_url": "https://sources.example/epss-fixture",
                "retrieved_at": "2026-11-07T14:00:00Z",
            }
        )
        record["sources"].insert(
            0,
            {
                "publisher": record["source"],
                "public_url": record["public_url"],
                "revision_id": record["revision_id"],
                "retrieved_at": record["retrieved_at"],
            },
        )
        record["affected"] = [
            {
                "product": "Example VPN",
                "versions": [{"version": "7.0.0", "lessThan": "7.0.2", "status": "affected"}],
            }
        ]
        if index == 0:
            record["ransomware"] = {
                "status": "known",
                "label": "Known ransomware use",
                "availability": "supplied",
                "publisher": "CISA fixture",
                "public_url": "https://sources.example/kev-fixture",
                "retrieved_at": "2026-11-07T14:00:00Z",
            }
        records.append(record)
    draft["cve_records"] = records
    entries = data["qualified_lead"]["validated_leads"][0]["entries"]
    for entry in entries:
        entry["source"]["fields"]["tag"] = ";".join(data["cves"])
    for asset in data["assets"]:
        asset["tag"] = ";".join(data["cves"])
    lead = {
        "entries": entries,
        "company": data["entity_name"],
        "domain": data["domain"],
        "entity_profile": {"city": "Greensboro", "state": "North Carolina"},
    }
    apply_outreach_template(lead, draft)
    data["composition"] = compose(data)
    capture_exhibit_masters(data["composition"])
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for scenario in ("Short_Narrative", "Two_Assets", "Multiple_CVEs"):
        data = specimen(scenario)
        model = next(e for e in data["composition"]["exhibits"] if e["type"] == "vulnerability")
        masters = prepared_pages(model)
        (args.output / (scenario + "_Source.json")).write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        node = next(
            n for n in data["composition"]["sections"] if n.get("exhibit_id") == model["id"]
        )
        data["composition"]["sections"] = [node]
        stem = args.output / ("Vulnerabilities_" + scenario)
        render_pdf(data, stem.with_suffix(".pdf"), args.output, draft=True)
        render_docx(data, stem.with_suffix(".docx"), args.output)
        for item in masters:
            (args.output / (stem.name + f"_{item.page.page}.svg")).write_bytes(item.standalone_svg)
        results.append(
            {
                "scenario": scenario,
                "pages": len(masters),
                "revision": REVISION,
                "narrative_revision": data["draft"].get("narrative_revision", "legacy"),
                "narrative_characters": len(model["narrative"]),
                "findings": len(model["items"]),
                "model_sha256": model["rendered_masters"]["model_sha256"],
                "pagination": [item.page.segments for item in masters],
            }
        )
    (args.output / "review.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(
        json.dumps([{k: v for k, v in r.items() if k != "pagination"} for r in results], indent=2)
    )


if __name__ == "__main__":
    main()
