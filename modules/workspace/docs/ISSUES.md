# Workspace issues

This tracker owns Workspace maintenance work. Last reviewed: **2026-11-22**.
Use the [module guide](README.md) for current contracts and verification, and
the [project register](../../../docs/ISSUES.md) for shared work and the global
index. Follow the [issue lifecycle](../../../docs/ISSUES.md#maintaining-this-register)
when adding, resolving or deferring an item.

[ISS026 reuse audit](../../tools/docs/ISSUES.md#iss026-reusable-tools-and-duplicate-capabilities)
includes atomic file publication, contained file reads and health timestamps.
Workspace retains backup, recovery and workspace lifecycle decisions.


Shared checks for this completed batch are recorded in the [November 21 validation](../../../docs/history/validation/maintenance-2026-11-21.md).
Individual entries retain their module benefit, scope and focused evidence.

## Register

| ID | Work | Status |
| --- | --- | --- |
| ISS004 | [Workspace facades and models](#iss004-workspace-facades-and-models) | Resolved |
| ISS005 | [Workspace queue presentation](#iss005-workspace-queue-presentation) | Resolved |
| ISS017 | [Read route mutation review](#iss017-read-route-mutation-review) | Resolved |
| ISS029 | [Workspace file ownership and consolidation](#iss029-workspace-file-ownership-and-consolidation) | Resolved |
| ISS053 | [Local views lost their connection while the console was open](#iss053-local-views-lost-their-connection-while-the-console-was-open) | Needs reproduction |

## ISS053 Local views lost their connection while the console was open

The analyst observed failures across views after importing a report with the Windows console still visible. The installed access log shows successful bootstrap, Workspace and intake progress requests. The operator subsequently uninstalled Eclipse and deleted its file tree after Defender quarantined the launcher. The logs establish neither when the running server stopped nor what caused the outage. [Project ISS054](../../../docs/ISSUES.md#iss054-defender-quarantined-the-windows-launcher) owns the quarantine investigation. The browser recovery correction is tracked in [UI ISS050](../../ui/docs/ISSUES.md#iss050-recovering-the-shell-after-a-lost-connection).

All ten sidebar destinations opened in sandboxed Edge from a fresh Windows source demo after an import. The browser recorded 31 successful API responses. In a separate 1,380-row import with synthetic capture, registry and DNS providers, all 408 domain groups qualified. The ten views opened during processing (41 API responses) and again after completion (39), without failed requests or uncaught browser errors. After verification, Windows held the load-test database open during temporary-directory cleanup. It was available for exclusive access after the runner exited. A repeat waited for the qualified-lead export acknowledgement and exited cleanly with all 408 groups qualified. The separately launched demo server also released its workspace database on exit. To distinguish a local service interruption from a failed individual request on recurrence, record the time, the response from `/api/health` on the same origin, and the HTTP status or browser network error for one failed view. Omit session URLs, tokens, cookies and case data. Close this issue after reproducing the fault, repairing the responsible path and verifying navigation during and after an import on Windows.

On November 22, the Windows source app retained both uploaded HTTP observations
and qualified their single domain group. Edge refused navigation to the local
stand-in for the reported hostname on the first attempt. The analyst resumed the
same import with synthetic website and registry evidence. Its original CSV
matched the uploaded bytes. The GUI completed review of all five sections,
certification, export, simulated delivery and closure. After a server restart,
the closed case reopened and served the same certified PDF by SHA-256. The
recipient PDF had ten pages. Microsoft Word also rendered the DOCX in ten pages.
The installed app's connection failure still needs reproduction.

## ISS029 Workspace file ownership and consolidation

**Owner:** Workspace, coordinating with Entities, Library, Settings, Observatory,
Investigations, Activity, Attribution and UI.

The module file audit found unrelated feature routes and frontend handlers in
Workspace, contact validation depended on a Workspace backup helper, and legacy
request/helper reexports survived only for tests and development callers. Planner
status and local-session discovery also maintained separate atomic-write code.
The data runbook described an obsolete two-database layout and schema version.

**Done when:** feature handlers and validators live with their owners, application
composition registers them explicitly, obsolete files/exports disappear after
caller migration, and existing shared publication handles failure cleanup. Keep
the data runbook and maintenance guide in scope. Preserve HTTP paths and schemas,
frontend behavior, transaction/locking boundaries and retained evidence bytes.
Demonstrate the improvement with the file inventory, before/after contracts,
failure-path checks and relevant module/caller tests; a reduced file count alone
does not establish success.

**Resolved 2026-11-21.** All 89 original Workspace files were reviewed; 84 remain
after six obsolete files/placeholders were removed or responsibilities moved and
one focused planner-publication regression file was added.
The per-file inventory explains retained boundaries as well as removals.

Library owns explainer endpoints, Settings owns settings mutations, and Workspace
owns its search/brief/queue adapters. The application composer explicitly registers
Observatory instead of relying on a nested registration. Contact provenance
validation lives in Entities and is reused by ordinary contact operations and
Workspace transfer/health checks. The unused cross-domain model facade, API model
reexports and Store primitive/default aliases are removed after caller migration.
Store's used service methods and the 27 owner model definitions are unchanged.

Attribution owns its review events, UI owns global search, Activity owns compact
activity rendering, and Investigations owns report-package views. Two unused UI
exports and their CSS are removed. The dashboard captures one date per render:
requests, heading and due-date links remain consistent across midnight. Seven
moved HTTP handlers and three moved frontend implementations retain their bodies;
six rendered outputs and all 284 live action names remain unchanged.

Planner status and launcher discovery reuse Tools' atomic writer. A reproduced
replacement failure previously left a planner temporary file; the shared writer
now cleans it while preserving prior status and committed data. Launcher JSON
bytes, DPAPI calls and private-file behavior are preserved, with publication
failures covered. Backup/health validation, strict input JSON versus retained
snapshot decoding, schema/migration order and locks remain separate where their
contracts differ. The data runbook now describes all three retained databases.

Verification: the complete Workspace plus API/model/lifecycle/settings selection
passed 232 tests and 33 subtests, with two existing platform/privilege skips.
Focused storage/contact checks passed 98 tests; session/security checks passed
58; destination route checks passed four. All 69 portable frontend suites and
five real Edge workflows passed. The 191 HTTP routes, complete OpenAPI document
and all 27 owner schemas match the before snapshot. Lint, regenerated ownership
map, copied installed-app imports/schema/upgrade inventory and source/installed
documentation links were checked; no full application or installer build was run.

The snapshot, all 89 file verdicts, exact commands, logs/JUnit, byte/AST comparisons
and final source hashes are in the Codex task's
`validation/workspace-file-audit-20261121-223701/` bundle. An early collection error
while route files were being moved is retained separately from the successful
completed checks. The Desktop working tree remains uncommitted on
`efccc0a0f476bf83078b26694afa8fad0372047c`, including inherited work; this scope does
not replace full-project or exact-version Windows release acceptance.

## ISS004 Workspace facades and models

**Owner:** Workspace.

The initial `modules/workspace/components/store.py` and `api_models.py` combined
responsibilities from multiple domains.

**Done when:** selected domain responsibilities move behind explicit interfaces,
with callers updated and regression evidence preserving shared transactions,
schema versions, startup recovery and serialized API contracts. Split one
responsibility at a time.

**Resolved 2026-11-21.** The selected slice moves
27 request models into six owning modules and leaves identity-preserving
compatibility reexports. All application callers use the owners directly.
An isolated-process check proves that each owner's request models can validate
input with the other application modules unavailable. All 27 model definitions,
JSON schemas and compatibility identities match the saved baseline. A common
model superclass was rejected because the existing configurations differ.

`Store.lead()` now delegates its projection to Entities' `entity_view()`, using
one read snapshot. A concurrent contact update previously combined an old profile
with a new completeness status; it now returns a coherent old view followed by
the updated view on the next request, without blocking the writer. This is the
functional benefit of the selected service extraction; the remaining Store
composition facade is not claimed to be eliminated.

The API/model/entity-review/settings selection passes 21 tests with one existing
dependency warning. Baseline reproduction, model parity and command/JUnit records
are in `validation/maintenance-batch-02/iss004-*` in the Codex workspace. Changes
are uncommitted on baseline `efccc0a0f476bf83078b26694afa8fad0372047c`.

## ISS005 Workspace queue presentation

**Owner:** Workspace, coordinating with Entities and Accretion.

Before this change, `modules/workspace/static/queues.js` combined the dashboard
with entity-list and import presentation.

**Done when:** entity and intake presentation live with their owning modules;
Workspace composes their interfaces. Queue behavior, loading, navigation and
event cleanup remain covered.

**Resolved 2026-11-21.** Entities now owns its
directory/dossier and Accretion owns intake/import/progress. Workspace retains
dashboard/current-work/report-list composition. Explicit `install(ctx)` owners
replace hidden feature installation; UI owns shared navigation/filter behavior.
Repeated dropzone binding no longer duplicates uploads, and teardown releases
intake listeners and pending entity lookups. These are concrete lifecycle gains
in addition to clearer maintenance ownership.

The affected DOM selection passes 44 suites. Nine selected rendered/model
outputs match the baseline, and all 283 existing action names remain available.
Real Chromium navigation and Library workflows pass with synthetic data, no
JavaScript errors and no external requests. The exact 32-file manifest,
before/after checks and screenshots are in the Codex workspace's
`validation/maintenance-batch-02/frontend-*` bundle. This local change shares the
ISS004 baseline above; it does not establish full browser or native acceptance.

## ISS017 Read route mutation review

**Owner:** Workspace, coordinating with the owners of any affected routes.

A legacy security follow-up notes possible incidental writes on read routes but
does not identify specific affected paths. The review needed triage before any
path could be treated as a confirmed defect. Some review refresh behavior is intentional:
`SectionReviewQueries.describe()` can record a stale review, while
`record_changes=False` provides a read-only projection.

**Done when:** the examined GET/read paths and their intended and observed
mutation behavior are recorded. Distinguish documented review refresh from
unintended writes; create a scoped fix with reproduction and regression coverage
for each confirmed problem, or close this review with evidence. Do not change
transaction or review-history behavior solely to satisfy a blanket read-only rule.

**Resolved 2026-11-21 — audit completed.** The source inventory finds
87 literal GET registrations across the application, including Attribution;
no additional dynamic GET registrations were found. Tracing the potentially
mutating notification, preview, export and auxiliary-store paths identified
documented compatibility, review-history, operation-journal and temporary-file
effects. The [read-route contract](README.md#read-route-boundaries) names these
exceptions and their owners. No unintended retained-record mutation was
reproduced by this review.

A new synthetic regression exercises 33 ordinary navigation/status paths with
Workspace connections forced query-only. All return successfully; the complete
Workspace logical database and retained originals/evidence/report/closure bytes
remain identical, and no case is created. It passes all 33 subtests (one existing
dependency warning). This is audit/verification debt addressed, not a claimed
functional enhancement or proof for every parameterized route/legacy state.
Existing notification initialization and stale-review chronology are preserved.

The exact inventory, command and JUnit/log evidence are in the Codex workspace's
`validation/maintenance-batch-02/iss017-*` bundle. The uncommitted audit/test/docs
change is based on `efccc0a0f476bf83078b26694afa8fad0372047c`.

## Related work

These entries retain their status and completion evidence in the owning tracker:

- [ISS003 Shared test fixtures](../../../docs/ISSUES.md#iss003-shared-test-fixtures).
- [ISS008 Browser suite coverage](../../../docs/ISSUES.md#iss008-browser-suite-coverage).
- [ISS009 Explicit resource encoding](../../../docs/ISSUES.md#iss009-explicit-resource-encoding).
- [ISS014 Current version Windows acceptance](../../../docs/ISSUES.md#iss014-current-version-windows-acceptance).
- [ISS048 Full-run runtime reliability](../../../docs/ISSUES.md#iss048-full-run-runtime-reliability), including the native interpreter crash during application construction and bounded lifecycle diagnostics.
- [ISS015 Pre-registration upgrade race](../../settings/docs/ISSUES.md#iss015-pre-registration-upgrade-race), including installed child-process lifetime.
- [ISS028 Root configuration and startup ownership](../../../docs/ISSUES.md#iss028-root-configuration-and-startup-ownership): Workspace now owns command-line/server startup and the shared exclusive session. Source and installed launchers use the owner directly; Accretion no longer imports the root launcher. The [startup contract](README.md#startup-and-workspace-sessions) records lock/replacement order and server/browser lifetime.
