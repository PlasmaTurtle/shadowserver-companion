# 0.12.0 — Guided Setup

- Start with guided setup for API connections, agency identity and jurisdiction, then optional automatic acquisition. Resume unfinished setup and keep API secrets in the existing credential services.
- Organize Settings around identity, jurisdiction, connections, automation, report defaults, data and software. Support agency presets, a custom agency and a name without a title.
- Filter recognized state-specific API subscriptions by the saved jurisdiction. Revalidate catalog requests and scheduled imports when scope changes; retain clearly labeled national and custom account subscriptions.
- Give Observatory national city lookup and a saved-jurisdiction map context while preserving entity identity and location provenance.
- Modernize the Windows installer with Eclipse artwork, clearer progress and a direct handoff to setup. Repair app-owned Python residue using a fresh installer runtime, including when the previous interpreter is missing or damaged.
- Add in-app release checks, verified installer downloads, an explicit install-and-restart action and versioned What’s New. Updates retain the workspace and wait for active work to finish.
- Keep this build a release candidate. Native Windows acceptance and publication of compatible update assets remain separate release steps.

# 0.11.1 — Workspace naming consistency

- Align documentation, source module/function names, UI helpers/styles, tests and benchmarks with Workspace. Its priority queue is part of the existing feature.
- Use `/api/workspace/queue` in the app and API documentation. Keep `/api/today` only as a hidden compatibility alias to the same handler.
- Preserve queue behavior, schema 20, stored records, report wording and dependency pins.

# 0.11.0 — Workspace Evolution

- Add append-only finding/observation qualification events and explicit legacy-unknown provenance without erasing known historical qualification or case disposition.
- Strengthen case/section ownership and JSON constraints; separate immutable evidence revisions from replaceable lookups and bind certified artifacts to saved manifest digests.
- Add reviewed ownership transfers and reasoned finding reactivation. Preserve recorded ownership and prevent a new business from inheriting prior notification/dismissal status or attribution approval.
- Batch Workspace priority-queue contact/case reads, scope Observatory details, maintain incremental analytical summaries with reconciliation, index current source selection, and bound planner maintenance.
- Add background workspace health, safe cleanup estimates, independent offline recovery and controlled compaction with verified checkpoints.
- Add an explicit compact recipient edition and shared package resources; full remains default and compact packages retain a separate complete report.
- Render reports outside the workspace write lock and recheck case revisions, review identities and source integrity before publication.
- Keep capture jobs busy until cleanup finishes, and use indexed root-domain ownership lookups as unrelated history grows.
- Preserve the approved template, historical files, installation/data identity and dependency pins. Exact-version native Windows acceptance remains outstanding.

# 0.10.1 — Analyst Workflow

- Add explicit report observation scope with audited exclusions, non-public address certification guards, exact affected-section reopening, and retained source history. Recipient finding/CVE counts and delivery coverage follow included rows.
- Save outreach preparation per case. Protect unsaved edits across closing/navigation, reject stale windows, preserve custom text during context changes, and recheck context before copy. Copy does not send or record delivery.
- Pin sender identity and verification details for new reports; reconcile custom agencies consistently. Make sender adoption explicit and preserve legacy/certified report content.
- Replace generic Workspace blockers with actionable saved-state guidance and correct destinations. Review entity field changes and reopen affected frozen sections atomically.
- Improve recipient reports with a first action and reply route, product/version labels, correct appendix references, and lossless supplementary-link packing. Mark closing previews as drafts and keep short event records together.
- Fix ignored-contact adoption and missing profile phone fallback. Add schema 16 for outreach drafts; validate saved preparation and scope during backup/restore.
- Bind report packages and closing snapshots to their database identities, verify mutable CVE/risk summaries against retained source bytes, align reference freshness and schema gates, and keep excluded CVEs out of notification coverage.
- Preserve inspection of an independently verified historical snapshot when rendered files are missing; complete-package delivery and transfer checks remain enforced.
- Read case lists from one consistent snapshot and remove quadratic observation-scope counting. Document the remaining condition-level approval-history gap and measured database growth/query recommendations in `docs/history/reviews/DATABASE_AUDIT_0101.md`.
- Preserve entity-map behavior, installation/data identity, dependencies, protected approved template, source evidence and historical report files. Candidate status remains pending exact-version Windows acceptance.

# 0.10.0 — Entity Map

- Make canonical known entities the map identity and primary count; associated
  assets and findings support the entity rather than becoming additional markers.
- Prefer saved entity city/state for placement. When profile city/state is missing,
  use city/state from the latest associated IP/hostname report in the selected
  scope, with explicit source, IP/hostname and date. Use approximate Census
  representative points rather than raw IP coordinates.
- Keep unsupported saved locations and unusable latest-report locations in an
  unplaced directory, without searching older reports for a convenient location.
- Distinguish current saved profile geography from dated report fallback geography
  governed by the selected observation cutoff.
- Review clustered-marker interaction, selection, filtering and detail provenance
  against the entity contract in docs/history/design/OBSERVATORY_ENTITY_MAP_0100.md.
- Retain the existing installation and data identity, dependency pins and schema.
  This release remains a candidate; see VALIDATION.md for the actual verification
  status and HOME_VALIDATION.md for native Windows acceptance.

# 0.9.99 — Maintenance Review

