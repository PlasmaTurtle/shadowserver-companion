# 0.9.89 — API download compatibility

Selecting a report could fail with “The download server returned an error document
instead of CSV.” The download endpoint returned a valid CSV attachment with HTTP
`Content-Type: text/html; charset=UTF-8`; Companion 0.9.88 rejected that header
before inspecting the body.

The downloader now treats MIME labels as advisory and validates the complete,
bounded CSV or CSV.gz before publishing its original bytes and receipt. It still
rejects actual HTML, JSON and XML bodies, malformed rows, truncated transfers,
compression mismatches, redirects and unsafe download identifiers. API JSON
discovery and signed authentication are unchanged.

## Installation

Close DarkMatter, run the 0.9.89 installer and keep **Retain existing data** selected.
Open **Shadowserver Data > API**, reconnect if needed, find the reports again, and
import the selection. A new listing refreshes download capabilities.

Schema 12, intake policy and temperatures, report generation, existing evidence,
stored records, credential storage and pinned runtime dependencies are unchanged.

## Verification

The regression reproduced the previous rejection, then passed after the fix.
Live verification downloaded the complete November 11 Vulnerable HTTP report:
1,579,534 bytes and 4,313 CSV rows, with its original-byte SHA-256 verified.
The actual intake reader parsed all 4,313 rows, preserved the hash and queued a
single import; a repeat handoff was deduplicated. The focused suite passed 183
tests and 107 subtests on CPython 3.14.10 with pinned dependencies.
Only aggregate verification results are distributed. Credentials, download URLs,
report rows and the verification workspace are excluded from release artifacts.

See VALIDATION.md for the completed test results. Native Windows installation and
the user's workstation network remain separate acceptance checks.
