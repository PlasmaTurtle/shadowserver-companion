# Database audit — 0.10.1

Reviewed November 13, 2026. The audit covered entity/observation/finding semantics,
case and report ownership, migrations/recovery, transfer validation, cross-store
reference integrity, query growth and concurrency. Main workspace schema is 16;
attribution schema is 2, catalog storage 1/analytics 2 and risk storage 1. Performance
probes used Python 3.14.10 and SQLite 3.53.1 on a shared machine.

**No SQLite replacement or general schema rewrite is justified by these findings.**
Stable entities, canonical reported history, independent pinned cases and immutable
certified files are appropriate boundaries. Narrow correctness fixes were implemented.
One major model defect remains **OPEN**: condition-specific qualification is absent
from the finding–observation relationship and can create false recurrence/change
history. A healthy SQLite file and passing foreign keys do not resolve that defect.

## Method and observed condition

Completed synthetic workday/restore/upgrade databases were inspected read-only;
database SHA-256 values were unchanged by that inspection. Adversarial mutations and
fault injection used disposable copies or in-memory stores. No real workspace was
migrated, repaired or changed for the audit, and no live provider or credential was
used by the probes.

Fresh, restored, upgraded schema-16 and retained schema-15 databases passed
`integrity_check` and `foreign_key_check`. Inspected current relationships had no
cross-owned case conditions, section-validation links, contact candidates or handled
finding references. Declared report/closure artifact hashes matched. A schema 15→16
upgrade preserved case rows and **167 retained files** exactly. The final separate
HTTP-workday restore preserved five checked tables and **88 protected files** exactly.
These are results for the inspected synthetic workspaces, not certification of an
unseen production database.

After the database fixes, a separate recheck exported the current three-case
workspace and restored it fresh: **all 42 main tables and 90 protected files**
matched, SQLite integrity passed and foreign-key errors were zero. This later
checkpoint is distinct from the earlier 88-file workday snapshot; evidence is
`workflow_review/post_database_results.json`.

