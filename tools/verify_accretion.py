"""Print a reproducible synthetic priority matrix; no network or workspace writes.

Run from a source checkout: python tools/verify_accretion.py --output matrix.json
These examples calibrate the provisional policy, not real organizations or CVEs.
"""

from copy import deepcopy
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workbench.accretion import policy_defaults, score_lead

STAMP = "2026-11-12T00:00:00Z"
CVE = "CVE-2026-99001"


def observation(*, detailed=False, severity="critical", tag=CVE):
    fields = {
        "hostname": "mail.example.com",
        "ip": "8.8.8.8",
        "region": "North Carolina",
        "city": "Burnsville",
        "tag": tag,
        "severity": severity,
    }
    normalized = {"profile": {"capability": "eligible"}}
    if detailed:
        fields.update(timestamp=STAMP, port=443, version="ExampleProduct/1.2")
        normalized["products"] = [{"product": "ExampleProduct", "version": "1.2"}]
    return {"source": {"fields": fields}, "normalized": normalized}


def reference(*, kev=False, ransomware=False):
    return {
        CVE: {
            "id": CVE,
            "status": "available",
            "cvss": 9.8,
            "severity": "CRITICAL",
            "catalog_stale": False,
            "kev": {
                "listed": kev,
                "entry": {"knownRansomwareCampaignUse": "Known" if ransomware else "Unknown"},
                "stale": False,
            },
            "epss": {"score": 0.9 if kev else 0.01, "stale": False},
            "warnings": [],
        }
    }


def matrix():
    detailed = observation(detailed=True)
    scenarios = [
        (
            "Sparse targeted low-severity finding",
            observation(severity="low", tag="service"),
            {},
            "cool",
        ),
        ("Sparse critical identifier; catalog unavailable", observation(), {}, "warm"),
        ("Versioned critical; low EPSS; not KEV", detailed, {"cve_records": reference()}, "hot"),
        (
            "Same evidence; known exploitation and high EPSS",
            detailed,
            {"cve_records": reference(kev=True)},
            "blazing",
        ),
        (
            "Known entity; ransomware-linked exploited critical",
            detailed,
            {
                "cve_records": reference(kev=True, ransomware=True),
                "association": {"status": "known", "basis": "hostname"},
            },
            "blazing",
        ),
        (
            "Versioned critical during Burnsville outreach focus",
            detailed,
            {"cve_records": reference(), "policy": {"priority_cities": ["Burnsville"]}},
            "hot",
        ),
    ]
    results = []
    for name, entry, options, expected in scenarios:
        score = score_lead([deepcopy(entry)], as_of=STAMP, **options)
        assert score["temperature"] == expected, name
        assert score == score_lead([deepcopy(entry)] * 100, as_of=STAMP, **options), name
        results.append({"scenario": name, "expected_temperature": expected, **score})
    return {
        "synthetic": True,
        "policy": policy_defaults(),
        "duplicate_invariance": True,
        "interpretation": "Temperature is outreach priority, not proof of exposure or exploitation.",
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    encoded = json.dumps(matrix(), indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