- Integrate the cumulative Field/Observatory, attribution approval reuse and NVD recovery checkpoint against verified 0.9.98 source.
- Bound read requests in the frontend and make developer verification fail closed on interruption, with child-process deadlines.
- Batch lead scope reads while preserving transaction and observation ordering.
- Reject inconsistent source dependency pins before packaging.
- Preflight recorded and orphan closing snapshots before restore recovery; stream
  artifact hashes during package verification instead of allocating whole files.
- Fix the NSIS Modern UI callback collision that blocked installer compilation.
- Include the approved favicon assets and maintenance/Field review documentation in both distributions.
- Retain release-candidate status and existing installation/data identity. See VALIDATION.md for actual automated results and remaining native Windows checks.

# 0.9.98 — Input Validation

- Centralize antimalware execution, typed security errors, strict JSON and text
  validation in Aegis, a shared standard-library-only security package.
- Validate remote response types, encodings and provider schemas before retaining
  evidence, with bounded requests and parsing.
- Require Windows contact responses to pass the local AMSI scanner before
  extraction; scan each browser resource before rendering and abort the whole
  capture on a blocked/unavailable scan. One bounded executor prevents stalled
  native scans from creating unlimited replacement threads.
- Store contact facts and source provenance as derived JSON instead of saving
  complete website bodies. Original response and derived artifact hashes have
  separate meanings.
- Exclude legacy raw contact pages from new routine evidence exports, retaining
  explicit omission metadata without rewriting certified files.
- Keep rejected provider replies as metadata and original-response hashes; do not
  save error pages or unsupported payloads as source records.
- Expand inert adversarial regression coverage across retrieval, persistence and
  export. See VALIDATION.md for the completed scope and platform limits.

# 0.9.97 — Notification Review

- Correct the current report subject to Cybersecurity and restore the visible
  notification date through a new pinned Introduction revision.
- Align narrative edit validation with normalized software versions and scoped
  findings; honor Attribution freezes when adopting a changed entity address.
- Protect newer edits and notification switches from late evidence/adoption
  responses, and align the Closing editor with the exported report.
- Distinguish product/version pairs in evidence and current compact appendices;
  present local NVD evidence in a readable summary.
- Copy verified source bytes atomically into report packages; remove inherited
  sample Word metadata and retain existing certified snapshots.
- Refresh synthetic examples and review the full notification lifecycle with
  regression, rendering and previous-release retention checks.

# 0.9.96 — Professional Review

- Rename the product Shadowserver Eclipse while retaining the ECLIPSE / Shadowserver
  Companion masthead and existing install/data/credential identity.
- Remove prototype wording and stale instructions from active UI and current docs;
  identify the separate internal evidence reader clearly.
- Coordinate installer replacement with app startup and wait for authenticated
  reuse when a second launch races initial startup.
- Add persistent, redacted scheduler diagnostics and safe windowless streams.
- Correct acquisition/intake shutdown order and NVD saved/session credential lifecycle.
- Expand targeted security-suite discovery; record dependency advisory, retention,
  source/package integrity and full regression results independently.
- Permit stable DarkMatter promotion without moving records; retain candidate status
  until acceptance of that exact version. Record the accepted 0.9.95 Windows baseline.


# 0.9.95 — Observatory: approach and resolve (2026-11-13)

- Make the Dark Matter Field the default, with organization-centered systems,
  distinct assets, density halos, priority marks and restrained contextual light.
- Resolve selected objects into focused traditional locations, product breakdowns,
  organizations, findings or history; restore the prior Field position on return.
- Share one scope/revision across views, fix reset and deep-link filtering, retain
  historical endpoint/source context, and separate condition-specific workflow.
- Reduce repeated history transport, page findings, cache map summaries, preserve
  source evidence on demand, and cancel obsolete requests and camera transitions.
- Register full Observatory controller, scene, shell and API acceptance; native
  Windows rendering and installer acceptance remain explicitly pending.

# 0.9.94 — Canonical awareness and scheduled intake (2026-11-13)

- Add schema 15 canonical assets, individual findings, source events and source provenance; retain originals and certified snapshots.
- Recognize applicable history early, recheck changed endpoints, and atomically Associate after qualification. Separate admission from outreach workflow.
- Consolidate entity, lead and Observatory counts; distinguish distinct events, observation days and finding counts. Keep density halos separate from outreach temperature.
- Add manually associated domains/rebrands, nationwide city/state autocomplete and contact field validation; compare Google and Cloudflare DNS with independent evidence.
- Automatically select reported CVEs from local catalog extracts for new notifications. Preserve scoped conditions and expose unavailable local records without network fallback.
- Repair named-section reopening with unsaved edits, unrelated frozen-section capture blocking, Introduction navigation, and bounded capture diagnostics.
- Restore compressed annual NVD bootstrap with separately measured stages and authenticated incremental synchronization.
- Add durable scheduled reference updates and Shadowserver acquisition through completed intake, late-arrival overlap, missed-run catch-up, and optional current-user Windows tasks.
- Cancel obsolete view reads and polling while preserving intentional background jobs.

# 0.9.93 — Data navigation hotfix (2026-11-12)

- Fix sidebar/default Data navigation trying to initialize an absent upload drop zone.
- Verify complete route/render/binding behavior and retain file uploads.
- Keep schema 14 and all 0.9.92 features unchanged.