The model inspection found two canonical source mappings without a compact `entries`
row. Both retained their original CSV/sheet/row and canonical observation. This is
intentional frontier retirement, not evidence loss: `entries` holds compact working/
case source rows; `awareness_*` holds canonical history; imports preserve original
files. Cleanup must respect those distinct lifecycles
([`lead_frontier.py:112`](../workbench/lead_frontier.py#L112),
[`awareness_migration.py:33`](../workbench/awareness_migration.py#L33)).

## Implemented correctness fixes

| Finding and reproduction | Corrected behavior and source |
|---|---|
| A case-list read combined old case stage with newly committed KEV intelligence, a combination never committed together. | Direct list calls now own one read snapshot and pass it through both adapters. The Workspace priority queue already passes its shared snapshot. [`services/case_queries.py:24`](../workbench/services/case_queries.py#L24). |
| Case/Workspace priority-queue counts expanded JSON exclusions once per observation, producing quadratic work. | Exclusions are materialized once per selected scope and joined by case/entry; counts aggregate in one pass. No new authority table or migration. [`repositories/cases.py:429`](../workbench/repositories/cases.py#L429), [`workspace_queue.py:39`](../workbench/workspace_queue.py#L39). |
| Delivery coverage included a CVE explicitly excluded from a mixed CVE/EOL report. | Canonical and earlier-schema coverage apply the same reasoned CVE-exclusion predicate as report composition. Actual delivery events and source findings are retained. [`cve_state.py:19`](../workbench/cve_state.py#L19), [`case_conditions.py:8`](../workbench/case_conditions.py#L8), [`awareness_history.py:71`](../workbench/awareness_history.py#L71). |
| Injecting report B's intact package path into report A passed file-hash validation; a changed closure snapshot digest was also accepted. | A shared contract now binds report ID, case, original entity and revision to the row; current ownership follows recorded merges. Modern analyst-certified rows cannot bypass the contract by pointing at an identityless legacy manifest. Genuine `legacy_finalized` reports remain supported and their declared identities are checked. Closure ID/case/digest must match. [`artifact_identity.py:14`](../workbench/artifact_identity.py#L14), [`artifact_identity.py:59`](../workbench/artifact_identity.py#L59). |
| Freshly retrieving an EPSS score dated ten days earlier gave conflicting freshness in direct risk and catalog views. | Both consumers use score date and retrieval age through one policy. [`cve_catalog/risk_policy.py:29`](../workbench/cve_catalog/risk_policy.py#L29). |
| An unsupported future risk schema blocked writes but was accepted by direct and catalog-attached reads. | The shared schema gate covers reads, writes and attached queries before journaling changes. Unrelated workspace/NVD reads remain available. [`cve_catalog/risk_policy.py:21`](../workbench/cve_catalog/risk_policy.py#L21). |
| A valid-JSON mutable cache could disagree with its intact captured provider response and still pass restore validation. | EPSS/KEV/CVE Program reuse decodes verified retained bytes. Current normalized NVD/CVE summaries are checked against those bytes and existing normalizers; corrupt current summaries become cache misses and cannot serve as failed-refresh fallback. Transfer rejects divergent captured projections. [`intelligence/acquisition.py:304`](../workbench/intelligence/acquisition.py#L304), [`intelligence/acquisition.py:328`](../workbench/intelligence/acquisition.py#L328), [`workspace_data_captures.py:61`](../workbench/workspace_data_captures.py#L61). |

The package-path and cache/proof reproductions were injected logical corruption,
not observed wrong deliveries or evidence that ordinary API refresh creates those
states. Fixes protect read/publication/transfer boundaries without rewriting pinned
case snapshots or historical files. Workflow integration also validates archived-only
captures and server-owned sender/scope metadata during transfer.

The final complete regression exposed an overbroad historical-editor check: requiring
all rendered package files hid an otherwise valid certified snapshot. Historical
inspection now verifies its own bounded, strictly parsed manifest, report identity,
safe member path and mandatory snapshot digest (`repositories/artifacts.py`,
`snapshot_inventory`). Missing PDF/DOCX files still block full-package availability,
download, handoff and transfer. Snapshot inspection never authorizes those operations
or populates their verification cache. Original legacy projection tests and additional
identity/digest/path failure cases cover that distinction.

## OPEN: condition–observation admission provenance

`awareness_memberships` currently stores only `(finding_id, observation_id)`
([schema:51](../workbench/awareness_migration.py#L51)). Membership is inserted even
when that condition was not qualified ([writer:484](../workbench/awareness.py#L484)).
History subsequently checks observation-wide `o.admitted=1`
([reader:45](../workbench/awareness_history.py#L45)); recurrence evaluation uses the
same broad assumption ([settle_findings:527](../workbench/awareness.py#L527)).

The adversarial sequence is concrete:

1. A November 1 measurement, version 7.3.25, is approved for CVE-A.
2. An unqualified source assertion associates CVE-B with that same measurement.
3. A November 2 measurement, version 8.0.0, is the first approved observation for B.
4. B's first-observed value remains November 2, but its history incorrectly contains
   two observations/two days and both versions, with state `changed` instead of one
   approved observation/new.

This can overstate per-finding approved counts/versions and create false changed or
recurrence signals. Entity finding summaries and downstream material-change consumers
need review. It does **not** establish that certification accepts an unqualified CVE,
that every priority score is wrong, or that original evidence/report bytes changed.
The reproduction remains failing outside the release test paths, recorded in
`database_review/membership_reproduction.log`; it has not been represented as fixed.

The proposed focused migration must:

- Preserve membership and canonical IDs, but add explicit `admitted`, `observed`
  and `legacy_unknown` relationship states with a projection version.
- Retain append-only source assertion/qualification events linking the exact import/
  source occurrence, observation, finding, decision basis, actor, policy and evidence.
  At least one retained affirmative decision is required to admit that pair.
- Separate reported, approved and legacy-unknown counts; use approved memberships
  for approved versions and material-change classification. A physical observation
  still counts once even when it reports multiple conditions.
- Start unresolved old relationships as `legacy_unknown`. Promote only from exact
  retained qualification evidence. Current tags, dates, domain ownership, another
  CVE's approval or a successful delivery cannot substitute for that evidence.
- Keep case exclusion, dismissal, notification and closure separate from historical
  qualification. Never rewrite original imports, source hashes, case scope, actual
  delivery events or certified packages to make the new projection look complete.

This needs a numbered transactional migration, versioned writers/readers together,
staged compatibility validation and a migration report. Required tests include the
reproduction above; independent approvals on one measurement; reordered/repeated
sources; multiple IPs/services; exclusions and close; merge chains; pruned legacy
working rows; interruption/retry; unchanged artifact hashes; and bounded query growth.
The detailed proposal is retained as
`database_review/membership_admission_proposal.md`. It is design work, not schema 16.

## Query growth and capacity

Measurements are three-call medians and SQLite VM work on isolated seeded stores,
not hardware-independent latency promises. The committed count optimization has a
growth regression based on exact counts, query shape and VM work, not wall time.

| Probe | Evidence | Disposition |
|---|---|---|
| One case, 2,500 observations, half excluded | Case-list work: 28.332m→188k VM steps, 2.662s→0.021s; Workspace priority queue: 37.838m→355k, 3.578s→0.182s. | Fixed repeated exclusion scans. Tests cover 500/1,000/2,500 rows. |
| Fixed entity history in 50k observations/5k findings/100 entities | 18.016m VM steps before statistics; 13k after ANALYZE with no new index. A separate `PRAGMA optimize` probe reached the same 13k plan on SQLite 3.53.1. | Plan measured statistics maintenance after material growth/migration, outside publication/request-critical transactions. No maintenance policy was added by this audit. |
| Workspace priority queue limit=100 with 1k active entities/cases | Baseline 7,014 traced statements; seven contact-summary reads per eligible entity dominate. | Bulk contact summaries and select eligible IDs before costly projection. Do not apply LIMIT before correct ranking/hold/new-finding semantics. Count work in this baseline predates the fixed query. |
| One Observatory observation detail, 1k→50k retained observations | 75k→3.594m VM steps because global densities/membership statistics are built first. | Add direct detail queries and scoped statistics. [`eclipse.py:218`](../workbench/eclipse.py#L218). |
| Observatory cache invalidation at 10k observations | Unrelated cache-key commit changed 0.113s/zero-SQL cached access into a 3.515s/56-statement rebuild. At 50k, cold builds varied substantially, including one instrumentation-deadline interruption. | Separate analytical revisions from unrelated writes, then evaluate incremental summaries with reconciliation. No broad projection/schema change implemented. [`observatory_view.py:30`](../workbench/observatory_view.py#L30). |
| Source lookup/current bank | Primary-key lookup stayed about 0.6–1.2ms through 100k unrelated revisions. Current-bank LIKE scanned history; equivalent prefix GLOB used the existing key range. | Point lookup is sound. Prefix optimization is lower priority; preserve key/case semantics. [`intelligence_index.py:24`](../workbench/intelligence_index.py#L24). |

Existing entity/asset/source/membership indexes support suitable plans. Statistics
and query shape are stronger next steps than indiscriminate additional indexes or
an engine migration. A bounded returned payload does not by itself bound the work.

## Integrity, migration and recovery strengths

- Connections enable foreign keys and a bounded busy timeout; reads use query-only
  transactions, and writes use a process lock plus `BEGIN IMMEDIATE`
  ([`workspace.py:52`](../workbench/workspace.py#L52)). Controlled readers retained
  their old snapshot while a writer committed; concurrent writers serialized without
  a lost/partial update. The SQLite timeout does not bound waiting on the Python lock.
- Ordered upgrades reject future schemas, preserve a database backup, apply pending
  migrations atomically and check foreign keys before commit
  ([`migrations.py:414`](../workbench/migrations.py#L414)). Schema 16 adds case-owned
  outreach preparation, not a rewrite of report/source content.
- **Verified full-workspace pre-upgrade restore points already exist.** Normal
  [`create_app:100`](../workbench/api.py#L100) calls
  [`before_schema_upgrade:159`](../workbench/workspace_data.py#L159) before Store
  construction. It uses export and isolated restore verification. Store's SQLite-only
  backup is an additional lower-level safeguard; direct Store callers bypass the
  application hook. A new full-checkpoint feature is not needed.
- Automatic retention keeps the latest **three total** restore points across reasons,
  not three per reason; status and ZIP files rotate together
  ([`workspace_data.py:119`](../workbench/workspace_data.py#L119)). Separately downloaded
  exports are outside that managed pool.
- Transfer snapshots databases, inventories files, verifies hashes/source references,
  bounds archive/member sizes, rejects unsafe paths and upgrades only a staged copy
  ([`workspace_data.py:341`](../workbench/workspace_data.py#L341),
  [`export_workspace:444`](../workbench/workspace_data.py#L444)). Replacement retains
  the prior tree until the installed copy passes checks; recovery handles interrupted
  rename/journal phases. Existing reports are never regenerated during recovery.
- Public catalogs/risk feeds are separate from immutable case evidence. Explicit
  source adoption creates retained captures/revisions; selected evidence is backed
  up while replaceable reference catalogs are intentionally excluded. Attribution
  restore checks retained response bodies and superseded historical results.
- Credentials are not SQLite records: session secrets are memory-only; remembered
  secrets use workspace-keyed current-user Windows Credential Manager. Tests used
  an injected vault backend, not a native Windows login session.

A deliberately pinned reader plus 80 synthetic 100KB cache replacements retained
an 8.90MB WAL; releasing the reader allowed a truncating checkpoint to clear it.
That is expected WAL behavior, not corruption. Certification currently holds the
process writer lock across rendering. Shortening that boundary requires preserving
immutable snapshot, revision, publication and recovery guarantees.

## Further proposals, not implemented migrations

Storage growth is mainly retained artifacts in the measured two-notification
workspace: the main SQLite file was **1.98 MB**, while 73 report-package files
occupied **44.98 MB**. SVG exhibits accounted for 18.82 MB, DOCX for 11.00 MB and
JSON snapshots for 10.69 MB. Full embedded font resources recur in self-contained
exhibits (`workbench/unicode_fonts.py:59`); the current section renderer deduplicates
resources within a section, not across the whole retained package
(`workbench/exhibit_masters.py:140`). Exact duplicate whole files accounted for
only 1.16 MB, so simple file deduplication is not the whole opportunity.

These are two synthetic reports, not a capacity forecast. A future versioned
package format should measure shared resources and snapshot representation while
preserving standalone rendering, all evidence, manifest verification and old
certified bytes. Do not strip fonts or compact existing reports in place.
Measurements: `workflow_review/database_storage_measurement.json` and
`workflow_review/database_artifact_storage.json`.

1. **Condition admission/provenance first:** resolve the confirmed open history defect
   above before treating approved recurrence counts as fully condition-specific.
2. **Targeted ownership/JSON constraints:** an in-memory clone accepted case conditions
   outside case membership, cross-case/section validation references and malformed
   draft JSON. No such data existed in the inspected workspaces and no normal API
   path producing it was demonstrated. Plan composite foreign keys and appropriate
   `json_valid` checks with preflight, preserved row IDs and history, rather than
   silently deleting suspect rows. Definitions:
   [`awareness_migration.py:56`](../workbench/awareness_migration.py#L56),
   [`migrations.py:276`](../workbench/migrations.py#L276).
3. **Typed evidence registry and artifact metadata:** separate mutable lookup projections
   from historical revisions with explicit provider, identity, file/hash and references.
   Consider unique package paths, retained manifest digest and immutable certification
   identity columns. Keep variable source fields and pinned compositions in JSON;
   normalize missing states/queried relationships, not every field.
4. **Health/recovery independent of successful startup:** reuse existing Workspace
   checks, diagnostics, staged validators and restore downloads outside ordinary
   initialization. Show schema/source/package integrity, feed freshness, DB/WAL sizes
   and last verified backup. Repairs should preserve a copy and present a plan.
5. **Evidence-aware maintenance:** start with storage counts and dry-run reclaim estimates.
   Expired attribution pointers and catalog history can accumulate; a table named
   `cache` also contains immutable evidence revisions. Do not clear it indiscriminately
   or invent a records-retention period. Keep pinned/superseded evidence protected.
6. **Lifecycle corrections:** add explicit finding reactivation with reason/history.
   Consider effective-dated asset/entity association only when legitimate domain
   transfer is supported; transferring a domain between businesses is not a merge.

## Validation record and limits

Focused post-fix targets recorded: 24 query/snapshot/growth tests; 25 artifact-binding/
backup/case tests; 25 notification-coverage/workday/workflow tests; and 99 cross-store
projection/capture/intelligence/catalog/acceptance tests. The subsequent shared-policy
extraction passed 58 boundary/risk/catalog-product/recovery tests. Four existing
pre-upgrade checkpoint/rotation/failure tests passed. These targets overlap and are
not a unique-test total. Final complete-suite/build counts are maintained by the
release owner separately. Lint and whitespace checks passed for the audited changes.
The final analyst-origin/identityless-manifest guard was added after those recorded
artifact-binding counts; its targeted validation and the final whole-suite result
must be read from the release validation record rather than inferred from them.

Evidence includes `database_review/model_audit.md`,
`database_review/membership_admission_proposal.md`,
`workflow_review/db_query_audit_findings.md`,
`workflow_review/database_migration_integrity_findings.md`,
`workflow_review/database_cross_store_findings.md`, their JSON probes/reproduction
scripts, `upgrade_result.json` and `integration_results.json`. Source line references
identify the reviewed 0.10.1 tree and may move in later revisions.

No native Windows/Microsoft Word acceptance, live-provider correctness proof,
production-data forensic audit or unlimited-scale guarantee is claimed. The
condition-membership reproduction remains an explicitly open correctness finding.

— GPT-6
