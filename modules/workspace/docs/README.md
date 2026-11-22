# Workspace

Workspace owns application composition, current-work queues, shared persistence,
local sessions, backup/recovery, workspace health and common input security.
This guide is the entry point for maintaining those responsibilities.

[Architecture](../../../docs/ARCHITECTURE.md) · [Workspace issues](ISSUES.md) · [Changelog](CHANGELOG.md) ·
[Data management runbook](DATA_MANAGEMENT.md) ·
[Framework decisions over 50 lines](../../../docs/DEVELOPMENT.md#framework-decisions-for-work-over-50-lines)

## Start here

| Maintenance area | Start here |
| --- | --- |
| Command-line startup and server/browser lifetime | [startup.py](../components/startup.py) |
| Exclusive workspace session and pending replacement | [workspace_session.py](../components/workspace_session.py) |
| Compose application routes and services | [api.py](../components/api.py), [store.py](../components/store.py) |
| Workspace projections and health HTTP adapters | [routes/overview.py](../components/routes/overview.py), [routes/workspace_health.py](../components/routes/workspace_health.py) |
| Connection and transaction scope | [workspace.py](../components/workspace.py) |
| Coordinated migrations and seed definitions | [databases/](../databases/) |
| Current-work priorities and presentation | [workspace_queue.py](../components/workspace_queue.py), [queues.js](../static/queues.js) |
| Export, staged replacement and retained records | [workspace_data.py](../components/workspace_data.py) |
| Read-only diagnostics and offline recovery | [workspace_read.py](../components/workspace_read.py), [workspace_recovery.py](../components/workspace_recovery.py) |
| Cross-process exclusion | [workspace_lock.py](../components/workspace_lock.py) |
| Installed child-process lifetime | [installed_process.py](../helpers/installed_process.py) |
| Browser credentials and launcher instance records | [local_session.py](../components/local_session.py) |
| Startup logs and detached console streams | [runtime_logging.py](../components/runtime_logging.py) |
| Shared input security | [aegis/](../components/aegis) |
| Retained snapshot encoding and common record values | [compact_json.py](../components/compact_json.py), [primitives.py](../components/primitives.py) |

## Boundary

The application composer connects module services. Shared storage and security
helpers must not acquire feature policy merely because several modules use them.
Domain repositories and business decisions stay with their owning module.
Coordinated migrations, transaction ownership and startup recovery are contracts
to preserve when changing their callers.

Request models belong to the module that owns the operation; callers import
that owner directly. `Store.lead()` delegates to Entities' `services/queries.py`, which
reads the profile and completeness summary from one snapshot. Workspace retains
connection lifetime and application composition, not entity query policy.

`routes/overview.py` owns dashboard, search, briefing and priority-queue projections,
including the hidden `/api/today` compatibility alias. Library owns explainer routes;
Settings owns settings mutations. `api.py` explicitly registers each owner, including
Observatory, rather than relying on another feature to register it.

`static/queues.js` owns dashboard/current-work presentation and next-action links.
Investigations owns the report list, Activity owns activity presentation, Entities
owns the directory/dossier, and Accretion owns intake/progress. Attribution owns its
events; UI owns global search and shared navigation/filter submission. The shell
installs each owner's explicit interface; Workspace does not install another
feature or its handlers as a side effect.

## Retained responsibilities

### Startup and workspace sessions

Root `run.py` is the stable source command entry point. It calls
`components/startup.py::main()`, which parses the existing command-line options,
validates edition/workspace identity, requests Accretion's scheduled-work handoff,
and serves within an exclusive workspace session. Default `data` and `data-demo`
paths remain relative to the application root, independent of the current working
directory. The installed desktop launcher imports the same `main()` directly.

`components/workspace_session.py::workspace_session(data)` accepts the caller's
resolved workspace `Path` and yields no value. Its context holds the stable
parent-directory lock, probes any older workspace lock, guards interrupted
recovery, applies pending replacement, then holds the live workspace lock until
the caller exits. Replacement occurs before opening the live lock so Windows can
rename the folder. An already-owned workspace raises the existing `SystemExit`;
the locks close on normal exit and exceptions. Accretion's scheduled runner uses
this context directly and owns its job lifecycle and handoff policy.

`startup.py::serve()` owns the server, instance record and browser readiness
thread. The browser opens only after this server binds; shutdown stops the thread
and removes its instance record. The source and installed launchers keep their
existing logging, exit-status and console behavior. These are ordinary Python
imports and a [`contextmanager`](https://docs.python.org/3.14/library/contextlib.html#contextlib.contextmanager),
not a root-module service interface. The ownership change is tracked in
[ISS028](../../../docs/ISSUES.md#iss028-root-configuration-and-startup-ownership).

### Read-route boundaries

Ordinary navigation/status projections must not create cases, start provider
jobs, adopt evidence, mark a release notice seen, or change retained records.
`tests/test_read_route_contracts.py` exercises the main navigation paths with
query-only Workspace connections and compares the complete logical database and
retained evidence/report bytes. This is a scoped regression, not a claim that
every GET handler is free of side effects.

| Read path | Deliberate behavior |
| --- | --- |
| Entity directory/detail, queues, search, activity, setup/software status | Project current state; mutations and job admission use explicit commands |
| Working notification detail (`/api/leads/{id}`, `/api/cases/{id}` and callers) | Investigations may initialize missing legacy draft defaults and record newly observed stale-review history; certified snapshots remain authoritative |
| Preview PDF | Investigations records the supervised render operation and creates temporary output; it does not certify or publish a report |
| Evidence/report downloads and derived ZIPs | Verify retained inputs, create temporary export files where needed, and clean them after the response; no provider refresh is implicit |
| Local Library/Attribution store access | Existing store-open compatibility may initialize/migrate an older auxiliary schema; it must not silently replace source evidence or start acquisition |

Investigations owns `services/notification_views.py`,
`services/compatibility.py` and `reviews/queries.py`. Its
`SectionReviewQueries.describe(record_changes=False)` supplies an explicitly
read-only projection when history recording is inappropriate. Preserve that
distinction rather than suppressing review chronology to enforce a blanket GET
rule. Startup schema/recovery work is a separate lifecycle boundary.

### Persistence lifecycle

`databases/migrations.py` owns the coordinated schema sequence and delegates to
module-owned migrations. `databases/workspace_defaults.py` owns non-destructive
seed definitions. A source refactor must preserve schema versions, migration
order and seed values unless a deliberate data migration is part of the change.

`workspace.py` owns live connection/transaction scope. The separate
`workspace_read.py` supplies bounded, read-only diagnostics; `workspace_lock.py`
owns process exclusion. `workspace_data*.py` separates backup orchestration from
domain record handling. These contracts remain distinct.

Workspace serializes recovery/transfer state through `write_state_json` and uses
the [Tools filesystem functions](../../tools/components/filesystem.py) for atomic
byte publication and contained file/directory reads. Sorted JSON bytes stay owned
here; Tools owns unique temporary files, file flush/fsync, replacement and cleanup.
Backup validation and health retain their domain inventory checks and transaction
policy. They no longer import case-package internals merely to resolve a file path.

Entities' [contact validation](../../entities/docs/README.md#contact-validation)
owns contact candidate and retained-source checks. Workspace orchestrates those
checks during restore and health inspection. Health passes its existing read-only
evidence reader; validating contacts must not initialize or migrate a workspace.

Accretion's independent `dark_matter.sqlite3` is included in backup, restore,
health and compaction. Store composition initializes its API and delivers the
durable workspace outbox at startup and after commit. A failed secondary delivery
remains queued; it never changes a successful primary commit into an apparent
rollback. Feature-specific archive schema and delivery logic remain Accretion-owned.
See [ISS025](../../accretion/docs/ISSUES.md#iss025-isolate-complete-dark-matter-storage).

The health panel uses UI's selected display-timezone helper and missing-value
handling. Workspace owns checks, polling and storage policy; shared formatting
has no persistence effects. See the
[shared browser contract](../../ui/docs/README.md#shared-browser-capabilities).

### Shared input and storage contracts

`aegis/` provides strict JSON/text representation checks and native contact scanning
without workflow, database or provider imports. Domain adapters choose accepted
formats and meanings. [Input validation](../../../docs/INPUT_VALIDATION.md) owns the
callable contracts and retention rules; native website capture remains separate.
`scan_text` is the canonical text-scanning entry point. The bounded executor keeps
a stalled native call's slot until it finishes instead of creating replacement workers.

`compact_json.py` is the versioned retained-report snapshot codec. Investigations
and backup readers share its lossless string resources and legacy plain-JSON support.
It is not interchangeable with Aegis's strict external-response parser. Preserve
existing snapshot decoding and certified bytes when changing either boundary.
`primitives.py` owns the shared `now`, `uid` and `dump` representations; import it
directly instead of relying on Store to reexport unrelated helpers.

### Local sessions and runtime boundaries

`local_session.py` owns one-time launch tokens, expiring browser sessions and
workspace-bound launcher credentials. Its instance record keeps the existing JSON
and DPAPI format; [Tools atomic publication](../../tools/docs/README.md#shared-operations)
owns private temporary-file creation, flush/fsync, replacement and failure cleanup.
A failed publication leaves the previous instance record intact.

`request_limits.py` applies endpoint-specific body limits before parsing or multipart
spooling. `crypto_policy.py` checks the affected runtime/FIPS configuration at startup.
These are application admission policies, separate from reusable input decoding.
`runtime_logging.py` uses standard rotating handlers and safe detached-console
streams; launcher, desktop and scheduled entry points share its redaction and
log-location rules. See [Security](../../../SECURITY.md) for workstation trust limits
and the [data runbook](DATA_MANAGEMENT.md) for operational log locations.

### Installed process lifetime

The native installer bootstrap acquires the start/install gate and creates an
inherited running handle before loading the replaceable Python runtime. Workspace's
`installed_child_options(application_root)` carries only that handle across an
installed child launch. Investigations uses it for report workers, so parent death
before worker imports cannot open an upgrade window. The helper is a no-op for
source-checkout execution and fails closed if an installed process has no guard.
Report supervision and cancellation remain Investigations' responsibilities.
New installed Python child launch paths must preserve this lifetime contract.
See the [installer protocol](../../../tools/windows_installer/REFERENCE.md#guarded-launch-and-maintenance)
for readiness, repair and older-launcher limits.

## Verification

Run checks from a configured source checkout, following the shared
[development setup](../../../docs/DEVELOPMENT.md#windows-ide-setup). Start with
the affected tests; the complete module suite is:

```text
python -m pytest -q modules/workspace/tests
```

For data replacement, inspect `test_workspace_data_080.py` and the attribution
and captured-evidence backup tests. For diagnostics/recovery, start with
`test_workspace_health_recovery_0110.py`; for local sessions, use
`test_local_session_072.py`. These files live in `modules/workspace/tests/`.
The session checks include failed publication retaining the old credential and
removing the temporary file. Shared input checks remain in root
`tests/test_security_json_0998.py`, `test_security_text_0998.py`,
`test_security_execution_0998.py` and `test_content_scan_0998.py`; they exercise
the actual parser/provider integration with synthetic inputs.

Startup changes also need the root `test_startup_readiness_0982.py`,
`test_launcher_restart_0982.py`, `test_launcher_reliability_0996.py` and
`test_runtime_071.py` checks. Accretion's `test_scheduled_runtime_0996.py` and
`test_scheduling_0994.py` cover the shared session and foreground handoff.

Frontend registration, browser groups and full-project checks are maintained in
[Development](../../../docs/DEVELOPMENT.md#verification). Persisted-record
changes also need the compatibility check below. Native installer acceptance is
a separate [release gate](../../../docs/WINDOWS_ACCEPTANCE.md).

## Maintenance and tracking

Use the [maintenance workflow](../../../docs/DEVELOPMENT.md#maintenance-workflow)
before editing. [Workspace issues](ISSUES.md) owns the module's planned work and
completion criteria; link shared work to its owning tracker. Update this guide
when ownership or contracts change, and the [data management runbook](DATA_MANAGEMENT.md)
when operator procedures change. Keep live records outside the source tree.

## Feature names

Use **Workspace** for the current-work area, including its priority queue, in UI,
source, tests and maintained documentation. Use `workspace_queue` and
`/api/workspace/queue` for that implementation. **Today** is only a historical name
or the hidden `/api/today` compatibility alias, not a separate feature. Ordinary
date wording and other modules' names are unaffected.

## Upgrade and backup compatibility

Keep the unmodified source release being checked in a separate folder and run:

```text
python modules/workspace/tools/verify_upgrade.py --baseline PATH_TO_BASELINE_SOURCE --current . --output PATH_TO_NEW_QA_FOLDER
```

Choose a new output directory outside both source trees. Record the actual baseline
version and source state with the result. The harness creates synthetic records using
the old code, then opens them and restores their backup using the current code.
It checks case relationships, recorded history and every protected artifact byte.
The offline harness permits literal loopback socket connections for native event-loop
IPC and rejects other connection destinations; `test_upgrade_harness.py` verifies
that boundary and real Windows socket-pair startup.
This is application compatibility testing, not a Windows installer test. For a
manual comparison, export from the baseline and import the copy into a separate
Shadowserver Eclipse workspace;
never point both editions at the same working directory.