# 0.9.92 — API setup, Accretion progress and entity directory (2026-11-12)

- Make Shadowserver API acquisition the default Data tab and expose both API connections in Settings.
- Use the user's NVD key for the full catalog download and daily changes, with resumable pages, shared pacing and secret-free evidence URLs. Preserve complete existing catalogs.
- Present Filter / Qualify / Urgency progress, recent intake patterns and explicit catalog-coverage warnings.
- Apply a 90% outreach-ranking penalty to known ISP-owned roots rather than excluding otherwise eligible findings.
- Fill blank entity names and addresses from the organization containing the matched RDAP field, with provenance and protection for manual details.
- Put domains, contacts, addresses and observation dates first; add Find all for gaps and per-entity contact refresh through the background queue.
- Read contact summaries in bounded asynchronous batches without resetting navigation or edits.
- Validate real report schemas and selected live workflows, historical report preservation, keyed NVD access and schema-14 migration/restore.
- Retain the 0.9.91 current-lead, inline attribution, recipient-safe priority marking, report-paper and Observatory-loading improvements.

# 0.9.91 — Current leads and real-schema acceptance (2026-11-12)

- Reconcile one current qualified lead per entity; combine same-day findings, compact repeat history, retire obsolete unworked scope, and preserve case evidence.
- Hide unfinished attribution from Leads; add Ignore / Refresh and remove stale pending counts.
- Exclude explicit ISP-owned roots without excluding their customer domains.
- Add inline Accept / Reject for the displayed registry match; treat shared IPs as dated associations.
- Queue automatic sourced contact discovery with a pending-confirmation default and protection for manual contacts.
- Limit frost to HUD surfaces, protect report paper, and remove internal temperature text from new PDF/DOCX products.
- Open Observatory immediately with the shared animated background and a loading/retry state.
- Refresh the official schema inventory; support agreed exposure adapters and real numeric-leading finding tags.
- Check 98,777 real rows across 17 downloaded files. Live DNS attribution was blocked by automatic approval review; see the explicit acceptance limits in docs/history/releases/RELEASE_0991.md.
- Upgrade to schema 13; retain scoring weights, dependency pins, edition identity and prior-version fixes.

# 0.9.90 — Component versions and report start dates (2026-11-12)

- Use `component_version` for software evidence with ordinary `version` fallback; preserve both original columns and product-pair source provenance.
- Carry the selected version through Accretion, leads/entities, Observatory, Dark Matter, assets and report findings.
- Remove API narrative-date filtering, readiness gating and import form controls.
- Date new narratives from the notification case's recorded start date; preserve saved narrative revisions and frozen/certified evidence.
- Allow current-policy re-evaluation of retained originals without erasing previous import decisions.
- Replay the actual 4,313-row report through intake: 1,401 observations admitted across 404 domain groups, with 1,022 using component versions. Live attribution and the user's local CVE catalog were not part of that isolated replay.
- Retain schema 12, scoring weights, dependency pins and the 0.9.89 download compatibility fix. See docs/history/releases/RELEASE_0990.md.

# 0.9.89 — Shadowserver report download compatibility (2026-11-12)

- Accept complete, valid CSV reports even when the download server labels them `text/html`.
- Validate original bytes before publishing the report or receipt; retain CSV syntax, gzip, byte-count, hash, redirect and credential protections.
- Add download and application-import regression coverage for mislabeled attachments and actual HTML/JSON/XML error bodies.
- Keep schema 12, scoring, UI, Windows runtime and dependencies unchanged.
- See docs/history/releases/RELEASE_0989.md for live verification and installation details.

# 0.9.88 — Accretion intake calibration (2026-11-11)

- Remove obsolete `.com`-only and numeric-root exclusions, including their influence from saved legacy settings.
- Keep hostname syntax, registrable-domain validity, jurisdiction and supported evidence requirements as admission checks.
- Tighten semantic junk handling before scoring while retaining profile-specific non-CVE and version exceptions.
- Keep placeholder-version parsing linear for long separator-heavy input without restricting valid vendor version formats.
- Match uppercase and IDNA attribution domains canonically across imports, review and restored evidence while retaining exact result identity checks.
- Compare independently recorded admission and temperature expectations across 1,000 intended-valid and 1,000 intended-invalid synthetic records.
- Keep provisional weights, saved report priorities, historical evidence, schema 12 and runtime/dependency pins unchanged.
- See docs/history/releases/RELEASE_0988.md and the final VALIDATION.md entry for the test scope and results.

# 0.9.87 — Accretion intake and Dark Matter (2026-11-12)

- Preserve proven import/evidence/attribution infrastructure while vetting distinct CVEs locally before admission.
- Add strict critical-or-known-exploited admission, separate Quality/Urgency scores and saved outreach temperatures.
- Rank Leads by aggregate; carry snapshots through case scope, certification and discreet finished-product markings.
- Persist usable rejected observations as Dark Matter; add Library browsing, Observatory filters and exact-root historical association.
- Add optional city/product outreach focus, transparent factors, bounded catalog/disposition reads and neutral legacy handling.
- Add schema 12 and verify upgrade/restore without regenerating historical reports. See docs/history/releases/RELEASE_0987.md.

# 0.9.86 — Focused data-path performance (2026-11-11)

