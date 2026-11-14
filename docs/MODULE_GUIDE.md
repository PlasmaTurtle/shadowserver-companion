# Where to make the next change

Use the smallest responsible layer, then test outward across its interfaces.
The interactive map includes every owned production Python/JavaScript module,
including tooling and the compatibility CLI. Vendor JavaScript, test files,
fonts and schema data are not counted as owned code modules.

| Change | Start here | Verify across this boundary |
| --- | --- | --- |
| Change common input security | `aegis/antimalware.py`, `execution.py`, `json.py`, `text.py`, `errors.py` | Shared capacity/deadlines, fail-closed Windows scan receipts, strict representation checks, stdlib-only imports; provider schemas remain in adapters |
| Add a scan format / preserve another column | `intake/files.py`, `intake/records.py`, `report_profiles.py` | Full rows, physical row numbers, eligibility and original-file hashes |
| Adjust workload filtering | `intake/validation.py`, `report_profiles.py` | Rejection reasons, jurisdiction, targeted inclusion and private-IP retention |
| Add an attribution method | `components/attribution/src/attribution/` | Evidence identity, review vs automatic match, first qualifying match and no loss of grouped observations |
| Change contact discovery scope or extraction | `contact_discovery/policy.py`, `engine.py`, `extract.py`, `transport.py` | Company apex/www pair, six ordinary requests plus two redirects, public-address checks, evidence retention and explicit review |
| Change contact evidence integrity or adoption | `contact_evidence.py`, `contact_records.py`, `contact_jobs.py` | Shared hash/path checks, attribution ownership, candidate revisions, manual contact preservation and backup validation |
| Handle a provider's changed response | `intelligence/adapters.py`, `cve_intelligence.py` | Published/rejected/reserved state, unknown vs zero/false, contributor identity and source revision |
| Change provider pacing / caching | `intelligence/acquisition.py`, `repositories/sources.py` | Deadline, cancellation, endpoint restrictions, validated source bytes, stale-data dates and acquisition outcomes |
| Combine additional intelligence | `intelligence/service.py` | Independent signals and immutable bank revision; case adoption remains explicit |
| Add source explainers | `content_bank.py`, `report_composition.py`, `appendix.py` | First-party citations, only sources used, pinned wording and freeze fingerprints |
| Change the document layout | `report_renderers.py`, `exhibit_rendering.py`, `print_policy.py` | Same snapshot in PDF/DOCX, approved emphasis colors, page markings, overflow and frozen history |
| Review the revised Introduction | `introduction_model.py`, `introduction_layout.py`, `introduction_renderers.py` | Explicit revision, exact wording, one-page scope, native Word prose, retained appendix, no draft migration |
| Change certification / case transitions | `services/reviews.py`, `services/certification.py`, `reviews/`, `cases.py` | Single transaction, expected revisions, reopens, chronology and recovery |
| Extend ECLIPSE | `eclipse.py`, `intelligence_index.py`, `static/eclipse.js` | Original-row denominator, approximate locations, current-status labeling and no new lookups |
| Change the UI | `static/modules/*_events.js`, `events.js`, `navigation.js` | Feature state, action contracts, unsaved changes, keyboard flow and real browser preview |
| Change storage | `workspace.py`, `repositories/`, `migrations.py` | Explicit migration, backup/restore and historical artifact bytes |
| Change release status / IDE setup | `RELEASE.json`, `release.py`, `tools/check_release.py`, `.vscode/` | Explicit home confirmation, consistent labels, isolated debug workspace |
| Change installation | `tools/windows_installer/` | Hash locks, clean install, obsolete-file cleanup and native Windows acceptance |

Paths without a prefix above are under `workbench/`, except `static/` and
`tools/`. Use `python -m pytest -q <test paths>` for the component-specific suites
listed in the map. Run `python tools/verify.py` and the upgrade harness before
shipping a release that crosses multiple areas.

## Narrative names and responsibility

