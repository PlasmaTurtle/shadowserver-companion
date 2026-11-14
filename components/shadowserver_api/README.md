# Shadowserver Reports Integration 0.1.2

Eclipse 0.9.98 vendors a locally patched **0.1.2** client. It validates bounded
plain/gzip CSV prefixes and headers before writing response bytes to staging,
then validates the complete CSV before publishing it. Valid CSV remains accepted
independently of HTTP MIME labels. `source-manifest.json` pins the integrated
files and records local patches; `baseline-0.1.1/` preserves the prior integration
manifest and changed-file baselines. These local changes are not an upstream release.

The prior Companion 0.9.89 integration used patched **0.1.1**. Authentication, discovery, one complete live
CSV download and the queued intake handoff were verified on November 12, 2026.
See `docs/RELEASE_0989.md` and `VALIDATION.md` at the application root. The original
standalone 0.1.0 distribution instructions below are retained as historical module
documentation; native Windows acceptance remains pending.

A standalone acquisition module for the Shadowserver Reports API. It discovers subscribed reports, downloads original files, records acquisition receipts, runs bounded research queries, and performs one repeatable synchronization run.

**Release status: implemented and validated with synthetic fixtures. Live API and native Windows acceptance are pending the requested credentials.** Shadowserver Companion 0.8.0 remains the accepted stable application; this package has no connection to its UI or database.

The module assumes the requested API key will grant `reports` access for the existing organizational subscription. It discovers actual subscriptions after authentication. It does not assume wider geographic or network entitlements.

## Quick start without an API key

Requires Python 3.11 or later. The runtime has no third-party dependencies. Extract the bundle, open a terminal in its folder, and install the included wheel:

```powershell
py -m pip install --no-index --no-deps .\wheels\shadowserver_reports-0.1.0-py3-none-any.whl
py -m shadowserver_reports demo --output .\demo-output
```

On Linux/macOS, use `python3` and forward-slash paths. The demo uses a simulated service and documentation-only IP/domain values. It runs the real signing, catalog, download, schema, and ledger code; it makes no network requests and reads no credentials.

In a new demo output folder, it downloads a synthetic report, repeats the pull to confirm unchanged bytes are reused, then changes the synthetic report and preserves both versions. `demo-result.json` contains the results. Reusing the same demo folder is safe, but existing versions will be counted as reused. Use a fresh folder to reproduce the original counts. The synthetic demo uses its own fixed 120-second, 30-request, 1 MiB budget; CLI global budgets apply to the real operations.

## When the credentials arrive

Use the **key and secret** supplied by Shadowserver. On Windows, enter them through hidden prompts:

```powershell
py -m shadowserver_reports --profile outreach configure
py -m shadowserver_reports --profile outreach connection
py -m shadowserver_reports --profile outreach subscriptions
py -m shadowserver_reports --profile outreach types
```

Windows Credential Manager stores credentials under the current user. The module never accepts API credentials as command arguments. `configure --delete` deletes only that profile's stored credential. For a service or non-Windows environment, use `--credentials env` with `SHADOWSERVER_API_KEY` and `SHADOWSERVER_API_SECRET` supplied by your local secret-management environment. The environment provider reads these variables without persisting them. Its variable names are shared across profiles; use different profiles/ledgers for different accounts and do not reassign an existing profile to an unrelated account.

The `connection` result separately reports whether the API is reachable and whether the key advertises Reports access. Numeric usage values returned as strings are normalized; an advertised quota of zero is not interpreted as unlimited.

Replace `YOUR_SUBSCRIPTION` below with a name returned by `subscriptions`. Discover the actual report type before selecting it; `scan_http_vulnerable` is the expected starting family from the documentation. Dates are explicit, inclusive source dates. These sample dates are historical examples, not retention guarantees.

```powershell
py -m shadowserver_reports --profile outreach list --start 2026-11-06 --end 2026-11-06 --subscription YOUR_SUBSCRIPTION --type scan_http_vulnerable
py -m shadowserver_reports --profile outreach download --start 2026-11-06 --end 2026-11-06 --subscription YOUR_SUBSCRIPTION --type scan_http_vulnerable --output .\reports
py -m shadowserver_reports --profile outreach schema scan_http_vulnerable --cache .\schemas
```

`download` retrieves the original CSV or CSV.gz and writes a separate receipt. It never imports the file into Companion. Receipt validation means the file passed structural CSV checks and local acquisition checks; it does not certify the vulnerability, business attribution, or completeness of Shadowserver's observations.

## Commands and results

Global options go **before** the command: `--profile`, `--credentials`, `--timeout`, `--max-requests`, `--max-bytes`. Use `--help` on any command.