- Index hostname and reported-IP association, and separate exact root/hostname query branches so existing indexes can be used. Retain ambiguous/shared-IP review behavior.
- Filter stored pending/deferred/dismissed lead dispositions before projection. Batch pending-observation existence checks without dropping any displayed observations or detail.
- Read vulnerability flags only from selected notification drafts; retain every result in all-case views.
- Reuse one read-only database snapshot for Workspace contact/history facts, avoiding a connection and discarded page cache per entity.
- Add schema 11 with two indexes and the existing pre-migration backup/atomic upgrade protections. Retain saved rows and historical packages.
- Add reproducible offline scaling measurements and scope/batch regressions. Preserve UI, artwork, reference catalogs, report output, acquisition limits and evidence integrity.

# 0.9.85 — Orbital cockpit and viewport evidence (2026-11-11)

- Integrate the approved 2048 × 1152 orbital scene: 144-second shared camera drift, shallow zoom, registered corona and flowing data. Preserve source art sharpness and cyan/violet palette.
- Add fixed dark frosted reading surfaces, denser table backgrounds, and an opaque fallback. Drift follows reduced motion, pauses in hidden tabs and Observatory, and has a remembered toggle.
- Add one-action reported-hostname viewport capture using an isolated installed Edge/Chrome session. Retain exact PNG bytes, final/requested URL, title, timestamp, viewport, status and SHA-256; include selected images in existing evidence packages.
- Bound capture work, reject non-public destinations, deny direct browser networking/downloads, preserve browser sandbox/TLS policy and protect frozen evidence from completion races.
- Add request byte ceilings before parsing/spooling, recorded preview hash checks, asynchronous image decoding and complete worker cleanup on abnormal shutdown.
- Reject the specifically affected CPython 3.14.10/OpenSSL FIPS configuration without disabling its policy. Public dependency advisories are checked separately from native-runtime acceptance.
- Keep Dark Matter installation/workspace identity, existing catalog indexes and historical artifacts. Native Windows, actual Edge capture and GPU acceptance remain pending.

# 0.9.84 — Product outreach Library and cosmic data field (2026-11-11)

- Fix adopted vulnerability source save/freeze by normalizing JSON number identity and registering immediately completed retrieval selections. Keep published text/metric tamper checks.
- Add local-first report retrieval and direct local CVE search; preserve immutable selected evidence.
- Add independent daily bulk EPSS/KEV synchronization, all available local CVSS assessments, source hashes and date-aware freshness.
- Add product dossiers, version research candidates, Critical/KEV scopes, field distributions, revision differences, saved views and observed-entity links. Build the index in the background without downloading the catalog again.
- Join current catalog intelligence to explicitly reported Observatory CVEs, preserve product cohorts and prevent unrelated findings from supplying priority.
- Add automatic cached registrable-root A/AAAA DNS to entity Connections with separate provenance and no attribution mutation; update Attribution component to 0.2.4.
- Rename the main card to See the Dark Matter; add generated cosmic/data artwork with slow layered motion and a reduced-motion alternative.
- Preserve Dark Matter workspace identity, startup fix and prior packages. Native Windows acceptance remains pending.

# 0.9.83 — Local CVE Library (2026-11-10)

- Add a searchable local NVD CVE catalog using verified bulk year feeds and daily modification-date API synchronization.
- Preserve completed imports and catch up after offline periods; retain original records and source provenance.
- Use local NVD records for source lookup while keeping report evidence immutable and other provider enrichment independent.
- Keep the catalog outside working-record backups, with explicit initial download, progress, cancellation and daily-update controls.
- Preserve the Dark Matter startup hotfix and existing installation identity.

# 0.9.82 Dark Matter — Eclipse across the application (2026-11-11)

- Windows startup hotfix (2026-11-10): remove the outbound port-availability probe, which incorrectly rejected a Windows loopback timeout. Let the application server own binding, and open the browser only after that server starts. Keep authenticated session reuse and workspace locking.

- Final sanity pass: distinguish an active listener from TCP TIME_WAIT on immediate restart; reopen repeated evidence links after Collapse without adding history entries.

- Replace the broad sidebar and card wall with a shared Eclipse identity, compact rail, ranked work index and continuous editorial layouts. Add a dedicated Investigations destination.
- Default Entities to readable dossiers with saved contacts, findings, notification history and a factual hostname/IP connection diagram. Put editing behind an explicit Details view.
- Give the report studio a numbered section rail and large paper canvas. Keep certification within Report; simplify Contact & delivery and Closing views. Preserve dirty-form guards and fast content freezes.
- Lead contact results with the actual route; collapse source history, reveal saved-plan editing on demand, and preserve blank-only autocomplete.
- Add semantic zoom, count-weighted relationships, recurrence marks, expanding map clusters, a numeric temporal matrix, persistent source selection and a mobile inspector to Eclipse.
- Rebuild internal evidence readers as finding-first dossiers with exact grouping and explicit provenance links. Version the neutral unknown-severity treatment for new report layouts while preserving historical revisions.
- Add Library reading mode, an Activity chronology and clearly separated recipient/internal package downloads.
- Isolate Dark Matter's installation, workspace, restore points, credentials, shortcuts and ports 8881/8882 from both earlier editions. Keep the release unstable pending Windows acceptance. See [release details](docs/history/releases/RELEASE_0982.md).

