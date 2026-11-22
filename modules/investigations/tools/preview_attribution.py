"""Offline review specimens for the opt-in Attribution page revision.

All organizations, addresses, registry records and decisions are synthetic.
The command renders saved evidence only; it never opens a case workspace,
queries DNS/RDAP or changes a draft. The pending specimen demonstrates how
unaccepted evidence must remain visibly different from a validated association.
"""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "modules/attribution/components/engine/src"))

from attribution.models import json_bytes
from modules.investigations.tools.preview_introduction import specimen as introduction_specimen
from modules.investigations.tools.preview_vulnerabilities import specimen as vulnerability_specimen
from modules.investigations.components.outreach_template import apply_outreach_template
from modules.investigations.components.report_composition import compose
from modules.investigations.components.report_renderers import render_pdf, render_docx
from modules.ui.components.exhibit_rendering import capture_exhibit_masters, prepared_pages

REVISION = "attribution-2026-11-07-review-1"
SCENARIOS = ("Registration", "DNS", "Analyst_Review", "Review_Required")


def evidence_fixture(scenario, entry, root_domain):
    """Use the same persisted record shape as attribution_bridge.attribution_record."""
    ip = entry["ip"]
    hostname = entry["source"]["fields"]["hostname"]
    keyword = scenario in {"Analyst_Review", "Review_Required"}
    retrieved = "2026-11-05T12:15:00Z"
    evaluated = "2026-11-07T14:20:00Z"
    method = "rdap_keyword" if keyword else "rdap"
    source_name = "Example Regional Registry (synthetic)"
    source_url = "https://sources.example/registry/ip/" + ip
    field = "/entities/0/vcardArray/1/0/3" if keyword else "/entities/0/vcardArray/1/1/3"
    value = "Harbor Example Health" if keyword else "security@" + root_domain
    match = {
        "target_domain": root_domain,
        "matched_domain": "" if keyword else root_domain,
        "field_path": field,
        "value": value,
        "field_type": "organization_name" if keyword else "email",
    }
    contact = [["fn", {}, "text", "Harbor Example Health"]]
    if not keyword:
        contact.append(["email", {}, "text", value])
    record = {
        "objectClassName": "ip network",
        "handle": "EXAMPLE-NETWORK-192-0-2",
        "name": "HARBOR-EXAMPLE-HEALTH",
        "startAddress": "192.0.2.0",
        "endAddress": "192.0.2.255",
        "ipVersion": "v4",
        "entities": [{"handle": "EXAMPLE-HEALTH", "vcardArray": ["vcard", contact]}],
        "fixture_note": "Synthetic layout evidence, not a live registry lookup.",
    }
    details = {"network_start": record["startAddress"], "network_end": record["endAddress"]}
    if keyword:
        details["matched_words"] = ["harbor", "health"]
    if scenario == "DNS":
        method = "dns"
        retrieved, evaluated = "2026-11-07T14:20:00Z", "2026-11-07T14:20:01Z"
        source_name = "Example workstation DNS resolver (synthetic)"
        source_url = "dns://system/" + hostname + "/A"
        match.update(
            matched_domain=hostname,
            field_path="/answers",
            value=ip,
            field_type="dns_address",
        )
        record = {
            "query": hostname,
            "type": "A",
            "answers": [ip],
            "fixture_note": "Synthetic saved response, not a live DNS lookup.",
        }
        details = {
            "dns_forward_match": True,
            "basis": "forward",
            "resolved_hostname": hostname,
            "reported_hostname": hostname,
        }
    snapshot_id = "synthetic-attribution-" + scenario.lower().replace("_", "-")
    evidence = {
        "method": method,
        "ip": ip,
        "source_name": source_name,
        "source_url": source_url,
        "retrieved_at": retrieved,
        "snapshot_id": snapshot_id,
        "related_snapshot_ids": [snapshot_id],
        "match": match,
        "details": details,
        "from_cache": scenario != "DNS",
    }
    proof = {
        "ip": ip,
        "registry": source_name,
        "source_url": source_url,
        "retrieved_at": retrieved,
        "protocol": "DNS" if method == "dns" else "RDAP",
        "attribution": {
            "root_domain": root_domain,
            "matched_domain": match["matched_domain"],
            "field": match["field_path"],
            "value": match["value"],
        },
        "record": record,
        "result_id": snapshot_id + "-result",
        "from_cache": evidence["from_cache"],
        "snapshot_id": snapshot_id,
        "body_sha256": sha256(json_bytes(record)).hexdigest(),
        "policy": {"version": "synthetic-review-fixture"},
        "evidence": evidence,
    }
    if scenario != "Review_Required":
        proof["evaluated_at"] = evaluated
    if scenario == "Analyst_Review":
        proof["review"] = {
            "decision": "accept",
            "reviewer": "Example Analyst",
            "reviewed_at": "2026-11-07T15:45:00Z",
            "note": "Reviewed the recorded organization name and covering network; accepted this synthetic association for the layout example.",
        }
    return proof


def specimen(scenario="Registration"):
    if scenario not in SCENARIOS:
        raise ValueError("Unknown attribution review scenario: " + str(scenario))
    data = introduction_specimen(70 if scenario == "Registration" else 1)
    # Keep the previously reviewed vulnerability source fixture intact in the
    # full snapshot, although these exports contain only the Attribution page.
    data["draft"]["cve_records"] = deepcopy(vulnerability_specimen()["draft"]["cve_records"])
    data["draft"]["attribution_revision"] = REVISION
    group = data["qualified_lead"]["validated_leads"][0]
    proof = evidence_fixture(scenario, group["entries"][0], group["hostname"])
    data["qualified_lead"]["whois"] = [proof]
    lead = {
        "entries": group["entries"],
        "company": data["entity_name"],
        "domain": data["domain"],
        "entity_profile": {"city": "Greensboro", "state": "North Carolina"},
    }
    apply_outreach_template(lead, data["draft"])
    data["composition"] = compose(data)
    capture_exhibit_masters(data["composition"])
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for scenario in SCENARIOS:
        data = specimen(scenario)
        model = next(e for e in data["composition"]["exhibits"] if e["type"] == "attribution")
        if model.get("layout_revision") != REVISION:
            raise ValueError("The Attribution review revision is not enabled in composition.")
        masters = prepared_pages(model)
        (args.output / (scenario + "_Source.json")).write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        node = next(
            n for n in data["composition"]["sections"] if n.get("exhibit_id") == model["id"]
        )
        data["composition"]["sections"] = [node]
        stem = args.output / ("Attribution_" + scenario)
        render_pdf(data, stem.with_suffix(".pdf"), args.output, draft=True)
        render_docx(data, stem.with_suffix(".docx"), args.output)
        for item in masters:
            (args.output / (stem.name + f"_{item.page.page}.svg")).write_bytes(item.standalone_svg)
        results.append(
            {
                "scenario": scenario,
                "pages": len(masters),
                "revision": REVISION,
                "reported_ip_count": len({entry["ip"] for entry in data["assets"]}),
                "supporting_associations": sum(
                    item["supporting_attribution_count"] for item in model["items"]
                ),
                "methods": [item["method_label"] for item in model["items"]],
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
