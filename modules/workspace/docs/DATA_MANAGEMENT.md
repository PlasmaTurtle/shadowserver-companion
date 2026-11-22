# Manage workspace data

This operational runbook covers backup, replacement, health checks and offline
recovery for an existing workspace. For implementation ownership and change
verification, use the [Workspace maintenance guide](README.md); track maintenance
work in [Workspace issues](ISSUES.md).

## Backup import and reset

Open **Settings → Backup & recovery** or **Workspace health & storage**.

- **Export data** downloads a ZIP containing snapshots of the workspace, Attribution and Dark Matter databases when present, original reports, evidence, completed notification and closing packages, and inbox files. The archive records SHA-256 hashes. Rebuildable reference feeds, exports and older migration backups are excluded.
- **Import data** replaces the current workspace with a Companion export. Select the ZIP and type **IMPORT**. The app checks archive paths, database integrity and schema compatibility, original-file hashes, report packages, attribution evidence, and captured contact-discovery responses before staging the change. Existing backup ZIPs without the new top-level manifest are accepted if their database and referenced artifacts pass validation.
- **Delete all data** creates a clean workspace with default settings. Type **DELETE** to confirm. This removes the entire working data folder, including originals, evidence, reports, inbox files, saved exports, and old backups.

Export first if you need to keep the current records. Finish report intake, attribution, source lookups and contact discovery before managing data. Contact candidates, review decisions and hashed source responses travel with the workspace backup.

Import and deletion are staged, not applied while the app is using its databases. **Close and reopen the app to apply.** Close its console window as well as the browser tab. Until then, the app pauses changes; Settings offers **Cancel staged change** to retain the current data. Invalid imports leave the current workspace untouched.

On the next launch, the app checks the staged files again, moves the old workspace aside, installs the replacement, verifies it, and only then removes the old files. A failed replacement is rolled back; an interrupted switch is recovered before opening any database or starting a worker. Browser sessions from the previous launch do not carry over.

The installer also offers **Retain existing data** (selected by default) or **Delete existing data and start fresh** when working records are present. Starting fresh requires a separate confirmation and clears pending data changes. Unattended installation retains data. Demo records and application logs are separate from working records. Uninstall still retains data.

The installed app writes new logs to the sibling `data-logs` folder (`data-demo-logs` for the demo). Older `data/logs` files remain part of the old workspace until an explicit import or deletion replaces it. Process locks and current log handles stay outside the folder during replacement so the operation can run on Windows.

Use one app process per workspace on a local disk. Import limits are 2 GB compressed, 8 GB expanded, and 100,000 archive members. The app rejects links, junctions, unsafe or duplicate paths, and unsupported newer schemas.

## Installation and retained identity

The installed program uses `%LOCALAPPDATA%\Programs\ShadowserverCompanionDarkMatter`;
working records use `%LOCALAPPDATA%\ShadowserverCompanionDarkMatter\data`.
These legacy names preserve the existing workspace and credential identity.
Separate historical Companion and Chaos installations are not searched, merged,
or copied automatically. Use the explicit backup and recovery procedures below.

Startup applies the supported migrations to older workspaces; guided setup progress
remains in saved settings. Do not open an upgraded workspace with an older app.


## Health and storage

Select **Check workspace**. A background job shows its current phase and can be cancelled. Settings preferences remain editable; checking does not migrate databases, repair records, refresh feeds or change retained evidence. It checks:

- Schema compatibility, SQLite integrity, foreign keys, business/case ownership and admission history.
- Captured evidence hashes, attribution and contact provenance, immutable revision registries, report and closing-package identities and file hashes.
- Disposable analytical counters against their canonical source records.
- NVD, EPSS and KEV freshness, individual database and WAL sizes, managed file storage, available disk space and the last verified export.

Each database uses its own committed read snapshot. A damaged or newer reference database is reported independently so the other results remain visible. Optional databases that have never been installed are shown as **absent**. Reference feeds live beside the workspace in `<workspace>-reference/nvd`; they are rebuildable and are not included in workspace exports. Attribution and Dark Matter databases live inside the workspace and are included when present.

Large checks have bounded SQL, row and time budgets. A cancelled or incomplete check is not a passing result; a verified export runs the complete staged restore validator. **Export diagnostic summary** still excludes source content, credentials, contact values and logs.

