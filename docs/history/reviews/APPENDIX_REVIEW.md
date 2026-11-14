# Recipient appendix review

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

Historical review status: **unstable review candidate; Microsoft Word on Windows acceptance was not recorded at that stage**. See the root `VALIDATION.md` and `HOME_VALIDATION.md` for the accepted 0.8.0 release.

This candidate removes the internal Closing and Resources and sign-off headings
from the recipient resource page. Recommended Resources becomes its main heading.
The approved responsibility paragraph, closing sentence, configured sender and
all eleven previously selected resource links remain unchanged.

## Appendix organization

| Section | Contents |
| --- | --- |
| A | Reported observations and source-file details |
| B | Attribution evidence and retained lookup history |
| C | Vulnerability records and source assessments |
| D1 | Numbered citations and complete source references |
| D2 | Supporting publications, source extracts and other retained material |
| D3 | Recommended resources and their saved catalogue provenance |

The contents page links to each included section. Each page repeats its appendix
name and local page count. Continuing records repeat their record number, title
and field-group heading. Record numbers such as A-01 and D-11 are separate from
section labels such as Appendix D1. Citation numbers remain unchanged.

Readable field labels accompany the original field keys. Group headings retain
their source JSON Pointer paths. Tables show structured fields; long descriptions
use full-width text. Empty strings, null, false, zero, arrays and objects remain
distinguishable. Long relationship lists paginate with their record.

All original appendix records, fields and values remain in the source model.
This is a presentation layer: it performs no new lookups and makes no new claims
about ownership, compromise or vulnerability. Saved source identifiers,
retrieval timestamps and provenance are retained. Recommended resources are
separate from sources cited as evidence for a finding.

## Components

- `workbench/appendix_view.py` groups existing records and supplies readable
  labels, stable bookmarks, the contents page and section ownership.
- `workbench/appendix_layout.py` measures and paginates the resulting text and
  tables. Field continuation retains its original path and line coverage.
- `workbench/appendix_renderers.py` creates selectable Word paragraphs, native
  tables and hyperlinks from the same saved page segments.
- The existing exhibit renderer draws PDF and SVG using the saved geometry.
  PDF and Word support contents/citation navigation. Standalone SVGs preserve
  external resource links; they do not provide cross-file appendix navigation.

The existing review workflow freezes appendix exhibits under their owning report
sections. Reopening still requires a logged reason; validation author and time
remain part of the section record. Approved historical masters are not rewritten.

## Selecting and reproducing this candidate

The draft API allowlists these values:

```json
{
  "closing_revision": "closing-2026-11-07-review-2",
  "appendix_revision": "appendix-2026-11-07-review-1"
}
```

Legacy remains the default for existing drafts. This review does not introduce
a new builder control or Windows installer. Select the revisions on an open
draft through the existing draft API when testing; reopen certified sections
through the normal workflow first.

From a configured development environment:

```sh
python tools/preview_appendix.py review-output
python -m pytest tests/test_appendix_review.py tests/test_closing_page_review.py tests/test_information_review.py tests/test_api_structure_071.py tests/test_citation_integrity_072.py tests/test_report_pipeline_071.py tests/test_section_validation_050.py tests/test_rendering_070.py tests/test_composition_070.py
python tools/program_map.py --check
```

The preview uses synthetic assets and findings. The standard sample starts at
Recommended Resources, followed by the complete appendices. The extended sample
contains a contents page and an observation with long text, unknown fields and
empty values. The JSON snapshots preserve the complete underlying composition.

Validation for this candidate: 64 targeted tests passed; Ruff, module-map and
diff checks passed. All 28 standard/extended pages were visually inspected in
both PDF and LibreOffice-rendered Word output. Page counts, body text character
counts and external link targets match between those render paths. Native Word
bookmark tests verify that every internal target exists exactly once. The
approved-template source file is unchanged. At this review stage, Windows acceptance had not been recorded.

