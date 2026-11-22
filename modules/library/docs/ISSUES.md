# Library issues

Module-owned maintenance work belongs here. Last reviewed: **2026-11-22**.

[Maintenance guide](README.md) · [Project issue index](../../../docs/ISSUES.md)

[ISS026 reuse audit](../../tools/docs/ISSUES.md#iss026-reusable-tools-and-duplicate-capabilities)
includes Library's Retry-After parsers and known-ransomware aliases. Library owns
provider timing policy and risk meaning; the linked inventory owns audit progress.


Earlier completed maintenance checks are recorded in the
[November 21 validation](../../../docs/history/validation/maintenance-2026-11-21.md).
Later work and the Library audit retain their own scope and evidence below;
they do not inherit that batch's completion claim.

## Register

| ID | Work | Status | Owner |
| --- | --- | --- | --- |
| ISS016 | [Bulk feed deadlines and cancellation](#iss016-bulk-feed-deadlines-and-cancellation) | Resolved | Library |
| ISS032 | [Consistent intelligence and source provenance](#iss032-consistent-intelligence-and-source-provenance) | Resolved | Library; Accretion and Investigations consumers |
| ISS033 | [Explainer edits and revision history](#iss033-explainer-edits-and-revision-history) | Resolved | Library; Investigations and Activity consumers |
| ISS034 | [Reproducible catalog views](#iss034-reproducible-catalog-views) | Resolved | Library; Observatory navigation |
| ISS035 | [Catalog consistency and measured performance](#iss035-catalog-consistency-and-measured-performance) | Resolved | Library; Observatory projection contract |
| ISS036 | [Provider access and version comparison](#iss036-provider-access-and-version-comparison) | Resolved | Library |
| ISS037 | [Library ownership and interfaces](#iss037-library-ownership-and-interfaces) | Resolved | Library; Workspace and Investigations |
| ISS038 | [Research and reference workflow improvements](#iss038-research-and-reference-workflow-improvements) | Resolved | Library; affected workflow owners |
| ISS052 | [Catalog update status after a failed sync](#iss052-catalog-update-status-after-a-failed-sync) | Display corrected, installed TLS incident open | Library |
| ISS058 | [Find open notifications affected by an explainer correction](#iss058-find-open-notifications-affected-by-an-explainer-correction) | Closed, builder owns sync | Library and Investigations |
| ISS059 | [Report guidance and changes affecting open notifications](#iss059-report-guidance-and-changes-affecting-open-notifications) | Implemented for entity-based research, editorial coverage ongoing | Library, with Investigations, Observatory and Accretion interfaces |

## ISS059 Report guidance and changes affecting open notifications

**Current scope.** Library publishes reviewed explanations, attributable vendor statements, and distinct entity counts for reported CVEs and products. The ranking links to the entities behind each count. Repeated sightings at the same entity have equal weight to a single sighting. Open notification synchronization belongs to Investigations’ builder. [Maintainer guide](README.md#analyst-reference-workflows)

Maintained explainer wording identifies the reporting source, what it observed, and the evidence limits. Professional references support the technical interpretation. Recipient wording describes facts and uncertainty and leaves decisions with the recipient.

**Intake dependency.** Shadowserver publishes plain-HTTP Basic authentication examples with a finding tag and no software version. Accretion currently requires a version for a non-CVE Vulnerable HTTP row before admission. The Library guide is available offline. Whether these source rows should become notification work belongs to Accretion. A scoped acceptance case would use the documented HTTP report identity and exact finding tag while preserving version requirements for lifecycle claims. [Shadowserver report examples](https://www.shadowserver.org/what-we-do/network-reporting/vulnerable-http-report/) · [Intake validation](../../accretion/components/intake/validation.py)

### Find guidance by report family, tag or field

The pinned Accretion inventory describes 177 report IDs and 746 fields. Of the 26 IDs with admission adapters, 20 map to ten report-family guides and six have context entries. Library also publishes 13 explanations of specific findings. All are available through offline search by title, report identity, finding tag, or qualifying field. A guide links to its publisher sources and records the evidence needed to interpret the observation. [Accretion inventory](../../accretion/docs/REPORT_SCHEMAS.md) · [Reviewed Library bank](../components/reviewed_guides.py)

For example, Shadowserver documents plain-HTTP Basic authentication as a medium-rated finding within its Vulnerable HTTP report. The guide describes the challenge and the implications if a client supplied credentials. It makes no claim that credentials were sent or intercepted. [Shadowserver HTTP findings](https://www.shadowserver.org/what-we-do/network-reporting/vulnerable-http-report/) · [RFC 7617](https://www.rfc-editor.org/rfc/rfc7617#section-4)

### Show which vendor fix applies

I parsed revision 3 of Red Hat's machine-readable record for CVE-2024-8929. Its fixed entries include an Enterprise Linux 8.10 PHP package with upstream version `7.4.33`. A report containing only `PHP/7.4.33` leaves the distribution, package release and patch status unresolved. Show the vendor statement, exact product identity, revision, source and missing evidence side by side. Try one publisher using local advisory files before budgeting for a subscription or a multi-vendor integration. The acceptance pair is an ambiguous banner and a matching, independently documented package build. Only the latter can establish a match to that vendor statement. [Red Hat advisory data](https://security.access.redhat.com/data/csaf/v2/vex/2024/cve-2024-8929.json) · [Red Hat package dispositions](https://access.redhat.com/security/cve/cve-2024-8929) · [Red Hat backport policy](https://access.redhat.com/security/updates/backporting)

Measure analyst accuracy and time on the same synthetic cases before and after each pilot. Reserve remediation outcomes for operator confirmation or other documented verification. Shadowserver can omit a daily report when it observes no relevant activity in the subscription window. [Shadowserver reporting FAQ](https://www.shadowserver.org/faq/what-information-do-you-include-in-your-reports/)

## ISS058 Find open notifications affected by an explainer correction

**Closed by product decision.** Short-lived notifications already have a synchronization path in their builder. Library maintains reference revisions and citations. Investigations owns notification sync and any future automation of it.

## ISS052 Catalog update status after a failed sync

A Windows catalog retained locally stored records and a recent successful update, then recorded a TLS failure on its next NVD request. A complete catalog could still display **Ready** above that error. The summary now shows the latest update outcome, the last successful sync and the failed attempt time when available. A new NVD failure distinguishes a certificate verification error from other TLS connection failures and includes the numeric verification code when available.

A fresh Windows demo correctly showed **Not downloaded** but the Products panel
claimed indexing was finishing with zero CVEs. Products now shows index coverage
only when the catalog has records and its index is incomplete.

Before module reorganization, NVD used Requests directly. The shared streaming implementation uses the Requests proxy and CA settings with HTTPX. A loopback HTTPS comparison retrieved identical bytes through both transports with a trusted fixture certificate. Both rejected the untrusted fixture. The installed incident predates detailed TLS classification. Its precise cause requires a failure from the affected workstation.

## ISS016 Bulk feed deadlines and cancellation

[NVDTransport](../components/cve_catalog/transport.py) and
[RiskTransport](../components/cve_catalog/risk.py) previously used Requests' connect/read idle
timeouts. Their elapsed-time limits and cancellation checks ran between delivered
128 KiB chunks: 900 seconds for NVD and 300 seconds for EPSS/KEV. These checks did
not impose a hard total network deadline while response headers or a body chunk
were still arriving. A trickling response could therefore delay cancellation.

The saved pre-change transport control flow and controlled stalled-I/O
reproduction establish this defect. Individual intelligence captures already
used a bounded Attribution transport; bulk feeds required a streaming interface.

**Done when:** bulk feed retrieval has an explicit total deadline and bounded
cancellation during headers, body streaming and retries. Synthetic slow-header
and trickling-body regressions must verify timely interruption, response/worker
cleanup and retention of completed data without publishing a partial feed.
Preserve provider pacing, retry decisions, byte limits and source integrity.

**Resolved 2026-11-21.** Library now uses a
managed streaming interface added to the independent Attribution engine 0.2.7.
One deadline spans headers/body/pacing/retries/redirects. Shared bounded resolver
workers avoid abandoned transfer threads; a subprocess alternative would have
added credential and streaming IPC without improving this ownership boundary.
Library retains provider rules and Requests configuration compatibility. The
[current contract](README.md#bulk-catalog-transport) records supported encoding,
proxy and native-DNS limits.

**Demonstrated benefit:** baseline stalled-header/body workers remained alive
with responses open after 0.20 seconds until their gates were released. Updated
workers stopped in 0.055/0.064 seconds while gates remained blocked, closing the
response/client/loop. Independent real TCP probes observed closure after stop
(about 0.076 seconds) and a 0.4-second deadline (about 0.412 seconds). These are
measured synthetic results, not a universal latency guarantee. A manager-level
stop retains committed CVE data, removes staging and starts no subsequent
provider. Retained-traceback rejection also closes annual-feed generators.

Independent review covered decompression limits (a 4 MiB expansion rejected at
16 KiB with under 512 KiB traced allocation), proxy normalization/redaction,
ambiguous raw deflate, native DNS slot release and actual socket closure. The
existing capture/resolver definitions remain AST-identical. Final module checks:
322 Library/bounded-source tests and 185 standalone engine tests passed; the
engine run used Windows Python 3.14.10 with `PYTHONUTF8=0`. Python 3.11 syntax was
checked, but execution on that interpreter was not performed.

The 0.2.7 wheel matches all 17 engine source files, and the application and
standalone hashed locks agree. Exact commands, source hashes, before/after probes,
review and JUnit logs are in the Codex workspace's
`validation/maintenance-batch-02/iss016-*` bundle. This uncommitted change is based
on `efccc0a0f476bf83078b26694afa8fad0372047c`; it does not promote application
0.12.0 from candidate or establish native release acceptance.

## November 21 Library audit

The audit covers the module's 88 maintained files, including implementation,
presentation, tests, documentation, package markers and the requested empty
module folders. It also traces consumers in Workspace, Accretion, Observatory,
Entities, Leads and Investigations. The intended outcome is trustworthy local
vulnerability research and reusable, source-backed notification content.

This audit identifies work; it does **not** resolve the new entries below.
Application behavior was not changed. Reproduced defects, measured costs,
source-confirmed design concerns and proposed features are distinguished.

**Source and evidence:** Desktop repository
`Repositories/shadowserver-companion-main`, based on
`efccc0a0f476bf83078b26694afa8fad0372047c` with inherited uncommitted work.
Evidence lives in the Codex task workspace under
`validation/library-audit-20261121/`: the before/after file hashes, per-file
verdicts, `content-results.json`, `frontend-probes.json`,
`intelligence-probe-results.json`, catalog probes and focused-check logs.
All application probes use disposable synthetic data. Measurements are local
Windows Python 3.14.10 / SQLite 3.50.4 observations, not production guarantees.

**Verification limits:** 69 existing intelligence/source-adoption checks and four
portable frontend suites passed on unchanged application code. They do not cover
the reproduced gaps. One Library browser run ended before assertions when Edge
closed; its logs are retained as incomplete evidence, not application acceptance.
No full application build, full Library suite, live full-catalog import or real
casework inspection was performed.

**Preserve:** immutable captured provider evidence; pinned notification wording;
explicit case adoption; separate unknown, missing and negative assessments;
same-CVE critical/KEV matching; product candidates distinguished from observed
findings; existing FTS5 search; resumable, checksum-verified transfers and bounded
cancellation. Catalog and risk stores have different publication contracts and
should not be merged merely because their method names resemble each other.

**Recommended sequence:** repair intelligence correctness (ISS032), lost edits
(ISS033) and misleading views (ISS034); then batch local-processing, snapshot
and readiness repairs (ISS035). Apply ownership changes alongside the affected
responsibility (ISS037). Improve provider/version support (ISS036), then add
the purpose-focused workflows in ISS038. Use focused module checks and one
appropriate combined integration run per compatible batch. A build is not
required to finish this audit.

## ISS032 Consistent intelligence and source provenance

**Resolved 2026-11-21.** A pure NVD metric selector now supplies the same valid version/Primary assessment to catalog storage, local selection and Accretion. Local references and SSVC normalize once with capture identity; the reproduced duplicates fall from two to one. Latest refresh outcomes remain visible on later cached reads. Legacy selections are validated and reprojected from retained bytes; pinned source records are not rewritten. SourceRepository now owns transaction-taking selection/state queries used by Investigations. The synthetic disagreement now resolves consistently to High/7.5. See [batch verification](#repair-batch-verification).

**Problem — reproduced, high priority:** the same reference can produce different
severity, duplicated source claims and disappearing acquisition warnings.

- **Score selection depends on input array order.**
  [adapters.py](../components/intelligence/adapters.py) selects its first CVSS
  assessment, while catalog storage and Accretion prefer a Primary assessment.
  A synthetic NVD record with Secondary 9.8 followed by Primary 7.5 becomes
  Critical/9.8 in the local source selection and High/7.5 in the catalog and
  Accretion. Reversing the array changes the source selection to 7.5.
  Preserve every assessment and its publisher/type; share the pure technical
  selection policy and expose any deliberate consumer-specific override.
- **Local normalization duplicates provenance.**
  [local.py](../components/intelligence/local.py) derives references/SSVC before
  attaching capture identity; [selection.py](../components/intelligence/selection.py)
  then appends revision-bound copies. One raw reference becomes two normalized
  references, one with no source revision; SSVC is duplicated too. The probe's
  selected SSVC was bound, so it does not establish that every selected assessment
  loses provenance. Normalize once with the source identity and deduplicate by
  actual source location, preserving genuinely distinct assessments.
- **Failed refresh status disappears on the next cache read.**
  [service.py](../components/intelligence/service.py) retains `cve-refresh:*`
  after a deferred refresh, but ordinary cached verification reads the earlier
  reference without that outcome. The probe keeps the same source bytes/revision
  yet loses `stale`, `refresh_status` and refresh errors, and its `checked_at`
  moves backward. Keep retained evidence separate from latest attempt state;
  query both without rewriting the immutable source.

**Done when:** ordinary local and acquired records choose the same documented
assessment regardless of input order; every derived source claim has one valid
capture binding; a failed refresh remains visible on later reads until superseded.
Verify rendered Library details, adopted notification content and Accretion's
consumer result, not only adapter fixtures. Older pinned evidence remains intact.

## ISS033 Explainer edits and revision history

**Resolved 2026-11-21.** Explainer writes require the expected revision, retain full immutable wording/citations and emit Activity events in the same transaction. The editor preserves a conflicting draft and requires deliberate comparison/rebase. History, comparison, usage, archive/unarchive and restore-as-new-revision are available. Current citations read the retained revision rather than depending on an evictable cache. Schema 23 preserves the old current revision without inventing lost earlier wording; existing case and certified snapshots remain unchanged. See [contracts](README.md#content-and-research-contracts) and [batch verification](#repair-batch-verification).

**Problem — reproduced, high priority:** Library silently loses edits from another
window. Two clients read revision 1; both PUTs return 200; revision 3 contains only
the second client's stale wording. The API does not accept an expected revision.
The existing frontend guards protect edits made during one form's save, which is
a different problem.

[content routes](../components/routes/content.py) update the current row in place.
[content_bank.py](../components/content_bank.py) retains old citation metadata,
but not the previous unpinned title/body/sources. The probe also records no Activity
event for either edit. Reports that already captured a snapshot retain their text;
this finding concerns the editable Library history.

**Repair:** put transactional editing in a Library content service/repository;
compare the expected revision inside the write transaction; return a useful
conflict while retaining the user's draft. Use the application's existing revision
pattern or [HTTP If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1),
not a custom locking protocol. Retain immutable explainer revisions with their
citations and record creation/update/archive actions through Activity's contract.

**Related validation defect:** source strings `https:` and
`http:///missing-host` are accepted without metadata, while metadata URLs require
an authority. Use one HTTP(S) citation validator for both representations and
return field-specific errors. This is a citation-quality defect, not a demonstrated
network exploit.

**Done when:** a stale second save cannot overwrite a newer revision; earlier
wording and citation metadata can be inspected/restored as a new revision;
Activity explains what changed; malformed citations are rejected consistently.
Preserve certified and pinned report content. Add usage/archival presentation
after this persistence contract is reliable (ISS038).

## ISS034 Reproducible catalog views

**Field filter repair, 2026-11-22.** Selecting `weakness = CWE-79` produced
26 synthetic matches. Exploring Attack vector then paging or reopening the
saved or shared selection queried `attack_vector = CWE-79` and returned zero.
All three paths now retain the 26-match selection. The clicked row supplies its
field even while a new Fields request is pending. Existing links and imported
browser views continue to open. The Library browser suite also exercised the
reverse sequence and reopened both the saved view and its link in fresh windows.
An old link that already paired a value with the wrong field lacks the original
field name. Re-select the value in Fields to generate a corrected link.

**Resolved 2026-11-21.** Filter state survives sync, explicit all-severity URLs round-trip, saved views have stable IDs, clearing a product invalidates its pending response, and catalog/Dark Matter/explainer panels fail independently. Only active panels load. Delayed initial responses and polling update data regions without replacing a form being edited; stale navigation cannot rewrite the destination URL. Named views persist in the workspace with revision-checked rename/delete and idempotent legacy-browser import. The browser checks retain exact result-count assertions. The cross-module replay also exposed duplicate canonical/archive observations, repaired under [Observatory ISS045](../../observatory/docs/ISSUES.md#iss045-duplicate-canonical-and-archive-observations). See [batch verification](#repair-batch-verification).

**Problem — six actual-module frontend reproductions:**

| Finding | Observable failure | Repair direction |
| --- | --- | --- |
| F04 · high | A sync completes while viewing CWE-79. The label still says CWE-79, but ordinary unfiltered search results replace the field results. | Refresh through the current selection's loader, retaining field/product/scope semantics. |
| F01 | An All severities share link opens as Critical-only in a fresh instance. | Preserve explicit empty severity in native URLSearchParams; distinguish omitted defaults from selected values. |
| F02 | Saving Apache/HIGH and Exchange/CRITICAL leaves only the second view. | Give saved selections stable identity independent of their display label; make replacement intentional. |
| F03 | Clear a product while its detail request is pending; the old dossier reappears with no selected product. | Invalidate the pending request generation on clear as well as on replacement. |
| F05 | An unavailable NVD search prevents a directly requested Dark Matter view from opening. | Restore navigation first and load the archive independently through Observatory. |
| F06 | An explainer read failure prevents any catalog request or display. | Give explanation and catalog panels separate loading/error states. |

Owners: [cve_catalog.js](../static/cve_catalog.js),
[catalog_library.js](../static/catalog_library.js),
[resources.js](../static/resources.js). The reverse failure was checked:
catalog rejection already allows explainers to render; do not remove that behavior.

**Done when:** shared/saved selections restore the same result membership;
background refresh preserves the displayed filter; stale requests cannot revive
cleared selections; one unavailable data source does not disable an independent
Library task. Exercise fresh and reused navigation state, asynchronous completion
orders, and actual results alongside labels. Existing portable tests pass despite
these defects and need the reproduced cases added during repair.

## ISS035 Catalog consistency and measured performance

**Resolved 2026-11-21.** Catalog read-only connections use one snapshot for counts and page rows; explicit initialization remains at writable maintenance boundaries. Index jobs distinguish ready, partial and empty coverage. The covering modification/ID index replaces the redundant single-column index. Each local batch validates/indexes its captured KEV feed once: the 1,000-selection probe fell from 15.275 s to 0.02384 s with unchanged evidence semantics. Same-fixture 100,000-record browse fell from 17.909 ms to 8.037 ms and exact lookup from 9.208 ms to 4.201 ms (medians, 2,000 KEV entries). Broad FTS, product filters and fields were essentially unchanged. Retain FTS5 and the current joins; measurements do not justify speculative caches or a second search system. The isolated 1,000-observation outreach projection measured 27/42 ms for CVE/product selection, excluding the real Observatory database projection; that limit remains explicit. See [batch verification](#repair-batch-verification).

**Correctness — reproduced:**

- [storage.py](../components/cve_catalog/storage.py) reads search count and rows
  without one explicit read transaction. A concurrent committed insert produced
  `total=1` with two returned rows. The same probe with `BEGIN` returned one
  consistent snapshot; the next read saw both records. Use SQLite's ordinary
  [read-snapshot behavior](https://www.sqlite.org/isolation.html).
- [analytics.py](../components/cve_catalog/analytics.py) records an index error,
  while [manager.py](../components/cve_catalog/manager.py) reports
  "Product index is ready". A malformed synthetic record produced indexed=0,
  errors=1, ready=false and a completed/ready job message. Surface partial/error
  completion and a useful record-level repair/retry path. Never certify coverage
  just because the worker returned.

**Speed — measured or traced:**

- **Highest-value measured repair:** local KEV processing in
  [local.py](../components/intelligence/local.py) parses and validates the same
  captured feed per CVE. A 1,500-entry / 417,108-byte synthetic feed took 1.44 s
  for 100 CVEs and 15.28 s for 1,000, excluding capture I/O and networking.
  Parse, validate and index it once per immutable batch snapshot; preserve its
  hash, completeness and provenance. Reuse the result across local batch callers.
- **Unnecessary serial requests:** opening Changes currently requests status,
  ordinary CVE search, products, then changes in sequence. Load the selected panel
  first, lazy-load inactive panels, and parallelize necessary independent reads
  with separate failure states. Keep status polling independent of editor state.
- **Catalog scale:** synthetic 100,000-record probes retained fast exact lookup
  (~9 ms) and ordinary browse (~18 ms), while broad text search was ~294 ms,
  product filtering ~203 ms and field aggregation ~115 ms. These are bounded
  local probes, not a complete NVD-sized or production-workspace benchmark.
  Review query plans and sort indexes before adding caching or another search
  system. Existing queries already use compact indexes and FTS5.
  An audit-only `(modified DESC,id DESC)` index improved a tied-date 10,000-row
  browse from ~31 to ~11 ms, and the larger spread-date case from ~18 to ~14 ms.
  Review its storage/write cost and the product filter's forced CROSS JOIN before
  choosing the production change; the latter is a tuning candidate, not proof
  that removing the join-order constraint is always better.
- **Lower priority:** alias-per-product reads and selected raw-record reads exist,
  but the alias overhead measured about 2 ms in the larger fixture. Explainer
  snapshots read 1,001 small SELECTs for 1,000 rows in ~14 ms. Query count alone
  is not a material defect in embedded SQLite; see its
  [small-query guidance](https://www.sqlite.org/np1queryprob.html).
- **Needs measurement:** [catalog_outreach.py](../components/catalog_outreach.py)
  traverses Observatory's full snapshot before paging, and a version comparison
  reloads the same observation summary. Profile representative retained volumes;
  reuse unchanged detail and request a bounded filtered projection from Observatory
  if needed. Library must not duplicate Observatory's normalization or SQL.

Catalog readers currently pass through writable initialization. Separate explicit
initialization/migration from reusable read snapshots when changing this boundary.
The audit's read during an active writer succeeded (~11 ms); it did **not** prove
that current reads are generally blocked. KEV join integrity is already checked
within its read snapshot and must survive any optimization.

**Done when:** counts/results share one snapshot; index status truthfully describes
coverage; a local batch validates each captured feed once and materially reduces
elapsed time with identical evidence; inactive panels cause no initial data work.
Retain before/after query plans and timings, result identities and provenance.
Choose further query changes from representative measurements, not file size or
arbitrary latency assertions.

## ISS036 Provider access and version comparison

**Resolved 2026-11-21.** Normal public annual-feed bootstrap and anonymous incremental updates no longer require an NVD key; explicit full API enumeration still does. Provider pacing, cancellation, checksums and publication remain enforced. Declared SemVer uses the maintained `semver` package for prereleases, build metadata, ranges and status transitions. Product indexing now retains initially unaffected ranges that later become affected/unknown; analytics schema 3 rebuilds existing derived memberships without changing source bytes. Unsupported schemes/configurations remain unresolved. The audited final-property streaming parser is retained: no current provider failure justified replacing it. A full live multi-year feed download was not performed; the normal feed/import/publication path was exercised with synthetic provider responses. See [batch verification](#repair-batch-verification).

**Existing policy limits availability:**
[Catalog._sync](../components/cve_catalog/catalog.py) requires an NVD key before
the normal initial annual-feed download. This is deliberate current behavior,
including a test, not an accidental regression. The feed transport does not send
that key, and the official [annual feed metadata](https://nvd.nist.gov/feeds/json/cve/2.0/nvdcve-2.0-2026.meta)
was readable without one during the audit. Allow public feed bootstrap without
requiring credentials; keep API credentials, provider pacing, retry guidance and
daily-update choices explicit. Update Settings/user instructions and the stale
expectation test as part of the behavior change. A full live feed import was not
performed by this audit.

**Limited/custom version comparison:**
[products.py](../components/cve_catalog/products.py) uses a numeric tuple parser
and a short product allowlist. Even `versionType=semver` uses that parser:
a valid prerelease is unresolved, while a four-component value can be treated
as a candidate. Its conservative unknown result is preferable to an invented
applicability claim, but it leaves ordinary research cases unsupported.

Use maintained scheme-specific comparators for declared version types, starting
with [SemVer](https://semver.org/) and representative reported products. Respect
the [CVE record format's version rules](https://cveproject.github.io/cve-schema/schema/docs/),
including status changes/defaults and source configuration conditions. Keep
unsupported schemes visibly unresolved; do not invent a universal natural-sort
version algorithm or equate a version candidate with an observed vulnerability.

**Done when:** a fresh installation can bootstrap public reference data without
an unrelated key prerequisite; valid supported prerelease/build/range cases work
against the scheme's reference implementation; malformed versions and unresolved
configuration conditions remain distinguishable. Verify normal provider behavior
and useful product research outcomes, not only accepted parser inputs.

**Provider-parser review, lower priority:** the custom annual-feed parser in
[streaming.py](../components/cve_catalog/streaming.py) requires the vulnerabilities
array to be the final top-level property. That is narrower than JSON's ordering
rules, but the audit did not demonstrate a current provider failure. Before
expanding this parser, compare an established incremental JSON parser against the
existing bounded-memory, duplicate-key, checksum and cancellation contracts.
Do not replace a working feed path solely because it contains custom code.

## ISS037 Library ownership and interfaces

**Resolved 2026-11-21.** Investigations now owns the notification source UI and report-layout preview. Library owns unchanged default/report/finding text assets and pure selection identity; case adoption consumes SourceRepository interfaces instead of Library storage keys. The preview uses current release identity and explicit sample-profile text. The existing native credential implementation exposes a public byte-store interface, with its original vendored baseline and exact local patch retained. Removed the test-only JSON forwarding wrapper. Reviewed the shared evidence registry and kept its single immutable persistence contract, historical IDs, digests and backup integration; no duplicate registry was created. Analytics stays cohesive around its explicit connection/index contract rather than being split mechanically. Distribution now explicitly includes the moved content banks and the credential patch/baseline; copied installed payloads import and start successfully. See [ownership](README.md#source-ownership) and [batch verification](#repair-batch-verification).

**Source-confirmed maintenance concerns:**

- The former Library source UI, now [Investigations source_intelligence.js](../../investigations/static/source_intelligence.js), owned notification selection,
  draft mutation, frozen-section/revision guards, modal lifecycle and adoption.
  These belong in Investigations. Library should return reusable reference
  results and render domain-only evidence; Investigations owns their application
  to a particular notification. Preserve existing explicit Load local CVEs behavior.
- Explainer defaults live in
  [Workspace defaults](../../workspace/databases/workspace_defaults.py);
  report-family and finding content banks live in Investigations. Consolidate
  reusable wording/citation assets under Library while keeping case-specific
  selection, recipient layout, approvals and pinned adoption in Investigations.
  Preserve existing IDs, bytes and revision identities during relocation.
- [export_explainer_templates.py](../../investigations/tools/export_explainer_templates.py) is a
  report-layout preview using Investigations' bank/renderers, not an export of
  editable Library records. Move the command to the report owner or clearly
  separate that purpose from a future Library content export. Its fixed legacy
  product/office labels also need an explicit sample-profile treatment.
- Investigations' draft service queries Library's `cve-reference`,
  `intelligence-latest` and `intelligence-version` storage keys directly.
  Extend [SourceRepository](../components/repositories/sources.py) with narrow
  transaction-taking queries. Investigations should retain adoption decisions
  without knowing Library's storage-key conventions.
- Library's source repository and index import Investigations' shared evidence
  registry. Review captured-revision storage as a shared persistence contract,
  separately from case workflow; do not create a second registry. A move requires
  preserving evidence digests, migrations, exports and historical key identities.
- [credentials.py](../components/cve_catalog/credentials.py) reaches into a private
  Accretion Windows credential adapter. Give reused OS credential access a stable
  shared interface if this boundary is changed; NVD key validation, targets and
  session policy remain Library-owned. Do not duplicate native credential code.
- [content_validation.py](../components/cve_catalog/content_validation.py) retains
  `decode_json_object`, a production forwarding wrapper used only by tests.
  Remove the unused wrapper when repairing that boundary and test real provider
  consumers or Workspace's canonical strict JSON helper directly. Retain the
  file's actively used feed-format and compressed-prefix validation.
- [analytics.py](../components/cve_catalog/analytics.py) spans index schema/build,
  risk joins, product/field queries and change history. Split those responsibilities
  only alongside a concrete repair and a clear internal query/connection contract.
  Keep the useful cve_sources facade, pure adapters, source jobs, routes and
  render/controller separation; fewer files is not by itself an improvement.

**Done when:** Library owns reference meaning/content and publication; consumers
request explicit inputs/outputs and retain workflow decisions. Moving a file must
remove its former implementation and preserve external behavior, persisted evidence
and consumer results. Do not add forwarding layers or a generic helper collection
solely to make the import graph look simpler. Empty boilerplate folders requested
for modules are intentional and are not counted as defects.

## ISS038 Research and reference workflow improvements

**Search coverage repair, 2026-11-22.** In a fresh workspace, searching for
“Detected CVE” used to show “No matching references” for both CVEs and products.
Those groups now explain that no CVEs are stored locally, alongside the matching
bundled explainer. With one of two local CVEs indexed, a matching product remains
selectable and the notice reports coverage of one of two records. Clearing a
pending search also clears its accessibility busy state.

**Verification for the November 22 search and field-filter repairs.** On Windows
with Python 3.14.10, `python -m pytest -q modules/library/tests` passed all
361 tests in an isolated run. `npm test` passed all 70 portable frontend suites.
The `library` and `catalog-scope` browser groups passed all four scripts with
synthetic data. The program map, scoped Ruff and Prettier checks passed.
An earlier Library run wrote 361 passing JUnit cases and then exited nonzero
without a summary. A separate application-startup failure and its HTTP contract
rerun are recorded under [ISS048](../../../docs/ISSUES.md#iss048-full-run-runtime-reliability).

**Resolved 2026-11-21.** Library now provides grouped local CVE/product/explainer search, named workspace research views, a concise source-review summary and complete explainer maintenance lifecycle. Changes can list affected active/completed cases through an Investigations-owned, bounded read query and compare retained source content and explicit KEV membership with current local references. Source dates, digest identity, stale warnings and unknown negative membership stay visible. Missing proof stays unknown; reviewing a change never adopts data or edits certified content. Bundled starting text, locally edited bundled text and analyst-created wording are distinguished. Usage is explicitly current-case selection usage, not a claim to inventory every historical report archive. See [contracts](README.md#content-and-research-contracts) and [batch verification](#repair-batch-verification).

**Proposed features, in recommended value order:**

1. **Changes that affect current work.** Extend the existing Changes view with
   affected findings and active notifications, the older pinned/current reference,
   and a concise reason to review. Include changed rejection, exploitation,
   affected-version and remediation information. Library supplies the change;
   Investigations owns review/adoption and Workspace can surface pending work.
   Success: an analyst can find and review affected work without opening every case;
   certified content never changes automatically.
2. **One source-review summary.** Present source revision, publication/retrieval
   dates, freshness, supported severity assessment, EPSS probability/percentile,
   KEV membership, reported observation and applicability uncertainty together.
   Reuse existing source/raw-record details and observed connections. Distinguish
   unknown/stale/conflicting evidence; follow [FIRST's EPSS guidance](https://www.first.org/epss/articles/prob_percentile_bins)
   rather than inventing an unexplained combined risk number. Success: an analyst
   can explain each displayed claim and reach its captured source.
3. **Maintainable explainer lifecycle.** On ISS033's revision foundation, add
   comparison, usage links, archival and deliberate restoration/adoption. Keep
   approved bundled text distinguishable from analyst-authored text. Success:
   obsolete wording stops being offered for new work while historical reports
   remain reproducible.
4. **A unified research entry point.** Search CVEs, products and explanation
   titles together with clearly typed results, then enter the existing detailed
   views. Keep text hits distinct from observed exposure evidence. Add named,
   workspace-backed saved views after ISS034 so useful selections survive backup
   and browser changes. Success: find and reopen the same research question
   without manually reconstructing filters.

Existing raw-source views, risk dates, product comparisons, saved views, change
history and observed connections already provide useful foundations. These
proposals extend them; they are not claims that those features are absent.
Implement one measurable workflow at a time, beginning after the correctness work.

## Repair batch verification

**Completed 2026-11-21 against the actual Desktop repository.** Detailed commands,
source manifests, failed attempts and results are retained in the external
`library-repairs-20261121` validation directory; `library-audit-20261121` retains
the before-change evidence. These are synthetic local results, not provider-wide
or release-acceptance claims.

| Verification | Actual result and scope |
| --- | --- |
| Complete Library + Observatory Python suites | 509 passed on a frozen validation copy; Library/Observatory application files matched the real repository |
| Combined caller/persistence/dependency batch | 602 passed, 3 skipped, 20 subtests passed; four historical-schema fixture failures were corrected and the full registry file then passed all 16 checks |
| Workspace upgrade and transfer | Current wording/citations preserved from schema 22; interrupted schema 23 rolls back; real export/restore retains named views, archive state and immutable history |
| Frontend | 70 portable suites passed; final narrow navigation guard passed its module/cancellation checks; both Library browser scripts and five Sources checks passed |
| Native workflow review | Two-window editor conflict/rebase, comparison, restore/archive, usage and Activity checked; catalog-scope browser passed all seven checks on the retained eight-row fixture, with normal local index rebuild after analytics upgrade |
| Distribution | Five packaging/privacy checks passed; actual copied installed payload contains the moved assets, imports their content and serves the new authenticated Library routes |
| Integrity and dependency review | Scoped Ruff passed; reviewed wheel lock/hashes and advisory audit passed (34 public packages, no known advisories); program-map and documentation-link checks retained alongside the source manifest |

Concurrent Accretion refactoring changed intake contracts during a fresh-fixture
run, producing 14 failures after 495 passes. That failed evidence is retained.
An immutable validation copy removed moving-source ambiguity and passed all 509
Library/Observatory checks. The final native catalog-scope replay used the same
previously imported eight-row fixture; it does not claim a new live import. No
unrelated in-progress source was overwritten. Historical overwritten explainer
wording, every archived report's usage and a full live multi-year NVD import remain
outside the demonstrated coverage. No full installer build or release acceptance
was performed.

The subsequent [full-build record](../../../docs/history/validation/full-build-2026-11-21.md)
covers the maintained explainer lifecycle browser check and fresh catalog-import
integration. It also records unresolved cross-project runtime validation findings;
the Library repair batch does not imply complete release acceptance.

## Shared work and dependencies

| Canonical item | Library involvement |
| --- | --- |
| [ISS004 Workspace facades and models](../../workspace/docs/ISSUES.md#iss004-workspace-facades-and-models) | Own source-job and reference-update request validation |
| [ISS006 Library editing in Settings](../../settings/docs/ISSUES.md#iss006-library-editing-in-settings) | Receive the editor implementation and define its interface with Settings |
| [ISS003 Shared test fixtures](../../../docs/ISSUES.md#iss003-shared-test-fixtures) | Keep provider fixtures reusable without importing another test by bare name |
| [ISS008 Browser suite coverage](../../../docs/ISSUES.md#iss008-browser-suite-coverage) | Review catalog/Library browser scripts and their data setup |
| [ISS009 Explicit resource encoding](../../../docs/ISSUES.md#iss009-explicit-resource-encoding) | Review repository resources without changing provider-input semantics |

Use the [project tracking rules](../../../docs/ISSUES.md#maintaining-this-register).
Update a shared item's canonical record rather than copying its status here.