| Command | Result |
| --- | --- |
| `connection` | Reachability, Reports access, normalized account diagnostics |
| `subscriptions` | Available organizational report subscriptions |
| `types` | Available report families and metadata; optional date range |
| `schema TYPE [--cache DIR]` | Raw field schema; optional versioned snapshot and changes |
| `list` | Public catalog metadata with completeness status; usable download tokens excluded |
| `download` | Selected original files and acquisition receipts |
| `query` | Research events with page counts and explicit completeness status |
| `sync` | One pull with a separate SQLite ledger and recovery history |
| `configure` | Hidden credential entry into Windows Credential Manager |
| `demo` | Entirely synthetic, offline demonstration |

Catalog commands require either `--subscription NAME` or `--all-subscriptions`, and either `--type NAME` or `--all-types`. Repeat the singular options for multiple selectors. Listing and download selection are distinct from event-query filtering.

JSON results go to stdout. Fatal errors go to stderr with safe messages. Partial batch results include successful receipts plus the error/status. Exit codes are `0` complete, `1` error, `2` partial/unknown or missing Reports access, and `130` interrupted. Query exhaustion is deliberately `unknown` until the real server's pagination behavior is verified, so a successful bounded query normally exits `2` in this release.

## Repeatable pulls

```powershell
py -m shadowserver_reports --profile outreach --timeout 300 sync --start 2026-11-01 --end 2026-11-06 --subscription YOUR_SUBSCRIPTION --type scan_http_vulnerable --output .\reports --ledger .\api-history.sqlite3 --lookback-days 2
```

`sync` executes once. It does not install a service, schedule tasks, send messages, or run in the background. A later scheduler can invoke the same operation.

The ledger is independent of Companion. It records runs, attempts, logical report identities, content revisions, and each acquisition receipt. It namespaces history by profile and checkpoints by selection scope. With the same start date/subscriptions/types and a later end date, a subsequent pull rechecks the recent window and then advances. A checkpoint means the catalog scan and selected downloads completed; it does not guarantee that a day's reports will never change or arrive later.

The default lookback is two calendar days, configurable up to 366. To check a much older correction, explicitly backfill the historical date range. There is no assumed retention or delivery SLA. Partial catalogs and failed/cancelled transfers never advance the checkpoint. The run stops at the first operational failure; retrying the command rechecks unfinished work. Resume is at the job level, not HTTP byte-range continuation.

Every selected report is fetched again during a recheck. The content hash determines whether storage can be reused. New tokens do not imply new content, and an unchanged token does not imply unchanged content. Changed bytes produce another immutable file. Multiple subscriptions can share a content file while keeping separate provenance.

## Research queries

Create `scope.json` containing an attribute matching the organization's actual authorized filters, such as its assigned ASN or network. Do not infer a query entitlement from the workstation location or from an API request-source restriction. Put additional conditions in `filters.json`. The API remains the authority on access.

```powershell
py -m shadowserver_reports --profile outreach query --start 2026-11-06 --end 2026-11-06 --scope-json .\scope.json --filters-json .\filters.json --page-size 100 --max-pages 5 --max-records 500
```

The client checks advertised query fields, prevents filters from overriding the supplied scope, keeps a fixed server page size, detects repeated pages, and enforces local record/page caps. Query type values are event filters; they must not be assumed identical to catalog report-family names. Query results contain less detail than complete reports and are never used as substitute report evidence. Empty, partial, unknown, denied, and failed results remain distinct.

## Files, dates, and schemas

The selected output folder contains `reports/` with SHA-256-named original files, `receipts/` with immutable JSON acquisition records, and a temporary `.partial/` directory. The server filename is metadata; it never determines a local path. Receipts include original filename, subscription, report type/date, acquisition time in UTC, byte count, SHA-256, validation outcome, and a source-identifier fingerprint. Raw download capabilities remain in memory, excluded from public output and the ledger.

An abrupt process kill may leave a temporary file; it is not treated as completed and will not be imported on restart. Successful content publication before a later receipt/ledger failure is recovered by rechecking and hashing the existing file. Existing content is verified before reuse; corrupt content is not overwritten silently.

Source bytes, report dates, row timestamps, and unknown CSV columns remain unchanged. **The narrative date-plus-one rule belongs only to Companion's report builder.** This module does not shift dates.

Schema snapshots use a canonical SHA-256 and report added, removed, or changed fields. The raw API map is retained, including unfamiliar schema values. Schema diagnostics do not coerce report cells. `iter_rows(path)` yields string values by header name. Its validation is lazy; consume the iterator to validate the entire file. Callers should use a receipt's successful validation status when they need a fully checked file.

## Python integration boundary

```python
from datetime import date
from shadowserver_reports import (
    Ledger, Operation, ReportDownloader, ReportsClient,
    ReportSelection, SignedTransport, sync_once,
)
from shadowserver_reports.credentials import WindowsCredentialProvider

selection = ReportSelection(
    date(2026, 11, 6), date(2026, 11, 6),
    subscriptions=("YOUR_SUBSCRIPTION",),
    types=("scan_http_vulnerable",),
)
operation = Operation(timeout=300, max_requests=30, max_bytes=256 * 1024**2)
with SignedTransport(WindowsCredentialProvider("outreach")) as transport:
    client = ReportsClient(transport)
    downloader = ReportDownloader("reports")
    with Ledger("api-history.sqlite3", profile="outreach") as ledger:
        result = sync_once(client, downloader, ledger, selection, operation=operation)
    print(result.public_dict())
```

