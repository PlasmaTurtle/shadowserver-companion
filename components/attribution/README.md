# Attribution Module

A standalone Python component for qualifying notification leads against public registration data. RDAP is the first provider, followed by current DNS association checks. The module accepts a root domain and candidate IPs, stops at the first qualifying match, and saves the responses and decision for later review.

This release is independent of the Shadowserver workbench. It includes a Python API, CLI, Windows launchers, persistent SQLite storage, and a printable HTML evidence exhibit. The workbench integrates this component and provides the analyst review screen.

## Windows quick start

1. Install Python **3.11 or newer** with the Python launcher available.
2. Extract the entire ZIP to a writable folder, such as `C:\AttributionModule`.
3. Double-click **Setup.cmd**. It creates a local virtual environment and installs the bundled wheels. Installation does not need PyPI access.
4. Double-click **Attribution.cmd**. Enter a root domain and its candidate IP addresses.
5. Open the generated `exports\<domain>-<id>\evidence.html` in your browser.

Live lookups require HTTPS access to `data.iana.org`, the relevant registry RDAP services, and HTTPS access to Google Public DNS at `dns.google`. The module queries registries, not the candidate servers.

Distributions omit historical live-lookup samples. The automated tests use synthetic responses; use the CLI export command with your own saved result when inspecting real attribution evidence.

## Command line

Run these from a terminal in the extracted folder:

```bat
Attribution.cmd check google.com 10.0.0.4 8.8.8.8 8.8.4.4 --export exports\google
Attribution.cmd check example.com 8.8.8.8 --hostname mail.example.com
Attribution.cmd check example.com 8.8.8.8 --rdap-only
Attribution.cmd batch examples\groups.jsonl --output results.jsonl --workers 2
Attribution.cmd history
Attribution.cmd history --root-domain example.com --status review
Attribution.cmd stats
Attribution.cmd export RESULT_ID exports\saved-result
Attribution.cmd verify exports\saved-result
```

`--db PATH` selects a database. The default is `data\attribution.sqlite3` relative to the working directory. The Windows launcher sets that directory to its own folder.

For `check` and `batch`:

| Option | Behavior |
|---|---|
| `--hostname mail.example.com` | For `check`: the reported hostname used for forward DNS. Without it the supplied root is queried. Batch candidates accept an optional `hostname` field. |
| `--rdap-only` | Disable DNS fallback while retaining registration-name partials for review. |
| `--offline` | Use only unexpired cached responses. A cache miss returns `deferred`; it makes no network request. |
| `--refresh` | Fetch new IP/entity records even when cached. Previous evidence is retained. IANA bootstrap data still uses its independent cache. |
| `--timeout 10` | Maximum inactivity timeout for an HTTP operation. |
| `--budget 45` | Per-provider, per-candidate time budget, checked between requests and streamed response chunks. |
| `--interval 0.5` | Minimum gap after a request to the same registry. |
| `--entity-limit 8` | Maximum referenced entity fetches for one candidate IP. |

The time budget is cooperative, not a hard operating-system cancellation deadline. An in-progress HTTP phase can last until its configured timeout. A long registry cooldown is returned immediately with `retry_at`, rather than sleeping through it.

JSON results go to stdout; batch progress and errors go to stderr. `check` exits `0` for a match, `1` for review/no match/no eligible IP, and `2` for incomplete/deferred/error. `batch` exits `2` if any completed group is review/incomplete/deferred; otherwise `0`. `verify` exits `1` when files differ from the manifest. Interrupted commands exit `130`.

Batch input is **one already-grouped notification lead per JSON line**:

```json
{"root_domain":"example.com","candidates":[{"entry_id":"sheet1-row2","ip":"8.8.8.8"},{"entry_id":"sheet1-row3","ip":"10.0.0.5"}]}
```

The IP/domain relationship above is a schema illustration, not a claim. Input must supply the intended registrable root domain; the module does not guess it by removing hostname labels. Excel filtering and public-suffix-based grouping remain upstream.

