# Library changelog

## Unreleased

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
