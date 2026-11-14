# Live acceptance — pending credentials

Status: NOT RUN. All existing automated tests use synthetic fixtures. Existing emailed report access is the design assumption; actual API entitlements are discovered from the key.

1. On a Windows workstation, install the included wheel and run the offline demo in a new folder. Enter the key and secret using `--profile outreach configure`; confirm storage/retrieval across a new terminal and deletion under a disposable test profile. Never put real credentials in chat, command arguments, source files, or captured evidence.
2. Run `connection`, `subscriptions`, and `types`. Record only redacted diagnostics. Verify the key advertises Reports access and the expected emailed subscription appears. Check advertised expiry and quota literally; do not interpret zero as unlimited.
3. List one recent date, one subscription, and one desired report type. Compare catalog metadata with the matching email. Verify manager-style selector semantics; if incompatible, explicitly test the single-type wiki adapter in Python. Do not silently broaden the request.
4. Download one report. Compare the original bytes or parsed rows with the report obtained from the corresponding email link. The raw-file hash is acquisition integrity evidence, not a server signature. Check the receipt, source date, UTC acquisition date, unknown columns, and absence of download capabilities in public output.
5. Repeat a one-day `sync` with the same profile and ledger. Confirm content reuse plus a new acquisition record. Interrupt a subsequent run and rerun it: incomplete work must not advance the completed scan checkpoint. Confirm on an actual corrected/late report if one is available; do not simulate a correction and label it live evidence.
6. Request the schema twice and compare snapshots. Confirm real UTF-8/CSV/gzip format and whether any field exceeds the current parser bound. Record any incompatible report formats for deliberate extension; do not convert away evidence.
7. Run a small query using a filter explicitly matching the subscription. Compare at least two pages at a fixed limit; test the record/window boundary conservatively. Record observed completeness and server limits. Do not declare exhaustive coverage based only on a short page.
8. Verify workstation proxy/certificate requirements, normal network errors, cancellation responsiveness, and native Windows filesystem/credential behavior. Redact raw server URLs or tokens from diagnostics. Confirm the output path uses NTFS or another hard-link-capable filesystem.

Acceptance record fields: module version, Python version, Windows version, date/time UTC, credential profile label, tested subscription/type/date range, safe request counts, acquisition hash/size, outcome per step, and unresolved behavior. Never include the actual key, secret, or usable download identifier.

Only after these checks should the module be treated as live-accepted. Companion integration remains a separate future change.
