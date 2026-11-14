# Shadowserver Eclipse 0.10.0 Entity Map validation

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

November 13, 2026. Release candidate; unsigned. Native Windows acceptance is not
claimed. The recorded earlier Windows baseline remains 0.9.96.

## Scope

The release continues from packaged 0.9.99 Maintenance Review source. Observatory
Atlas now uses one canonical known entity per marker, with supporting assets,
findings and observation provenance. Complete saved city/state takes precedence;
missing profile city/state allows the latest selected associated IP/hostname
report's city/state. Both resolve to approximate Census representative points,
never raw IP coordinates. Complete unsupported saved locations and unusable latest
reports remain unplaced; older reports are not searched for a convenient location.

Saved-profile geography is current. Reported fallback geography follows the selected
evidence cutoff and identifies its source, IP/hostname and date. Neither establishes
an exact physical address or historical entity-location reconstruction. Regional
place coverage is North Carolina and South Carolina. Map and directory output each
cap at 1,800 entries with exact full-selection counts and explicit omissions.

## Executed feature verification

- **134 focused backend tests passed in 19.22 seconds**, across nine Observatory and
  entity suites including 17 new entity-map cases. These cover aggregation, repeats,
  location precedence and fallback, newest-report selection, historical cutoff,
  source provenance, cache invalidation after actual profile saves and merges,
  map/directory caps and unique workflow counts. One existing Starlette/httpx
  deprecation warning was emitted. Ruff checks passed for the changed Python paths.
- **53 portable frontend suites passed in the final full rerun**, exit 0, after the
  last cluster-refresh correction. Frontend syntax checks also passed. Evidence is
  retained in frontend_final.log and frontend_syntax.log.
- Actual production backend fixture through controller and Canvas: **four entities,
  three mapped, one unplaced, one unassigned asset**. Report fallback placed Raleigh
  from reported city/state despite raw New York coordinates. Heavy support of
  **10,000 observations, 200 findings and 45 assets remained one entity**; 80
  co-located entities retained an entity count of 80.
- Production Canvas/model tests cover deterministic separated clusters, exact entity
  counts, mixed location provenance, keyboard member highlighting, height resize,
  viewport fit and no observation-driven entity-marker inflation. Controller tests
  cover entity-first summaries, workflow, unplaced directory, source separation,
  drill/back, scope refresh, moved cluster members, empty states, missing basemap
  behavior, keyboard controls and date semantics.
- The actual native-browser fixture setup was exercised with browser launch replaced
  only to inspect its synthetic API data: **six entities, five mapped, one unplaced**,
  four distinct city points and a reported Asheville fallback. This validates fixture
  construction, not browser interaction. The updated production browser script was
  syntax checked but **not executed**; earlier browser launch was blocked by the
  environment's singleton-socket restriction.

## Final integration and package checks

- Release identity check passed for 0.10.0 Entity Map, candidate status, no current
  native confirmation. The prior accepted Windows baseline remains separately 0.9.96.
- Regenerated component map passes: **329 owned modules, 21 components, no cycles or
  errors**. Python lint passes; **457 Python files** satisfy formatting. Frontend
  formatting and syntax pass.
- Offline dependency checks pass for all **34 exact wheel artifacts**, their locks,
  source dependency pins and bundled component source. No new public advisory scan
  was run for this map release; earlier advisory evidence is not re-dated.
- Source and installer builders enforce release identity, dependency integrity and
  the regenerated map. Exact archive/installer size, SHA-256, source manifest and
  extracted payload verification are recorded in the companion package evidence.
  Successful compilation/extraction is not native Windows acceptance.

## Preservation and limits

The complete backend/Attribution suite was **not rerun for this map release**. The
0.9.99 full run and its follow-up corrections remain historical evidence and are
not presented as current map validation. Upgrade/restore and certified-file
preservation were not rerun for this feature. No production workspace was opened.
The map reads saved records; no schema migration or certified-record mutation was
introduced. Schema version 15, installation/data identity and dependency pins remain
unchanged. No GitHub push was made.

NSIS compilation and extracted hashes establish package consistency, not native
Windows behavior. Windows browser rendering, DPI/input behavior, AMSI, desktop
startup, scheduled handoff and retained-data upgrade/uninstall remain separate
acceptance work in HOME_VALIDATION.md. The gazetteer does not provide nationwide
placement or street-address precision. Stable promotion requires explicit acceptance
of this exact version.

The detailed contract, source/test references and audit dispositions are in
`docs/history/design/OBSERVATORY_ENTITY_MAP_0100.md`. Baseline evaluation results describe the old
asset-map behavior; they are not acceptance tests for the changed entity semantics.

