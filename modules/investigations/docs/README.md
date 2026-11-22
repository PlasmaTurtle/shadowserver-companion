# Investigations

Investigations owns cases, drafts, scoped report observations, evidence, section
review, notification preparation, document composition, certification and
retained report packages. This guide maps maintenance work to those contracts.

[Architecture](../../../docs/ARCHITECTURE.md) · [Investigations issues](ISSUES.md) ·
[Analyst workflow](../../../docs/USER_GUIDE.md)

## Start here

| Maintenance area | Start here |
| --- | --- |
| Case lifecycle and command transactions | [cases.py](../components/cases.py), [services/](../components/services) |
| Certification and interrupted publication | [certification.py](../components/services/certification.py), [recovery.py](../components/services/recovery.py), [report_publication.py](../components/repositories/report_publication.py) |
| Case, review, evidence and report request validation | [api_models.py](../components/api_models.py) |
| Review policy, projections and guards | [reviews/](../components/reviews) and [review command ownership](#review-command-ownership) |
| Render jobs and cancellation | [report_operations.py](../components/report_operations.py) |
| Frozen inputs and document output | [report_snapshot.py](../components/report_snapshot.py), [report_renderers.py](../components/report_renderers.py) |
| Website capture retention, adoption and jobs | [website_evidence.py](../components/website_evidence.py), [website_jobs.py](../components/website_jobs.py); reusable engine in [Tools](../../tools/docs/README.md) |
| Case and evidence-registry schema | [databases/](../databases/) |
| Report editor and saved outreach presentation | [editor.js](../static/editor.js), [outreach_preparation.js](../static/outreach_preparation.js) |
| Certified package list and case workflow presentation | [workflow.js](../static/workflow.js) |
| Synthetic report previews and review utilities | [tools/](../tools) |

Reusable report-family and finding wording/citations live in
[Library resources](../../library/resources/). Investigations keeps exact source
selection, case pinning and report layout. The offline
[export_explainer_templates.py](../tools/export_explainer_templates.py) command
renders the static report-family bank using the production Information renderer:

```text
python modules/investigations/tools/export_explainer_templates.py output.pdf --qa layout.json
```

The preview uses the current application name and an explicit sample footer;
it has no case or agency profile and does not export the editable Library bank.

## Boundary

Investigations explicitly adopts Entities, Attribution and Library evidence into
case snapshots. It owns report wording and the Attribution exhibit in a report;
Attribution owns identity-matching decisions. Shared font and geometry utilities
belong to UI.

Attribution exhibits and observation-scope checks use Tools' shared mapped-IP
comparison. Investigations retains its own nonpublic-address eligibility and
saved-evidence interpretation; this comparison never rewrites frozen inputs.

Preserve approved wording, frozen artifact bytes, revision guards, worker inputs
and staged publication/recovery order. `components/approved_template.py` must
retain its approved bytes. Orchestration, persistence and rendering have distinct
roles even when they operate on the same case.

`package_files.py` is the single manifest reader for registry, inventory, recovery
and migration. It owns the `manifest.json` name and 20 MiB metadata limit, reuses
Aegis strict object decoding, and returns original bytes alongside the decoded
object. Duplicate members, nonfinite numbers, invalid Unicode and excessive
nesting have the same interpretation across readers. Valid legacy metadata and
unrecognized fields remain intact; reading never rewrites a retained package.
The [Tools filesystem functions](../../tools/components/filesystem.py) own generic
contained paths, optional read limits and SHA-256 checks. Required file inventories,
identity binding, export selection and the operation-scoped verification cache
remain Investigations responsibilities.

Request models live in `components/api_models.py`, independently of application
composition. Routes and development consumers import them directly. Preserve
field validation and serialized request schemas when changing these contracts.

`workflow.js::install(ctx)` registers `reportsPage` alongside case workflow actions.
Investigations owns the certified package list and download presentation; Workspace
owns the dashboard and priority-queue API, including its historical `/api/today`
alias. The ownership consolidation is tracked in
[Workspace ISS029](../../workspace/docs/ISSUES.md#iss029-workspace-file-ownership-and-consolidation).

`ReportOperations.run` supplies report cancellation/deadline checks through the
[UI rendering-control interface](../../ui/docs/README.md#rendering-control).
Investigations owns the operation state and publication policy; UI invokes the
supplied checkpoint without importing the report manager. Child-renderer timeout
and termination remain the responsibility of `report_execution.py` in the parent.
Installed report workers also use Workspace's
[`installed_child_options`](../../workspace/docs/README.md#installed-process-lifetime)
to inherit the running guard before Python loads. This prevents an early parent
exit from opening an upgrade window; the existing parent-death watcher still
controls worker termination. Source-checkout subprocess behavior is unchanged.

## Supporting folders

Use the [shared folder definitions](../../../docs/ARCHITECTURE.md#find-the-owner)
for placement. `databases/` owns case and evidence-registry migrations; it does not
hold working case databases. Saved outreach presentation lives in `static/`
alongside the rest of the case workflow, and Entities supplies its contact context.

## Verification

Run checks from a configured source checkout, following
[Development](../../../docs/DEVELOPMENT.md#working-in-a-module). Start with the
affected tests; the complete module suite is:

```text
python -m pytest -q modules/investigations/tests
```

Use `test_website_capture_0985.py` and
`test_website_capture_navigation_contract.py` for case jobs and evidence attachment;
use `test_report_operations_080.py` and `test_report_operations_095.py` for render
operations, and `test_report_recovery_parity_0110.py` for recovery. These files
live in `modules/investigations/tests/`. Pure browser/tool regressions and their
fixtures live in [Tools](../../tools/docs/README.md#verification).

Use [project verification](../../../docs/DEVELOPMENT.md#verification) for
frontend, cross-module and browser checks. Layout changes also require relevant
synthetic PDF/DOCX previews and the applicable native Word acceptance checks.

The routine browser groups `investigations` and `sources` cover section freezes,
contact workflow and local evidence adoption. Fixtures exclude nonpublic rows
through the real scope-review API rather than weakening recipient-report policy.
The focused `workflow` group and manual evidence-reader/package checks retain
their setup in `python tools/verify.py --list-browser`; use that single catalog
alongside the [registration rules](../../../docs/DEVELOPMENT.md#working-in-a-module).

## Website loading and capture

The [qualified-lead screenshot lifecycle](../../accretion/docs/PIPELINE.md#screenshots)
captures during Qualify, displays a Leads thumbnail and adopts that same evidence
into the report. Every report must include a relevant retained screenshot;
functioning login/admin captures qualify. Cross-module implementation and verification
are tracked in [ISS027](../../accretion/docs/ISSUES.md#iss027-qualify-decisions-and-workflow).

[`website_evidence.py`](../components/website_evidence.py) owns the pre-case artifact:
`retain(store, png, metadata, root_domain=...)` stores the original, safe PNG preview
and capture provenance before an entity exists. `get` and `preview` verify all
three retained files against their hashes. `bind` associates an admitted capture
with an entity inside Associate's transaction; `projection` supplies the verified
working URL and screenshot endpoint to Leads and Entities. A diagnostic or unrelated
destination cannot become the entity's qualifying website.

Case creation and scope extension call `adopt_for_case`. Adoption references the
same original and preview, copying only immutable metadata under the evidence ID
expected by the established report machinery. It never invokes a browser. A new
capture gets a new ID and paths; existing case evidence and frozen report packages
keep their original revision. Workspace backup includes the evidence directory and
verifies retained captures even when they have not yet been adopted by a case.
Workspace health uses that same integrity check before compaction; cache cleanup
and database compaction leave retained images intact.
Entity merges transfer the capture's display/adoption association while keeping
its bytes, source provenance and case revisions intact.

`export_references(store, evidence)` exposes the selected case evidence revision's
capture ID, requested/loaded URLs, time, outcome and original digest without storage
paths. It never substitutes the entity's latest capture. Manual screenshots retain
their stated source URL and evidence identity without invented browser observations.

Report readiness and Attribution section validation require a relevant included
website image with valid original, preview and retained capture metadata hashes.
Required website images render in the report's main Attribution content even when
the optional technical appendix is disabled.

The reusable browser engine lives in [Tools](../../tools/docs/README.md#website-loading-and-capture).
Investigations owns [website_jobs.py](../components/website_jobs.py), the
[capture controls](../static/website_capture.js), case routes and evidence attachment.
The job service calls the public `modules.tools.components.website_capture`
interface; it does not implement browser networking or page readiness.

The selected hostname must come from the notification. The adapter starts the
tool with that reported URL, preserves it as the attachment identity, and retains
the final destination, redirects and fallback provenance returned by the tool.
It rechecks case version and section editability before committing the validated,
hashed PNG. Functioning related login pages are included by default. Partial,
challenge and unrelated captures remain excluded. Completion must not overwrite unsaved narrative or attach
to a case that became frozen or was cancelled.

Use the [Tools verification guide](../../tools/docs/README.md#verification) for
browser loading and native output checks, and
[Tools ISS020](../../tools/docs/ISSUES.md#iss020-reported-host-loading-and-redirects)
for capture repair and ownership history. Static contact acquisition remains in
Entities, and existing evidence/provenance formats remain unchanged.

## Evidence retention and transport

Certified snapshots and source evidence remain byte-preserved. Re-encoded screenshot
previews are presentation artifacts with separate hashes, checked before viewing,
certification and backup restoration. Legacy evidence without a recorded preview
hash retains its original-byte and certified-package checks. New contact/provider
retention follows [Input validation](../../../docs/INPUT_VALIDATION.md); historical
certified packages are not rewritten to apply the current retention policy.

For older report ZIPs, `package_integrity.py` gives screenshot originals a `.bin`
suffix in the delivered transport. `certified-manifest.json` preserves the original
manifest bytes; `export-manifest.json` records delivered hashes and maps original
names to transport-safe names. The snapshot retains its original names. Use that
mapping to verify certified hashes. This download is not a workspace restore
archive; [backup and recovery](../../workspace/docs/DATA_MANAGEMENT.md) owns restoration.

Report claims use their selected captured source revisions. Missing optional scores
remain unavailable; an explicitly referenced revision that is absent or inconsistent
requires review before certification. A failed refresh must not retimestamp a prior
successful response or replace the record selected for a certified notification.

## Maintenance and tracking

Follow the [maintenance workflow](../../../docs/DEVELOPMENT.md#maintenance-workflow).
Keep issue status and completion evidence in [Investigations issues](ISSUES.md),
with links to shared rendering and persistence work owned elsewhere. Update
current contracts here; preserve historical report wording and review records.

## Report requirements

TLP:AMBER

The original 0.7.0 implementation contract is preserved in the
[historical report requirements](../../../docs/history/design/REPORT_REQUIREMENTS_070.md).
It records the decisions and baseline for that release; it is not the current
release checklist.

For current report preparation, review and certification, use the
[User Guide](../../../docs/USER_GUIDE.md). For release evidence and remaining acceptance
steps, use the [validation records](../../../docs/history/README.md#validation-records) and
[Windows acceptance](../../../docs/WINDOWS_ACCEPTANCE.md).

The archived contract retains its TLP:AMBER handling instructions and source
restrictions. See the [documentation history](../../../docs/history/README.md) for
related release records and reviews.

## Report layout references

[Report layout review record](REPORT_LAYOUT_REVIEWS.md) preserves the Introduction,
Vulnerabilities, Attribution and Information revision contracts and their
synthetic preview commands. Its historical review status does not establish the
current release's defaults or acceptance.

## Review command ownership

Section commands live in `modules/investigations/components/services/reviews.py`; projections/freeze guards
in `modules/investigations/components/reviews/queries.py`; deterministic fingerprints in `reviews/policy.py`;
and append-only writes in `repositories/reviews.py`. Lower-level code must not
import the compatibility `section_validation` facade. Repositories never commit
review writes: the command service owns the connection and transaction.

## Publication state and recovery

Certification and recovery share the guarded case/lead transition in
`components/repositories/report_publication.py`. It uses the service's SQLite
connection and never opens or commits a transaction. A successful case transition
sets the related lead to completed, clears its legacy observation counter and
updates both timestamps together. Visible pending findings continue to come from
the Leads scope projection; the transition does not delete or adopt observations.

The services retain review, readiness, operator and package-integrity checks,
report/artifact registration, audit events and filesystem publication order.
Recovery activates only a matching editable case with the saved draft revision
and, for schema 5, the saved case version. If activation is stale, the intact
package remains available as history without changing the case or lead. Already
registered reports are not reconciled retroactively because later work may have
changed their entity's status.

`test_report_recovery_parity_0110.py` covers actual interruption, restart and
observable lead/dashboard state; repository contract checks cover conditional
activation and transaction rollback. Keep those checks with any change to the
publication transition. [ISS019](ISSUES.md#iss019-interrupted-certification-state)
retains the demonstrated defect and completion evidence.

## Deliberate separations

The versioned `notification_narrative*` files preserve wording selected by saved
draft revisions. Similar helper bodies in those historical generators are not
independent current implementations to merge. Model, layout and PDF/DOCX renderer
files also serve different contracts; keep their approved output and revision
boundaries intact when refactoring.
