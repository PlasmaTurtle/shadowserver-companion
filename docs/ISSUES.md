# Project issues and module issue index

This register owns shared project work and indexes module-owned issues. Last
reviewed: **2026-11-21**. Each issue has one canonical home: its owning module's
`docs/ISSUES.md`, or this file for project-wide coordination. Status and completion
evidence stay at that home. The [module directory](README.md#module-documentation-and-tracking)
links every guide and tracker, including modules without recorded open items.

Follow the [maintenance workflow](DEVELOPMENT.md#maintenance-workflow) before
refactoring. Choose work by its demonstrated benefit to the owning module.
ISS001 and ISS003 address verification and fixture-maintenance debt. ISS014 is a
release gate; deferred refactors need a concrete maintenance or reuse need.
ISS015 and ISS016 address startup exclusion and bounded acquisition; ISS017's
completed triage found no unintended retained-record mutation in the examined scope.


Earlier maintenance checks are recorded in the [November 21 validation](history/validation/maintenance-2026-11-21.md).
Individual entries retain their module benefit, scope and evidence; later work
records its own verification and does not inherit that batch's completion claim.

## Issue index

| ID | Canonical issue | Primary owner |
| --- | --- | --- |
| ISS001 | [Capture test expectations](../modules/investigations/docs/ISSUES.md#iss001-capture-test-expectations) | Investigations |
| ISS002 | [Shared rendering deadline dependency](../modules/ui/docs/ISSUES.md#iss002-shared-rendering-deadline-dependency) | UI |
| ISS003 | [Shared test fixtures](#iss003-shared-test-fixtures) | Project |
| ISS004 | [Workspace facades and models](../modules/workspace/docs/ISSUES.md#iss004-workspace-facades-and-models) | Workspace |
| ISS005 | [Workspace queue presentation](../modules/workspace/docs/ISSUES.md#iss005-workspace-queue-presentation) | Workspace |
| ISS006 | [Library editing in Settings](../modules/settings/docs/ISSUES.md#iss006-library-editing-in-settings) | Settings |
| ISS007 | [Entity presentation in Leads](../modules/leads/docs/ISSUES.md#iss007-entity-presentation-in-leads) | Leads |
| ISS008 | [Browser suite coverage](#iss008-browser-suite-coverage) | Project |
| ISS009 | [Explicit resource encoding](#iss009-explicit-resource-encoding) | Project |
| ISS010 | [Legacy intake network path](../modules/accretion/docs/ISSUES.md#iss010-legacy-intake-network-path) | Accretion |
| ISS011 | [Remaining service SQL](#iss011-remaining-service-sql) | Project |
| ISS012 | [Browser composition interfaces](../modules/ui/docs/ISSUES.md#iss012-browser-composition-interfaces) | UI |
| ISS013 | [Rendering resource inputs](../modules/ui/docs/ISSUES.md#iss013-rendering-resource-inputs) | UI |
| ISS014 | [Current version Windows acceptance](#iss014-current-version-windows-acceptance) | Project |
| ISS015 | [Pre-registration upgrade race](../modules/settings/docs/ISSUES.md#iss015-pre-registration-upgrade-race) | Settings |
| ISS016 | [Bulk feed deadlines and cancellation](../modules/library/docs/ISSUES.md#iss016-bulk-feed-deadlines-and-cancellation) | Library |
| ISS017 | [Read route mutation review](../modules/workspace/docs/ISSUES.md#iss017-read-route-mutation-review) | Workspace |
| ISS018 | [Command-palette focus after search](../modules/ui/docs/ISSUES.md#iss018-command-palette-focus-after-search) | UI |
| ISS019 | [Interrupted certification state](../modules/investigations/docs/ISSUES.md#iss019-interrupted-certification-state) | Investigations |
| ISS020 | [Reported-host loading and redirects](../modules/tools/docs/ISSUES.md#iss020-reported-host-loading-and-redirects) | Tools |
| ISS021 | [Enforce the intake funnel](../modules/accretion/docs/ISSUES.md#iss021-enforce-the-intake-funnel) | Accretion |
| ISS023 | [Remove repeated funnel work](../modules/accretion/docs/ISSUES.md#iss023-remove-repeated-funnel-work) | Accretion |
| ISS024 | [Filter contracts and interruption](../modules/accretion/docs/ISSUES.md#iss024-filter-contracts-and-interruption) | Accretion |
| ISS025 | [Isolate complete Dark Matter storage](../modules/accretion/docs/ISSUES.md#iss025-isolate-complete-dark-matter-storage) | Accretion; Observatory, Leads and Workspace |
| ISS026 | [Reusable tools and duplicate capabilities](../modules/tools/docs/ISSUES.md#iss026-reusable-tools-and-duplicate-capabilities) | Tools; affected module owners |
| ISS027 | [Qualify decisions and workflow](../modules/accretion/docs/ISSUES.md#iss027-qualify-decisions-and-workflow) | Accretion; Attribution, Entities, Tools, Leads and Investigations |
| ISS028 | [Root configuration and startup ownership](#iss028-root-configuration-and-startup-ownership) | Project; Workspace and Accretion |
| ISS029 | [Workspace file ownership and consolidation](../modules/workspace/docs/ISSUES.md#iss029-workspace-file-ownership-and-consolidation) | Workspace; affected module owners |
| ISS030 | [Preserve settings changes across saves](../modules/settings/docs/ISSUES.md#iss030-preserve-settings-changes-across-saves) | Settings; Workspace persistence and setup callers |
| ISS031 | [Evaluate scoring matrix and active scope](../modules/accretion/docs/ISSUES.md#iss031-evaluate-scoring-matrix-and-active-scope) | Accretion; Leads |
| ISS032 | [Consistent intelligence and source provenance](../modules/library/docs/ISSUES.md#iss032-consistent-intelligence-and-source-provenance) | Library; Accretion and Investigations |
| ISS033 | [Explainer edits and revision history](../modules/library/docs/ISSUES.md#iss033-explainer-edits-and-revision-history) | Library; Investigations and Activity |
| ISS034 | [Reproducible catalog views](../modules/library/docs/ISSUES.md#iss034-reproducible-catalog-views) | Library; Observatory |
| ISS035 | [Catalog consistency and measured performance](../modules/library/docs/ISSUES.md#iss035-catalog-consistency-and-measured-performance) | Library; Observatory |
| ISS036 | [Provider access and version comparison](../modules/library/docs/ISSUES.md#iss036-provider-access-and-version-comparison) | Library |
| ISS037 | [Library ownership and interfaces](../modules/library/docs/ISSUES.md#iss037-library-ownership-and-interfaces) | Library; Workspace and Investigations |
| ISS038 | [Research and reference workflow improvements](../modules/library/docs/ISSUES.md#iss038-research-and-reference-workflow-improvements) | Library; affected workflow owners |
| ISS039 | [Settings interaction reliability](../modules/settings/docs/ISSUES.md#iss039-settings-interaction-reliability) | Settings; UI and Workspace |
| ISS040 | [Reviewed software update identity](../modules/settings/docs/ISSUES.md#iss040-reviewed-software-update-identity) | Settings |
| ISS041 | [Supported display timezones](../modules/settings/docs/ISSUES.md#iss041-supported-display-timezones) | Settings; UI and release tooling |
| ISS042 | [Setup completion review consistency](../modules/settings/docs/ISSUES.md#iss042-setup-completion-review-consistency) | Settings; Accretion |
| ISS043 | [Associate scope and component boundaries](../modules/accretion/docs/ISSUES.md#iss043-associate-scope-and-component-boundaries) | Accretion; Entities and Leads |
| ISS044 | [Qualified website contact scope](../modules/entities/docs/ISSUES.md#iss044-qualified-website-contact-scope) | Entities; Accretion and Investigations |
| ISS045 | [Duplicate canonical and archive observations](../modules/observatory/docs/ISSUES.md#iss045-duplicate-canonical-and-archive-observations) | Observatory; Accretion and Library navigation |
| ISS046 | [Typed Accretion handoffs](../modules/accretion/docs/ISSUES.md#iss046-typed-accretion-handoffs) | Accretion; Attribution, Entities, Leads and Workspace |
| ISS047 | [Command palette reopen lifecycle](../modules/ui/docs/ISSUES.md#iss047-command-palette-reopen-lifecycle) | UI |
| ISS048 | [Full-run runtime reliability](#iss048-full-run-runtime-reliability) | Project; Investigations, Workspace and release tooling |

## Project work status

| ID | Status | Coordination |
| --- | --- | --- |
| ISS003 | Resolved | Root test harness and affected modules |
| ISS008 | Resolved | Project verifier and module browser fixtures |
| ISS009 | Resolved | Resource readers across tools and modules |
| ISS011 | Deferred | Accretion and Investigations service/repository boundaries |
| ISS014 | Pending validation | Release, Settings, Workspace and affected modules |
| ISS028 | Resolved | Root configuration, dependency/release tooling, documentation and Workspace startup |
| ISS048 | Needs triage | Unexplained certification-integrity failure and native interpreter crash during full verification |

## ISS028 Root configuration and startup ownership

The root-file audit found repeated formatting configuration, contribution policy,
application versions and dependency hashes, plus reusable workspace-session code
imported by Accretion from the root launcher. Root security and maintenance guides
also repeated implementation details maintained by module owners.

**Done when:** root files have distinct responsibilities; reusable startup/session
behavior has a Workspace owner; dependency versions and approved hashes have a
single maintained lock; obsolete files and references are removed; source and
installed distributions retain their intended entrypoints, release notes and
integrity checks. Verify actual configuration discovery, dependency artifacts,
startup/locking callers, copied installed payload and documentation links without
requiring a full installer build for this maintenance change.

**Resolved 2026-11-21.** The Desktop repository has 21 root files instead of 24.
Prettier settings live in its native `package.json` configuration; contribution and
shared maintenance policy live in Development. README, AGENTS and SECURITY are
shorter entrypoints. Older changelog entries are archived together, with exact
baseline reconstruction and unchanged current-release title/13 highlights.

Workspace owns startup and exclusive-session lifetime; `run.py` is a seven-line
entrypoint instead of 142 lines. Installed desktop and Accretion callers import
the owners directly. AST/CLI comparisons preserve lock/replacement order, server
and browser lifecycle, and command-line behavior. This removes a dependency on
the root launcher as a shared library.

`VERSION` supplies the Python runtime version. Three npm application-version copies
are removed; `RELEASE.json` retains its explicit version binding for acceptance
and downgrade checks. The Windows dependency lock is the maintained version/hash
authority. Common constraints are generated, source requirements select names,
and checker/installer share artifact verification. The root wheel-hash manifest
is removed; the independent Attribution package keeps its own packaging metadata.
The installed payload omits source-only AGENTS and constraints.

Focused verification: 23 dependency tests plus 12 subtests passed; source and
Windows pip dry-runs resolved the same 34 packages with unchanged approved
versions, filenames and hashes. Startup selections passed 142 tests with three
platform/privilege skips, and 16 native command-wrapper checks passed. The
release/payload/update selection passed 42 tests initially. Two initial failures
came from concurrent ISS027 changes (architecture boundaries and a stale
scheduled-intake fixture); both passed targeted reruns after that work updated
them. No assertions were weakened and no full application/installer build was run.

The regenerated program map, source/installed document links, actual copied
payload imports and upgrade inventory are checked with the final evidence in the
Codex task's `validation/root-file-audit-fixes-20261121/` bundle. It retains initial
failures, commands, source hashes, preservation comparisons and the focused scope.
The working tree remains uncommitted on `efccc0a0f476bf83078b26694afa8fad0372047c`,
including separately changing ISS027 work; these checks do not certify that entire
change set or replace Windows release acceptance.

## ISS003 Shared test fixtures

Before this change, module tests imported fixtures by another test file's bare
name. For example, Leads' `test_lead_frontier_0991.py` imported Entities'
`test_contacts_api_090.py`. The fixture-name guard caught filename collisions but
did not remove this dependency on flat import paths.

**Done when:** reusable fixtures have explicit support-module imports, feature
fixtures remain with their owner, and pytest plus directly executed browser
fixtures work without ambiguous test names. Coordinate any import-mode change
with those callers.

**Resolved 2026-11-21.** The complete local-helper
audit removed 389 bare imports: 307 cross-test imports, eight browser/conftest
imports and 74 named root-helper imports. Fifty-eight historical providers now
share 41 cohesive support modules (39 application, two standalone); 134 moved
helper/class definitions are AST-identical apart from explicit import paths.
No test assertions or fixture teardown rules were changed by the extraction.

Application supports import under isolated Python with only the repository root
and engine source on the path, and can build/persist a synthetic Entity contact.
Previously importing a browser helper also replaced `requests.get` and the native
scanner and loaded a test module; support imports now preserve those globals and
load no test/browser entry point. Retired test-directory injection is removed
from pytest, direct browser bootstrap and verifier launch paths. Default pytest
import mode and the filename-collision guard remain intact.

The extraction's collection check retained every original test: 3,218 versus its 3,215 baseline,
with the three additions belonging to ISS010/ISS017. The provider selection passed
891 tests with eight skips; nine boundary tests, 141 independent engine tests and
12 direct browser CLI checks also passed. The final path cleanup has collection,
boundary and direct-import evidence and is included in the completed 3,294-test
backend collection. Exact commands, source manifests, AST audit and before/after
isolation proofs are in the Codex workspace's
`validation/maintenance-batch-02/iss003-*` bundle. The uncommitted source remains
based on `efccc0a0f476bf83078b26694afa8fad0372047c`.

## ISS008 Browser suite coverage

The previous verifier registered six browser suites while other feature scripts
had no maintained routine/focused disposition. Some dormant fixtures also assumed
obsolete setup, canonical-count and editor behavior. Discovery alone did not
establish executed coverage.

**Done when:** each additional browser script is reviewed and either registered
with its required fixture/setup or documented as a deliberate focused check.
Validate the chosen routine suite together; do not equate script discovery with
executed coverage. The [development guide](DEVELOPMENT.md#working-in-a-module)
describes the current registration rules.

**Resolved 2026-11-21.** One verifier catalog now
owns 16 routine scripts in ten isolated fixture groups, four explicit focused
groups, two manual artifact checks and one exploratory fixture. New, missing or
duplicate script dispositions fail validation. Every script gets a fresh launcher
credential; shared fixture setup makes post-setup/offline boundaries explicit.
The obsolete Contacts 090/095 browser scripts are replaced by current contact
and lifecycle coverage, with historical outcome/asset checks retained in their
existing backend and portable suites.

Five asynchronous Playwright predicates previously returned truthy Promises
before their conditions were satisfied. A controlled false predicate resolved in
23 ms despite a 250 ms timeout. The replacement bounded API poll retries actual
responses and reports the last observed state on timeout. Its portable regression
is part of the frontend runner. Canonical-count, scope-review and source-adoption
fixture corrections preserve the current application contracts; they do not
change production rules to satisfy stale expectations.

All 16 routine scripts passed together in 185.729 seconds. The four focused groups
also passed, as did the package-shell checks across 12 theme/mobile layouts and
the file-based evidence reader. Package checks verified retained PDF/DOCX/archive
bytes and downloads. The exploratory Field fixture was prepared, not accepted as
a browser test. Nine verifier contract tests (19 subtests), two polling tests and
the complete portable frontend runner passed. The keyboard review separately
found and fixed [ISS018](../modules/ui/docs/ISSUES.md#iss018-command-palette-focus-after-search).

This is improved verification reliability and coverage, not a claim that every
fixture repair enhanced a module. Exact dispositions, source hashes, coverage
mapping and execution records are in the Codex workspace's
`validation/maintenance-batch-02/browser008-*` bundle, based on the uncommitted
source at `efccc0a0f476bf83078b26694afa8fad0372047c`.

## ISS009 Explicit resource encoding

Earlier Windows verification exposed implicit repository-resource reads using
cp1252. Development and IDE checks set `PYTHONUTF8=1`; individual resource readers
needed review beyond that workaround. The observed failure and workaround are
recorded in [relocation validation](history/validation/module-reorganization-validation.md#browser-evidence-and-corrected-fixture-setup).

**Done when:** text resources with a UTF-8 contract use explicit encoding and
relevant Windows reads pass under a non-UTF-8 default. Preserve input-specific
encoding rules for imported reports; do not change every reader indiscriminately.

**Resolved 2026-11-21.** Reviewed application/tool
resource readers and UTF-8 fixture producers/consumers now state their encoding.
This fixes actual Windows cp1252 failures loading accented entity place names and
advisory JSON. The updated readers preserve `Cañon City` and accented advisory
text with `PYTHONUTF8=0`; resource bytes and approved report wording are unchanged.
Imported-report decoding and OS/protocol-specific ASCII readers retain their
existing contracts. New regressions also treat implicit-encoding warnings as
errors, so UTF-8-default CI cannot conceal the defect.

The initial Windows selection passed 360 tests and 11 subtests, skipped one, and
reported the expected in-progress ISS016 wheel/source mismatch. After packaging
engine 0.2.7, the affected dependency/resource selection passed all seven tests
and 11 subtests. Eleven direct browser fixture CLI imports also passed under
cp1252; this checks their setup, not browser interaction. Exact changes, preserved
asset hashes, intentional remaining default-text readers and before/after results
are in the Codex workspace's `validation/maintenance-batch-02/iss009-*` bundle.
The changes are uncommitted on `efccc0a0f476bf83078b26694afa8fad0372047c`.

## ISS011 Remaining service SQL

Intake and publication/recovery services retain aggregate SQL. Extract it when
working on those services rather than moving queries independently of their
transaction and filesystem protocols.

**Done when:** the selected queries have cohesive repository ownership while
caller-owned transactions, rollback and interrupted-publication recovery remain
covered. Revisit this deferred item when a concrete service refactor is selected.

**Reviewed 2026-11-21.** The selected intake change replaces the legacy CLI's
network path; it does not alter application intake transactions or publication
recovery. Moving aggregate SQL during that work would add transaction risk
without a demonstrated service benefit. This item remains deferred until an
actual intake/publication change establishes the repository contract and its
observable before/after outcome.

[ISS019](../modules/investigations/docs/ISSUES.md#iss019-interrupted-certification-state)
now owns a concrete publication slice: normal certification and interrupted
recovery disagree on persisted lead state. Its shared transition keeps the
caller-owned transaction and package protocol intact. Remaining aggregate SQL
stays deferred; this targeted repair does not justify moving unrelated queries.

## ISS014 Current version Windows acceptance

`RELEASE.json` records 0.12.0 as a candidate with no current-version home
confirmation. The recorded 0.9.96 Windows baseline does not accept this build.
Portable tests and source packaging do not establish native installer, Word,
display-scaling, Task Scheduler or workstation-security behavior.

**Done when:** the [Windows acceptance checklist](WINDOWS_ACCEPTANCE.md) is
completed for the exact candidate, with installer hash, outcomes and any remaining
limitations recorded. Keep detailed acceptance steps in that checklist and
version status in [release metadata](../RELEASE.json).

**Partial evidence 2026-11-21.** The preceding maintenance candidate, installer
SHA-256 `b0c0445941161abc8e2d25fd0b7d79e0681272bdd1c1fa210758da5ab4e96aac`,
passed its packaged offline `runtime_self_test()` on Windows 10 Pro build 19045
with embedded Python 3.14.10. It created a synthetic SQLite workspace and
PNG/DOCX/PDF files, then removed them normally; all 2,467 copied app/runtime files
remained unchanged. The 4.679-second run and two corrected instrumentation-only
failures are retained in `validation/maintenance-batch-03/packaged-selftest-*`
in the Codex workspace.

This called the self-test function directly with network and sensitive native
actions denied. It did not exercise the launcher, application lifespan, full
report workflow, installer, Task Scheduler, credentials, Word or display scaling.
Word 16.0.20326.20318 is available for a later controlled layout check. The actual
installer uses the existing app's fixed registry and shortcut identity, so a
different `/D` directory alone does not isolate full installation acceptance.
The recorded self-test applies only to the named artifact; ISS014 remains pending.

## ISS048 Full-run runtime reliability

**Status: Needs triage. Owner: Project**, with Investigations for rendered-resource
integrity and Workspace/release tooling for interpreter and application-lifecycle
diagnosis. These are two observed failures; a common cause has not been established.

The November 21 full verification produced:

- One synthetic certification returning HTTP 422 with `Rendered SVG resource
  integrity check failed.` The failure occurred before the recovery test's
  simulated lost publication commit. No failing resource bytes survived the
  renderer's temporary cleanup. The original workspace and operation journal
  were preserved. The isolated case, whole recovery file and exact saved-workspace
  replay passed, which does not resolve the original observation.
- A later unsharded diagnostic run terminated at about 68% with native exception
  `0xC0000005`. Windows recorded a fault in `python314.dll` during garbage
  collection while the fixture constructed a FastAPI/Pydantic application.
  This is a process crash, not a failed assertion or a passing partial run.

The runtime is GIL-enabled Windows x64 Python 3.14.10 with Pydantic 2.14.3 and
core 2.50.4. Installed native extension bytes match their approved wheels.
Read-only native-call and resource-code reviews found no concrete causal defect.
The external diagnostic wrapper rethrows original SVG errors and changes no
successful rendering or native child command. Its only captured SVG exception
before the crash was an intentional corrupt-resource test that passed.

Bounded diagnostics separately completed 100 normal application construction,
cleanup and garbage-collection cycles, then 20 full inline certifications on fresh
verified copies of the failed synthetic workspace, under Python's debug allocator.
Both completed without a crash; the rendering probe retained all integrity checks.
These are diagnostic limits, not a runtime fix or clean full-suite acceptance.
No GC control, dependency pin or integrity assertion was changed to force a pass.

**Next evidence needed:** a reproducible triggering sequence or native crash dump
with matching symbols and resource context. The original WER temporary dump was
already removed; the fault event, module identity, stack and saved workspace remain.
Do not attribute the failure to application code, a dependency or hardware without
evidence, and do not replace a causal repair with repeated green focused runs.

**Done when:** the cause or environmental boundary is established, the appropriate
repair is demonstrated on the failing sequence, and full verification plus repeated
certification succeed with the original integrity checks. The intended benefit is
reliable report generation and runtime operation; until then the candidate is not
cleared by a full regression pass. Exact counts, source state and evidence locations
are in the [full-build record](history/validation/full-build-2026-11-21.md).

## Maintaining this register

Choose the primary owner before creating an item. Module-specific work belongs
in that module's tracker; cross-project coordination belongs here. Name affected
collaborators and link dependencies to their canonical entries. Other trackers
may link an issue, but must not copy its status, description or completion criteria.

Use a stable, globally unique `ISS` number; check this index and all module
trackers before allocating the next number. Add the index link in the same
change. Preserve IDs when ownership changes, move the complete entry and update
links. Use Open, In progress, Needs triage, Deferred, Pending validation, Resolved
or Superseded to describe the actual state. Record a blocker or deferral reason
where it matters; do not create speculative defects to fill an empty tracker.

Each entry identifies its owner, observed problem or concrete goal, relevant
source/evidence and completion criteria. Define a material module benefit and
observable before-and-after criteria before implementing a change. To resolve it,
retain the completion date, change reference, demonstrated benefit and relevant
verification under the entry. Describe test-only repairs as verification debt;
they do not establish a module enhancement. A file move or related passing check
alone does not resolve an issue. Superseded items identify
the successor. Keep completed entries available until deliberately archived.

The canonical trackers own maintenance status. GitHub issues and pull requests
provide linked discussion/change references when used; update the canonical
entry rather than maintaining a second backlog. Architecture owns current
contracts, module guides own maintenance instructions, and dated validation
records retain past results without becoming live status pages.
