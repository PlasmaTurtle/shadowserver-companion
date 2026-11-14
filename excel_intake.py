"""Read Shadowserver workbooks, qualify hostname groups, and write lead JSON."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterable
from contextlib import closing
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from zipfile import BadZipFile

from workbench.intake import (
    DomainMatch as DomainMatch,
    EntryValidator as EntryValidator,
    ExcelReader as ExcelReader,
    QualifiedLeads as QualifiedLeads,
    UnvalidatedEntry as UnvalidatedEntry,
    ValidatedEntry as ValidatedEntry,
    ValidatedLeads as ValidatedLeads,
    WhoisEvidence as WhoisEvidence,
    WhoisLookupError as WhoisLookupError,
    WhoisRecord as WhoisRecord,
    is_empty_entry as is_empty_entry,
    registry_address as registry_address,
    root_domain as root_domain,
)
from workbench.intake.records import json_default as json_default

import requests
from openpyxl.utils.exceptions import InvalidFileException


REGISTRIES = {
    "rdap.arin.net": "ARIN",
    "rdap-bootstrap.arin.net": "ARIN",
    "rdap.db.ripe.net": "RIPE NCC",
    "rdap.apnic.net": "APNIC",
    "rdap.lacnic.net": "LACNIC",
    "rdap.afrinic.net": "AFRINIC",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class RdapWhoisClient:
    """HTTPS registry lookups with one in-memory cache per run."""

    def __init__(self, timeout: float = 10, retries: int = 1, interval: float = 0.25):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be positive and finite")
        if retries < 0 or retries > 3:
            raise ValueError("Retries must be between 0 and 3")
        if not math.isfinite(interval) or interval < 0:
            raise ValueError("Request interval must be nonnegative and finite")
        self.timeout, self.retries, self.interval = timeout, retries, interval
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/rdap+json, application/json",
                "User-Agent": "ShadowserverLeadIntake/1.0",
            }
        )
        self.cache: dict[str, WhoisRecord | WhoisLookupError | None] = {}
        self.requests_made = 0
        self.cache_hits = 0
        self._next_request = 0.0

    def close(self) -> None:
        self.session.close()

    def lookup(self, value: str) -> WhoisRecord | None:
        address = registry_address(value)
        ip = address.compressed
        if not address.is_global or address.is_multicast:
            raise WhoisLookupError("Nonpublic addresses are not eligible for registry lookups")
        if ip in self.cache:
            self.cache_hits += 1
            cached = self.cache[ip]
            if isinstance(cached, WhoisLookupError):
                raise cached
            return cached
        try:
            result = self._lookup(ip)
        except WhoisLookupError as error:
            self.cache[ip] = error
            raise
        self.cache[ip] = result
        return result

    def _lookup(self, ip: str) -> WhoisRecord | None:
        url = f"https://rdap.arin.net/bootstrap/ip/{ip}"
        for _ in range(6):
            parts = urlsplit(url)
            if (
                parts.scheme != "https"
                or parts.hostname not in REGISTRIES
                or parts.port not in (None, 443)
            ):
                raise WhoisLookupError(f"Unexpected registry redirect: {url}")
            response = self._request(url)
            try:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    if not location:
                        raise WhoisLookupError("Registry redirect has no destination")
                    url = urljoin(url, location)
                    continue
                if response.status_code == 404:
                    return None
                if response.status_code != 200:
                    raise WhoisLookupError(f"Registry returned HTTP {response.status_code}")
                try:
                    data = response.json()
                    if not isinstance(data, dict) or data.get("objectClassName") != "ip network":
                        raise ValueError("Response is not an IP network record")
                    start = ip_address(data["startAddress"])
                    end = ip_address(data["endAddress"])
                    address = ip_address(ip)
                    if address.version != start.version or not start <= address <= end:
                        raise ValueError("Returned network does not contain the queried IP")
                except (ValueError, KeyError, TypeError) as error:
                    raise WhoisLookupError(f"Invalid registry response: {error}") from error
                return WhoisRecord(ip, REGISTRIES[parts.hostname], url, utc_now(), data)
            finally:
                response.close()
        raise WhoisLookupError("Too many registry redirects")

    def _request(self, url: str):
        for attempt in range(self.retries + 1):
            pause = self._next_request - time.monotonic()
            if pause > 30:
                raise WhoisLookupError("Registry cooldown is active; retry this lead later")
            if pause > 0:
                time.sleep(pause)
            self.requests_made += 1
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=False)
            except requests.RequestException as error:
                self._next_request = time.monotonic() + self.interval
                if attempt == self.retries:
                    raise WhoisLookupError(f"{type(error).__name__}: {error}") from error
                self._next_request += 2**attempt
                continue
            self._next_request = time.monotonic() + self.interval
            if response.status_code not in (429, 500, 502, 503, 504):
                return response
            delay = float(2**attempt)
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = float(retry_after)
                except ValueError:
                    try:
                        until = parsedate_to_datetime(retry_after)
                        delay = (until - datetime.now(timezone.utc)).total_seconds()
                    except TypeError, ValueError, OverflowError:
                        pass
            if not math.isfinite(delay):
                delay = 30
            delay = max(0, delay)
            # Keep a long service cooldown across IPs without blocking this run.
            self._next_request = max(self._next_request, time.monotonic() + delay)
            if attempt == self.retries or delay > 30:
                status = response.status_code
                response.close()
                raise WhoisLookupError(f"Registry returned HTTP {status}; retry later")
            response.close()
        raise WhoisLookupError("Registry request failed")


class LeadRuntime:
    """Orchestrate reading, filtering, grouping, and qualification."""

    def __init__(
        self,
        regions: set[str],
        lookup_whois: Callable[[str], WhoisRecord | None],
        progress: Callable[[dict[str, object]], None] | None = None,
    ):
        self.validator = EntryValidator(regions)
        self.lookup_whois = lookup_whois
        self.progress = progress or (lambda event: None)
        self.run_log: dict[str, object] = {}

    def run(self, paths: Iterable[Path], sheet: str | None = None) -> list[QualifiedLeads]:
        workbooks = discover_workbooks(paths)
        validated: list[ValidatedEntry] = []
        rejections: Counter[str] = Counter()
        rows_read = 0
        ignored_empty_rows = 0
        self.run_log = {"started_at": utc_now(), "workbooks": [str(p) for p in workbooks]}
        for index, path in enumerate(workbooks):
            self.progress(
                {"stage": "reading", "completed": index, "total": len(workbooks), "item": path.name}
            )
            with closing(ExcelReader().read(path, sheet)) as entries:
                for entry in entries:
                    if is_empty_entry(entry):
                        ignored_empty_rows += 1
                        continue
                    rows_read += 1
                    result = self.validator.validate_entry(entry)
                    if result is None:
                        rejections[self.validator.rejection_reason(entry)] += 1
                    else:
                        validated.append(result)
        groups = ValidatedLeads.group(validated)
        qualified: list[QualifiedLeads] = []
        outcomes: list[dict[str, object]] = []
        for index, group in enumerate(groups):
            self.progress(
                {
                    "stage": "qualifying",
                    "completed": index,
                    "total": len(groups),
                    "item": group.hostname,
                }
            )
            lead = group.qualify(self.lookup_whois)
            if lead is not None:
                qualified.append(lead)
                status = "qualified"
            elif any(attempt["status"] == "lookup_error" for attempt in group.attempts):
                status = "lookup_error"
            elif all(attempt["status"] == "skipped_nonpublic" for attempt in group.attempts):
                status = "no_public_ip"
            else:
                status = "no_match"
            outcomes.append(
                {
                    "hostname": group.hostname,
                    "status": status,
                    "entry_count": len(group.entries),
                    "attempts": list(group.attempts),
                }
            )
        self.run_log.update(
            {
                "finished_at": utc_now(),
                "rows_read": rows_read,
                "ignored_empty_rows": ignored_empty_rows,
                "validated_entries": len(validated),
                "rejected_entries": sum(rejections.values()),
                "rejection_reasons": dict(rejections),
                "hostname_groups": len(groups),
                "qualified_leads": len(qualified),
                "unresolved_leads": sum(item["status"] == "lookup_error" for item in outcomes),
                "outcomes": outcomes,
            }
        )
        self.progress(
            {
                "stage": "complete",
                "completed": len(groups),
                "total": len(groups),
                "item": f"{len(qualified)} qualified leads",
            }
        )
        return qualified


def discover_workbooks(paths: Iterable[Path]) -> list[Path]:
    workbooks: dict[Path, None] = {}
    for supplied in paths:
        path = Path(supplied).expanduser().resolve()
        candidates = sorted(path.iterdir()) if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.name.startswith("~$") or candidate.is_dir():
                continue
            if candidate.suffix.lower() not in (".xlsx", ".xlsm"):
                if path.is_dir():
                    continue
                raise ValueError(f"Expected .xlsx or .xlsm workbook: {candidate}")
            if not candidate.is_file():
                raise ValueError(f"Workbook not found: {candidate}")
            workbooks[candidate.resolve()] = None
    if not workbooks:
        raise ValueError("No Excel workbooks found")
    return list(workbooks)


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths", nargs="+", type=Path, help="Original workbooks or directories containing workbooks"
    )
    parser.add_argument(
        "--region",
        required=True,
        action="append",
        help="Exact allowed region value. Repeat for each region.",
    )
    parser.add_argument("--sheet", help="Worksheet name. Defaults to the first worksheet.")
    parser.add_argument("--output", type=Path, default=Path("qualified_leads.json"))
    parser.add_argument("--log-file", type=Path, help="Defaults to OUTPUT.run.json")
    parser.add_argument(
        "--timeout", type=float, default=10, help="Seconds per HTTP request (default 10)"
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="Additional attempts per failed HTTP request (0 to 3)",
    )
    parser.add_argument(
        "--interval", type=float, default=0.25, help="Minimum seconds between HTTP requests"
    )
    parser.add_argument("--quiet", action="store_true", help="Hide progress messages")
    args = parser.parse_args(argv)
    output = args.output.expanduser().resolve()
    log_file = (args.log_file or output.with_suffix(".run.json")).expanduser().resolve()

    def progress(event: dict[str, object]) -> None:
        if not args.quiet:
            print(
                f"{event['stage']} {event['completed']}/{event['total']}: {event['item']}",
                file=sys.stderr,
                flush=True,
            )

    try:
        if (
            output == log_file
            or output.suffix.lower() != ".json"
            or log_file.suffix.lower() != ".json"
        ):
            raise ValueError("Output and log must be different .json files")
        with closing(RdapWhoisClient(args.timeout, args.retries, args.interval)) as client:
            runtime = LeadRuntime(set(args.region), client.lookup, progress)
            qualified = runtime.run(args.paths, args.sheet)
            runtime.run_log.update(
                {"http_requests": client.requests_made, "cache_hits": client.cache_hits}
            )
            payload = QualifiedLeads.to_json(qualified)
            log_payload = (
                json.dumps(runtime.run_log, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
            )
            write_atomic(log_file, log_payload)
            write_atomic(output, payload)
    except (BadZipFile, InvalidFileException, OSError, TypeError, ValueError) as error:
        print(f"Lead intake failed: {error}", file=sys.stderr)
        return 1
    print(f"Saved {len(qualified)} qualified leads to {output}", file=sys.stderr)
    if runtime.run_log["unresolved_leads"]:
        print(
            f"{runtime.run_log['unresolved_leads']} leads need a lookup retry. See {log_file}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
