# Shadowserver Companion 0.9.0 · UNSTABLE

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

Verified November 9, 2026 (UTC). This feature upgrade awaits version-specific
acceptance; 0.8.0 remains the last accepted stable release. Automated checks do
not promote a release. Current results below apply to 0.9.0. The archived 0.8.0
notes afterward describe that baseline and its release metadata only.

## Contact discovery scope

- Discovery starts only from an entity root backed by retained, supported attribution evidence, with an explicit optional `www` alias. It does not derive new businesses from an IP address or use third-party contact providers.
- Six total HTTPS attempts include redirects. The homepage, plain-text `security.txt` and selected direct homepage links share a 30-second deadline, eight-second request limit, 1 MiB page limit, 3 MiB total body limit and 50-candidate ceiling. Visible HTML is supported; PDF and JSON-LD extraction are deferred.
- The transport checks every resolved address, rejects nonpublic destinations, pins the public connection while preserving the original TLS hostname, and disables ambient proxies, cookies and authentication. Off-scope redirects stop for review; no recursive crawling, form submission or messages occur.
- Candidates retain captured source bytes, SHA-256 hashes, excerpts, retrieval times, attribution references and distinct discovery/reviewer status. Public listing is not evidence of deliverability, asset responsibility or successful notification. Confirm, Ignore and Return to review remain explicit value-bound decisions.
- Jobs support progress, cancellation, duplicate protection and finite completion. Refresh preserves prior evidence and decisions; incomplete searches do not treat unseen candidates as conclusively absent. Explicit use fills blank contact-plan fields and preserves populated manual values and frozen reports.
- Schema 8 adds discovery runs, candidates, source associations, review history and transient job locks. Workspace export/import checks the retained contact evidence. Contact evidence integrity helpers sit below workflow so acquisition, records and backup validation remain acyclic.
- The separate Shadowserver API module is not connected by this upgrade. No live business contact searches were performed for this verification.

## Executed automated checks

All **950 final collected backend tests** passed in the complete sharded run or
final targeted reruns, with **29 passing subtests** and no unresolved failures.
This is not a claim of one uninterrupted 950-test invocation.

The broad run collected 948 tests: 945 passed and three synthetic legacy-schema
fixtures failed because their simulated downgrade retained the new schema-8
tables. Those fixtures now remove the empty contact tables before marking their
workspace as schema 4, 5 or 6. All three reruns passed; production migration
integrity was not relaxed. The final contact suite passed 72 tests, including two
bounded evidence-read regressions added after the broad collection. The complete
collection and reconciliation are recorded in `final-validation.json` and the
accompanying test logs.

All **13 frontend module suites**, frontend syntax/format checks and global Python
Ruff lint/format checks passed. **Four existing browser suites** and **nine contact
browser check groups** passed in Chrome Headless Shell 145 with Playwright 1.62.1
on Linux. The contact run used the real engine, local API, persistence and browser
workflow against synthetic website responses. It recorded zero page errors and
zero external browser requests. Tests covered source explanation copying,
evidence download, review/adoption, refresh, cancellation and navigation cleanup.
The standalone feature guide was also rendered and inspected at desktop and
mobile widths without clipping or horizontal overflow.

Focused tests cover host and redirect boundaries, public-IP pinning and TLS,
request/byte/deadline limits, malformed and oversized content, conservative role
classification, security.txt expiry/canonical checks, stale revisions, preserved
manual/frozen data, attribution scope changes, merging, evidence tampering,
backup/restore, job recovery and escaped browser content. Captured restored
responses are size-bounded before hashing. Release/privacy/installer checks also
passed; the generated source map contains 17 components, 198 owned modules and no
cycles or boundary violations. All 34 pinned dependency artifacts retain their
verified hashes; no dependency upgrade is included.

## Upgrade and restore from accepted 0.8.0

