"""JSON command-line interface for the standalone report module."""
from __future__ import annotations

import argparse
from dataclasses import is_dataclass
from datetime import date
import getpass
import json
import math
import os
from pathlib import Path
import sys
import warnings
from typing import Sequence

from .control import Operation
from .credentials import EnvCredentialProvider, WindowsCredentialProvider, validate_profile
from .errors import ConfigurationError, ShadowserverError
from .models import Credentials, QuerySpec, ReportSelection


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's normal errors echo unexpected arguments. A mistyped secret
        # must not become an error log; help is the detailed syntax reference.
        raise ConfigurationError("Invalid command arguments. Use --help for syntax; credentials must not be passed as arguments.")


def _date(value: str) -> date:
    try:
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError
        return result
    except ValueError:
        raise argparse.ArgumentTypeError("Use YYYY-MM-DD dates.") from None


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
        if parsed <= 0:
            raise ValueError
        return parsed
    except ValueError:
        raise argparse.ArgumentTypeError("Use a positive integer.") from None


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
        if not math.isfinite(parsed) or parsed <= 0:
            raise ValueError
        return parsed
    except ValueError:
        raise argparse.ArgumentTypeError("Use a positive finite number.") from None


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="shadowserver-reports", description="Standalone Shadowserver Reports API client. Global options precede the command. No credentials are accepted as arguments.")
    parser.add_argument("--version", action="version", version="shadowserver-reports 0.1.0")
    parser.add_argument("--profile", default="default", help="Credential and synchronization namespace (default: default).")
    parser.add_argument("--credentials", choices=("env", "windows"), default="windows" if os.name == "nt" else "env", help="Credential provider; default Windows Credential Manager on Windows, environment elsewhere.")
    parser.add_argument("--timeout", type=_positive_float, default=120.0, help="Whole-operation time budget in seconds (default: 120).")
    parser.add_argument("--max-requests", type=_positive_int, default=100)
    parser.add_argument("--max-bytes", type=_positive_int, default=1024 ** 3, help="Total received-byte budget (default: 1 GiB).")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    commands.add_parser("connection", help="Check authentication and report access.")
    commands.add_parser("subscriptions", help="List authorized report subscriptions.")
    types = commands.add_parser("types", help="Discover available report types.")
    types.add_argument("--start", type=_date)
    types.add_argument("--end", type=_date)
    schema = commands.add_parser("schema", help="Retrieve report field metadata.")
    schema.add_argument("report_type")
    schema.add_argument("--cache", type=Path, help="Save an immutable schema snapshot and compare it with the previous snapshot.")

    def selection_args(command):
        command.add_argument("--start", type=_date, required=True)
        command.add_argument("--end", type=_date, required=True)
        subscriptions = command.add_mutually_exclusive_group(required=True)
        subscriptions.add_argument("--subscription", action="append", dest="subscriptions", help="Repeat for multiple subscriptions.")
        subscriptions.add_argument("--all-subscriptions", action="store_true", help="Select every subscription authorized to this key.")
        types = command.add_mutually_exclusive_group(required=True)
        types.add_argument("--type", action="append", dest="report_types", help="Repeat for multiple report types.")
        types.add_argument("--all-types", action="store_true", help="Select every available report type.")
        command.add_argument("--limit", type=_positive_int, default=1000, help="Listing response cap; hitting the cap is reported as incomplete.")

    listing = commands.add_parser("list", help="List report metadata without exposing download tokens.")
    selection_args(listing)
    download = commands.add_parser("download", help="Download selected original reports and receipts.")
    selection_args(download)
    download.add_argument("--output", type=Path, required=True)
    download.add_argument("--max-reports", type=_positive_int, default=100)
    download.add_argument("--max-file-bytes", type=_positive_int, default=256 * 1024 ** 2)
    sync = commands.add_parser("sync", help="Run one bounded pull with an isolated SQLite ledger.")
    selection_args(sync)
    sync.add_argument("--output", type=Path, required=True)
    sync.add_argument("--ledger", type=Path, required=True)
    sync.add_argument("--lookback-days", type=_positive_int, default=2)
    sync.add_argument("--max-file-bytes", type=_positive_int, default=256 * 1024 ** 2)
    query = commands.add_parser("query", help="Run a bounded event query; results are separate from full reports.")
    query.add_argument("--start", type=_date, required=True)
    query.add_argument("--end", type=_date, required=True)
    query.add_argument("--scope-json", type=Path, required=True, help="JSON object containing your authorized geo/ASN/domain/IP scope.")
    query.add_argument("--filters-json", type=Path)
    query.add_argument("--page-size", type=_positive_int, default=100)
    query.add_argument("--max-pages", type=_positive_int, default=10)
    query.add_argument("--max-records", type=_positive_int, default=1000)
    query.add_argument("--sort", choices=("ascending", "descending"), default="ascending")
    query.add_argument("--facet")
    configure = commands.add_parser("configure", help="Enter credentials privately into Windows Credential Manager.")
    configure.add_argument("--delete", action="store_true", help="Remove only this profile's stored credentials.")
    demo = commands.add_parser("demo", help="Run a synthetic offline example; no key or network required.")
    demo.add_argument("--output", type=Path, required=True)
    return parser


