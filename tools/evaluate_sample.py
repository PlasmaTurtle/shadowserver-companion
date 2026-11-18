"""Evaluate selection against analyst labels; labels are never passed to policy decisions.

Run with --live for actual registry/CVE requests. Defaults to offline intake-only scoring.
"""

from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from excel_intake import EntryValidator, root_domain
from workbench.intake_service import read_entries, IntakeService
from workbench.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=Path("benchmark-data"))
    parser.add_argument("--output", type=Path, default=Path("benchmark.json"))
    args = parser.parse_args()
    validator = EntryValidator({"North Carolina"})
    sources = list(read_entries(args.input, ""))
    jobs = {}
    if args.live:
        store = Store(args.data_dir)
        with store.transaction() as db:
            settings = store.settings()
            settings["watch_inbox"] = False
            db.execute("UPDATE settings SET value=? WHERE key=?", (json.dumps(settings), "profile"))
        intake = IntakeService(store)
        imp = intake.enqueue(args.input.name, args.input.read_bytes())
        intake.process(imp["id"])
        jobs = {
            j["domain"]: j
            for j in store.all(
                "SELECT domain,status,attempts,error FROM jobs WHERE import_id=?", (imp["id"],)
            )
        }
        job = store.one("SELECT * FROM imports WHERE id=?", (imp["id"],))
        if job["status"] == "error":
            raise SystemExit(job["error"])
    outcomes = []
    for entry in sources:
        fields = entry.fields
        reason = validator.rejection_reason(entry)
        group = jobs.get(root_domain(fields.get("hostname", "")), {})
        status = "filtered" if reason else group.get("status", "prelookup_pass")
        # Hidden/missing fields and previously reported records cannot be scored as new leads.
        eligible = (
            fields.get("review_color") in ("yellow", "red")
            and bool(fields.get("hostname"))
            and bool(fields.get("region"))
        )
        outcomes.append(
            {
                "row": fields.get("fixture_row"),
                "hostname": fields.get("hostname"),
                "label": fields.get("review_color"),
                "expected": fields.get("expected_result"),
                "scored": eligible,
                "outcome": status,
                "reason": reason,
            }
        )
    summary = {}
    for label in ("yellow", "red"):
        rows = [r for r in outcomes if r["scored"] and r["label"] == label]
        summary[label] = {
            "total": len(rows),
            "qualified": sum(r["outcome"] == "qualified" for r in rows),
            "prelookup_pass": sum(r["outcome"] == "prelookup_pass" for r in rows),
            "filtered": sum(r["outcome"] == "filtered" for r in rows),
            "no_match": sum(r["outcome"] == "no_match" for r in rows),
            "deferred": sum(r["outcome"] == "deferred" for r in rows),
        }
    result = {
        "mode": "live" if args.live else "prelookup only",
        "summary": summary,
        "outcomes": outcomes,
        "groups": [{k: v for k, v in g.items() if k != "attempts"} for g in jobs.values()],
        "note": "Labels are analyst expectations, not authoritative ownership facts. Manual website/business qualification is not automated.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
