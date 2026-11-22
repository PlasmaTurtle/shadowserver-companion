# Observatory

Observatory owns read projections, analytical indexes, map/scene interaction,
geographic reference assets, and visualization of retained observations. This
guide covers the maintenance boundaries behind those views.

[Module issues](ISSUES.md) · [Changelog](CHANGELOG.md) · [Architecture](../../../docs/ARCHITECTURE.md) ·
[Maintenance workflow](../../../docs/DEVELOPMENT.md#maintenance-workflow) ·
[Framework decisions over 50 lines](../../../docs/DEVELOPMENT.md#framework-decisions-for-work-over-50-lines)

## Start here

| Responsibility | Start here |
| --- | --- |
| Canonical evidence selection and support | [observatory_queries.py](../components/observatory_queries.py), [observatory_intelligence.py](../components/observatory_intelligence.py) |
| Archive presentation and complete-field browser | [observatory_dark_matter.py](../components/observatory_dark_matter.py), [dark_matter_browser.js](../static/dark_matter_browser.js) |
| Scoped responses, Field paging and read models | [observatory_view.py](../components/observatory_view.py), [observatory_field.py](../components/observatory_field.py), [eclipse.py](../components/eclipse.py) |
| Query counters | [analytical_index.py](../components/analytical_index.py) |
| Browser loading and controller | [eclipse.js](../static/eclipse.js), [eclipse_controller.js](../static/eclipse_controller.js) |
| Geographic assets and provenance | [geography reference](../static/geo/README.txt) |

## Boundary

Observatory reads retained evidence and clearly displays scope, coverage, recency,
and approximate location. Opening or navigating a visualization must not
requalify records, start provider lookups, or rewrite source evidence. UI provides
the shared shell and visual primitives. Preserve one primary entity marker and
the established geography provenance/fallback rules when changing the controller.

Keep the read layers distinct: `observatory_queries.py` selects canonical rows,
`observatory_intelligence.py` aggregates bounded evidence support,
`observatory_view.py` owns the shared revision-scoped response, and
`observatory_field.py` pages the Field's objects. `analytical_index.py` maintains
the query counters used by those projections. They are complementary layers.

Accretion's [Dark Matter API](../../accretion/components/dark_matter.py) owns
complete source rows, normalization, outcome history, field queries and archive
identity. Observatory calls `store.dark_matter` and never reads its tables or
constructs canonical asset/finding identities for archived rows.
`observatory_dark_matter.py` translates public archive records into display rows;
malformed identifiers and out-of-jurisdiction evidence remain visible and
unapproved. Source records use their own stable IDs. Canonical observation
identity and source-row identity are distinct; visual grouping does not merge
their evidence or establish ownership. Promoted archive rows leave the default
archive selection and their canonical evidence remains in the qualified view.

Archive detail reads use the saved complete fields directly. They do not copy,
hash or rescan the original report. Canonical historical detail may still verify
its original evidence when required. Read-only Library decoration supplies local
CVE/risk context to both displays without changing archive data or calculating
lead scores. The archive revision participates in Observatory cache keys.

The source browser is owned by Observatory and hosted in Library's Dark Matter
tab, with a direct link from Observatory. It discovers known and newly observed
fields through `/api/dark-matter/fields`, submits typed field/operator predicates
to `/api/dark-matter`, and displays original values, normalized values and field
errors. Missing, malformed and present values are separate filters. The API also
provides `/api/dark-matter/facets` and `/api/dark-matter/{record_id}`. Routes validate
query shape and delegate selection to the component; field SQL remains private.

The graphical projection is bounded at 100,000 archive records and explicitly
reports incomplete coverage at that boundary. The paginated source browser can
query the complete archive independently of graphical limits. Every ordinary
read remains local and does not enqueue work, score findings or mutate evidence.

The geography assets also have separate contracts: `states.json` supplies map
boundaries, `places.json` supplies unambiguous approximate city coordinates, and
`entity-places.json` supplies city-name validation. Keep each asset's provenance
and its documented omissions in [the geography reference](../static/geo/README.txt).

## Verification

Browser formatting and Fetch mechanics reuse UI's
[shared browser capabilities](../../ui/docs/README.md#shared-browser-capabilities).
Navigation supplies the canonical encoder to the synchronous classic facade.
Observatory retains selection generations, revision-conflict recovery, slow-load
messages and independent 120-second view / 20-second detail deadlines. Structured
HTTP 409 details survive the shared transport. The concise Updated clock remains
local display time. Library's [risk predicate](../../library/static/risk.js)
interprets known-risk aliases; exact-CVE filtering still uses finding-level risk.

Use the [project development setup](../../../docs/DEVELOPMENT.md#windows-ide-setup).
From the repository root:

```text
python -m pytest -q modules/observatory/tests
```

`test_dark_matter_component_routes.py` checks complete-field filtering, malformed
rows, read-only projections, promotion and cache invalidation. The browser's
host integration is covered by
`modules/accretion/tests/test_dark_matter_ui_0987.cjs`; run it with
`node --experimental-vm-modules`. It verifies typed predicates, safe rendering,
field discovery, paging and failed-search isolation.

The [acceptance guide](OBSERVATORY_ACCEPTANCE.md) owns focused frontend/browser
commands, the behaviors they cover, and the Observatory-specific native visual
checklist. Project-wide release acceptance remains in the
[Windows checklist](../../../docs/WINDOWS_ACCEPTANCE.md).

## Maintenance and tracking

Keep map projection, navigation state, and scene rendering separately testable.
Use [Observatory issues](ISSUES.md) for module-owned work and links to shared UI
dependencies. Follow the [project maintenance workflow](../../../docs/DEVELOPMENT.md#maintenance-workflow),
then update this guide or the acceptance checklist when a behavior contract
changes. Record outcomes against the exact build rather than treating the
checklist itself as evidence of a pass.
