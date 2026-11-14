# Analyst workday review — 0.10.1

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

Reviewed November 13, 2026. This review follows a synthetic analyst from opening the
application through intake, entity/map review, report certification, interrupted
outreach preparation, recorded delivery, closure, later intake and workspace restore.
It distinguishes implemented changes from open proposals.

The integrated replay made **163 authenticated local HTTP requests**, with no
unexpected status responses. Six deliberate invalid/conflicting actions returned
the expected 422/409 responses. It restarted the application at three points and
restored an exported workspace. External providers, organizations, contacts and CVE
examples were synthetic; no real messages were sent and no remediation was verified.
Production frontend modules were exercised in the portable DOM/Canvas harness.
This is not live-browser, native Windows, accessibility or Microsoft Word acceptance.

## What changed during the working day

| Analyst stage | Observation and implemented result |
|---|---|
| Open Workspace | Existing guidance was generic, rather than wholly absent. Saved blockers now name missing sources, unresolved scope, sender adoption or the next section to review and link to that section. Custom instructions still take precedence. Automatic closing guidance now opens Closing instead of Contact. |
| Start the demonstration workspace | The public-exposure gate exposed documentation-address demo seeds that could not certify. Demonstration seeds now use explicitly synthetic public-address exemplars, with no provider request or gate bypass. Their report identity states that no real exposure was assessed. |
| Import and inspect the map | Original source files and row coordinates remain retained. The existing 0.10.0 entity-map contract remains: one known entity identity, supporting asset/finding counts, and observation provenance. The final replay exercised the map before, during and after the workday. |
| Resolve location | Complete saved entity city/state takes precedence. An incomplete profile uses city/state from the most recent associated IP/hostname report in the selected evidence scope, with its source and date. Placement is an approximate Census point, never raw IP coordinates or an asserted street address. Unsupported complete profiles and unusable latest reports remain discoverably unplaced. |
| Review recipient scope | A qualified domain formerly allowed a private sibling IP into the notification. Invalid/nonpublic observations now block relevant review until a reasoned exclusion. Individual decisions preserve sibling hosts, shared-IP observations and original evidence. Counts, narrative, inventory, sources and recipient appendices follow included scope. |
| Review larger scopes | The scope panel puts unresolved anomalies first, supports search and 50-row pages, and permits explicit bulk review of up to 1,000 flagged rows. It requires a reason and current case/draft versions. |
| Correct identity after review | Entity updates now have a before/after plan showing affected sections. One reasoned, version-checked action repins identity and reopens only affected frozen sections, preserving earlier validation records. Sender name, organization, office, optional title, reply email and document verification route are separately pinned to the report. |
| Review sources and certify | Excluding the last observation for a CVE removes its active selection and related explanations while retaining exact archived selections for restoration without a new lookup. Scope changes reopen affected sections explicitly. Attribution proof can remain support-only without returning to the notified inventory. |
| Read the recipient packet | Covers now identify product and version together, provide the first action and configured reply/verification route, and tolerate long business/sender details. EOL headings use readable pinned explanations. References point to the actual bibliography; repeated publication metadata and sparse trailing pages are reduced without deleting evidence. |
| Prepare first contact | Subject, message and call outline are saved per case, with explicit Save/Reset and optimistic revisions. They survive closing the dialog, restart and backup/restore. Unsaved edits are protected during navigation, Escape and unload. Late saves retain newer typing rather than replacing it. |
| Recheck before copying | Copy rechecks current route usability, hold/closure state, preparation revision and reviewed context. A stale response cannot copy against a newly displayed hold. Copy does not send, attach a report or record delivery. Historical reports containing invalid/nonpublic scope require revision and recertification before new handoff/copy. |
| Record outcomes | Contact discovery, analyst route selection, email sent and successful delivery remain separate facts. Delivery requires the recipient and current certified revision. Bounces affect their actual destination; no-answer does not invalidate a route. A reasoned restoration survives refresh and transfer. |
| Close | Open-case previews now say `PREVIEW — CASE OPEN` and proposed administrative closure. Final output records actual closure. The report distinguishes delivery from a recipient's unverified statement that patching occurred. An all-excluded case cannot certify a notification but can close with an out-of-scope conclusion. |
| Resume after later intake | Earlier certified files, delivery facts and closed cases remain unchanged. New findings lead to comparison/new work rather than silently reopening old history. Derived notification coverage now honors reasoned CVE exclusions as well as observation exclusions. |
| Restore the working day | Export, staged import and restart restored schema 16 and exact case, membership, contact-attempt, outreach-policy and preparation tables. All **88 protected files** matched their prior hashes; later intake also left those 88 files unchanged. Foreign-key checks passed. |

Map geography and regional coverage are detailed in
[the entity-map contract](OBSERVATORY_ENTITY_MAP_0100.md). This work does not add
nationwide place coverage, street geocoding or historical business-location inference.

## Recipient and case-file readthrough

Every page of the final HTTP-generated Harbor notification (10 pages), Ridgeview
EOL notification (9 pages), closing preview (1 page) and final closure (1 page) was
read. The final cover, technical page, information page and sign-off consistently
identify the configured Example Cyber Outreach Unit. The custom introduction no
longer inherits an unrelated agency mission. The generic executive/IT addressee and
historical case title remain intentional template/snapshot choices.

