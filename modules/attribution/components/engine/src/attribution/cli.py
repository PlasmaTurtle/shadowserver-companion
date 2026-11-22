"""Windows-friendly CLI; JSON results on stdout, progress/errors on stderr."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .models import CandidateIP, Settings, VERSION, json_bytes
from .module import AttributionModule
from .render import EvidenceRenderer, atomic_write, verify_export
from .store import EvidenceStore


def parser():
    root = argparse.ArgumentParser(prog="attribution", description="Attribution Module — registration evidence for notification leads")
    root.add_argument("--version", action="version", version=VERSION)
    commands = root.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", type=Path, default=Path("data/attribution.sqlite3"))
    network = argparse.ArgumentParser(add_help=False)
    network.add_argument("--timeout", type=float, default=10)
    network.add_argument("--budget", type=float, default=45, help="Time budget per candidate IP")
    network.add_argument("--interval", type=float, default=0.5, help="Minimum gap between requests to one registry")
    network.add_argument("--entity-limit", type=int, default=8)
    network.add_argument("--rdap-only", action="store_true", help="Skip DNS fallback; still retain partial registration-name matches")
    mode = network.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true", help="Refresh IP/entity responses even when cached")
    mode.add_argument("--offline", action="store_true", help="Use only fresh cached records; make no network requests")
    check = commands.add_parser("check", parents=[common, network], help="Attribute one root-domain group")
    check.add_argument("root_domain")
    check.add_argument("ips", nargs="+")
    check.add_argument("--hostname", help="Reported hostname for forward DNS; defaults to the root domain")
    check.add_argument("--output", type=Path, help="Also save the result JSON to this file")
    check.add_argument("--export", type=Path, help="Export an evidence directory (must be empty)")
    batch = commands.add_parser("batch", parents=[common, network], help="Read grouped candidates from JSON Lines")
    batch.add_argument("input", type=Path)
    batch.add_argument("--workers", type=int, default=2)
    batch.add_argument("--output", type=Path, help="Write JSON Lines as each group finishes")
    export = commands.add_parser("export", parents=[common], help="Export a saved result, without network access")
    export.add_argument("result_id")
    export.add_argument("destination", type=Path)
    verify = commands.add_parser("verify", help="Verify exported files against their SHA-256 manifest")
    verify.add_argument("directory", type=Path)
    commands.add_parser("stats", parents=[common], help="Count saved results, responses, and cache entries")
    history = commands.add_parser("history", parents=[common], help="List saved results for later export")
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--root-domain", help="Filter saved results by their root domain")
    history.add_argument("--status", choices=('matched','review','no_match','incomplete','deferred','no_eligible_ip'))
    commands.add_parser("interactive", parents=[common], help="Prompt for a domain and IP addresses")
    return root


def groups(path):
    with path.open(encoding="utf-8-sig") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            if len(line) > 10 * 1024 * 1024:
                raise ValueError(f"Input line {line_number} exceeds 10 MB")
            try:
                group = json.loads(line)
                domain = group["root_domain"]
                candidates = [CandidateIP(c["entry_id"], c["ip"], c.get("hostname")) for c in group["candidates"]]
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(f"Invalid input group on line {line_number}: {error}") from error
            yield domain, candidates


def emit(value):
    print(json.dumps(value, ensure_ascii=True, allow_nan=False))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "verify":
            result = verify_export(args.directory)
            emit(result)
            return 0 if result["valid"] else 1
        if args.command in ("export", "stats", "history"):
            if not args.db.is_file():
                raise ValueError("Attribution database does not exist")
            with EvidenceStore(args.db) as store:
                if args.command == "stats":
                    emit(store.stats())
                elif args.command == "history":
                    emit(store.history(args.limit, root_domain=args.root_domain, status=args.status))
                else:
                    emit({"evidence_html": str(EvidenceRenderer(store).export(args.result_id, args.destination).resolve())})
            return 0
        if args.command == "interactive":
            domain = input("Root domain: ").strip()
            ips = input("IP addresses (spaces or commas between them): ").replace(",", " ").split()
            if not ips:
                raise ValueError("Enter at least one IP address")
            with AttributionModule.open(args.db) as module:
                result = module.attribute(domain, [CandidateIP(str(i), ip) for i, ip in enumerate(ips, 1)])
                out = Path("exports") / f"{result.root_domain}-{result.result_id[:8]}"
                path = EvidenceRenderer(module.store).export(result.result_id, out)
                print(f"\nOutcome: {result.status}\nEvidence: {path.resolve()}\nResult ID: {result.result_id}")
                return 0 if result.status == "matched" else 1
        settings = Settings(timeout=args.timeout, operation_budget=args.budget, interval=args.interval,
                            max_entity_requests=args.entity_limit, enable_dns=not args.rdap_only)
        with AttributionModule.open(args.db, settings=settings) as module:
            if args.command == "check":
                result = module.attribute(args.root_domain, [CandidateIP(str(i), ip, args.hostname) for i, ip in enumerate(args.ips, 1)],
                                          refresh=args.refresh, offline=args.offline)
                if args.output:
                    atomic_write(args.output, json_bytes(result.to_dict()))
                if args.export:
                    EvidenceRenderer(module.store).export(result.result_id, args.export)
                emit(result.to_dict())
                return 0 if result.status == "matched" else (2 if result.status in ("incomplete", "deferred") else 1)
            output = None
            try:
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    # Refuse truncation of a previous batch's results.
                    output = args.output.open("x", encoding="utf-8")
                count, needs_review = 0, False
                for result in module.attribute_many(groups(args.input), workers=args.workers,
                                                     refresh=args.refresh, offline=args.offline):
                    count += 1
                    needs_review |= result.status in ("review", "incomplete", "deferred")
                    payload = result.to_dict()
                    if output:
                        output.write(json.dumps(payload, ensure_ascii=False) + "\n")
                        output.flush()
                    emit(payload)
                    print(f"[{count}] {result.root_domain}: {result.status}", file=sys.stderr)
                return 2 if needs_review else 0
            finally:
                if output:
                    output.close()
    except (ValueError, KeyError, OSError, sqlite3.Error) as error:
        print(f"Attribution error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted. Completed results and retrieved records remain saved.", file=sys.stderr)
        return 130