Each name identifies a responsibility and an ownership boundary. Aegis is the
shared protection layer.

| Module | Current implementation | Owns | Must not own |
| --- | --- | --- | --- |
| Accretion | `workbench/intake/`, `workbench/accretion.py`, `workbench/intake_service.py` | Intake filtering, qualification, agency-priority scoring and final association | Notification rendering or copies of shared antimalware/decoding policy |
| Observatory | `workbench/eclipse.py`, `workbench/observatory_view.py`, `static/eclipse.js` | Scoped read models and visualization of findings, observations and density | Requalifying incoming records or rewriting source evidence |
| Aegis | `workbench/aegis/` | Shared representation validation, bounded local antimalware execution and typed failure receipts | Agency-priority scoring, entity attribution, report management, provider schemas or network acquisition |

Domain modules call Aegis at their input boundaries and keep their own semantic
checks. A valid JSON response still needs its provider schema; a clean scan still
needs contact extraction and does not establish entity ownership or lead urgency.

## Choosing the unit of reuse

- **Function/module:** deterministic transformations, identifiers, formatting and small safety boundaries.
- **Internal package:** a cohesive set of modules with one usable interface, such as intake or intelligence. It ships with the application.
- **Independent library:** separate consumers, explicit inputs/outputs, no workbench imports, its own tests and a meaningful compatibility/version policy. Attribution meets this standard today.
- **UI component:** owned inputs, state and mount/unmount behavior. Existing feature modules are a start; their shared action registry is still an integration boundary.
- **Application service:** coordinates repositories, providers and user intent. It owns transaction scope rather than hiding commits inside lower-level helpers.

No microservices, plugin discovery framework or new dependency-injection package
is needed for these boundaries. Use direct imports and explicit parameters.
Split packages when consumers or change patterns justify an independent contract.

## Maintenance sequence

Completed in 0.7.4: review policy/query/command separation; workspace and
entity/artifact/review repositories; entity/export/recovery services; closing
render separation; certification service; removal of the seven-module import
cycle; manual unstable-release gate and optional IDE configuration.

Completed in 0.7.5: case queries and scope/contact writes, entity mutations and
source-cache persistence moved into repositories. Related projections use a
read-only snapshot; current CVE/revision publication is atomic. Captured provider
data travels with its matching proof. Feature interaction handlers are separate
from the delegated browser listener owner; startup/teardown are explicit.

1. **Remaining persistence.** Intake and certification/recovery aggregate SQL
   still lives with those services. Preserve their crash/publication protocols
   when extracting it; never add independently committing helpers.
2. **Browser interfaces.** Event ownership is separated. The shared action
   registry and ECLIPSE global still need explicit render interfaces before any
   independent UI packaging.
3. **Rendering inputs.** Define asset-resolution and font inputs before deciding
   whether the renderer needs to be an independent library.
4. **CLI compatibility.** Deliberately migrate or retire the legacy CLI network
   client; the web application already uses standalone Attribution.
5. **Release acceptance.** Kyle accepted 0.8.0 as stable on November 8, 2026.
   Version 0.9.0 remains unstable and requires its own version-specific
   confirmation. Follow `HOME_VALIDATION.md` for the current workstation gate.

Attribution owns the bounded provider transport also used by CVE capture. Contact
discovery has a separate website transport because it must check every resolved
address, pin the connection to a public IP while retaining the original TLS
hostname, disable ambient proxies/cookies/authentication, and count redirects
inside one discovery budget. Its stricter destination contract is not a drop-in
replacement for the provider transport. Any future extraction of shared transport
code must preserve both contracts and their tests.

## Introduction page review candidate

`tools/preview_introduction.py <output-directory>` produces synthetic one-,
eight- and seventy-IP examples through the production composition and export
interfaces. The data contains fictional CVE and exploitation assertions solely
to exercise layout. It never opens a workspace or performs a provider lookup.