The Harbor recipient PDF and all DOCX XML parts omit the excluded private IP and
hostname. Its internal Evidence Record explicitly shows **3 included, 1 excluded,
4 original observations retained**, with source row, reason, analyst and timestamp.
Recipient ZIPs contain the notification PDF and recipient manifest; the Harbor and
Ridgeview internal ZIPs contain 39 and 34 members. Each archived notification PDF is
byte-identical to its certified file. This verifies recipient/internal separation,
not deletion of inconvenient evidence.

The EOL technical page explains that no CVSS score is assigned and that the observed
version alone neither establishes current support coverage nor proves a particular
CVE applies. The final closure preserves the same three contact events as its
preview; only closure state/metadata changes. It does not transform a recipient's
patching statement into analyst-verified remediation.

Expanded rendering used production composition and package construction, followed
by independent DOCX rendering through `render_docx.py` and **LibreOffice**. PDF and
LibreOffice-rendered DOCX had the following page counts:

| Variant | Prior PDF | Current PDF / rendered DOCX |
|---|---:|---:|
| One CVE, several IPs and shared services | 10 | 10 / 10 |
| PHP EOL, no CVE | 10 | 9 / 9 |
| Six fictional CVEs | 13 | 13 / 13 |
| Long company/address | 10 | 10 / 10 |
| Long sender/title/company plus verification | 10 | 10 / 10 |
| Long verification route | 10 | 10 / 10 |
| PHP and IIS on separate IPs/ports | 11 | 10 / 10 |
| Notification without its appendix | 7 | 7 / 7 |
| Packaged Sample / Multiple CVE examples | 10 / 15 | 10 / 10 and 14 / 14 |
| Short exercise closure / open-case preview | 2 each | 1 / 1 each |
| Nine long contact events | Stress case | 11 / 10 |

The long closure differs by renderer font metrics; substantive text and attribution
are retained. Notification comparisons found no text outside page bounds or missing
DOCX internal-link targets. Raw appendix record counts were unchanged. The
appendix-off variant retains a separate three-page appendix internally; explicitly
including it adds that file to the recipient ZIP. Historical certified artifacts
are not regenerated. Approved template source was not cosmetically rewritten.

## Analyst assessment

**Keep:** stable entity identity; separate observation, finding and case concepts;
retained original files; explicit frozen-section review; pinned report identity;
distinct discovery/sent/delivered outcomes; holds that remain meaningful; and
delivery/closure history that does not silently change after later intake. These
features make the record defensible and the next day's work understandable.

**Improved:** identifying the actual next task, correcting identity without manually
reopening several sections, recognizing private observations before certification,
preserving interrupted outreach wording, preventing stale-dialog actions, and giving
the recipient a useful first action. The fresh replay and interrupted/race tests
exercise these behaviors rather than inferring them from static templates.

**Still needs work:**

1. **OPEN, high priority — condition-specific observation admission.** A canonical
   measurement approved for CVE-A can contaminate CVE-B's approved recurrence history
   after B is approved later. The reproduced result adds an earlier unqualified
   version/day and reports a false `changed` state. Case-specific recipient exclusions
   do not fix this underlying provenance problem. The proposed admission/event model
   and conservative legacy treatment are in [the database audit](../reviews/DATABASE_AUDIT_0101.md).
2. **Recipient length and repetition.** A simple packet still has six core pages
   before appendices. The general information, report-family explanation and resources
   repeat some guidance; six-CVE narratives are dense. A separately approved short
   recipient edition could consolidate background while retaining the full certified
   case file. This review did not remove approved explanatory intent to chase page count.
3. **Correction of mistaken dismissal.** Add explicit reasoned finding reactivation
   from canonical/current evidence. Reimport should not silently undo suppression.
4. **Scale and health visibility.** Bulk Workspace priority-queue contact summaries, scoped Observatory
   detail and selective analytical invalidation deserve follow-up. A unified health/
   storage view should distinguish retained evidence from disposable lookup projections.
5. **Actual desktop acceptance.** Perform native Windows startup/upgrade/restore,
   browser keyboard/DPI/accessibility and Microsoft Word checks on the exact release.
   Portable harnesses and LibreOffice rendering do not establish those results.

## Verification scope and evidence

Focused tests cover scope mutation/restoration, freeze rollback, legacy revision,
sender adoption, contact boundaries, stale/late responses, saved outreach, exclusions
after certification/delivery/close, immutable historical files and transfer. The final
document/appendix target passed 29 tests; sender/narrative, workflow, scope, outreach
and database owners recorded their targeted suites separately. Overlapping runs are
not summed into a unique-test total. Final whole-suite and packaging results belong
to the release validation record, not an assumed count in this review.

A later post-database-fix transfer recheck restored the current three-case workspace
with all 42 main tables and 90 protected files exact, integrity passing and zero
foreign-key errors. It is a separate checkpoint from the original 88-file replay.
The separate security gate recorded 383 passing tests and 78 passing subtests; the
public dependency audit found no reported advisories across 33 packages/34 wheel
artifacts. Those scoped checks are not the final full backend suite or a native
desktop acceptance result.

Reproduction evidence retained with this evaluation includes
`workflow_review/integration_results.json`, `analyst_workday_final/exercise.py`,
`analyst_workday_final/restore_result.json`, the scope/identity/workflow/outreach/document
findings, document comparison results and page renders. Database correctness and
performance evidence are cataloged in [DATABASE_AUDIT_0101.md](../reviews/DATABASE_AUDIT_0101.md).
These are synthetic evaluation artifacts, not operational case files or evidence of
real notification delivery.

— GPT-6

