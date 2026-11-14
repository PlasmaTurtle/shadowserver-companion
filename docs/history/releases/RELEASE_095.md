# Shadowserver Companion 0.9.5 · UNSTABLE

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

0.9.5 completes a substantial part of the 1.0 blueprint: compact report storage,
bounded rendering, recoverable data changes, practical contact decisions and a
daily outreach queue. The independent Shadowserver API module remains separate.
This release adds an offline receipt handoff; it does not connect a live account.

Version 0.8.0 remains the last accepted stable release. See
[VALIDATION.md](../../../VALIDATION.md) for checks actually executed and
[HOME_VALIDATION.md](../../../HOME_VALIDATION.md) for exact-build workstation acceptance.
No test result in these release notes substitutes for native Windows observation.

Terminology: the daily queue labeled **Today** in 0.9.5 is now part of
**Workspace**. This historical release note uses the current name for that same
feature.

## Delivered workflow

| Area | Behavior in 0.9.5 |
| --- | --- |
| Workspace priority queue | Due follow-ups/reconsiderations, saved severity and exploitation facts, later observations and a suggested next action; urgency stays separate from contact readiness. Workspace/map landing preference is remembered. |
| Finding history | Distinct retained sightings grouped by reported asset and CVE/tag, first/last observation, version changes and links to earlier delivered notifications. Coverage remains unknown; not seen is not remediation. |
| Outreach decisions | Active, Deferred and Do not contact with reason, operator and optional reconsideration date; Deferred requires a date. Due/material-change review never silently removes a hold or reopens a closed case. |
| Contact usability | Published-source review, practical usability and preference are distinct. Bounces and reasoned unusable decisions affect readiness and renewed research; last successful delivery is shown. No-answer is not an invalid destination. |
| Selected discovery | Explicitly select one to 25 businesses. Existing hostname constraints, bounded requests, source capture and per-entity results remain. |
| Prepare outreach | Selected route, source explanation, exact certified report, configured official verification route, editable introduction and call outline. Message edits are temporary; nothing is sent or marked delivered. |
| Stages and activity | Five consistent stages with hostname-group versus notification-case counts; delivery differs from closure without delivery. Search saved activity by text, recorded operator and action. |

## UI refinement

The final UI pass clarifies the daily workflow and keeps secondary details
available without placing them ahead of the next action:

- The Workspace priority queue prioritizes suggested actions; entity queues retain visible selection
  counts and recovery guidance. Activity keeps text search prominent and places
  exact operator/action filters in an expandable area.
- Contact discovery and usable routes appear before deeper policy/history
  details. Holds remain visible. Asset controls and business-record links retain
  their case context while background results preserve in-progress edits.
- Settings groups notification preferences, workload filters, appearance and
  data controls. It shows unsaved/saving/saved feedback, protects edits made
  while a save is in progress, and keeps destructive data actions separate.
  The header appearance choice is saved through the existing settings API.
- Dialogs have explicit titles and initial focus, with focus returned when
  closed. Editor tabs support keyboard navigation. The mobile drawer contains
  focus while open and removes hidden controls from keyboard navigation.
  Status notices are dismissible and repeated success notices are bounded.
- Responsive layouts wrap controls and long content; wide data tables keep
  their own horizontal scrolling with a visible hint. Report-section review
  states and blocked actions have clearer wording.

These changes affect frontend presentation and interaction, not Python business
rules or saved report formatting. The review used
[W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/) and the
[WAI-ARIA APG modal dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/)
as design references. No accessibility conformance is claimed. Native Windows,
screen-reader and actual browser-zoom acceptance remain pending; executed checks
and the final browser/layout review status are recorded in `VALIDATION.md`.

## Reports and execution

- Newly persisted report/review JSON uses a lossless, versioned shared-string
  envelope. Long repeated resources are stored once within that document and
  verified while decoding. `workbench.compact_json` reads both this format and
  legacy plain JSON. No external resource store is required to restore a package.
- Historical certified files remain unchanged. Package checks can be reused
  inside one read operation; bytes used for export still receive integrity checks.
- New packages omit redundant standalone exhibit variants while retaining the
  reviewed model, necessary masters/fallbacks and supporting records.
- One heavy report operation runs at a time. Rendering uses a cancellable child
  process with a deadline; phases and recent results persist across restart.
  Interrupted work is identified without assuming success or retrying publication.
- Cancellation is accepted before publication. Once saving the reviewed revision
  begins, that atomic step finishes; inspect the resulting case/report before retry.