Each candidate needs a distinct nonblank `entry_id`. Results retain **all candidates**, including private addresses, duplicates, and those not queried after a match. Batch results are emitted in completion order and saved individually. An interrupted batch can be rerun using its saved cache; this release does not have a persistent batch queue or automatic resume cursor. A pre-existing output JSONL file is never truncated.

## Python API

```python
from attribution import AttributionModule, CandidateIP, EvidenceRenderer

with AttributionModule.open("data/attribution.sqlite3") as module:
    result = module.attribute(
        root_domain="google.com",
        candidates=[
            CandidateIP(entry_id="row-2", ip="10.0.0.4"),
            CandidateIP(entry_id="row-3", ip="8.8.8.8"),
            CandidateIP(entry_id="row-4", ip="8.8.4.4"),
        ],
    )
    print(result.status, result.matched_entry_id)
    result_json = result.to_dict()
    EvidenceRenderer(module.store).export(result.result_id, f"exports/{result.result_id}")
```

The caller owns the full original rows. `matched_entry_id` identifies the existing row to move to `[0]` in its `ValidatedLeads.entries`; all other rows and fields retain their existing order. The workbench adapter can then attach the module's evidence to its notification parent. The new JSON schema is deliberately provider-neutral; it is not a drop-in replacement for the workbench's legacy `whois` dictionary.

The module and its default provider are context-managed. If you inject an externally constructed `EvidenceStore` or provider, the caller closes it. A shared module supports up to four batch worker threads. Use one running module process per database for predictable rate scheduling; SQLite protects writes across processes, but the request-spacing locks are process-local.

## Qualification behavior

The default `RootDomainPolicy` accepts a complete target-domain or subdomain occurrence supplied by RDAP. It does not impose a contact-role, business-name similarity, DNS, website, or state-registration gate.

| Input evidence for `example.com` | Decision |
|---|---|
| `security@example.com` | Match |
| `abuse@mail.example.com` | Match |
| `https://www.example.com/contact` | Match |
| `notexample.com` | No match |
| `example.com.unrelated.net` | No match |
| `https://unrelated.net/?name=example.com` | No match |

Email fields use the email's domain; URL fields use the URL's hostname. Free text is checked for domain tokens, with embedded emails and URLs parsed first. Names are compared as normalized IDNA ASCII labels; case and one terminal DNS dot do not alter the match.

Service metadata (`notices`, protocol links, events, conformance declarations, `port43`, and redaction metadata) is retained as evidence but excluded from matching. Entity lists of other networks/ASNs are also excluded: a domain on another resource must not qualify this IP. Registration remarks, contact fields, names, and unknown registration fields remain searchable. Contact roles are recorded, not used as another gate.

| Result status | Meaning |
|---|---|
| `matched` | A provider supplied evidence accepted by the configured policy. Stop immediately. |
| `review` | No exact attribution; one or more registration-name word matches retained in `partial_evidence`. `matched_entry_id` remains null. Individual failed attempts remain visible and retryable. |
| `no_match` | The configured retrieval process completed without a qualifying occurrence; attempt reasons distinguish no record from domain absent. |
| `incomplete` | Invalid, omitted, redacted, or inaccessible data or an entity traversal limit prevented a complete negative result. |
| `deferred` | A transient failure, cooldown, time budget, or offline cache miss prevented completion. |
| `no_eligible_ip` | No candidate was eligible for a public registry lookup. |

A positive match is sufficient even when a different field is redacted or an earlier IP failed. Without an exact match, partial evidence produces `review`; without partial evidence, deferred attempts take precedence over incomplete ones, and incomplete attempts take precedence over no-match. None of these outcomes deletes source observations.

## Retrieval and storage