The candidate is selected only by `introduction_revision` equal to
`introduction-2026-11-07-review-1`. It is not the installed builder default.
Existing wording and later report sections remain intact. Approval of page one
precedes a separate adoption change and an unstable application release.

The model owns wording and selected evidence. The layout owns measured lines,
font sizes and a finite Summary Exhibit budget. The renderers own native PDF
text and native Word paragraphs with SVG/PNG exhibits. Overflow produces a
clear error instead of microscopic text or missing details. Source rows are
retained in the unchanged appendix. New Office SVGs name the bundled fonts;
the DOCX embeds those fonts and sets explicit image spacing for consistency.

The bundled `resources/timezones` TZif record is the Windows fallback for
America/New_York. Its version, license and hash travel with the source. Original
timestamps stay in the source model; timestamps lacking a zone are identified
as such rather than assigned an invented zone.

## Vulnerabilities page review candidate

`tools/preview_vulnerabilities.py <output-directory>` produces three entirely
synthetic, offline examples: one asset, two assets with a shared finding, and
six CVEs. It runs the notification narrative generator and production exporters.
Select `vulnerability_revision` equal to
`vulnerabilities-2026-11-07-review-1` to use this candidate. It is separate from
the installed builder default and does not promote an application release.

`notification_narrative.py` generates one paragraph for the whole notification,
using the established opening, attribution and closing once. Common findings
combine; distinct products, versions and services retain their asset scope.
Per-finding insertable values and original source rows remain separate records.
`narrative_revision` identifies this aggregation rule in draft and review
snapshots. An existing frozen section must be reopened before changed wording
can be certified; completed drafts and historical packages remain unchanged.
The historical `approved_template.py` source and other approved paragraphs are
unchanged.

`vulnerability_model.py` joins the exact draft narrative and selected finding
records. `vulnerability_layout.py` measures them together in a 477.6 × 650 pt
page frame. Narrative is 11 pt with 15.5 pt leading; findings and citations
stay at least 10 pt. Whole paragraphs and whole findings move to a fresh page
when they fit there; oversized content continues without clipping or shrinking.
Every continuation repeats the section title, and split findings repeat their
identifier. Citations accompany independent source metrics and assessments.

`vector_layout.py` owns common geometry and font metrics. `exhibit_rendering.py`
emits PDF vector text and Word SVG with a PNG fallback. `document_fonts.py`
embeds the bundled fonts once per document. `exhibit_masters.py` stores page
geometry, SVG/PNG bytes and hashes in the review snapshot. Unchanged frozen
content reuses those masters; changed source/model/font inputs require a new
review through the existing stale-section policy. Hashes detect modification;
they do not replace the existing certification chronology or provide a digital
signature. No live lookup occurs during rendering or review comparison.

The Introduction, Attribution, Information, Closing and full source appendix
retain their existing content. The only general renderer changes are shared
font/geometry helpers and opt-in handling of page-sized exhibits. Older exhibit
layouts and their review fingerprints retain their original output path.

## Attribution page review candidate

`tools/preview_attribution.py <output-directory>` renders four offline synthetic
examples: exact registration evidence for a 70-IP group, a saved DNS answer,
an analyst-accepted registration-name association, and an unresolved partial
match. Select `attribution_revision` equal to
`attribution-2026-11-07-review-1` to use this candidate. The installed builder
default remains unchanged while the page is reviewed.

`attribution_model.py` compares the selected source observation at group index
zero with the case-frozen proof. It distinguishes a saved A/AAAA answer, exact
domain evidence in a registered network, and explicit analyst acceptance.
It checks IP equivalence, network containment, saved field values and source
identity. Missing validation times remain unknown; retrieval time never becomes
validation time. These checks explain saved evidence and do not perform new
lookups or change intake qualification. One supporting association never implies
individual validation of every reported IP in the group.

