# Library changelog

## Unreleased

## 0.12.1

- Added a workspace frequency view for reported CVEs and product or service labels. Library shows observation counts and coverage independently of catalog severity.
- Made reviewed report and finding guides searchable offline by report identity, finding tag and documented field. Added nine sourced finding explanations and exposed the versioned bank through the Library API.
- Added a separate Red Hat guidance panel and callable read and refresh APIs for exact publisher wording and product-scoped advisories.
- Added an automatic comparison of open notification selections against the current local CISA KEV catalog in the Changes view.

## 0.12.0

- Added search across local CVEs, products and explainers. Named research views
  retain their filters across catalog updates. Analysts can compare a retained
  source with its current reference and see which cases use it.
  [Research workflow](ISSUES.md#iss038-research-and-reference-workflow-improvements)
- Added revision history, comparison, restore and archive for explainers.
  Conflicting saves preserve the analyst's draft. Each saved revision retains
  its wording and citations. [Explainer history](ISSUES.md#iss033-explainer-edits-and-revision-history)
- Library and intake now use the same NVD severity assessment. Product searches
  include versions that become affected later in a published range, and
  unfiltered catalog browsing uses an index for faster paging.
- Public NVD annual feeds and incremental updates now work without an API key.
  Canceling a transfer preserves committed records. After a failed sync, the
  catalog shows the failure alongside its last successful update.