- IANA IPv4/IPv6 bootstrap records select the authoritative service by longest prefix. The resolver supports HTTPS service alternatives and validates redirects.
- An IP response must be an `ip network` object whose start/end range includes the queried IP.
- Embedded entities are examined first. Incomplete entities are followed through their RDAP self links, using a depth limit of three and a default request limit of eight. Cycles are deduplicated; a matching entity ends retrieval immediately.
- The network client accepts only IANA-discovered or known regional-registry HTTPS hosts, port 443, and bounded redirects. It never follows business website URLs found in contact information.
- Successful and 404 responses are cached by exact request URL. IP lookups use normalized addresses; IPv4-mapped IPv6 maps to IPv4. A network range is never used to infer cached answers for other IPs.
- Successful records have a default maximum reuse age of 24 hours; 404 responses ten minutes. HTTP cache directives may shorten these limits. Responses marked `no-store` are not reused as cache entries; an archival copy is still retained with the result.
- HTTP 429 and `Retry-After` cooldowns are persisted per registry. Server/network errors get bounded retries and are never negative-cache entries. Simultaneous identical requests share the populated cache; a forced refresh deliberately performs a fresh request.
- Response bodies, including redirects and error bodies, are size-limited and stored independently of the cache. Body bytes are preserved after supported HTTP content decoding. Selected headers, actual URL, status, UTC retrieval time, and SHA-256 are retained.
- Unknown JSON fields are preserved. Ambiguous JSON with duplicate members or non-finite values is rejected. An oversized or invalidly compressed body is not saved as a complete response.
- Evidence export reads the saved result and snapshots; it never re-queries a registry. Cached retrieval timestamps are not reset to the current evaluation time.

Default limits are defined in `Settings`. The database is a local SQLite file with WAL enabled. Shut down the module before copying the database for backup, or use SQLite's backup API. Do not back up only the main file while it is actively writing.

## Evidence package

Each export contains:

- `attribution.json` — complete result, candidate list, attempts, matched entry, policy/provider versions and settings.
- `responses.json` — response metadata and raw-body file paths.
- `responses/` — preserved response bodies, including bootstrap/referral records and DNS observations.
- `analyst-reviews.json` — included when the workbench exports a recorded review decision; original automated results stay immutable.
- `evidence.html` — escaped, self-contained, printable attribution exhibit, with expandable source records.
- `manifest.json` — SHA-256 for the exported files.

`AttributionEvidence` uses common fields (`method`, `ip`, `source_name`, `source_url`, `retrieved_at`, `match`, snapshot references). RDAP network-specific fields live in `details`, so another provider does not need to pretend to be a registry.

This is a reproducible record of what the workstation retrieved and how the matcher evaluated it. SHA-256 detects changed bytes against the stored manifest; it is not a digital signature or an independently authenticated timestamp. A match records an association in registration data, not verified asset ownership or a vulnerability finding.

## Adding a provider

Implement `AttributionProvider.collect(ip, root_domain, refresh=False, offline=False) -> ProviderResult` and give the provider a unique `name`. A provider retrieves evidence and identifies candidate matches; `QualificationPolicy.accepts()` remains responsible for acceptance. Implement `describe()` to record the provider's version and configuration in results.

Pass providers through `AttributionModule(store, providers=[...], policy=...)`. The default policy accepts `rdap` and `dns`. DNS requires a hostname at/below the supplied root and an address response containing the reported IP; a PTR name alone does not qualify. `RootDomainPolicy(("rdap",))` restores registration-only qualification. `Settings(enable_dns=False)` also prevents DNS requests. Registration-name partials use method `rdap_keyword` and cannot qualify automatically. Providers used with batch workers must be thread-safe and save referenced snapshots in the shared evidence store.

## Development and validation

```text
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[test]"
.venv\Scripts\python -m pytest -q
```

On macOS/Linux, use `.venv/bin/python` instead. Tests use synthetic registration data and mocked HTTP/DNS; they make no external requests. See `VALIDATION.md` for this release's execution results and live registry smoke checks. Actual Windows execution remains to be verified on the intended workstation.

