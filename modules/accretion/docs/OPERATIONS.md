# Accretion operations

[Module guide](README.md) · [Pipeline contracts](PIPELINE.md) ·
[Report schemas](REPORT_SCHEMAS.md) · [Dark Matter](DARK_MATTER.md) · [Issues](ISSUES.md)

Accretion accepts original reports, runs the intake funnel, and records enough
state to resume interrupted work. Acquisition, import processing and group
qualification have separate lifecycles; a completed download is not a qualified lead.

## Entry points and retained originals

`IntakeService.enqueue(name, content)` accepts manual files;
`enqueue_stream(name, stream, max_bytes=..., acquisition=...)` handles bounded
streams and verified API receipts. `scan_inbox()` uses the same manual path.
Accepted formats are `.xlsx`, `.xlsm`, `.csv` and `.csv.gz`.

| Input boundary | Limit |
| --- | --- |
| Manual upload or inbox file | 50 MiB per file; HTTP upload accepts at most 20 files |
| API report with public download receipt | 256 MiB per report; receipt JSON at most 64 KiB |
| Expanded CSV stream | 512 MiB |
| Expanded workbook archive | 250 MiB |
| Filter traversal | 250,000 source rows |

The service streams into a temporary file, hashes and flushes it, then publishes
the original under `originals/<sha256><extension>`. An existing original is
hash-checked before reuse. The import fingerprint combines source digest with
captured policy, input format, worksheet, effective report-profile selection,
jurisdiction and local catalog revision. Uploading the same CSV and retrieving it
through the API with the same selection reuses the import, its groups and leads.
Each distinct API receipt survives, including a retrieval received while intake
is processing the original. A matching import from policy version 14 keeps
its original ID on redelivery. Re-evaluate original applies current policy.

Workbook upload, manual API retrieval and scheduled API retrieval all enter the
same Filter and qualification worker. The profile resolver uses the explicit
workspace selection first, then a row's report type. In automatic mode a verified
API receipt or recognizable filename supplies the report type for a row that
omits it. Source files with different encodings or worksheet selections retain
their own original and provenance.

The import's `config` records admission/scoring policy, acquisition provenance,
profile facts and progress. Reading an original through the HTTP API produces a
verified copy, preventing a later pathname change from altering the response.
Originals and prior finding history survive re-evaluation.

With `watch_inbox` enabled, the worker scans the workspace `inbox/` every 30
seconds. It ignores unsupported files, Excel lock files and files modified within
the last two seconds. A successful size/mtime signature suppresses repeat reads;
changing the file makes it eligible for another check.

## Import and group lifecycles

| Import status | Meaning and next action |
| --- | --- |
| `queued` | Waiting for the single intake worker |
| `running` | Filter or a later stage is executing |
| `paused` | User pause; resume with import retry |
| `needs_retry` | Processing ended with one or more deferred groups |
| `done` | No pending/deferred groups remain; attribution reviews or unsuccessful groups may still exist |
| `error` | An import/export operation failed; inspect its error and retained state before retrying |

Jobs represent domain groups within an import. Their statuses are `pending`,
`qualified`, `review`, `no_match`, `no_public_ip`, `deferred` and `dismissed`.
The persisted `qualified` state follows successful Evaluate/Associate publication;
it does not mean a report has been sent or contacts have been found. Each job
retains source payload, attempts, attribution-result reference and qualification
evidence. Leads owns later pending/assigned work and notification scope.
`groups_done` counts every non-pending group outcome; `qualified` and progress
`associated_groups` count committed qualified outcomes. They do not count sent
notifications or distinct entities after pending-lead consolidation.

Filter publishes all jobs and archive-delivery outbox events atomically. Its
`intake_progress.filter_complete` marker also covers zero-survivor imports, so a
retry does not reread a completed filter. Later processing loads one group payload
at a time and commits each guarded transition separately. See the
[pipeline](PIPELINE.md) for stage products, evidence gates and transaction ownership.

## Pause, retry, review and recovery