Unmodified 0.8.0 source created a synthetic schema-7 workspace containing three
saved reports and 15 section validations. Both direct upgrade to 0.9.0/schema 8
and opening a separately restored backup passed offline. Each path preserved all
342 protected files and protected database rows, verified 15 historical download
hashes, and retained all 15 validated section displays. Contact attempts,
closures, appearance and historical report bytes remained unchanged. The result
is recorded in `upgrade-acceptance-result.json`; synthetic workspaces and large
backup files are excluded from the distribution evidence package.

## Distribution and remaining workstation checks

The source and installer builders enforce release identity, dependency locks,
source ownership and the shared program-file privacy allowlist. Distribution
verification compares source ZIP members and extracted installer payloads with
their SHA-256 manifests and the final reviewed source. The evidence package holds
the actual build hashes, extraction/parity results and Linux source smoke checks.
No working records, generated test workspaces, launcher state or credentials are
included in either distribution.

The installer is an unsigned Windows x64 NSIS package with the unchanged pinned
Python 3.14.10 runtime. Native Windows installation, a desktop Microsoft Word run
and live-business contact discovery were not executed in this environment.
Linux browser tests, payload inspection and source smoke tests do not establish
those outcomes. `HOME_VALIDATION.md` records the remaining workstation review;
`RELEASE.json` remains unstable with no 0.9.0 home confirmation.

## Historical baseline · 0.8.0 STABLE

Automated verification performed November 8, 2026 (UTC). Kyle explicitly accepted version 0.8.0 for stable release on November 8, 2026 (America/New_York): “Everything seems good to me. We can mark stable.” `RELEASE.json` records that acceptance. The promotion changes release metadata, release documentation and distribution labels; application behavior, dependencies, schemas and report examples remain unchanged. Individual native Windows and desktop Word check results were not separately supplied and are not inferred.

## Scope

- Settings exports a complete checksummed workspace, verifies backup imports and stages import/deletion for the next launch. Staging can be cancelled; active work is gated before a swap. Data migration is schema 6 to 7.
- Installer keeps existing data by default and offers a separately confirmed fresh start. The reset helper has a fixed application-data target, rejects links/junctions, and clears any pending import that could otherwise restore removed records.
- Missing and prepopulated business name/address fields display informational yellow review text. Confirm/Ignore decisions apply to their exact values; deliberate nonempty edits confirm the field without another step.
- The redundant mandatory website checkbox and duplicate passed-check list are removed. Section review, source integrity, citation integrity and frozen-content protection remain.
- Assets support individual or remaining-asset attribution, cancellation, saved evidence and explicit adoption into editable cases. DNS proof remains scoped to its checked hostname. Merges retain lookup history.
- Attribution 0.2.3 uses Google Public DNS over HTTPS for new DNS lookups. It stores the exact response, query URL, retrieval time and hash. Google is identified as a public recursive resolver. Historical workstation DNS evidence retains its actual identity.
- Reports can include the appendix or retain it as separately downloadable PDF and Word documents. Omission keeps concise references in the recipient report and adds “The full supporting appendix is available upon request.” to the closing footer. The selection participates in section freeze protection.
- New reports justify paragraph prose in PDF and Word, including source descriptions, advisory lists, caveats and appendix explanations. Final lines, headings, signatures, raw records and compact data values retain normal spacing. Prior document policies remain pinned until explicit format adoption.

## Report stall findings

Two renderer failures were reproduced with synthetic inputs: an appendix heading leaving no space for source text could make pagination loop without progress; long unbroken field values repeatedly measured the entire remaining string. Oversized repeated labels now stop with a clear error rather than looping. Bounded prefix measurement and linear font-run construction preserve existing line breaks; a 100,000-character fixture improved from more than 10 seconds to approximately 0.12 seconds in focused testing.

PDF preview no longer generates unused raster masters. A deterministic regression confirms identical PDF bytes for editable geometry, frozen masters and the previous prepared-page rendering path. Existing master hashes still protect frozen geometry. Freeze artwork is prepared outside the workspace writer lock, then the draft revision and complete source dependencies are rechecked before committing.