`attribution_layout.py` integrates the unchanged attribution paragraph and
association cards into a measured page exhibit. Ordinary cards stay together;
long content continues without omission or reduced type. Text is black; blue
graphics identify complete supporting evidence and red graphics identify review
needs. Source and validation details stay visible; raw record pointers and full
responses remain in Appendix B. Source citations and included screenshots retain
their existing reference and appendix paths.

The common exhibit dispatcher preserves geometry, SVG/PNG and font hashes for
both page revisions. `report_snapshot.py` reuses each section's own frozen
artwork. An incomplete attribution exhibit cannot be certified. Layout adoption
and content changes use the established reopen, reason and validation chronology.
No other section's approved wording changes with this revision.

## Finding an operation in the IDE

| Operation | Entry point | Records / policy |
| --- | --- | --- |
| Validate or reopen a section | `services/reviews.py:SectionReviewService` | `repositories/reviews.py`, `reviews/policy.py` |
| Show freeze status / stale dependencies | `reviews/queries.py:SectionReviewQueries.describe` | `record_changes=False` is read-only |
| Edit the draft | `services/drafts.py:DraftService.save` | One transaction covers case, legacy projection and event |
| Revise a certified report | `cases.py:Cases.revise`, `repositories/cases.py` | Existing package retained; audit event uses caller's connection |
| Certify a report | `services/certification.py:certify_report` | Snapshot → package → rename → database publication |
| Recover after interruption | `services/recovery.py` | Validate package inventory; reconcile only eligible state |
| Merge businesses | `services/entities.py:EntityService.merge_entities` | Move related records in one transaction; export after commit |
| Read one notification | `repositories/cases.py:CaseRepository.view` | Entity and case rows share one read snapshot |
| Capture provider data | `intelligence/acquisition.py:capture_json` | `CapturedSource` retains matching data/proof; `cached_json` keeps its pair contract |
| Publish source revisions | `repositories/sources.py:SourceRepository` | Transaction supplied by acquisition/enrichment service |
| Handle a browser action | `static/modules/*_events.js:createHandlers` | `events.js` alone attaches delegated listeners |
| Start or remove browser app | `static/app.js:createApplication` | Idempotent start; destroy removes listeners and owned timers |
| Read all entity data | `repositories/entities.py:EntityRepository.lead` | Full fields; attribution entry first |
| Export qualified leads | `services/lead_exports.py:LeadExportService` | Existing JSON contract retained |
| Render closing document | `closing_renderers.py:render_closing` | Receives snapshot and destination |

New internal consumers use the owning module. Existing consumers can retain
Store, SectionReviews, reporting and closing compatibility imports. Do not use a
facade from a lower layer to reach a helper; the import checker rejects it.

# Information page review

The opt-in draft revision `information-2026-11-07-review-2` selects the cohesive
Information Exhibit with revised page-two copy. The first review revision remains
supported with its original wording and source record. Existing drafts continue
to use their selected layout.

- `workbench/information_model.py` retains the approved security introduction
  and four protective actions. Revision two contains separately identified
  editorial risk/advisory copy and exact IC3 figures without a calculated average.
  FBI BEC guidance, the joint StopRansomware guide and the IC3 annual report
  support the explanations. Each reviewed extract retains its actual source URL,
  retrieval time and section/page locators. These are explicitly reference
  extracts, not archived copies of the full source documents.
- `workbench/information_layout.py` measures the approved body text and keeps
  ordinary paragraphs together. Longer additions continue with a repeated
  section title, without repeating the introduction or shrinking body text.
- `tools/preview_information.py` renders the standard two-page exhibit and a
  synthetic long-explainer specimen through the production PDF/Word exporters.

Selected custom explainers retain their source citations, overrides and pinned
revisions. Source records and the citation register remain in Appendix D.
Composition and export are offline. The Information revision participates in
section freezing; certified SVG/PNG masters are reused across exports and
reopening still requires the recorded reason. The approved template constants
are unchanged. Revised page-two text is an editorial candidate, not an assertion
of agency policy approval. This is a review candidate, not a change to installed defaults.