| Action | Preserved contract |
| --- | --- |
| Pause import | Interrupts Filter at a checkpoint; during qualification it finishes the current group and then stops. Progress cannot overwrite the paused state. |
| Shut down application | Signals browser/provider cancellation and checks before evaluation/publication; cancellation does not claim successful completion. |
| Retry import | Leaves completed filtering/jobs intact, resets only `deferred` jobs to `pending`, and queues the import. Refreshes provider timeout/retries/interval from current settings while keeping captured admission/scoring policy. |
| Retry one group | Requires its current attribution result ID. Permitted for review/no-match/deferred/no-public-IP/dismissed groups; queues its parent and requests fresh attribution. Prior attempts/evidence remain retained. |
| Re-evaluate original | Verifies retained bytes against the original SHA-256, then enqueues under current policy. It can return a duplicate if the fingerprint is unchanged. |
| Accept attribution review | Requires the current saved partial result and source index/IP. Reuses the retained website evidence, checks current finding/ownership scope, and passes through Evaluate and Associate. |
| Dismiss review | Records the analyst decision and Dark Matter disposition without publication. |

Workspace startup changes interrupted `running` imports back to `queued`. Before
new work, IntakeService reconciles eligible saved reviews and repairs outstanding
exports. A newly accepted attribution can qualify already-waiting sibling reviews
only through Attribution's reuse checks and the complete product boundary;
explicit dismissal or requested refresh is never overridden.

Association, job completion and the `exports_pending` obligation commit together.
`export_pending()` holds the established workspace writer lock while exporting and
acknowledging that obligation. Export failure leaves it available for retry or
startup repair. A completed import with no new associations or pending obligation
does not regenerate exports. Dark Matter has its own durable delivery/recovery
contract described in the [archive guide](DARK_MATTER.md).

## HTTP interface

The route adapters are [intake.py](../components/routes/intake.py) and
[shadowserver_api.py](../components/routes/shadowserver_api.py). Workspace supplies
the application/session boundary; route handlers delegate work to the component
owners. Request models are owned by Accretion or Attribution as appropriate.

| Route family | Operations |
| --- | --- |
| `/api/intake/progress`, `/api/intake/capabilities` | Progress summary, supported input limits and notification profiles |
| `/api/imports` | List imports; upload manual files |
| `/api/imports/api-receipt` | Upload report plus verified public receipt |
| `/api/imports/{id}` | Import/group summaries; `/pause`, `/retry`, `/reevaluate`, `/original` |
| `/api/inbox/scan` | Request an immediate inbox scan |
| `/api/groups/{id}`, `/api/reviews` | Saved group evidence and attribution review list |
| `/api/groups/{id}/review`, `/retry`, `/attribution.zip` | Review decision, explicit refresh, retained attribution export |
| `/api/shadowserver/*` | Account configuration, connection, catalog, import and acquisition-job cancellation |
| `/api/schedule`, `/run`, `/background` | Durable schedule configuration, requested run and Windows task registration |

