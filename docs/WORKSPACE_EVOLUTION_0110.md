# Workspace Evolution — 0.11.0 implementation record

The operator authorized completing the outstanding 0.10.1 audit upgrades and creating
one cohesive next build. This record closes that scope. Final automated results are in `VALIDATION.md`;
exact-version native workstation acceptance remains outstanding.

## Upgrade scope

| Area | Required outcome | Status |
|---|---|---|
| Qualification provenance | Exact finding–observation admission events; separate reported, approved and legacy-unknown history; conservative schema migration | Complete |
| Relational integrity | Composite case/section ownership constraints, validated server-owned JSON, preflight and atomic rollback | Complete |
| Evidence registry | Typed immutable captures/revisions separate from disposable lookup projections; legacy identity preserved | Complete |
| Certified artifact identity | Stored manifest identity/digest and unique paths; original identity immutable across merges | Complete |
| Planner maintenance | Bounded statistics refresh after meaningful growth/migration, outside evidence transactions | Complete |
| Workspace priority queue | Bulk contact/eligible-case reads with exact priority/hold semantics | Complete |
| Observatory scale | Direct detail reads, analytical revision invalidation, incremental summaries and reconciliation | Complete |
| Current source lookup | Indexed current-bank prefix selection with unchanged key semantics | Complete |
| Health and recovery | Read-only unified health/storage view and recovery before ordinary startup | Complete |
| Safe maintenance | Dry-run reclaim estimates, revision-checked disposable-only cleanup and controlled compaction | Complete |
| Finding correction | Explicit reasoned reactivation; reimports never silently undo suppression | Complete |
| Ownership transfer | Effective association episodes, immutable observed ownership, separate new-owner work; no entity merge | Complete |
| Report storage | Versioned resource sharing for newly generated packages; all old certified bytes preserved | Complete |
| Recipient edition | Explicit compact edition with practical first action, concise findings and full retained evidence | Complete |
| Integration | Migration/restore/restart, simulated workdays, report readthrough, security/boundary checks and full regression | Complete |
| Distribution | Source/installer/evidence; extraction and hash checks recorded separately with the delivered build | Packaging verification recorded separately |

The current release remains a candidate until exact-version native Windows
acceptance. Existing full-workspace upgrade restore points remain in use. No
retention period is invented, and no immutable evidence or historical report is
rewritten to make a new projection appear complete. The protected approved template
module remains unchanged; new presentation behavior is versioned separately.

## Changes that matter in daily work

The same entity, case, review and notification workflow remains in place. The map
still uses one marker per entity and prefers a saved city/state, then the most
recent associated report location in the selected scope. A transfer now separates
current asset navigation from the business recorded on historical observations;
old measurements cannot supply a new owner’s location or risk.

New qualification history records the exact condition, observation and source
that was approved. Historical aggregate qualification and case disposition stay
visible when the exact older source cannot be proven; the UI labels that
provenance unavailable rather than declaring it approved or rejected.

Ownership transfer and dismissed-finding restoration each show an explicit impact
review, require a reason, and reject stale submissions. Transfer is effective on
confirmation. Previously closed work remains with the original business. Older or
undated incoming evidence requires ownership review, including newly seen children
of a transferred domain.

Settings adds a background health check, storage totals, analytical consistency
checks, cleanup estimates and an explicit rebuild of disposable counters. Offline
recovery can inspect a damaged/future-schema workspace without normal startup.
Only expired lookup pointers are cleanup candidates; evidence and historical
reports are retained. Recovery and compaction preserve verified checkpoints.

## Report and performance comparisons

| Scenario | Previous | This build |
|---|---:|---:|
| Single-CVE recipient report | Full: 10 pages | Compact: 8 pages |
| Six-CVE recipient report | Full: 13 pages | Compact: 9 pages |
| EOL recipient report | Full: 9 pages | Compact: 7 pages |
| New full package size | Baseline | 51–64% smaller |
| Compact package with separate complete report | Baseline | 43–58% smaller |
| Workspace priority queue: 1,000 active cases | 7,014 statements | 33 statements; identical result |
| Workspace priority queue: 5,000 cases, 100 active | 6.372 million VM steps | 299,000 VM steps; identical result |
| Direct observation detail | Previously grew with all history | 7,000 VM steps at both 10,000 and 50,000 observations |

Full remains the default recipient edition. Compact is explicit and keeps a
separate complete report, reviewed source models, citations and evidence in its
internal package. All twelve PDF/DOCX matrix specimens had matching page counts in
LibreOffice; full-edition PDF text matched the prior specimens. The protected
approved template and existing certified bytes are unchanged.

## Integration defects found and corrected

- SQLite replacement writes could bypass delete-only immutability triggers.
  Duplicate insert guards now protect the new immutable ledgers and identities.
- Same-owner attribution refresh needed to update its historical association;
  a transfer must leave the new owner’s proof unset. Separate trigger conditions
  enforce these different operations.
- Newly seen subdomains with pre-transfer or undated evidence could inherit the
  new owner and clear the review requirement on replay. Historical ownership
  resolution and a durable review basis close that path.
- Interrupted certification recovery needed the same current-readiness and
  certifying-operator checks as normal publication. A stale orphan package stays
  recorded and inspectable without advancing the current case.
- Report rendering held the workspace writer lock. Rendering now runs outside
  that lock; publication rechecks the case version, review identities, evidence
  readiness and operator inside a writer transaction.
- Inherited root-domain ownership lookup scanned unrelated assets. Canonical
  asset-key lookups now use the existing unique index, with fixed work at both
  1,000 and 10,000 unrelated records.
- Website capture jobs could announce failure or cancellation before temporary
  files were removed. Terminal status now publishes after cleanup, keeping
  workspace maintenance blocked while the job still has work to finish.

## Database assessment

SQLite remains appropriate for this local, single-workstation application. The
upgrade strengthens retained evidence and ownership, adds bounded planner
maintenance and rebuildable analytical data, and keeps the existing supported
backup/restore protocol. No server database, distributed service or arbitrary
retention policy is introduced.

The release migration is 16 → 17 → 18 → 19 → 20. Failed preflight rolls back the
entire upgrade and preserves a pre-upgrade SQLite backup. Tested schema 16 data
retained all sampled source/case/review/report rows and all 90 protected files;
upgrade/export/restore compared 57 application tables exactly. Final validation
records in `VALIDATION.md` identify the tested source and results.

Planner work uses SQLite’s recommended `PRAGMA optimize` mechanism with explicit
time and analysis bounds. Recovery checkpoints use SQLite-consistent backups.
Technical references: [SQLite ANALYZE](https://www.sqlite.org/lang_analyze.html),
[SQLite backup](https://www.sqlite.org/backup.html), and
[SQLite VACUUM](https://www.sqlite.org/lang_vacuum.html).

## Remaining practical limits

- The first complete Observatory graph at 50,000 synthetic observations took 20.17 s
  on the shared test host; warm views took 35–39 ms. Full cold graph construction
  remains linear in retained events. A lazy/paged graph representation is a
  separate future architecture change, not a correctness fix disguised by
  silently dropping evidence.
- Native Windows installation, Microsoft Word layout, workstation scaling,
  browser interaction and native security-provider acceptance remain unverified
  for this exact build. The existing Windows baseline is 0.9.96. This build stays
  a release candidate and the installer is unsigned.
- The runtime intercepted local HTTP attempts; the fresh analyst day therefore
  uses authenticated ASGI requests against the app. It verifies application
  behavior, persistence and reports, and does not claim browser or native desktop
  acceptance. External providers and all outreach outcomes are synthetic.