# 0.9.81 Chaos - Isolated comparison and observation workspace (2026-11-11)

- Add a separate Chaos Windows identity, fixed install directory, shortcuts, workspace, logs, restore points and ports 8879/8880. Keep 0.9.8 available for comparison through explicit backup export/import; prevent cross-edition program overlays and data resets.
- Refocus Workspace on saved workflow, due work and activity without report-file hashing. Add Leads views, sorting and pagination.
- Add Ctrl+K Search & jump across entities, notifications, incoming leads, source files and Library, with bounded read-only queries, keyboard navigation and stale-query protection.
- Rebuild Eclipse Observatory around Field, Atlas and Pulse with Finding, Shared IP, Organization, Service and Version lenses. Preserve source provenance, unknown locations/dates and visible coverage limits; co-occurrence is not an ownership or compromise conclusion.
- Simplify contact results and refine fax/recruitment classification while preserving historical source evidence and immediate blank-field suggestions.
- Add offline search, category filters and explicitly selected-file SHA-256 comparison to new internal evidence readers. Preserve historical packages and the established recipient PDF/DOCX layout.
- Retain fast content freezes, schema 10 and existing dependency pins. Keep Chaos unstable; native Windows, live API and live contact-site acceptance remain pending. See [release details](docs/history/releases/RELEASE_0981.md) and [executed validation](VALIDATION.md).

# 0.9.8 - Independent records and readable evidence (2026-11-11)

- Separate Workspace notifications, pending Leads and independent Entities; add schema 10 with pinned report identity and explicit notification creation.
- Freeze content without rendering; keep legacy reviews and historical packages intact.
- Condense the appendix and add a portable Evidence_Record.html with originals, chronology and hashes.
- Simplify contact findings and autocomplete, reuse known contacts, and increase bounded capture limits while preserving complete tokens from partial pages.
- Integrate the pinned Shadowserver API module with credential isolation, report selection, receipt-backed imports, deduplication and cancellation.
- Clean navigation labels and redundant interface language. Keep the release unstable pending Windows acceptance and live API credentials.

# 0.9.7 - Contact discovery from the Fortune 500 findings (2026-11-10)

- Handle the company-domain/www pair automatically within an explicit eight-request ceiling (six ordinary requests and two redirect requests), unchanged time and byte limits.
- Retain local department context, form-routing choices and published reporting links. Separate security and IT referrals from product support and unrelated departments; exclude physical-emergency lines from routine cyber suggestions.
- Add dated coverage, clear incomplete outcomes and specific-page inspection without treating failure as absence or publication as delivery.
- Preserve existing evidence and review history; do not invalidate unrelated contacts after a focused page check. Keep arbitrary subdomains/external forms as reviewable pointers, not automatic fetch targets.
- Keep 0.9.6 explainers and historical certified reports unchanged. Native Windows acceptance remains pending.

# 0.9.6 - Report explainers and optional titles (2026-11-10)

Adds ten cited recipient one-pagers, exact report-family selection, supported
intake adapters, evidence-appropriate narrative copy and optional sender titles.
Preserves previous frozen/certified reports and selection defaults.
See docs/history/releases/RELEASE_096.md for report priorities and scope, VALIDATION.md for executed
checks. Release remains unstable pending this exact build's Windows acceptance.

# 0.9.5 — Daily workflow, report execution and recovery · UNSTABLE

- Add the Workspace priority queue (then labeled Today) with explainable next actions, consistent five-stage counts, finding recurrence/version history, reasoned outreach holds and due reconsiderations. A hold is never removed automatically, and absence never means remediation.
- Add searchable recorded activity with structured context for new events; leave unknown historical operators explicit. Schema 9 adds activity fields and case outreach policy.
- Keep published-source confirmation separate from contact usability. Bounces and explicit unusable decisions affect readiness and renewed discovery; preferred routes and last successful delivery are visible. Contact discovery batches use explicit selections of one to 25 entities.
- Add Prepare outreach with source explanation, certified-report link, editable first-contact message/call outline and configured independent verification route. Nothing is sent or marked delivered.
- Compact newly persisted report/review snapshots with lossless shared strings; retain legacy readers and unchanged historical certified files. Reuse package verification within a read operation and omit redundant standalone exhibit variants.
- Add a single-heavy-operation gate, durable report-operation history, bounded child-process rendering, cancellation before publication, phase/status UI and interrupted-on-restart recovery guidance.
- Separate recipient notification ZIPs from internal case-record ZIPs and version the Principal Executive addressee correction.
- Enforce the same export/restore limits, preflight disk space and verify offered exports using isolated restore. Keep the latest three full working-record restore points before imports and application schema upgrades. Allow explicit repair imports without retaining damaged current data; always verify incoming bytes. Permanent deletion removes managed restore points.
- Add workspace checks, redacted diagnostics, earlier startup logging and installation/log shortcuts. Installer preflight checks application downgrade and schema compatibility before cleanup; program activation rollback and console replacement remain deferred.
- Add bounded CSV.gz import and a receipt-verified offline handoff from the independent API downloader. Preserve original bytes, acquisition receipts and separate dates; unconfirmed API narrative basis remains research-only. Live API selection and scheduled pulls are not enabled.
- Use file hashes in normalized observation identity. Separate syntax, suffix-policy and numeric-root exclusion reasons and show representative excluded rows without silently changing existing defaults.
- Refine the Workspace priority queue, entity/contact queues, Assets, report-section controls and Activity around visible next actions, selection counts, saved context and expandable supporting detail. Improve responsive wrapping and contained table scrolling.
- Reorganize Settings with save-state feedback, edit preservation, separate backup/recovery controls and explicit destructive actions. Persist the header appearance choice through the existing settings API.
- Add named-dialog focus handling, keyboard editor tabs, mobile-drawer focus containment and dismissible bounded success notices. These are frontend changes; saved report formats and Python business rules are unchanged. Screen-reader, actual browser-zoom and native Windows acceptance remain pending; no WCAG conformance is claimed.
- Keep 0.8.0 as the last accepted stable baseline. Final automated results belong in VALIDATION.md; native Windows, live API/contact acceptance and publisher signing remain pending for this build.