Preview, validation and certification use duplicate-action protection, visible errors, a 120-second client request bound and cooperative 110-second server preparation checks. Client timeout does not claim an already-submitted mutation was rolled back and never automatically retries it. Navigation or later typing cannot be overwritten by a delayed response. Closing preview uses the same bounded request helper.

These are reproduced causes and verified fixes, not proof of the precise trigger in Kyle's original failing report; that report should be retested on the Windows workstation.

## Executed automated checks

The final verification covers all 878 unique collected backend tests and 29 subtests, with no backend failures or skipped nodes. A complete three-shard pass and 112 focused final tests cover the later formatting and appendix changes; exact collected-node reconciliation is included in the validation evidence. All 12 frontend module suites, four Chromium suites, formatting checks and architecture boundaries passed. One browser-test attempt exhausted temporary disk storage while exporting a complete synthetic workspace; completed test workspaces were removed and the complete frontend run passed on retry.

Targeted checks additionally cover data round trips, corrupt/missing references, archive traversal and Windows device paths, interrupted swap recovery, confirmation/cancellation, entity value binding, merge behavior, per-asset scope and evidence adoption, preserved report bytes, timeout/error recovery, concurrency and unsaved-edit handling. Network-facing providers are tested with controlled responses; no live target attribution is performed by the test suite.

The approved template SHA-256 remains:
`3b139d987f9e83e97f289b45b69f8b755a06bda1b495452697c59bc8d494d1d3`.

The 0.7.7 narrative receipt rule remains source-row calendar date plus one day. Original scan timestamps and historical narrative revisions remain unchanged. No AI generation service is required.

## Real supplied report check before formatting updates

The supplied Wasabi sample generated a 49-page production PDF preview in 0.178 seconds without raster capture. Its section artwork capture took 5.456 seconds total and its frozen preview took 0.219 seconds in this environment. All page text, decoded PDF content streams, geometry and 25 distinct external link targets matched 0.7.7. All 12 original input files remained unchanged. This check caught and corrected a compatibility issue distinguishing historical normalized Google DNS records from new raw Google JSON responses. It uses the production composition/render/capture functions; the Store-backed validation API is covered by synthetic tests.

## Upgrade and recovery evidence

Unmodified 0.7.7 created a synthetic workspace. Version 0.8.0 opened that workspace and a separately restored backup with network access blocked. Both paths retained all 341 protected files and all protected database rows, verified 15 historical downloads, and kept 15 section-validation displays validated. The new schema adds review and asset-lookup metadata without rewriting saved report packages.

The upgrade and restore phases were repeated after the appendix and justification changes. Historical artifacts and section validation remained unchanged.

## Final report examples

The supplied Wasabi report renders as 49 pages with the appendix, seven pages without it, and a separate 43-page supporting appendix. PDF and LibreOffice-rendered Word exports have matching page counts, body characters and link targets. Its narrative begins “On November 6, 2026” from the November 5 source row; all 12 original input files retain their hashes. Compound source fields containing multiple URLs remain literal source text rather than one invalid hyperlink.

The bundled synthetic examples use the current document policy and clearly identified Google Public DNS fixtures. They contain 30 and 47 pages respectively. Native PDF and LibreOffice-rendered Word pages are inspected at full resolution; exact image hashes permit reuse of unchanged-page inspections after narrow formatting corrections. The rendered Word checks used LibreOffice. Native Microsoft Word was not independently executed in this build environment.

## Distribution and limits

Source and installer builders enforce release identity, source-map ownership and offline dependency integrity. Attribution 0.2.3 is the only package version change; its wheel hash is `ce260a20eea28cc6642e08f8b50802943584ee1e0e2f3f88af909894a61a2ae3`.

The installer is an unsigned Windows x64 NSIS package built cross-platform. Payload extraction, file manifests, retained-data overlay simulation, installed-source smoke checks and timezone fallback are automated checks; they do not establish native Windows installation or desktop Word behavior. `HOME_VALIDATION.md` retains the workstation checklist and the explicit user release acceptance; it does not claim individual test outcomes that were not supplied.

TLP:AMBER

