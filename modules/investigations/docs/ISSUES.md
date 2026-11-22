# Investigations issues

This tracker owns Investigations maintenance work. Last reviewed: **2026-11-21**.
Use the [module guide](README.md) for current contracts and verification, and
the [project register](../../../docs/ISSUES.md) for shared work and the global
index. Follow the [issue lifecycle](../../../docs/ISSUES.md#maintaining-this-register)
when adding, resolving or deferring an item.

[ISS026 reuse audit](../../tools/docs/ISSUES.md#iss026-reusable-tools-and-duplicate-capabilities)
includes duplicate manifest parsing and shared file-reader ownership. Manifest
schema, artifact inventory and case evidence remain Investigations responsibilities.


Earlier maintenance checks are recorded in the [November 21 validation](../../../docs/history/validation/maintenance-2026-11-21.md).
Individual entries retain their module benefit, scope and evidence; later work
records its own verification and does not inherit that batch's completion claim.

## Register

| ID | Work | Status |
| --- | --- | --- |
| ISS001 | [Capture test expectations](#iss001-capture-test-expectations) | Resolved |
| ISS019 | [Interrupted certification state](#iss019-interrupted-certification-state) | Resolved |
| ISS020 | [Reported-host loading and redirects](../../tools/docs/ISSUES.md#iss020-reported-host-loading-and-redirects) | Moved to Tools |

## ISS001 Capture test expectations

**Owner:** Investigations.

**Historical scope:** this entry records verification of the earlier request
broker. Its scanner-specific expectations were superseded by the native browser
implementation in [ISS020](#iss020-reported-host-loading-and-redirects); they are
not requirements to restore in the current capture path.

Three capture-test failures reproduce in untouched baseline
`efccc0a0f476bf83078b26694afa8fad0372047c`. The 2026-11-21 baseline reproduction
ran the two affected parametrized tests: three failed and five passed.

`modules/investigations/tests/test_website_capture_0985.py` passes a blocked count
to the boolean `document_failed` parameter in the `info3-200-True-2-partial` case.
The blocked/unavailable cases in
`modules/investigations/tests/test_website_browser_0985.py` expect a browser
failure command although preflight content scanning stops before browser startup.

**Done when:** classification cases test document failure and partial capture
explicitly; driver tests distinguish preflight rejection from rejection after
browser startup and verify cleanup. Preserve fail-closed scanning and rerun the
affected complete suites. These are recorded test-contract mismatches, not
evidence that the reorganization introduced a capture defect.

**Resolved 2026-11-21.** Classification now tests
the boolean document-failure contract, including partial/not-loaded cases.
Driver cases separately exercise preflight rejection and script rejection after
startup, with assertions for failed requests, absent screenshots, profile/peer/
process cleanup and the unchanged user-cancellation flag. Runtime capture policy
is unchanged. This repairs verification debt rather than claiming a new capture
capability.

The three capture/browser/diagnostic suites pass: 37 tests, one existing dependency
warning. The local uncommitted change is based on
`efccc0a0f476bf83078b26694afa8fad0372047c`; command, log and JUnit evidence are in
the Codex workspace's `validation/maintenance-batch-02/iss001-capture.*` bundle.

## ISS019 Interrupted certification state

**Owner:** Investigations; Entities and Workspace consume the resulting status.

A synthetic failure after a certified package is renamed into place but before
its database transaction commits leaves an intact package for startup recovery.
Recovery advances the case to `pending_notification`, but leaves the associated
lead `in_progress`. The completed lead filter then omits the business, while the
dashboard counts it as both completed and in progress. Case detail masks the
inconsistency by deriving its displayed status from the case stage.

**Module benefit and done when:** interrupted certification restores the same
case and lead state as normal publication in one caller-owned transaction.
Unchanged reviewed work appears consistently in lead filters and dashboard
counts after restart. Stale cases, changed review inputs and changed operators
retain the intact package as history without activating it or changing lead
state. Recovery must remain idempotent, preserve every package byte, and roll
back all database changes together if the transition fails.

The selected scope is a shared Investigations publication persistence operation,
used by certification and recovery. Services retain package assembly/rename,
review and integrity checks, transaction ownership, artifact registration and
audit policy. A second lead update in recovery would repair the immediate symptom
but leave the two paths free to diverge again; a general repository framework or
unrelated intake SQL extraction adds no benefit to this fix.

**Resolved 2026-11-21.** The source baseline is byte-identical to the completed
maintenance batch, on uncommitted revision
`efccc0a0f476bf83078b26694afa8fad0372047c`. A real post-rename exception reproduced
the inconsistent filter/dashboard results using only synthetic records. Baseline
source, commands and scenario outcomes are retained in the Codex workspace's
`validation/maintenance-batch-03/` bundle. This is the concrete publication slice
of [ISS011](../../../docs/ISSUES.md#iss011-remaining-service-sql); it does not
expand the remaining intake refactor.


The shared transition now restores both records atomically. Replaying the same
interruption puts the business in the completed filter, removes it from the
in-progress count, and aligns case/lead update timestamps. All ten package files
retain their hashes. Later unassigned findings remain visible; repeated recovery
does not overwrite subsequent administrative changes. A synthetic failure during
the lead update rolls back report registration, artifact registration and the
case change, leaving the package available for a successful later recovery.

Five behavioral checks passed; nine repository checks passed after correcting
their fixture's missing attribution-entry relationships without weakening foreign
keys. The initial failed fixture run remains recorded. A separate before/after
replay also passed. The complete unsharded backend then passed **3,288
tests and 207 subtests**, with **17 documented skips**.
Exact commands, JUnit results, skips, source hashes and independent review are in
the same evidence bundle. Python lint/format, the 446-program ownership graph
and release identity checks passed. No frontend or API shape changed, so browser
checks were not repeated for this backend repair.

The updated candidate artifacts and verification reports are retained under
`dist/maintenance-2026-11-21-recovery/`. Full Windows acceptance remains separate
under ISS014; this repair does not promote the release candidate.

## ISS020 Reported-host loading and redirects

The canonical record moved to [Tools ISS020](../../tools/docs/ISSUES.md#iss020-reported-host-loading-and-redirects)
with the reusable browser engine. Investigations retains the case/job and evidence
attachment contracts described in its [module guide](README.md#website-loading-and-capture).

### Live-page completeness and diagnostics

See the [Tools live validation record](../../tools/docs/ISSUES.md#live-page-completeness-and-diagnostics).
These anchors remain for existing links; status and completion evidence have one
canonical home in Tools.

## Related work

These entries retain their status and completion evidence in the owning tracker:

- [ISS002 Shared rendering deadline dependency](../../ui/docs/ISSUES.md#iss002-shared-rendering-deadline-dependency).
- [ISS003 Shared test fixtures](../../../docs/ISSUES.md#iss003-shared-test-fixtures).
- [ISS004 Workspace facades and models](../../workspace/docs/ISSUES.md#iss004-workspace-facades-and-models), including owned case/report request contracts.
- [ISS008 Browser suite coverage](../../../docs/ISSUES.md#iss008-browser-suite-coverage).
- [ISS009 Explicit resource encoding](../../../docs/ISSUES.md#iss009-explicit-resource-encoding).
- [ISS011 Remaining service SQL](../../../docs/ISSUES.md#iss011-remaining-service-sql).
- [ISS013 Rendering resource inputs](../../ui/docs/ISSUES.md#iss013-rendering-resource-inputs).
- [ISS014 Current version Windows acceptance](../../../docs/ISSUES.md#iss014-current-version-windows-acceptance).
- [ISS048 Full-run runtime reliability](../../../docs/ISSUES.md#iss048-full-run-runtime-reliability), including the unexplained certification SVG-resource rejection and preserved diagnostic evidence.
- [ISS015 Pre-registration upgrade race](../../settings/docs/ISSUES.md#iss015-pre-registration-upgrade-race), including inherited protection for report workers.
