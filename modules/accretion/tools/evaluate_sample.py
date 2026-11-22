"""Evaluate selection against analyst labels; labels are never passed to policy decisions.

Default mode compares structural row checks with analyst labels; it does not run
full Filter eligibility or urgency scoring. Use --live for the full intake funnel,
including website capture and attribution requests.
"""

from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from modules.accretion.components.intake import EntryValidator, root_domain, read_entries
from modules.accretion.components.intake_service import IntakeService
from modules.workspace.components.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run Filter, Qualify, Evaluate and Associate, including website and attribution requests",
    )
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
        # Select the labelled comparison cohort; this is not an urgency assessment.
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
        "note": (
            "Labels are analyst expectations, not attribution evidence. "
            "Offline mode checks structural row rules only; --live runs the full intake funnel "
            "with website capture and attribution. The scored flag marks rows included in "
            "label comparison, not an urgency score."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
