# Settings issues and planned work

This register owns Settings issues and their completion evidence. Last reviewed:
**2026-11-22**. [Settings maintenance guide](README.md) describes current contracts;
the [project issue index](../../../docs/ISSUES.md) links shared work and other owners.
Follow the [tracking rules](../../../docs/ISSUES.md#maintaining-this-register).

[ISS026 reuse audit](../../tools/docs/ISSUES.md#iss026-reusable-tools-and-duplicate-capabilities)
includes Settings consumers of timestamp formatting, Blob downloads and atomic
file publication. Settings retains export, schedule and update workflow decisions.

| ID | Work | Status | Owner and collaborators |
| --- | --- | --- | --- |
| ISS006 | [Library editing in Settings](#iss006-library-editing-in-settings) | Resolved | Settings; Library |
| ISS015 | [Pre-registration upgrade race](#iss015-pre-registration-upgrade-race) | Resolved | Settings; Workspace and installer tooling |
| ISS030 | [Preserve settings changes across saves](#iss030-preserve-settings-changes-across-saves) | Resolved | Settings; Workspace persistence and setup callers |
| ISS039 | [Settings interaction reliability](#iss039-settings-interaction-reliability) | Resolved | Settings; UI and Workspace |
| ISS040 | [Reviewed software update identity](#iss040-reviewed-software-update-identity) | Resolved | Settings |
| ISS041 | [Supported display timezones](#iss041-supported-display-timezones) | Deferred | Settings; UI and release tooling |
| ISS042 | [Setup completion review consistency](#iss042-setup-completion-review-consistency) | Deferred | Settings; Accretion |
| ISS057 | [Recognize configured keys in onboarding](#iss057-recognize-configured-keys-in-onboarding) | Resolved | Settings; Accretion and Library credential interfaces |


Shared checks for this completed batch are recorded in the [November 21 validation](../../../docs/history/validation/maintenance-2026-11-21.md).
Individual entries retain their module benefit, scope and focused evidence.

## ISS006 Library editing in Settings

Before this change, `modules/settings/static/settings.js` included Library
editor presentation.

**Done when:** Library owns its editor implementation and Settings invokes an
explicit interface, preserving save, cancellation and unsaved-change behavior.
Library remains responsible for reference-data policy; UI remains responsible
for shared presentation primitives.

**Resolved 2026-11-21.** Library owns reference
editor rendering and events through `resources.install(ctx)` and
`library_events.createHandlers(ctx)`. Its editor works without installing
Settings. UI composes the editor, catalog and Workspace Health once each instead
of Settings secretly installing them. Save, cancel and retained-draft behavior
are covered by the owning portable suite and a real Chromium workflow.

A Settings test previously exited before its deferred-save assertions finished;
its fixture now isolates the unrelated onboarding hook and detects premature
completion. The shared 44-suite DOM selection and two browser workflows passed;
all 283 existing action names and nine selected outputs are preserved. Exact
commands, baseline comparison and screenshots are in the Codex workspace's
`validation/maintenance-batch-02/frontend-*` bundle. The uncommitted source is
based on `efccc0a0f476bf83078b26694afa8fad0372047c`; full browser coverage is tracked
separately in ISS008.

## ISS015 Pre-registration upgrade race

The previous installed launcher imported Python modules and loaded release metadata before
`hold_installation_mutex()` registers the running process. The installer holds
the shared start/install gate during file replacement, but that gate cannot
exclude interpreter/DLL loading and early imports that have already started.
Launching during replacement therefore retained a pre-registration
race. Baseline source: `tools/windows_installer/desktop.py` and `installer.nsi`; the
[security guide](../../../SECURITY.md) records this boundary.

The native baseline probe now reproduces the ordering: the old launcher imports
183 modules and reads release metadata while the install gate is held, before
running registration. It establishes early runtime entry, not a claim that actual
user records were corrupted. Older/direct launchers cannot retroactively honor
the native guard; the first-upgrade policy remains explicit.

**Done when:** a bootstrap outside the replaceable runtime, or version-staged
installation, excludes early loading from the replacement window. Native upgrade
tests must exercise overlapping launches, existing instances, interrupted
replacement and retained records, including an explicit older-launcher policy.
Coordinate the change with Workspace startup and the installer owner; ordinary
post-registration mutex tests alone do not establish completion.

**Resolved 2026-11-21.** A content-addressed immutable NSIS
bootstrap outside `app/` and `runtime/` registers an inherited running handle
before starting Python. A ready marker is withdrawn before replacement and
published only after payload verification and scheduled-action restoration.
The installer preserves prior owned bootstraps instead of overwriting an image
that may already be waiting on its gate. Installed scheduled acquisition and
render subprocesses need the same pre-import lifetime protection; desktop
shortcuts alone are insufficient. Both paths now carry pre-import protection.
This extends the existing NSIS/stdlib maintenance boundary without adding a
second runtime dependency or changing workspace identity.

Nine native bootstrap cases pass: held-gate exclusion, loaded-image protection,
running-instance exclusion, survival of bootstrap/parent death, incomplete
readiness, Unicode arguments, overlong scheduled arguments and bounded ordinary
waiter exit. The saved-source baseline demonstrates the earlier gap. These probes
use synthetic identities/directories and preserve a data sentinel. The production
app, records and tasks are untouched. Real Task Scheduler integration exposed
Windows XML default normalization that mocked tests did not exercise. The
corrected comparison recognizes documented defaults and unordered schema fields
while retaining every nondefault value and rejecting unknown/privileged principals.
A sanitized native export protects that behavior in the source test distribution;
the initial failure and successful native replay remain in the evidence bundle.

All seven native integration cases pass: ready publication and actual guarded
launch, legacy task migration, interrupted replacement repair, missing-ledger
recovery with an owned task, missing local inventory, preserved disabled intent,
and task/bootstrap removal with a mapped ordinary launcher waiting on the gate.
The real COM task retains its triggers/settings. All synthetic tasks/processes
are removed and retained sentinel bytes are unchanged. The integration uses real
helpers/COM/launcher with emulated NSIS payload copy/delete, not a full wizard run.
The focused scheduling/runtime selection passes 99 tests. The independent native
uninstall-tail probe also verifies locked-shortcut failure with a retry uninstaller,
successful retry, absent-key idempotence and retention of unknown files.

Ownership recovery and failure handling are part of the change: missing-ledger
repair reuses verified prior launchers, capacity is checked before mutation, and
an uninstaller/shortcut/registration write failure cannot publish readiness.
Sixteen root recovery tests pass; the broader installer owner selection passes
33 tests with one Windows symlink-privilege skip. The full installer template
compiles with warnings treated as errors; its compile-only payload is not run.
The [installer protocol](../../../tools/windows_installer/REFERENCE.md#guarded-launch-and-maintenance)
owns current behavior and the first-upgrade/direct-Python limitation. Exact source
hashes, focused checks and native evidence are retained in the Codex workspace's
`validation/maintenance-batch-02/iss015-*` and `native-probes` bundles. Whole-release
acceptance remains separately tracked in ISS014.

## ISS030 Preserve settings changes across saves

Two reproduced save paths lost user changes. When
reviewing completed setup, editing identity and navigating directly to Retrieval
schedule let Finish discard the retained profile draft without saving or asking.
Separately, Settings and setup profile updates read the complete profile before
starting their write transaction; a competing save committed between those steps
was overwritten, including an unrelated verification route or appearance choice.

**Done when:** finishing setup retains unsaved identity and schedule choices until
the user explicitly saves the profile, and both profile endpoints merge against
the latest committed preferences inside their write transaction. Failed profile
saves must retain drafts; jurisdiction notifications remain after commit, and
existing notification drafts retain their explicit adoption rules.

Use the existing Entities verification-settings transaction as the backend
reference and the setup form's explicit Save profile action as the UI contract.
Retain failing reproductions, Settings regressions and the synthetic setup browser
workflow. The source baseline is the uncommitted tree at
`efccc0a0f476bf83078b26694afa8fad0372047c`, captured before this change in the Codex
task's `validation/settings-reliability/` bundle. This work does not accept a new
installer or change saved-data formats.

**Resolved 2026-11-21.** Both profile endpoints now read and merge preferences
within the existing write transaction. The setup completion action rejects a
retained profile draft before making any schedule or completion writes and
explains how to save it. The schedule remains editable, and returning to the
profile preserves both forms' inputs. Failed profile saves retain those drafts.
This prevents silent loss of unrelated committed preferences and unsaved setup
identity changes; it does not introduce conflict detection for same-field edits.

Both new concurrency cases fail against the captured baseline and pass after the
repair. The frontend draft regression likewise fails with the baseline browser
module and passes with the guard. Final verification on Windows with Python
3.14.10 and Node 24.22.3 passed 133 backend tests: all Settings tests plus setup
integration, sender-profile backup, API jurisdiction and module request contracts.
The complete portable frontend runner and the setup browser group passed; the
browser verified zero writes on rejected completion, preserved inputs and an
explicit profile save followed by successful completion, with no page errors or
external requests. Scoped Ruff/Prettier checks, complete frontend syntax checking,
dependency integrity and the regenerated program-map check also passed.

Commands, source hashes, original failures and results are retained in the same
evidence bundle. Changes remain uncommitted on
`codex/settings-reliability-20261121`; this is scoped module/caller verification,
not a complete application or native installer acceptance run.

## ISS039 Settings interaction reliability

The full module review reproduced several
ordinary interactions that lost or failed to apply changes:

- The header theme shortcut submitted a cached full profile, reverting a newer
  office or jurisdiction saved elsewhere. Overlapping theme requests could also
  leave the screen and persisted preference on different themes.
- The generic Settings change handler consumed agency-preset changes before the
  preset handler ran. A delayed options response could leave the selector empty
  when the user had already edited an unrelated field.
- An entered NVD key did not activate navigation, unload or update-install dirty
  guards. A successful earlier key save erased a newer entry typed while waiting.
- A required field inside a collapsed section could prevent saving without
  revealing or focusing the invalid field. Chromium reported that the control
  could not be focused.
- Partial outreach updates could reject a return to critical-only scope because
  validation used the stale compatibility flag. Malformed persisted setup flags
  and step records could incorrectly report completed setup.

**Done when:** narrow appearance saves preserve other profile values, same-view
preference writes keep submission order, presets work through real delegated
events, key drafts remain only in the DOM and survive unrelated responses, hidden
invalid fields become reachable before a write, and damaged setup progress asks
for review without modifying stored data during reads. Preserve explicit sender
adoption, legacy request keys and rejection of invalid submitted jurisdictions.

The baseline includes real Chromium reproductions and desktop/narrow screenshots,
plus deterministic asynchronous and backend probes. The existing native form
validation, explicit-save workflow, SQLite transaction and delegated-event
contracts provide the working references. Evidence lives in the Codex task's
`validation/settings-full-review/` bundle, based on the uncommitted source at
`efccc0a0f476bf83078b26694afa8fad0372047c` after ISS030.

**Resolved 2026-11-21.** Appearance-only requests preserve newer profile fields,
and a shared Settings write queue orders theme and form saves. The form renders
pending appearance when opened during a save; failed saves preserve newer choices.
Presets now reach their delegated handler and populate despite unrelated edits.
Credential revisions retain newer DOM input, include it in existing dirty guards,
and provide separate clear-entry and remove-saved-key actions with inline feedback.
Native validation opens invalid controls' ancestor sections before requesting focus.
Partial scope updates normalize the canonical mode before reason validation, and
malformed setup records require review without read-side writes.

Final local verification passed 152 backend tests (the complete Settings suite and
affected setup, sender-backup, jurisdiction, request-model and HTTP-contract
callers), the complete portable frontend runner and the expanded setup browser
group. The browser demonstrated preset updates, no writes for hidden invalid
fields, focus recovery, preservation of a newer office during theme changes,
newer key entry retention and declined-navigation protection. NVD writes in that
browser scenario were intercepted with synthetic responses; no native credential
was saved. Desktop and 390-pixel-wide screenshots are retained. An initial browser
run passed those interactions but failed its final screenshot step by trying to
click an offscreen, closed navigation control; the corrected harness uses the
navigation's expanded state and waits for its closed position.

Ruff, Prettier, frontend syntax, dependency integrity, release identity and the
regenerated program map passed. Exact commands, before/after failures, tested
source hashes and a scoped diff are in the evidence bundle. Source remains
uncommitted on `codex/settings-reliability-20261121`; unrelated concurrent module
work is not certified by these checks. No full application backend run or native
release acceptance is claimed.

## ISS040 Reviewed software update identity

A delayed initial status request could replace
an active update check with idle state and stop polling. A rejected poll from a
disposed view could replace a newly loaded ready state with failed state.
Separately, install confirmation carried no release identity: another view could
prepare a different installer after review, and the original confirmation would
launch that different candidate. A synthetic transport and launcher spy reproduced
the mismatch without network traffic or executing an installer.

**Done when:** obsolete responses cannot replace current update state or polling,
and installation checks the reviewed version, channel and installer SHA-256 under
the update lock before reserving the workspace. A changed candidate must require
another review and must not launch or reserve. Preserve all existing release,
checksum, busy-workspace and installer-readiness gates.

The status projection adds `installer_sha256`; install requests require
`{version, channel, installer_sha256}`. The browser captures these values when
displaying the review and sends that captured identity on confirmation. Missing
review bodies are rejected with 422; changed candidates are rejected with 409.
This deliberately retires unbound install requests; cached older clients must
reload to review the exact candidate. Evidence is retained alongside ISS039.

**Resolved 2026-11-21.** Request ordering and view-generation checks preserve the
newest status, polling and failures. Review identity is captured at dialog display
and checked under the service lock before reservation. Synthetic regressions
confirm that changing version, channel or installer bytes after review cannot
reserve or launch, and a fresh review permits the verified handoff. The initial
race and mismatched-candidate probes, independent review and the final complete
Settings suite are included in the verification retained under ISS039. This tests
the admission protocol with controlled transport/launcher doubles; native Windows
installation remains part of ISS014.

## ISS041 Supported display timezones

**Deferred 2026-11-21.** Settings offers a free-text IANA timezone, but a Windows
runtime without an IANA database accepts only the seven documented fallback
zones. A valid `Europe/London` selection is rejected in that environment. Guided
setup already offers the fallback choices; the free-text Settings control does
not explain the platform difference.

Choose a shared advertised supported-zone contract before expanding this UI.
Either expose the server's actual supported choices and preserve existing saved
zones, or deliberately package maintained timezone data and validate its release
and upgrade behavior. Avoid an unrelated dependency-lock change in the current
interaction repair. **Done when:** both settings views offer choices the installed
runtime accepts and invalid choices provide actionable feedback, including tests
with and without system timezone data. Stored event instants remain UTC.

## ISS042 Setup completion review consistency

**Deferred 2026-11-21.** Automation review validates the schedule at the moment
the step is saved, but completion does not compare its recorded manual/configured
mode with the current schedule. A later schedule change can leave a completed
record describing an earlier choice. The ordinary wizard saves and reviews the
schedule sequentially, so this requires an overlapping view or direct API caller.

Define whether completion should reject a stale review or require the user to
review a refreshed summary, then cover the schedule/profile consistency boundary.
**Done when:** changing automation after its review cannot silently complete a
contradictory setup record, and recovery preserves saved profile and schedule data.
Reopening an already-completed setup currently remains a review session; changing
that resume policy is a separate product decision, not part of corrupted-record
recovery in ISS039.

## ISS057 Recognize configured keys in onboarding

Onboarding showed blank, required credential forms even when Shadowserver and
NVD reported available keys. This made configured services look unfinished.

**Done when:** each detected key shows completed credential setup, only missing
keys prompt for entry, and both detected keys complete a missing connections
step. Live Shadowserver connection testing remains explicit; detection must not
overwrite an existing manual choice or discard an unfinished key for the other
service. Secret values remain outside application state and browser storage.

The change consumes existing credential status APIs and the existing setup
progress endpoint. No credential storage or backend schema changes are needed.
The original failing regression and scoped verification are retained in
`validation/onboarding-detected-keys` under the local Codex task workspace.

**Resolved 2026-11-22.** Detected credentials now replace entry forms with
completed cards. Missing connection progress is recorded when both APIs are
configured during onboarding. Merely reviewing an established workspace does
not start mandatory onboarding. Shadowserver retains Test connection and points
to Data → API for credential management; NVD points to Settings.

The original regression fails against the saved baseline and passes with this
change. Coverage includes every key-presence combination, configured without a
live connection, existing manual choices, optional review of established
workspaces, and preserving the other provider's unsaved key. Final verification
passed all portable frontend suites, 17 onboarding/backend integration tests,
the setup browser group, scoped Prettier, frontend syntax and the regenerated
program-map check. Desktop and 390-pixel browser captures show the completed
cards; browser checks recorded no page errors or external requests. Credential
status was synthetic; this is not native credential-manager acceptance.

## Full module review

The November 21 review covered profile/jurisdiction persistence, sender snapshots,
guided setup, agency presets, appearance, form validation and dirty state, NVD and
Shadowserver credential boundaries, schedule summaries, data/recovery adapters,
update discovery/download/review/handoff and the delegated UI lifecycle. Desktop
and 390-pixel-wide browser views were inspected with synthetic records.

The highest-value changes are the concrete save, feedback and update-review
repairs above. Sender adoption/certified-output protections, delegated service
ownership, release source restrictions and checksum verification remain sound in
the inspected scope. This is not a certification of unexercised native installer,
Task Scheduler or credential-manager behavior; ISS014 owns that acceptance.
Cross-window editing of the same profile field still uses the last successful
save. Optimistic conflict detection would be a separate feature with an explicit
resolution UI, not a claim made by the narrow-save repair.

## Shared work affecting Settings

- [ISS003 Shared test fixtures](../../../docs/ISSUES.md#iss003-shared-test-fixtures)
- [ISS004 Workspace facades and models](../../workspace/docs/ISSUES.md#iss004-workspace-facades-and-models), including settings-update request validation.
- [ISS008 Browser suite coverage](../../../docs/ISSUES.md#iss008-browser-suite-coverage)
- [ISS009 Explicit resource encoding](../../../docs/ISSUES.md#iss009-explicit-resource-encoding)
- [ISS014 Current version Windows acceptance](../../../docs/ISSUES.md#iss014-current-version-windows-acceptance), including guided setup and update handoff.

Status and completion evidence for shared items stay at their linked home.
The [software-update reference](SOFTWARE_UPDATES.md) owns distribution procedures
and the dated source-availability observation.