Name matching uses the supplied root’s first label, not service labels or the public suffix. The caller must continue to supply the correct registrable root. Network `name` and entity jCard `org`/`fn` values supply tokens; explicitly individual `fn` names are skipped. There is no dictionary, stopword list, minimum word length, fuzzy match, or business-specific allowlist. Numbers alone are not words. Every match includes its original JSON Pointer and source snapshot.

DNS uses **Google Public DNS**, a public recursive resolver, over HTTPS at `https://dns.google/resolve`. It is not an authoritative name server for the reported domain. Each observation preserves the exact JSON response body, SHA-256, original UTC retrieval time, HTTP status/headers, and complete HTTPS query URL. The matched address cites its exact JSON Pointer. Cached evidence retains its original retrieval time. Existing workstation-resolver evidence keeps its original source name and captured bytes; it is never relabeled as Google evidence.

Queries use absolute names, the candidate IP family, DNSSEC validation enabled (`cd=false`), and `edns_client_subnet=0.0.0.0/0`. Responses must match the exact question. Only addresses at the queried name or its validated CNAME chain can qualify; unrelated answer records cannot. PTR names still require root-domain boundaries and a matching forward lookup. The provider limits each operation's total elapsed time, response size, CNAME depth, and PTR candidates (eight), supports cancellation, and does not follow redirects away from the fixed service. Complete HTTP/DNS failure responses are saved, but failures are not cached as successful evidence. Positive answers use the minimum applicable DNS/HTTP TTL. NXDOMAIN/no-answer are distinct from timeout/service failures. Current resolution does not prove a historical address change. No HTTP request is made to reported hosts.

Provider API and response semantics: [Google JSON API documentation](https://developers.google.com/speed/public-dns/docs/doh/json) and [Google DNS-over-HTTPS documentation](https://developers.google.com/speed/public-dns/docs/doh). The evidence source is the saved response from the query URL; these documentation links describe the service and are not substituted for an observation. Callers can pass `cancel_event` to `AttributionModule` or `DnsProvider`; injected `resolver` objects retain the legacy DNS interface for offline fixtures or explicit custom-resolver integrations.

Main source files: `module.py` (orchestration/policy), `rdap.py` (provider/discovery), `http.py` (retrieval), `matching.py` (domain rules), `name_matching.py` (review words), `dns_lookup.py` (DNS provider interface), `google_dns.py` (Google Public DNS capture and validation), `store.py` (persistence), `render.py` (evidence), and `cli.py` (commands).

References: [IANA IPv4 bootstrap](https://data.iana.org/rdap/ipv4.json), [IANA IPv6 bootstrap](https://data.iana.org/rdap/ipv6.json), [RFC 9224](https://www.rfc-editor.org/rfc/rfc9224.html), [RFC 9082](https://www.rfc-editor.org/rfc/rfc9082.html), [RFC 9083](https://www.rfc-editor.org/rfc/rfc9083.html), [RFC 7480](https://www.rfc-editor.org/rfc/rfc7480.html), [ARIN RDAP](https://www.arin.net/resources/registry/whois/rdap/).


## Database schema 2 (module 0.2.1)

Saved results have `root_domain`, `status`, and `policy_version` metadata alongside the complete original `payload`. Root-domain and status history queries are indexed. The policy version is the recorded policy ID, such as `root-domain-v2`; a custom policy without an ID remains NULL. SQL checks keep this metadata consistent with the saved JSON.

`EvidenceStore.history(limit=20, root_domain=None, status=None)` supports optional filters. The CLI provides `history --root-domain DOMAIN --status STATUS`. History retains its existing result fields. Full result and response exports are unchanged.

Opening an existing schema-1 database creates a backup in the adjacent `backups` folder and upgrades it transactionally. Captured bodies, result JSON, IDs, cache entries and cooldowns are preserved. Failed upgrades roll back; unsupported future versions are rejected. Close the module before restoring a backup, and do not use an older module against the upgraded database. The public result JSON remains schema version 2.