# 0.9.0 — Bounded contact discovery · UNSTABLE

- Add lightweight discovery of published contacts from an entity's attributed website, without a third-party contact provider.
- Restrict requests to the approved hostname and accepted aliases, with a small request budget and bounded time and response sizes.
- Preserve source URLs, retrieval dates and the entity connection so a chosen outreach route has an explainable basis.
- Distinguish security contacts, general contacts and searches with no usable result; keep candidate adoption under explicit review.
- Add schema 8 records for discovery runs, candidates, retained sources and immutable review history. Workspace exports preserve the captured contact evidence.
- Begin a new unstable release. Version 0.8.0 remains the last accepted stable baseline; its acceptance is not transferred to this upgrade.

# 0.8.0 — Stable workspace controls and report reliability

- Promote the accepted build to stable on November 8, 2026 following Kyle's explicit confirmation; retain the same application behavior, dependencies and schemas.
- Add a per-report appendix option; keep compact source references when omitted and retain separate supporting-appendix documents for requests.
- Justify natural-language paragraphs in PDF and Word under a versioned document policy, preserving historical artwork until explicit format adoption.
- Export complete data backups, verify imports and stage import/reset operations for the next launch; keep the current workspace intact until a verified replacement can be applied.
- Offer a retain-data default and an explicitly confirmed fresh start in the Windows installer.
- Mark missing or prepopulated entity fields with a yellow Review required alert; retain value-specific confirm/ignore decisions and acknowledge deliberate edits.
- Remove the redundant mandatory website checkbox and duplicate passed-check list while preserving section validation and evidence integrity checks.
- Run attribution for a selected asset or all remaining assets, retain lookup evidence and explicitly adopt qualifying results through existing review guards.
- Name Google Public DNS accurately as a recursive DNS service and preserve exact response provenance; historical workstation evidence retains its original identity.
- Fix non-terminating appendix pagination and expensive long-value wrapping; surface preview failures and bound report operations with duplicate-submission protection.
- Preserve the next-day narrative receipt rule, original scan data and historical certified packages.

# 0.7.7 — Unstable narrative receipt-date correction

- Restore the opening receipt date in narrative v3 using the associated scan row calendar date plus one day, following the established reporting schedule.
- Preserve original scan timestamps and keep report/retrieval dates separate; retain explicit missing-date behavior.
- Preserve legacy, v1 and v2 generators and require logged adoption through existing section-freeze guards.
- Regenerate synthetic and real-data review examples offline and verify the narrow narrative/date change.
- Preserve dependencies, schemas, Windows installation identity and the unstable release channel.

# 0.7.6 — Unstable report finalization

- Integrate the reviewed notification pages, source references and organized appendix into report generation.
- Generate a consolidated narrative deterministically from structured records, including honest missing-version and receipt-date handling.
- Remove the closing Responsibility heading without deleting the established paragraph.
- Preserve prior certified packages and section-review history during layout adoption.
- Keep editor reads free of raster generation; capture artwork on section validation or export and return artwork metadata in editor responses while retaining complete verified masters in storage and report packages.
- Reduce recipient appendix repetition without dropping original scan values; retain full technical metadata in the saved source model.
- Store shared embedded font resources once per new exhibit with per-page content verification; preserve legacy artwork decoding and frozen bytes.
- Bundle the timezone fallback in the installed payload so report time conversion works without system IANA data.
- Retain the unstable channel pending native Windows confirmation; no source lookup requires an AI service.

# 0.7.5 — Unstable maintenance: persistence and browser lifecycle

- Extract case projections/scope/contact writes, entity mutations and source cache into caller-transaction repositories.
- Use read-only snapshots for multi-query entity/case and cache/proof views; pin Python transaction mode explicitly.
- Publish source reference/revision together; keep completed acquisition records if publication fails.
- Retain each provider response with its own captured source/attempt through enrichment, avoiding a later current-cache lookup.
- Move browser feature interactions out of navigation; retain a single delegated event owner with explicit cleanup.
- Make startup idempotent; stop stale bootstrap/poll/narrative/source-progress updates on teardown and coalesce import polls.
- Add concurrency/failure/lifecycle regression coverage and refresh the source map and IDE guide.
- Keep the build unstable pending Kyle's home confirmation; no new product features, dependency upgrades or schema migrations.

# 0.7.4 UNSTABLE — Lifecycle boundaries and IDE handoff