Import and review lists currently return all matching records. Bounded review
summary paging is an open [ISS027](ISSUES.md#iss027-qualify-decisions-and-workflow)
follow-up; callers must not assume pagination or a resumable whole-group deadline.

## Shadowserver Reports integration

Configure credentials in the application's API connection settings, then use
**Data → API** to connect, list reports and import selected files. Live selection
and offline receipt import are implemented features. Account entitlements and
current-version live acceptance are separate from feature availability.

`APIAcquisition` owns one background operation at a time and an in-memory catalog
and recent-job list. Its statuses are `queued`, `running`, `completed`, `cancelled`,
`partial` and `failed`. Successful imports are retained on cancellation/failure;
their durable import IDs remain available even after an acquisition job expires.
Session credentials remain in memory. Remembered credentials use the Windows
Credential Manager under a workspace-specific target. Credential replacement or
removal clears old catalog selections; session-only replacement removes a saved
account so it cannot silently return next launch.

The account's subscriptions and report types define available selections.
Jurisdiction checks hide explicit other-state subscriptions while retaining
national/custom scopes with explanatory context; Filter still checks each row's
region. Listing is bounded to 31 calendar days and 100 reports per interactive
selection. Stale selections and scope changes are rechecked before import.
An incomplete listing reports its limits instead of claiming full coverage.

Application operations use a 120-second budget for connection/catalog and 300
seconds for interactive import, each capped at 100 requests and 512 MiB aggregate
response bytes. Scheduled retrieval uses 1,800 seconds, 1,000 requests and 2 GiB.
These [acquisition limits](../components/api_acquisition.py) are separate from the
per-report limit and later qualification/capture budgets. Completed imports remain
durable when a later operation exhausts its budget.

The vendored client owns signed API requests, unsigned report downloads, transport
budgets and public receipts. Credentials and usable download capabilities do not
enter browser responses or the workspace database. `api_import.py` verifies receipt
shape, filename, size, logical identity and the streamed file hash before enqueue.
Report dates and retrieval times remain provenance; report narrative dates belong
to the report builder.

### Integration status

The vendored client identifies itself as **0.1.2**. Its
[source manifest](../components/shadowserver_api/source-manifest.json) records
integrated runtime files and local patches, including CSV validation independent
of MIME labels. It is an independent integration, not an official Shadowserver SDK.
`shadowserver_reports/` contains runtime; `shadowserver_api/` holds provenance,
historical patches and baseline bytes. Preserve recorded patch headers and hashes.

Earlier 0.9.89 live authentication/discovery/download evidence and the
[standalone reference](shadowserver/REFERENCE.md) are dated records. They neither
certify current release acceptance nor imply that the application lacks live API
selection. Consult [application validation](../../../docs/history/validation/VALIDATION_0120.md)
and [Windows acceptance](../../../docs/WINDOWS_ACCEPTANCE.md) for that scope.

## Scheduling

`AcquisitionSchedule` persists configuration, cursor, current run and the latest
20 runs under settings key `scheduled_acquisition`. Defaults are disabled, local
06:00 anchor, four-hour interval, seven-day lookback, with report/reference work
selected. Enabled report schedules require a subscription and report types.
Intervals support 1–24 hours and lookback 1–30 days; missed runs coalesce.

The sequence is `retrieving → importing → complete/partial/failed`. Reference
updates belong to Library. Report acquisition requires a complete listing from
the selected subscription. With an incomplete local NVD catalog, Filter uses
the same reported-severity and available-reference rules as a manual upload.
The schedule persists queued import IDs as they arrive.
Completion waits for Accretion import outcomes, not just downloads. Successful
report intake advances its cursor even if reference refresh needs attention;
an unsuccessful overall run retries after one hour. On restart, interrupted
retrieval becomes an interrupted importing run so already-enqueued work is accounted
for before another retrieval. Saved scope is revalidated against jurisdiction.

The execution clock is the machine's local clock; UI display-timezone selection
only changes timestamp presentation. Schedule history and due instants are stored
with timezone information. Corrupt optional configuration is reported for resaving
without overwriting the stored value or blocking existing workspace records.

### Installed scheduling

`windows_schedule.py` owns current-user, least-privilege Task Scheduler integration.
Closed-app operation requires saved Windows credentials for each selected provider.
Installed tasks use the verified active immutable bootstrap with
`--scheduled --data-dir <workspace>`; scheduled mode opens no browser/server.
Workspace owns exclusive session/replacement locks. `schedule_handoff.py` requests
cooperative release to a foreground instance; it never kills the owner or deletes
its workspace lock.

Installer `prepare_upgrade`/`commit_upgrade` hooks journal, disable, verify and
update only a recognized task, preserving enabled intent and task settings.
Repair resumes the journal; uninstall removes only verified owned task state.
Existing direct Python launchers cannot acquire the bootstrap gate before runtime
load. The remaining acceptance/first-upgrade limitation belongs to
[ISS015](../../settings/docs/ISSUES.md#iss015-pre-registration-upgrade-race).

## Develop and verify

Run commands from the repository root with the
[development environment](../../../docs/DEVELOPMENT.md#windows-ide-setup) active:

```text
python -m pytest -q modules/accretion/tests
python -m pytest -q modules/accretion/tests/shadowserver_api_module
python tools/verify.py --only-browser --browser-suite api
python tools/program_map.py --check
python modules/accretion/tools/verify_accretion.py --output build/accretion-matrix.json
python -m modules.accretion.components.shadowserver_reports demo --output build/api-demo
```

The first suite includes the vendored fixtures; the second is a focused client
check. The matrix and API demo use synthetic inputs and no network; use a new demo
output directory for reproducible new/reused counts. `--list-browser` describes
browser fixtures. Native Task Scheduler and credential changes also require the
relevant Windows acceptance checks; synthetic tests do not establish them.

`python modules/accretion/tools/evaluate_sample.py --help` describes analyst-label
comparison. Its default
performs offline structural row checks; `--live` runs the full intake funnel with
website/attribution network work.
`python modules/accretion/tools/run_scheduled.py --help` describes the headless
saved-schedule runner. Keep benchmark outputs and operational workspaces
outside maintained source. Record actual commands, source hashes and limitations
in the owning issue, following the [maintenance policy](../../../docs/DEVELOPMENT.md#maintenance-workflow).