- **Recipient package** contains the certified notification PDF and a small
  transport manifest. An already embedded appendix remains part of its PDF.
  A separately retained appendix is included only when explicitly requested.
  **Internal case record** contains the full evidence and chronology export.
- The new addressee revision says **Principal Executive / IT Director**.
  Saved old formats keep their wording until deliberate adoption. The programmatic
  narrative, established emailed row-date-plus-one rule, optional appendix,
  citations and justified paragraph text remain supported.

## Data, installation and diagnostics

Every offered export exercises the restore path on an isolated copy. Export and
restore enforce the same limits: **2 GiB compressed, 8 GiB expanded, 100,000 ZIP
members**, with a bounded manifest and free-space preflight. Each recorded report
snapshot also has a **256 MiB** read limit during restore verification. A larger unsupported
workspace stops with an explanation instead of receiving an unusable backup.

Verified restore points precede imports and schema upgrades during normal app
startup. The latest three are kept beside the workspace in `data-restore-points`
and can be downloaded in Settings. If current data is damaged, Import offers an
explicit choice to skip retaining that current copy; incoming data is always
validated. Permanent deletion removes managed points but does not delete backups
the user exported elsewhere. Backup/export and restore remain synchronous,
exclusive data operations; this release does not add a background transfer service.

Schema 9 adds case outreach decisions and structured context for new activity.
Low-level database migrations retain their database backup; the app startup path
adds the complete working-record restore point. A failed pre-upgrade backup stops
before migration. Recover with the matching application/data version; do not change
the database's schema number to force a downgrade.

Installer preflight checks installed application version and retained database
compatibility before cleanup. Working data is retained by default; fresh start is
explicit. The installer still overlays program files and has no staged activation
rollback. The application still uses its console to run and stop.

Settings adds **Check workspace** and **Export diagnostic summary**. The summary
contains build/runtime/schema, counts and health metadata; raw reports, contacts,
credentials, tokens, file paths and logs are excluded. Startup logging begins
before session/port checks. Start-menu shortcuts expose **Check installation** and
**Application logs**. Normal installed logs are in the sibling `data-logs` folder.

## Offline API handoff and intake

The downloader's public receipt and previously downloaded CSV/CSV.gz can enter
Companion through `workbench.api_import.enqueue_download(...)` or the authenticated
`POST /api/imports/api-receipt` endpoint. This is currently an integration surface,
not a live account selection screen.

| Multipart field | Meaning |
| --- | --- |
| `report` | Original downloaded CSV/CSV.gz, with its original filename. |
| `receipt` | JSON public receipt produced by the independent module; secret or unsupported fields are rejected. |
| `narrative_date_basis` | Default `unconfirmed` retains the report for research. `emailed_row_plus_one` explicitly confirms the existing emailed-report receipt policy. |

The adapter checks report identity, filename, byte count and SHA-256. Original
compressed bytes, report date, actual retrieval time and distinct acquisition
receipts are retained. Downloaded and completed intake are different states.
Replaying the same report/receipt does not create duplicate work. A receipt is
provenance, not independent authentication of Shadowserver or catalog completeness.

Ordinary uploads accept XLSX/XLSM/CSV/CSV.gz up to **50 MiB** each. Receipt handoffs
accept CSV/CSV.gz up to **256 MiB**, with **512 MiB** expanded CSV limits. HTTP-vulnerable
profiles are notification-supported; other report types remain research-only.
Unconfirmed receipt-date policy also remains research-only.

Normalized occurrence references now use immutable file content identity. Filter
reasons distinguish malformed hostnames, suffix policy and numeric-root policy;
representative excluded rows are shown. Existing jurisdiction/critical/.com/numeric
preferences are not silently changed.

## Still outside this release

- Live API account/report picker, scheduled pulls and live account acceptance.
- Native Windows installation, upgrade, endurance and actual-network acceptance;
  publisher signing remains pending and the installer is unsigned.
- Screen-reader and actual browser-zoom acceptance, and a full accessibility
  conformance audit.
- Staged installer activation/rollback, tray/status launcher and background data
  transfer jobs.
- A materialized large-workspace map index and complete queue-pagination overhaul.
- Automatic outreach/certification, broader scraping, third-party contact vendors,
  cloud synchronization and multi-user administration.

Performance measurements and final regression outcomes belong in VALIDATION.md.
Operational acceptance should measure actual handling time as well as latency,
and verify preserved historical reports after upgrade and restore.

TLP:AMBER