- Split section policy/fingerprints, review projections, persistence and commands.
- Extract SQLite workspace infrastructure, entity/artifact repositories, entity services,
  compatibility exports and interrupted-publication recovery from Store.
- Move certification into services and separate closing content/rendering from publication.
- Remove the lifecycle import cycle; prohibit lower layers from importing command services.
- Add release metadata that stays unstable until explicit, version-specific home confirmation.
- Label UI, launcher, installer, manifests and program map consistently; preserve numeric
  application version fields and existing installation/workspace identity.
- Include optional VS Code demo debugging, test tasks, navigation guidance and home checks.
- Preserve approved template bytes, transactions, schema versions and historical artifacts.
- Defer all new product features and source-explainer changes during maintenance.

# 0.7.3 — Internal modules and program map

- Separate intake records/readers/validation from the legacy CLI and job orchestration.
- Separate pure CVE normalization, captured source acquisition/cache and enrichment behind the existing facade.
- Move generic JSON/time/ID helpers out of Store and remove ECLIPSE's intake-worker dependency.
- Add a generated interactive source map, component registry, module guide and enforced import boundaries.
- Document the remaining case/review/certification cycle and staged repository/frontend extractions.
- Preserve database/renderer/source-policy versions, approved wording and historical records.

# 0.7.2 — Security and source integrity

- Protect sensitive local API reads, downloads and writes using launcher-established sessions.
- Enforce bounded source-response acquisition and clamp provider cooldowns.
- Validate screenshot types, preserve original evidence under neutral filenames, and constrain exports to manifest members.
- Correct supplementary CVSS citations and retain exact source revisions across offline report generation.
- Update dnspython and rebuild the standalone Attribution dependency and canonical wheel locks.
- Remove verified obsolete installer-owned program files before upgrade; retain workspaces and unlisted files.
- Preserve approved report language and historical certified artifacts; defer source explainers to a separate release.
- Retain explicit unsigned-installer and native Windows acceptance limitations.

# 0.7.1 — Stabilization

- Preserve all 57 existing API paths and schemas while extracting feature routes,
  draft services and explicit compatibility projections.
- Separate report snapshot, renderer, package and certification responsibilities;
  package path rewrites cannot mutate the caller's snapshot.
- Add internal report/intelligence contracts without dropping raw source fields.
- Replace frontend globals with application-owned state and native feature modules.
- Align source and installer Windows dependencies on Python 3.14 and canonical locks.
- Read VERSION in launchers; add formatting, lint and repeatable verification commands.
- Keep approved paragraphs, schemas, renderer identity and historical bytes unchanged.
- No new application features or security audit conclusions in this release.

# Changelog

## 0.7.0 — 2026-11-07

- Integrated Summary, Attribution, and Vulnerability exhibits with full native-text Companion Appendix after the closing/signature.
- Added Companion/USSS branding profiles, separate light/dark/system appearance, blue confirmation/red adverse semantics, and black report text.
- Added workspace-wide TLP:AMBER and top-right/bottom-right document markings, including appendices and internal reports.
- Added independent KEV, known ransomware, dated SSVC, source-supported impact, and EPSS records with source revisions and explicit adoption.
- Pinned the Shadowserver report inventory and introduced report-specific adapter metadata, critical-only lead eligibility, targeted inclusion reasons, and multi-product version preservation.
- Extended section review dependencies to full exhibit/appendix/source/presentation content, retaining frozen and certified historical artifacts.
- Tightened distribution allowlists to exclude working records and historical lookup/scan samples; bundled synthetic selection tests.
- Retained the existing Windows installation/workspace identity and offline dependency versions. The installer is unsigned; native Windows acceptance is recorded separately from cross-platform tests in VALIDATION.md.

## 0.6.0 — 2026-11-07

- Added ECLIPSE as the opening view, with navigation to the reporting workspace and back.
- Connected the observatory to original imported rows and current qualification/notification records, retaining excluded observations in its inventory.
- Added local geographic, density and shared-ASN views, source-row inspection, explicit unplaced observations and scan-date filtering.
- Bundled D3 and Census-derived map geometry for local rendering without external map requests.
- Preserved the report builder, approved template paragraphs, section freezes, certification history and existing Windows data paths.
- Retained database schema 6 and Attribution Module 0.2.1.

## 0.5.0 — 2026-11-07

- Renamed the product Shadowserver Companion, retaining existing Windows workspace paths and upgrade identity.
- Replaced raw attribution fields with explicit reported/validated IPs, a match explanation, source, actor, and separate decision/retrieval timestamps.
- Added section validation, frozen revisions, reasoned reopening, and an internal certification chronology.
- Simplified the interface to Scan Validation, Documentation, Pending Notification, and Closing Report, with Completed as an archive.
- Added a coordinated light/dark workspace, clear status indicators, readable typography, and reduced-motion support.
- Excluded entirely blank worksheet rows from rejected-observation counts.

## 0.4.1 development checkpoint — 2026-11-07

- Development checkpoint incorporated into 0.5.0: renamed the application to **Shadowserver Companion**, retaining existing workspace paths and launcher names for compatibility.
- Restored the user's approved paragraphs and fixed-token narrative generation.
- Reorganized the builder into five sections matching the report.
- Fixed the report addressee and sourced sender identity from Settings.
- Moved recipient contact/address details into an editable entity profile, with schema-5 migration and backups.
- Retained previous drafts and certified packages; case edits to approved prose cannot replace template wording.
- Kept standalone attribution and runtime dependencies unchanged.