def _selection(args) -> ReportSelection:
    return ReportSelection(start=args.start, end=args.end, subscriptions=tuple(args.subscriptions or ()), types=tuple(args.report_types or ()), limit=args.limit)


def _json_file(path: Path) -> dict:
    try:
        with path.open("rb") as stream:
            content = stream.read(65537)
        if len(content) > 65536:
            raise ValueError
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result
        result = json.loads(content.decode("utf-8-sig"), object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (OSError, ValueError, UnicodeError):
        raise ConfigurationError("Query input must be a readable UTF-8 JSON object no larger than 64 KiB, with unique keys and finite numbers.") from None


def _public(value):
    if hasattr(value, "public_dict"):
        return _public(value.public_dict())
    if is_dataclass(value):
        # Every token-bearing model must implement public_dict. Do not use
        # dataclasses.asdict blindly on unknown objects.
        raise ConfigurationError("This response has no public serialization contract.")
    if isinstance(value, dict):
        return {str(key): _public(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_public(item) for item in value]
    return value


def _error(error: ShadowserverError) -> dict:
    return {"code": getattr(error, "code", "shadowserver_error"), "message": str(error)}


def _run(args, operation: Operation):
    profile = validate_profile(args.profile)
    if args.command == "demo":
        from .demo import run_demo
        return run_demo(args.output), 0
    if args.command == "configure":
        provider = WindowsCredentialProvider(profile)
        # Fail before prompting when a Windows store is unavailable.
        provider._backend()
        if args.delete:
            return {"status": "deleted" if provider.delete() else "not_found", "profile": profile}, 0
        if not sys.stdin.isatty():
            raise ConfigurationError("Configure requires an interactive terminal for hidden credential entry.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                api_key = getpass.getpass("Shadowserver API key: ")
                secret = getpass.getpass("Shadowserver API secret: ")
        except (getpass.GetPassWarning, EOFError):
            raise ConfigurationError("A terminal with hidden credential entry is required.") from None
        provider.store(Credentials(api_key=api_key, secret=secret))
        return {"status": "configured", "profile": profile, "provider": "windows"}, 0

    from .client import ReportsClient
    from .transport import SignedTransport
    provider = WindowsCredentialProvider(profile) if args.credentials == "windows" else EnvCredentialProvider()
    with SignedTransport(provider) as transport:
        client = ReportsClient(transport)
        if args.command == "connection":
            result = client.check_connection(operation=operation)
            return result, 0 if result.get("reports_access") is True else 2
        if args.command == "subscriptions":
            return {"subscriptions": client.list_subscriptions(operation=operation)}, 0
        if args.command == "types":
            if (args.start is None) != (args.end is None):
                raise ConfigurationError("Provide both --start and --end, or neither.")
            return {"types": client.list_report_types(start=args.start, end=args.end, operation=operation)}, 0
        if args.command == "schema":
            schema = client.get_schema(args.report_type, operation=operation)
            body = {"schema": schema}
            if args.cache:
                from .schema import SchemaStore
                body["snapshot"] = SchemaStore(args.cache).capture(args.report_type, schema).public_dict()
            return body, 0
        if args.command == "query":
            spec = QuerySpec(start=args.start, end=args.end, scope=_json_file(args.scope_json), filters=_json_file(args.filters_json) if args.filters_json else {}, page_size=args.page_size, max_pages=args.max_pages, max_records=args.max_records, sort=args.sort, facet=args.facet)
            result = client.query_events(spec, operation=operation)
            return {"kind": "event_query", "records": list(result.records), "completeness": result.completeness, "pages": result.pages, "reasons": result.reasons}, 0 if result.completeness == "complete" else 2
        selection = _selection(args)
        if args.command == "list":
            result = client.list_reports(selection, operation=operation)
            return {"reports": [item.public_dict() for item in result.reports], "completeness": result.completeness, "reasons": result.reasons}, 0 if result.completeness == "complete" else 2

        from .download import ReportDownloader
        downloader = ReportDownloader(args.output, max_file_bytes=args.max_file_bytes)
        if args.command == "sync":
            from .ledger import Ledger
            from .sync import sync_once
            with Ledger(args.ledger, profile=profile) as ledger:
                result = sync_once(client, downloader, ledger, selection, operation=operation, lookback_days=args.lookback_days)
            body = {"status": result.status, "downloaded": result.downloaded, "reused": result.reused, "failed": result.failed, "receipts": [receipt.public_dict() for receipt in result.receipts], "checkpoint": result.checkpoint, "reasons": result.reasons}
            return body, 0 if result.status == "complete" else (130 if result.status == "cancelled" else 2)
        catalog = client.list_reports(selection, operation=operation)
        if len(catalog.reports) > args.max_reports:
            raise ConfigurationError("Selection exceeds --max-reports; narrow the selection or explicitly raise that bound.")
        receipts = []
        failure = None
        for report in catalog.reports:
            try:
                receipts.append(downloader.download_report(report, operation=operation).public_dict())
            except ShadowserverError as exc:
                # Stop the batch on a failed download. Repeated invalid links can
                # trigger upstream blocking; a future invocation is deliberate.
                failure = _error(exc)
                break
        complete = catalog.completeness == "complete" and failure is None
        result = {"status": "complete" if complete else "partial", "catalog_completeness": catalog.completeness, "selected": len(catalog.reports), "finished": len(receipts), "receipts": receipts, "reasons": catalog.reasons}
        if failure:
            result["error"] = failure
        return result, 0 if complete else 2


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        operation = Operation(timeout=args.timeout, max_requests=args.max_requests, max_bytes=args.max_bytes)
        result, code = _run(args, operation)
        print(json.dumps(_public(result), ensure_ascii=False, allow_nan=False, indent=2))
        return code
    except KeyboardInterrupt:
        print(json.dumps({"error": {"code": "cancelled", "message": "Operation cancelled."}}), file=sys.stderr)
        return 130
    except ShadowserverError as exc:
        print(json.dumps({"error": _error(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except (ValueError, TypeError, OSError):
        print(json.dumps({"error": {"code": "local_error", "message": "Invalid local input or unavailable local storage. Check command options and file access."}}), file=sys.stderr)
        return 1
    except Exception:
        # Avoid traceback dumps that can include request objects or credentials.
        print(json.dumps({"error": {"code": "internal_error", "message": "An unexpected internal error stopped the operation."}}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