Select **Review safe cleanup** to see the exact count and estimated row payload of expired attribution lookup pointers. Type **CLEAN** to apply that reviewed plan. The app rechecks it under a database write lock and rejects a changed plan. This removes only expired reuse pointers: captured responses, result history, immutable revisions, case/report records and files remain retained. The estimate is not a promise of immediate physical disk savings; deleted rows make SQLite pages reusable. There is no automatic evidence-age retention or deletion policy.

If health finds analytical counters inconsistent, **Rebuild analytical counters** recreates only the disposable counters from saved observations, ownership and admission decisions. Type **REBUILD** to confirm. The source records and historical decisions remain unchanged, and the rebuilt counters must reconcile before the transaction commits.

## Recovery before the app can start

Offline recovery does not initialize the current workspace through normal application startup. It can inspect corrupt or newer databases. Restore verifies a selected backup in a separate folder first, then preserves the entire previous workspace before installing the verified replacement. This is the recovery path to use when the app cannot open; the in-app damaged-data import option does not retain the previous tree after restart.

Close the app and its console before restoring, rolling back or compacting. In Windows **Command Prompt**, the installed Eclipse commands are:

```bat
"%LOCALAPPDATA%\Programs\ShadowserverCompanionDarkMatter\runtime\python.exe" -m modules.workspace.components.workspace_recovery --data-dir "%LOCALAPPDATA%\ShadowserverCompanionDarkMatter\data" check
```

The command prints JSON with the same database, evidence, storage and feed findings. It does not make provider requests. Exit status is **0** for passing checks, **1** for reported health failures, and **2** for a blocked or failed command. For a custom workspace, replace the `--data-dir` value with its full path. Use `data-demo` only when intentionally working on the demo.

After selecting the exact backup ZIP to restore:

```bat
"%LOCALAPPDATA%\Programs\ShadowserverCompanionDarkMatter\runtime\python.exe" -m modules.workspace.components.workspace_recovery --data-dir "%LOCALAPPDATA%\ShadowserverCompanionDarkMatter\data" restore "C:\Backups\Eclipse-backup.zip" --confirm RESTORE
```

Replace the example ZIP path with your chosen export or managed restore-point ZIP. A running workspace, unsafe path, incompatible backup or failed verification blocks replacement. Successful output gives `preserved_workspace` and `recovery_record`: the old tree is retained under a sibling `data-recovery-<identifier>\preserved` folder, including damaged bytes and files outside the normal backup inventory. Recovery does not automatically delete these preserved folders. A normal install failure rolls back the original tree.

If power loss or process termination interrupts the folder switch, normal startup refuses to initialize an empty workspace. Recover the preserved original with:

```bat
"%LOCALAPPDATA%\Programs\ShadowserverCompanionDarkMatter\runtime\python.exe" -m modules.workspace.components.workspace_recovery --data-dir "%LOCALAPPDATA%\ShadowserverCompanionDarkMatter\data" rollback --confirm ROLLBACK
```

Rollback checks the interrupted operation's workspace identity, restores its preserved tree and keeps any partial replacement in `interrupted-install`. Inspect the recovery record, then repeat the restore with the selected backup when ready.

## Offline compaction

Compaction is a separate, explicit operation after health checks. It requires the app and all other SQLite readers/writers to be closed, compatible healthy workspace databases, enough temporary disk space and a successfully verified restore point. It compacts the workspace, Attribution and Dark Matter databases when present; it does not remove retained rows or files.

```bat
"%LOCALAPPDATA%\Programs\ShadowserverCompanionDarkMatter\runtime\python.exe" -m modules.workspace.components.workspace_recovery --data-dir "%LOCALAPPDATA%\ShadowserverCompanionDarkMatter\data" compact --confirm COMPACT
```

The command rejects active process or database locks. It performs a controlled WAL checkpoint and SQLite compaction with an exclusive lock, then verifies integrity. Output records the actual reduction in database file bytes and the saved restore point. The latest three automatic restore points are retained across all reasons, including upgrades, import and compaction.

For a source checkout, use its configured Python environment with the same `-m modules.workspace.components.workspace_recovery` arguments. The installed commands above use the bundled Python runtime and do not require a system Python installation.