Basic catalog/download use does not require a database. Pass a `threading.Event` to `Operation(cancel_event=...)` for cooperative cancellation. Never serialize `ReportDescriptor` with generic `dataclasses.asdict`; its private in-memory fields contain the remote capability. Use `public_dict()`. API credentials also have a deliberately redacted representation; do not serialize credential objects.

## Bounds and compatibility

- API requests sign exactly the transmitted UTF-8 JSON bytes with HMAC-SHA256. Only supported read-only endpoints are allowed.
- Signed API traffic and unsigned downloads use separate HTTPS contexts. TLS verification stays enabled, redirects are rejected, and credentials never accompany download requests. The catalog documentation URL is never used as the download target.
- API transient failures have at most three attempts by default, bounded by the shared operation budget. Valid `Retry-After` values are honored when the budget permits. Authentication/scope/protocol errors stop. Downloads have no automatic retry to avoid repeated expired-link requests.
- Default budgets: 120-second operation, 20-second request timeout, 100 HTTP attempts, 1 GiB cumulative received bytes, 16 MiB API response, 1,000 listed reports, 256 MiB per raw or decompressed report. `download` also defaults to 100 selected reports. Per-operation date ranges are capped at 366 days.
- Deadlines and cancellation are checked between network/file steps and during streaming; socket timeouts are reduced to the remaining deadline. OS-level DNS resolution and filesystem calls are outside Python's strict timing control, so this is not a hard real-time guarantee.
- CSV support is UTF-8/UTF-8 BOM, at least two unique nonempty headers, consistent row widths, quoted multiline fields, and optional gzip. The Python CSV parser's field-size limit is retained (normally 128 KiB per field); larger fields fail explicitly. UTF-16, ZIP containers, and malformed encodings are not silently converted.
- Atomic immutable publication requires a filesystem supporting hard links, such as NTFS or common Linux filesystems. Use a local NTFS directory on Windows. Unsupported storage fails without publishing a verified receipt.
- Network proxies are not inherited from environment variables. `SignedTransport(proxy=...)` supports an explicit API proxy. A deployment needing proxy-backed downloads must inject a separate verified, non-redirecting unsigned opener; no proxy configuration is built into this CLI release.
- Catalog requests follow the official manager's `reports` subscription array and `types` report-family array. An explicit Python compatibility option `ReportsClient(..., selector_style="wiki")` supports the wiki's singular `type`. There is no silent fallback that broadens selection. Missing server type metadata is inferred only when exactly one type was explicitly requested.
- Catalog requests partition by day, with a conservative local cap of 1,000 results per daily response even when the total selection budget is larger. Hitting any limit is reported as partial; there is no invented server pagination. Narrow the range or selectors before increasing budgets. Query completeness remains unknown pending live verification of the conflicting documented limits.
- No app integration, scheduler, notification delivery, attribution, CVE enrichment, scanning, subscription mutation, or historical-data retention guarantee is included.

## Validation and live acceptance

Run the fixture suite after installing the wheel:

```powershell
py -m unittest discover -s tests -v
```

`VALIDATION.json` and `validation/test-results.txt` record the build's actual checks. Tests include exact signing bytes, Unicode, credential redaction, authentication/scope errors, malformed responses, retries/deadlines, report limits, pagination, interrupted transfers, file safety, gzip bounds, changed columns, revisions, interrupted runs, profile isolation, and checkpoint correctness. All report/account content is synthetic.

Once credentials are available, perform the small live sequence in `LIVE_ACCEPTANCE.md`. The test gate verifies actual access, selection-field compatibility, one complete download compared with the corresponding emailed report, repeat/correction behavior, query boundaries, and Windows credential storage. This release does not claim those tests have already run.

## Primary protocol sources

Reviewed November 8–9, 2026:

- [Reports API](https://github.com/The-Shadowserver-Foundation/api_utils/wiki/API:-Reports-Query)
- [General API and authentication](https://github.com/The-Shadowserver-Foundation/api_utils/wiki/call_api-Documentation)
- [Official signing helper](https://github.com/The-Shadowserver-Foundation/api_utils/blob/main/call-api.py)
- [Official report manager](https://github.com/The-Shadowserver-Foundation/api_utils/blob/main/report-manager.py)
- [Report delivery guidance](https://www.shadowserver.org/faq/how-are-reports-delivered/)
- [API access and sample reports](https://www.shadowserver.org/faq/can-i-access-your-reports-through-an-api/)

This is an independent project, not an official Shadowserver SDK.