## 0.4.0 — 2026-11-06

- Replaced mandatory screenshot certification gates with structured source evidence and recorded website/contact review.
- Added NVD-first descriptions, source-specific CVSS assessments, dated EPSS/KEV metadata, explicit fallback/status handling, and preserved source revisions.
- Added a shared report composition with numbered citations, a distinct-CVE table and quoted descriptions, all-group attribution on a new page, and optional exhibits.
- Added per-CVE official-text fallback/exclusion dispositions, pinned advisory text, case overrides, and template selections.
- Preserved working source selections across subsequent imports and business combination, and retained certified reports/delivery/closure history.
- Kept database schema 4 and Attribution Module 0.2.1; changes extend existing JSON records.

## 0.3.0 — 2026-11-06

- Added a separate self-contained Windows x64 EXE installer with CPython 3.14.10, current-user shortcuts, data outside the program folder, repeat-launch handling, and a file-inventory-based uninstaller that retains working records. Source ZIP launchers remain compatible with Python 3.12.
- Preserved consolidation of untouched intake groups when businesses are combined; cases with separate analyst histories stay separate.
- Added persistent notification cases beneath business entities, with separate observation membership, attribution, drafts, evidence, report revisions and history.
- Implemented five workflow stages in the dashboard and a filterable case queue, including due follow-ups and separate delivered/closed-without-delivery metrics.
- Tied certification to a specific report revision and analyst. Recipient information can be completed afterward; new content requires certification again.
- Added contact plans and append-only contact activity. Sent email remains pending; successful delivery names the recipient and current certified revision.
- Added internal closing PDF/DOCX reports and JSON chronologies, distinguishing recipient-reported and independently verified information. Finalized cases stay unchanged when later scans arrive.
- Added transactional schema-4 migration, retained legacy report/delivery history, startup recovery for interrupted closing commits, and closing packages in backups.
- Added report-package hash verification at availability/download/delivery boundaries, and workflow/recovery/migration/UI checks.
- Retained the standalone Attribution Module at 0.2.1 and the existing offline Windows dependency bundle.

## 0.2.2 — 2026-11-06

- Replaced startup schema patching with numbered, transactional workbench migrations through schema 3. Existing databases receive a backup; failed upgrades roll back and future schema versions are rejected.
- Removed duplicate hostname entity ownership. Added deferred foreign keys tying attribution entries, full observations, hostnames and entity assignments to the same domain group.
- Added direct job-to-attribution result references, backfilled earlier records, and checked cross-database result/domain identity at use boundaries.
- Added database constraints for workflow states, review decisions, flags and counters, plus indexes verified against entity/report/review query plans.
- Upgraded the independently installable Attribution Module to 0.2.1, database schema 2: indexed result metadata, filtered history/CLI queries, and consistency checks without rewriting raw evidence or saved result JSON.
- Preserved source files, entity IDs, archived drafts, report revisions, completed packages and both JSON export contracts.

## 0.2.1 — attribution fallbacks and analyst review

- Adds DNS association after exact RDAP matching: reported-hostname A/AAAA, then forward-confirmed PTR names under the same root.
- Retains any word overlap from registration network/entity names for analyst review. Partial matches never auto-qualify and never stop later exact-match attempts.
- Adds a dedicated review queue, matching-word highlighting, saved source response inspection, accept/dismiss decisions, explicit retries, and dashboard counts.
- Records the selected original row, analyst, timestamp, note, and immutable result ID. Acceptance qualifies the full group and promotes its supporting entry to `[0]`.
- Retains incomplete lookup attempts alongside partial matches. Repeated/stale decisions are rejected; retries preserve earlier results.
- Includes Attribution Module 0.2.0 and the dnspython wheel in the offline Windows dependency bundle.

## 0.2.0

- Integrated the independently installable Attribution Module into production intake. IANA bootstrap, authoritative RIR routing, bounded lookups, linked-entity handling, response caching, retry states and raw evidence exports now use the same implementation as the CLI.
- Separated observed hostnames and root-domain attribution groups from notification entities. Added entity renaming and combination with complete asset retention, archived drafts, and unchanged completed report history.
- Allowed CVE-only findings without a version; retained the version requirement for EOL/other findings. Region matching is case-insensitive. Numeric service labels are retained. Root digit and .com workload preferences are configurable.
- Added automatic CVE Program record verification after registration attribution, preserving source responses and timestamps. Failed or unavailable references remain reviewable. Manual reference refresh retains FIRST EPSS/CISA KEV retrieval.
- Added inspection/download of attribution evidence for unmatched groups, and raw registry/reference artifacts in completed packages.
- Added database migration with backup, attribution database backup support, schema-2 entity JSON, and upgrade-aware Windows launchers, and an offline hash-pinned Windows x64 Python 3.12 dependency bundle.
- Added labeled-sample evaluation and integration tests for migrations, entity merges, reference failures, response integrity, and the production RDAP adapter.

The workbench previously displayed `1.0.0` without a coordinated release sequence. This release standardizes the requested project version to **0.2.0**. The embedded standalone Attribution Module remains **0.1.0**, since its core code has not changed.

