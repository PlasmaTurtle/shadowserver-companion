# Report layout review record

These historical notes preserve the opt-in report revisions identified below by
their `2026-11-07` revision IDs. Statements about review status and installed
defaults describe that review scope; they do not establish current release
acceptance or authorize a new layout adoption. The revision-specific wording and
output contracts remain relevant when maintaining saved reports.

Use the [Investigations guide](README.md) for current ownership and verification,
and [Investigations issues](ISSUES.md) for outstanding work. Paths and synthetic
preview commands below are relative to the repository root.

## Introduction page review candidate

`modules/investigations/tools/preview_introduction.py <output-directory>` produces synthetic one-,
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

The bundled `modules/investigations/resources/timezones` TZif record is the Windows fallback for
America/New_York. Its version, license and hash travel with the source. Original
timestamps stay in the source model; timestamps lacking a zone are identified
as such rather than assigned an invented zone.

## Vulnerabilities page review candidate

`modules/investigations/tools/preview_vulnerabilities.py <output-directory>` produces three entirely
synthetic, offline examples: one asset, two assets with a shared finding, and
six CVEs. It runs the notification narrative generator and production exporters.
Select `vulnerability_revision` equal to
`vulnerabilities-2026-11-07-review-1` to use this candidate. It is separate from
the installed builder default and does not promote an application release.

`modules/investigations/components/notification_narrative.py` generates one paragraph for the whole notification,
using the established opening, attribution and closing once. Common findings
combine; distinct products, versions and services retain their asset scope.
Per-finding insertable values and original source rows remain separate records.
`narrative_revision` identifies this aggregation rule in draft and review
snapshots. An existing frozen section must be reopened before changed wording
can be certified; completed drafts and historical packages remain unchanged.
The historical `modules/investigations/components/approved_template.py` source and other approved paragraphs are
unchanged.

`modules/investigations/components/vulnerability_model.py` joins the exact draft narrative and selected finding
records. `modules/investigations/components/vulnerability_layout.py` measures them together in a 477.6 × 650 pt
page frame. Narrative is 11 pt with 15.5 pt leading; findings and citations
stay at least 10 pt. Whole paragraphs and whole findings move to a fresh page
when they fit there; oversized content continues without clipping or shrinking.
Every continuation repeats the section title, and split findings repeat their
identifier. Citations accompany independent source metrics and assessments.

`modules/ui/components/vector_layout.py` owns common geometry and font metrics. `modules/ui/components/exhibit_rendering.py`
emits PDF vector text and Word SVG with a PNG fallback. `modules/ui/components/document_fonts.py`
embeds the bundled fonts once per document. `modules/investigations/components/exhibit_masters.py` stores page
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

`modules/investigations/tools/preview_attribution.py <output-directory>` renders four offline synthetic
examples: exact registration evidence for a 70-IP group, a saved DNS answer,
an analyst-accepted registration-name association, and an unresolved partial
match. Select `attribution_revision` equal to
`attribution-2026-11-07-review-1` to use this candidate. The installed builder
default remains unchanged while the page is reviewed.

`modules/investigations/components/attribution_model.py` compares the selected source observation at group index
zero with the case-frozen proof. It distinguishes a saved A/AAAA answer, exact
domain evidence in a registered network, and explicit analyst acceptance.
It checks IP equivalence, network containment, saved field values and source
identity. Missing validation times remain unknown; retrieval time never becomes
validation time. These checks explain saved evidence and do not perform new
lookups or change intake qualification. One supporting association never implies
individual validation of every reported IP in the group.

`modules/investigations/components/attribution_layout.py` integrates the unchanged attribution paragraph and
association cards into a measured page exhibit. Ordinary cards stay together;
long content continues without omission or reduced type. Text is black; blue
graphics identify complete supporting evidence and red graphics identify review
needs. Source and validation details stay visible; raw record pointers and full
responses remain in Appendix B. Source citations and included screenshots retain
their existing reference and appendix paths.

The common exhibit dispatcher preserves geometry, SVG/PNG and font hashes for
both page revisions. `modules/investigations/components/report_snapshot.py` reuses each section's own frozen
artwork. An incomplete attribution exhibit cannot be certified. Layout adoption
and content changes use the established reopen, reason and validation chronology.
No other section's approved wording changes with this revision.


## Information page review

The opt-in draft revision `information-2026-11-07-review-2` selects the cohesive
Information Exhibit with revised page-two copy. The first review revision remains
supported with its original wording and source record. Existing drafts continue
to use their selected layout.

- `modules/investigations/components/information_model.py` retains the approved security introduction
  and four protective actions. Revision two contains separately identified
  editorial risk/advisory copy and exact IC3 figures without a calculated average.
  FBI BEC guidance, the joint StopRansomware guide and the IC3 annual report
  support the explanations. Each reviewed extract retains its actual source URL,
  retrieval time and section/page locators. These are explicitly reference
  extracts, not archived copies of the full source documents.
- `modules/investigations/components/information_layout.py` measures the approved body text and keeps
  ordinary paragraphs together. Longer additions continue with a repeated
  section title, without repeating the introduction or shrinking body text.
- `modules/investigations/tools/preview_information.py` renders the standard two-page exhibit and a
  synthetic long-explainer specimen through the production PDF/Word exporters.

Selected custom explainers retain their source citations, overrides and pinned
revisions. Source records and the citation register remain in Appendix D.
Composition and export are offline. The Information revision participates in
section freezing; certified SVG/PNG masters are reused across exports and
reopening still requires the recorded reason. The approved template constants
are unchanged. Revised page-two text is an editorial candidate, not an assertion
of agency policy approval. This is a review candidate, not a change to installed defaults.
