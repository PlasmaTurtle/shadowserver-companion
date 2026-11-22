# Library maintenance guide

Library owns local CVE and risk catalogs, provider intelligence capture/parsing,
reference content, source revisions, catalog search and reference-data tools.
Use this guide to locate maintenance work and preserve its evidence contracts.

[Module issues](ISSUES.md) · [Changelog](CHANGELOG.md) · [Architecture](../../../docs/ARCHITECTURE.md) ·
[Project maintenance workflow](../../../docs/DEVELOPMENT.md#maintenance-workflow) ·
[Library selection](../../../docs/DEVELOPMENT.md#library-selection)

The [November 21 audit and work sequence](ISSUES.md#november-21-library-audit)
records reproduced correctness problems, measured performance, ownership repairs
and proposed workflow improvements. Status and completion criteria live there;
the guide below describes current implementation contracts.

## Boundary

The Dark Matter tab hosts Observatory's
[source browser](../../observatory/static/dark_matter_browser.js). Library keeps
the navigation and saved selection; Observatory owns loading, field predicates
and rendering through Accretion's archive API. Library does not normalize or
persist Dark Matter rows. See
[ISS025](../../accretion/docs/ISSUES.md#iss025-isolate-complete-dark-matter-storage)
for the owning storage work.

Library records provider provenance and distinguishes missing, rejected, stale
and current evidence. Publishing a source revision does not silently adopt it
into an investigation. Source capture, parsed reference content and explicit case
adoption remain separate. The module owns provider schema checks and pacing;
generic safety helpers remain shared.

## Source ownership

| Location | Maintained responsibility |
| --- | --- |
| [components/cve_catalog/](../components/cve_catalog/) | Local NVD catalog, product indexes, EPSS/KEV risk data, provider transport and update scheduling |
| [components/intelligence/](../components/intelligence/) | Captured provider evidence, parsing, selection and local-reference integration |
| [components/repositories/sources.py](../components/repositories/sources.py) | Source revisions using caller-owned transactions |
| `components/cve_sources.py`, `cve_intelligence.py`, [source_jobs.py](../components/source_jobs.py) | Application interfaces, source jobs and orchestration over the owned implementations |
| [components/intelligence/selection_identity.py](../components/intelligence/selection_identity.py) | Pure immutable-selection identity shared by acquisition, persistence and adoption |
| [components/content_bank.py](../components/content_bank.py), [resources/](../resources/) | Editable explainer defaults and reusable, versioned report/finding wording and citation banks |
| [components/routes/content.py](../components/routes/content.py) | Explainer listing, creation and revision-update HTTP adapters |
| [static/catalog_library.js](../static/catalog_library.js), [cve_catalog.js](../static/cve_catalog.js), [resources.js](../static/resources.js), [library_events.js](../static/library_events.js) | Catalog/reference editing presentation, events and lifecycle |

Catalog and risk storage have different database and transaction contracts.
Catalog initialization and writable connections are distinct from RiskStore's
read-only snapshot path. Their managers also own independent update schedules,
cancellation and retry state. Similar metadata or lifecycle methods do not make
these stores or managers interchangeable. Keep the cohesive subpackages intact
when refactoring an individual responsibility.

Library owns the reusable report-family and finding banks in `resources/`.
Investigations owns case-specific selection, pinned adoption and recipient layout.
Its [reference preview command](../../investigations/tools/export_explainer_templates.py)
renders the static report bank through production report layout; it does not export
editable Library records or imply an agency profile. Bank relocation preserves
wording bytes, IDs and revision identities.

`components/api_models.py` owns source-job, source-metadata and block-update
request contracts. The reference editor's `install(ctx)` returns its actions
and starts no requests/listeners. The shell installs it explicitly alongside
the catalog; Settings installation is not a prerequisite. Library owns editor
save/cancel, retained drafts and dirty-state behavior. The portable
`tests/test_resources_ui.cjs` suite verifies this independent composition.

`routes/content.py::register(app, *, store)` registers explainer routes with
Library request models and `services/content.py`. Workspace supplies composition
and transaction infrastructure; Library owns source metadata and revision policy.
See [Workspace ISS029](../../workspace/docs/ISSUES.md#iss029-workspace-file-ownership-and-consolidation).

## Content and research contracts

`services/content.py` owns create/update/archive/restore transactions and Activity
events; `repositories/content.py` owns the current projection and retained
revisions. Updates require `expected_revision`. A stale writer receives HTTP 409
with current revision information while the editor retains its draft; comparing
and rebasing is explicit. Archive hides obsolete text from new selections. Restore
publishes a new revision instead of rewriting history. Existing case selections
and certified packages retain their original wording and citations.

Workspace schema 23 installs Library-owned `databases/content_schema.py` and
`databases/research_schema.py` in the migration transaction. Upgrade preserves the
existing current explainer and available citations as `legacy_current`; it cannot
reconstruct earlier overwritten wording. Revision rows reject UPDATE/DELETE.
Workspace export/restore carries history, archival state and saved research views.

| Interface | Contract |
| --- | --- |
| `/api/explainers`, `/{id}` | Active listing and revision-checked editing; `include_archived` enables maintenance listing |
| `/{id}/history`, `/{id}/revisions/{revision}` | Paged history and complete retained wording/citations |
| `/{id}/usage` | Current case selections; this is not an inventory of all historical report packages |
| `/{id}/archive`, `/{id}/restore/{revision}` | Explicit lifecycle actions with expected current revision |
| `/api/library/views` | Named workspace selections with stable IDs; update/delete check the current revision |
| `/api/library/views/import` | Idempotent migration of old browser-local selections without overwriting later edits |
| `/api/library/search` | Submitted local query, bounded typed CVE/product/explainer results, independent availability per group |
| `/api/library/changes/{cve_id}/impact` | Paged read-only comparison of current local NVD content and retained case selections |

The explainer-relative paths above begin with `/api/explainers`. Research request
models and their small service live in `components/research.py`; routes only adapt
HTTP input/output. Saved selections use schema version 1, including explicit empty
severity (all severities), field predicates and Dark Matter filters. They survive
browser changes; equal names do not merge different views. Mounted Library panels
load independently and only the active catalog view loads its data. Request
generations prevent cleared or replaced selections from accepting stale responses.

`components/reference_changes.py` consumes Investigations'
`repositories/reference_usage.py` read interface. Investigations owns exact CVE
membership, active/completed scope and case links. Count/page share one database
snapshot. Comparisons use retained raw NVD data when available; missing proof stays
unknown. A certified badge describes the case's retained certification, not proof
that its current draft matches an older package. This query never adopts data,
changes a report, retrieves a provider response or rebuilds Observatory's snapshot.

The comparison also reads current local KEV membership through `RiskStore.get`,
retaining source dates/digests and stale warnings. NVD-content and KEV-membership
differences stay separate. A historical default false is not proof of absence:
negative pinned membership requires recorded complete-catalog provenance. Missing,
invalid or incomparable risk data remains unknown; this view never refreshes it.

The shared captured-revision registry remains the single existing
`Investigations.evidence_registry` persistence contract. Library consumes only its
transaction-taking immutable record operations, not case workflow. Its historical
keys, digest checks, migrations and backup integration remain intact. Moving that
shared registry alone would add churn without changing the reviewed boundary.

## Reference consistency and query behavior

`intelligence/metrics.py` supplies one pure NVD assessment selector to Library,
Accretion and catalog indexing: supported CVSS version precedence, then valid
Primary assessment preference. All assessments and publishers remain retained.
Consumer-specific severity presentation stays explicit. Normalization binds each
derived reference/SSVC assessment once to its capture; legacy cached selections
are validated and reprojected from retained bytes without rewriting pinned evidence.
SourceRepository pairs current reference and latest acquisition outcome inside
the caller's transaction, so failed refresh warnings survive later cache reads.

Catalog read connections use SQLite `mode=ro` and one read transaction for counts
and rows. Writable initialization and indexing run at the manager/maintenance
boundary. The `(modified DESC,id DESC)` index supports deterministic pagination.
Index jobs report partial coverage and error counts until every record is indexed;
completion does not equate to readiness. Batched local selections parse and
validate a captured KEV payload once per batch, not once per CVE.

Provider-declared `semver` rules use the maintained Python `semver` parser and
comparator, including prereleases, build metadata and status transitions. Invalid
SemVer and unsupported vendor schemes remain unresolved. A product/version match
is a candidate for investigation, never confirmation of observed vulnerability.

## Verification and maintenance

[static/risk.js](../static/risk.js) owns the frontend known-ransomware predicate
shared by Library intelligence and Observatory projections. It recognizes the
existing three evidence aliases and returns whether known evidence is present;
false does not turn missing/unassessed data into an explicit negative assessment.
Finding-level exact-CVE filtering remains separate from aggregate row risk.
The source checkout's `modules/ui/tests/test_shared_frontend_helpers.cjs`
exercises aliases and preserves the unassessed label. Consolidation tracking lives
in [ISS026](../../tools/docs/ISSUES.md#iss026-reusable-tools-and-duplicate-capabilities).

With the [project development environment](../../../docs/DEVELOPMENT.md#windows-ide-setup)
active, run module regressions from the repository root:

```text
python -m pytest -q modules/library/tests
```

Provider changes use the test-double boundary described [below](#provider-verification).
Catalog persistence changes must cover both writable publication and read-only
snapshots. Use the shared [verification guide](../../../docs/DEVELOPMENT.md#verification)
for integration, DOM and browser checks.

The routine browser groups `library`, `sources` and `catalog-scope` exercise the
catalog/editor, local evidence adoption and scoped Observatory navigation. Use
`python tools/verify.py --list-browser` for their maintained fixture/setup and
`--only-browser --browser-suite <group>` for a focused run. Fixtures use local
synthetic NVD/EPSS/KEV data and explicit post-release startup state.

The routine `library` group also runs explainer lifecycle acceptance through
`modules/library/tests/test_content_lifecycle_browser.cjs` in the source checkout:
real forms and delegated events create cited text, retain a conflicting draft,
compare/rebase, restore, archive/unarchive and display usage/Activity. The check
keeps the case's originally pinned wording and citations unchanged through the
entire workflow. Keep this coverage in the maintained suite when editing the
content API, revision policy or editor lifecycle.

Record module work and dependencies in [ISSUES.md](ISSUES.md).
Update this guide when ownership or a contract
changes and follow the shared
[documentation maintenance rules](../../../docs/README.md#keep-the-documentation-dependable).

## Source configuration

Library shows the CVE count on disk alongside the outcome of the latest NVD update. After **Last update failed**, use the last successful sync to judge how current the records are. The failed attempt time and, when scheduled, the next check time appear in the same panel.

A source deployment may supply `NVD_API_KEY` for catalog acquisition. Do not commit
keys or copy them into examples. Initial catalog seeding uses public compressed
annual NVD feeds without requiring a key; normal incremental API updates also
work without one at the provider's anonymous pace. A key enables faster API
updates. Only explicit full API enumeration (`bootstrap="api"`) requires a key.
Library owns key syntax, target names and session policy and reuses the standalone
Shadowserver SDK's public `WindowsCredentialStore.read/write/delete` byte interface.
There is one native Win32 implementation; the standalone SDK imports no application
module. Application setup and
credential choices are described in the [user guide](../../../docs/USER_GUIDE.md).

## Provider verification

### Bulk catalog transport

`cve_catalog/control.py` owns cancellation and a monotonic deadline for each
transfer: 900 seconds for NVD, 300 seconds for EPSS/KEV. The same deadline covers
pacing, redirects, retries, opening headers and body consumption; retries cannot
renew it. A multi-year catalog import comprises several separately bounded
transfers. Provider classes retain URL allowlists, retry decisions, schemas,
receipt hashes and publication policy.

`cve_catalog/feed_http.py` adapts Requests' prepared headers, netrc, HTTP/HTTPS
proxies, NO_PROXY and CA configuration to the independent Attribution engine's
managed `stream_response()` API. HTTPX owns cancellable I/O; no abandoned Requests
transfer threads are used. Certificate verification is required. Scheme-less
HTTP proxy configuration remains supported; SOCKS is explicitly unsupported in
this adapter, matching the bundled Requests capability. Errors exposed to the
provider layer are classified and redact connection details.

Requests advertise identity encoding. Unexpected gzip/x-gzip or deflate HTTP
encoding is decoded with separate bounded wire and expanded counts; other or
invalid encodings fail closed. Annual `.gz` file bytes retain their existing
receipt/hash contract. Close every response and source iterator on success,
rejection and cancellation, including prefix-validation failure. Cancellation
retains committed data and removes incomplete staging; it does not publish a
partial feed. Native DNS work uses the engine's two bounded resolver slots and
can outlive cancellation until the operating system returns.

### Retry guidance

NVD and risk feeds use the shared Tools
[`parse_retry_after`](../../tools/components/http.py) parser: explicit header and
timezone-aware current instant in, server delay or `None` out. It uses Python's
[`parsedate_to_datetime`](https://docs.python.org/3.14/library/email.utils.html#email.utils.parsedate_to_datetime)
for dates and the decimal-seconds/date forms in
[HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3).
Library keeps provider pacing, minimum waits, backoff and persistence. Risk feeds
retain their 60-second minimum and one-hour fallback; invalid guidance now stays
distinguishable from a server deadline. Decimal fractions, signed numbers and
nonfinite values are not server delays. NVD's accepted input forms are unchanged.
Standalone Attribution and vendored Shadowserver retain their independent package
interfaces; they do not import application Tools.

### Test boundaries

Test doubles for provider HTTP now target
`modules.library.components.intelligence.acquisition._response_get`. Offline provider fixture tests
can import `modules.library.components.intelligence.adapters` without application initialization.
Public consumers can continue using `modules.library.components.cve_sources.verify/enrich` and
`modules.accretion.components.intake`. The former spreadsheet qualification command has been removed.

Bulk feed doubles use `cve_catalog.transport._response_get` and
`cve_catalog.risk._response_get`; transport-contract tests inject a controlled
HTTPX transport at `cve_catalog.feed_http._stream_response`. The root offline
harness blocks this real-I/O seam by default. Exercise stalled headers, trickling
bodies, stop/deadline cleanup, bounded decoding, provider retries and manager
publication before changing these boundaries.
