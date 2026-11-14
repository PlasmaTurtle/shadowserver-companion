# Observatory Field review — November 13, 2026

This is a source checkpoint for the next Windows build, based on delivered 0.9.98 and the pending attribution/NVD corrections. It is not a newly tested Windows release.

## Purpose and visual contract

Observatory explores relationships, expansion, persistence and changes that individual leads conceal. It does not rank outreach effort or replace the temperature queue.

| Information | Encoding | Limits |
| --- | --- | --- |
| Unique retained source observations | Corona intensity/thickness and existing density bands | Exact boundaries remain ≤50, 51–200, 201–1,000 and >1,000. Reimports do not create additional density. |
| Distinct assets | Real branches and bounded constellation breadth | Overview satellites are sampled; explicit asset pages expose the remaining real endpoints. No synthetic nodes stand in for missing records. |
| Newly learned or materially changed information | Discovery depth | Local discovery is distinct from reported observation time. Equal discovery dates use stable identity, so daily repeats do not reshuffle them. |
| Unadmitted observations | Shadow envelope with bent boundary light | Every cloud requires retained data. An asset uses its own evidence; an organization can aggregate associated evidence. Shared identifiers do not prove ownership. |
| Agency priority | Small temperature marker | Does not determine position, body paint order or label precedence. |

Dark transparent panels remain local to controls and the inspector. Lower blur and near-black tint preserve background depth. Ambient artwork drifts independently of stable data targets. Camera approaches and a short reveal provide movement without a continuous data-canvas animation loop. Reduced-motion and user-pause preferences remain respected.

## Findings and remediation

| Finding | Consequence | Change |
| --- | --- | --- |
| Backend limited graph hubs to 60; frontend clipped again | Entire objects could be unreachable | Revision-pinned object pages, exact range/total and explicit older/newer navigation. |
| Field computed and returned aggregates for other views | Large initial response and repeated unnecessary work | Dedicated bounded Field read path; cached selection/index; traditional views retrieve their own aggregates. |
| Selection zoom multiplied the entire field's fit scale | Approaching one object barely changed the view | Local constellation framing, inspector space reserved, full focused asset pages. |
| Focused graph replacement reset its semantic camera baseline | Endpoints stayed tiny/unlabeled after arrival | Explicit focused-model detail contract; verified with production-canvas renders. |
| Two handlers initiated competing focus transitions | Camera behavior depended on event order | Controller owns Field selection; scene handles its one transition. |
| Observatory explicitly paused the global background | Drift disappeared after loading | Independent approach wrapper over existing ambient drift, with a shared pause control. |
| Rapid Field/traditional tab reversals accepted obsolete payloads | A view could be backed by the wrong response shape | Superseding requests and stale-response rejection in both directions. |
| Focus from a later object page retained the previous offset | A one-object scope could render empty | Reset object/asset offsets and retain a reversible overview snapshot. |
| Field's empty state depended on finding count | Retained dark-only objects could be hidden | Field emptiness depends on actual displayed objects. |
| Entity density propagated to individual asset nodes | An endpoint could inherit another endpoint's dark cloud | Field asset counts and reason aggregates use their own unique matching observations. |
| Dark-only sources and unadmitted conditions could disappear from Records | Clouds could not be fully inspected | Separate source-observation pages, scoped reasons/detail context, and distinct finding/observation counts. |
| Dark matter was only faint specks/dashes | Its intended purpose was visually unclear | Data-backed shadow envelopes, separate approved cores, dates and exclusion-reason details. |
| Density/temperature competed with recency in placement and labels | Spatial importance could silently duplicate lead ranking | Stable discovery order, breadth-based spread, depth-based paint/label order. |
| KEV retrieval timestamp preceded CISA dateAdded | Unchanged refreshes could appear newly significant | Prefer the actual KEV publication date; preserve distinct local chronology metadata. |

## Data and interaction safeguards

Counts of findings, observations, assets and entities keep separate meanings. Source observations retained outside admission remain distinguishable from approved findings. Focus and traditional drill-downs use the same scope; Back restores the prior page, selection and camera. Pagination is pinned to a revision, and changed revisions restart at the newest page rather than mixing datasets.

Unresolved endpoints are navigable main objects. Evidence examples are labeled as examples, never treated as a complete history. Dark-source records can be explored without turning them into qualified leads. Original imports and certified reports are not migrated or rewritten by this pass.

The scanner is a short visual reveal of an already loaded page. It is not a live network scan or a claim that loading progress is measured record by record. Data targets and keyboard access remain available during the reveal. The data canvas has no perpetual idle render loop; the existing background owns ambient motion.

## Performance evidence and limits

A local synthetic 3,000-object benchmark measured approximately 583 ms for the first Field projection, 829 ms for the traditional projection and 1.94 ms for a following cached Field page. Its Field payload was approximately 145 KB versus 3.71 MB for the traditional response (about 96% smaller). Later chronology/reason metadata modestly increases the Field payload. These are indicative Linux measurements under concurrent work, not a Windows performance guarantee.

The canonical selection/index still processes the filtered cohort once per revision. Index ordering is O(N log N); subsequent pages materialize a bounded object/asset set. Canvas depth ordering is computed on model replacement; drawing remains bounded by visible nodes/edges plus bounded label collision work. This improves substantial data transfer and repeat work without weakening input validation or dropping evidence.

A reusable isolated fixture includes 96 entities, 472 assets and 1,719 observations, with mixed chronology, admitted/dark evidence and all density bands. Read-path checks reached all 96 objects across four pages and paged a 271-asset constellation without inventing nodes.

## What remains uncertain

- Full browser layout, interactive animation feel and native Windows behavior have not been verified in this environment. Separate browser launch was blocked by socket restrictions; automatic approval review rejected escalation because sandbox approvals are disabled. The available cloud browser could not reach the local fixture. Production Canvas rendering provided a narrower visual check and caught the focused-detail bug, but does not validate browser CSS, focus behavior or Windows typography.
- The NSIS installer now has a separate UI singleton guard. No code path deliberately opening two installers was found. Native compilation/focus behavior still requires the normal Windows build/test pipeline.
- Discovery chronology records when Eclipse acquired or changed findings. Importing old evidence today can correctly be newly learned while remaining old observed evidence. The inspector exposes both clocks.
- A full historical ledger of local reference-risk transitions does not exist. NVD modification dates describe record updates; they are not proof of when severity changed. This pass exposes available dates without inventing missing event history.
- An overview page deliberately samples a few assets per body. It is an orientation view; focused pagination supplies the complete bounded traversal. The design should be assessed on real workstation data before increasing the number of simultaneous bodies.

## Other requested changes

Workspace is the default start view while explicit deep links remain honored. Its summary is work-focused: Leads, Active investigations, Follow-ups and Completed, with actionable rows rather than source-observation totals. The existing Eclipse header is retained; the favicon now follows that mark with SVG/PNG/ICO variants. The installer wizard has a version-independent singleton separate from its existing file-mutation lock.

Validation logs and exact changed-file hashes accompany the source checkpoint. No GitHub push, installation or production-data modification is part of this review.
