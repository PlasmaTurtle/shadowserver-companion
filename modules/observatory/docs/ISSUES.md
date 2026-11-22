# Observatory issues and planned work

Last reviewed: **2026-11-21**. No module-owned open issues are currently recorded.
Keep new confirmed Observatory work here using the
[project tracking rules](../../../docs/ISSUES.md#maintaining-this-register), with
an owner, status, affected behavior and completion criteria.

[Module maintenance guide](README.md) owns implementation boundaries, and
[Observatory acceptance](OBSERVATORY_ACCEPTANCE.md) owns verification procedures.
An empty issue register does not replace acceptance evidence.

## ISS045 Duplicate canonical and archive observations

**Owner:** Observatory · **Status:** Completed 2026-11-21.

A rejected finding could retain a canonical observation while its original source
remained unpromoted in the archive. Observatory appended that same source a second
time: an eight-row imported report displayed nine observations after clearing the
Library catalog filter. The finding count was correct.

Archive projection now skips an immutable source key already represented by a
canonical observation. Different source rows remain distinct even when their IP,
CVE and other fields match. Rejected findings, archive detail access and stored
source records remain intact; the archive scan limit still marks incomplete
coverage when a limited page contains duplicates.

Verification: `test_archive_source_membership.py` proves exact-source deduplication,
distinct-row retention, unchanged archive records and bounded-scan disclosure.
Together with the existing canonical, semantics, Dark Matter detail and route
checks, **33 tests passed**. Replaying the original successfully imported eight-row
fixture now yields **eight observations and nine findings**, preserving its rejected
finding and unchanged archive record. Library owns the related
[catalog scope](../../library/docs/ISSUES.md#iss034-reproducible-catalog-views) and
[reference workflow](../../library/docs/ISSUES.md#iss038-research-and-reference-workflow-improvements)
work; this issue owns only Observatory projection.

Final native catalog-scope replay passed all seven unchanged checks on a copy of
that retained fixture, including reset to eight observations, exact filtered
membership and mobile layout. The normal local index rebuild handled analytics
schema 3. Complete Library/Observatory suites passed 509 checks on frozen source;
[Library's batch record](../../library/docs/ISSUES.md#repair-batch-verification)
retains the concurrent-intake fresh-fixture failure and verification limits.

## Work owned elsewhere

| Item | Observatory dependency |
| --- | --- |
| [ISS026 Reusable tools and duplicate capabilities](../../tools/docs/ISSUES.md#iss026-reusable-tools-and-duplicate-capabilities) | Share UI formatters and review request mechanics/risk aliases while retaining selection, revision recovery and finding-level scope. |
| [ISS025 Isolate complete Dark Matter storage](../../accretion/docs/ISSUES.md#iss025-isolate-complete-dark-matter-storage) | Accretion owns archive storage and query semantics; Observatory owns its API-backed field browser and presentation. |
| [ISS012 Browser composition interfaces](../../ui/docs/ISSUES.md#iss012-browser-composition-interfaces) | UI coordinates the shared action/render contract with Observatory. |
| [ISS003 Shared test fixtures](../../../docs/ISSUES.md#iss003-shared-test-fixtures) | Fixture extraction affects module tests and direct browser bootstrap. |
| [ISS008 Browser suite coverage](../../../docs/ISSUES.md#iss008-browser-suite-coverage) | The project verifier owns suite registration. |
| [ISS014 Current version Windows acceptance](../../../docs/ISSUES.md#iss014-current-version-windows-acceptance) | Observatory supplies its visual and scoped-evidence checks to release acceptance. |

Follow the linked owner for status and completion evidence; do not maintain a
second copy of those issue records here.
