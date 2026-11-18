# Observatory entity map release contract

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

Shadowserver Eclipse 0.10.0 Entity Map is a release candidate. Its map answers which
known organizations are represented and what saved evidence supports their exposure.
The primary unit is a canonical entity. The release must not make a busy host,
multiple assets or repeated observations appear to be multiple organizations.

## Identity and counts

- A canonical known entity has one map identity and at most one individual marker.
  A visual cluster groups entity markers without inventing a new entity identity.
- Entity count is primary. Assets and findings are supporting counts with distinct
  meanings. Observations provide source and timing provenance, not extra entity nodes.
- Selecting an entity or cluster must preserve canonical IDs through the model,
  renderer, controller and details route. Counts, selection and supporting detail
  must describe the same filter scope.
- Known entities represented in the selected evidence remain discoverable even when no supported placement is possible.
  Unknown/unattributed observations must not be promoted to known organizations.

## Geographic meaning and precedence

A complete saved entity city/state takes priority. If either city or state is missing
from the entity profile, placement falls back to the city/state of the most recent
associated IP/hostname report in the selected evidence scope. The fallback must
identify its reported source basis, IP/hostname and date in details.

Both sources resolve city/state to an approximate Census representative point for
the place. Neither asserts an exact business address or operating location. Raw IP
coordinates are not used as map placement. Asset and observation geography remains
reported context rather than proof of where the organization physically operates.

A complete but unsupported or unmatched saved city/state stays unplaced; it is not
silently overridden by report geography. If the latest selected associated report
has missing or unusable city/state, the map stays unplaced instead of searching
older reports for a convenient location. Unplaced entities remain discoverable in
a directory that distinguishes missing placement from zero entities or hidden filters.

The bundled regional gazetteer covers North Carolina and South Carolina. A state or
city outside this support is not evidence that the entity is out of jurisdiction or
unimportant. Nationwide placement and street-address geocoding are outside this
release's geographic coverage.

## Time and supporting evidence

Observation time filters and cutoffs select supporting evidence. Saved entity
identity and profile geography reflect the current profile. Reported fallback
geography follows the selected evidence cutoff and displays the selected report's
date. The view is not a historical reconstruction of the organization's physical
address or ownership.

Supporting asset/finding counts must disclose their scope and must not be labeled
as total history when evidence is filtered or bounded. Repeated observations retain
provenance and timing without multiplying entities. Navigation to an entity or
supporting record must preserve the canonical relationship and must not trigger
external research merely to display the map.

## Interaction and rendering acceptance

1. Multiple assets or observations under one entity yield one entity identity.
2. Co-located entities remain individually accessible through cluster expansion or
   details; cluster totals reconcile to their member entities.
3. Filters and time changes reconcile visible markers, unplaced directory entries,
   totals, selection and detail. A stale selected record must not silently display
   evidence or fallback geography from an older scope.
4. Pan, zoom, resize and return navigation preserve usable hit targets and readable
   labels. User interaction does not reset the camera unexpectedly.
5. The details view presents entity identity first, supporting assets/findings next,
   and observation provenance without confusing their counts or location sources.
6. A supported saved profile location takes precedence. Missing profile city/state
   allows the latest selected report city/state, with explicit source and date.
   Unsupported complete profiles and unusable latest reports remain unplaced;
   there is no raw-coordinate or older-report guessing.
7. Synthetic regressions cover multiple observations per entity, multiple assets,
   co-location, supported and unsupported profile locations, missing profile fields,
   latest-report fallback, unusable latest reports, empty scopes and changing cutoffs.

## Baseline audit dispositions

These entries distinguish implemented corrections from native acceptance limits.
References name the final source files and the focused regressions executed for
this release; the full backend suite was not rerun for the map feature.

| Audit concern | Required disposition | Integration evidence |
| --- | --- | --- |
| Map identity and primary totals follow observations rather than canonical entities | Use one canonical entity identity; observations remain supporting provenance | Implemented in workbench/observatory_view.py:319-438; tests/test_observatory_entity_map.py:50-89; 134 focused backend tests passed |
| Resource geography can be mistaken for an organization address | Prefer complete saved entity city/state; otherwise use latest selected report city/state with explicit source/date; label Census placement approximate | Implemented in workbench/observatory_view.py:274-316 and workbench/eclipse.py:148-174; tests/test_observatory_entity_map.py:116-228 cover precedence, fallback, cutoff and source provenance |
| Entities without supported geography can disappear from the user's model | Keep a discoverable unplaced directory; do not override unsupported saved locations or guess from older reports | DTO in workbench/observatory_view.py:424-438; UI tests/test_observatory_entity_controller.cjs:100-158,255-264; exact full counts and 1,800-entry caps tested in tests/test_observatory_entity_map.py:299-322 |
| Cluster, selection and detail scope can diverge | Reconcile canonical IDs and filter scope across DTO, model, renderer and controller | static/eclipse_space.js:3-114 preserves deterministic entity membership; static/eclipse_scene.js:824-830 highlights selected members; tests/test_observatory_entity_controller.cjs:175-238 covers refresh and moved members |
| Time cutoff may imply an historical entity profile or address | Distinguish current profile geography from dated fallback geography in the selected evidence scope | workbench/observatory_view.py:391-408; tests/test_observatory_entity_map.py:163-250 covers selected cutoff and current saved profile behavior |
| Portable rendering checks cannot establish native browser usability | Record actual visual checks separately; retain Windows acceptance checklist | Production controller/canvas exercised with actual backend fixture and dense synthetic cases; browser fixture data validated without browser launch; native Windows and browser interaction acceptance not executed |

## Verified renderer corrections

Stable member-anchored clustering replaces centroid movement that could pull separate
clusters onto the same pointer target (static/eclipse_space.js:3-47). Canonical member
selection now highlights its cluster (static/eclipse_scene.js:824-830), and a fitted
overview refits after either width or height changes while preserving deliberately
navigated views (static/eclipse_scene.js:238-260). The production renderer tests in
tests/test_observatory_entity_map.cjs cover exact entity counts, mixed location
provenance, deterministic separated clusters, selection, resize and fit behavior.

The actual backend fixture produced four selected entities, three mapped and one
unplaced, with one unassigned asset. Its report fallback resolved Raleigh from
reported city/state while ignoring raw New York coordinates. The renderer retained
one marker/count for an entity supported by 10,000 observations, 200 findings and
45 assets; 80 co-located entities retained an aggregate count of 80. These are
production-code harness checks, not measured browser FPS or native Windows approval.

Map nodes and the unplaced directory each cap at 1,800 entries. Full-selection totals
and explicit omissions remain available; displayed items are not claimed to be an
unlimited inventory. Entities without selected evidence do not appear merely because
they have a saved profile. The native-browser fixture produced six entities (five
mapped, one unplaced), including reported Asheville fallback, but the browser itself
was not launched for that check.

## Release preservation and remaining limits

This feature reads saved records. It must not migrate certified reports, modify
original imports or create entity associations as a side effect of viewing the map.
The established installation/data identity, schema version and dependency pins are
retained. The source and installer packages include this contract through an exact
release-policy allowlist entry.

Final executed checks belong in VALIDATION.md. HOME_VALIDATION.md records native
Windows browser, DPI, input, installation and retained-data checks. The release
remains a candidate until exact-version acceptance is recorded. No GitHub push is
part of this work.

