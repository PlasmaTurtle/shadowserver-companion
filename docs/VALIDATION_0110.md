# Validation — 0.11.0 Workspace Evolution

This is a **release candidate**. Exact-version native Windows/Word/browser acceptance
remains outstanding. The separately recorded Windows baseline is 0.9.96.

## Final checks

| Gate | Result |
|---|---|
| Complete backend suite | **2,934 passed, 0 skipped, 151 subtests passed**. All 2,934 collected tests across 217 files were covered in disjoint processes. |
| Source stability during final suite | SHA-256 checked 718 source/test files; no changes during the run. |
| Portable frontend | **60 suites passed**, including stale dialogs, entity-map behavior, qualification categories, workspace health and cleanup review. |
| Security/data boundary gate | **458 passed**, plus 78 subtests; these overlap the full suite and are not additional unique tests. |
| Dependency integrity/advisories | All 34 pinned wheel artifacts verified; 33 public Python packages, zero reported advisories. No dependency upgrade in this release. |
| Architecture/style | 364 owned modules, 21 components, zero dependency cycles/boundary violations; Python lint/format, frontend syntax and Prettier passed. |
| Upgrade and restore | Schema 16→20; 13 sampled source/workflow tables unchanged; all 57 application tables equal after export/restore; all 90 protected files byte-identical. |
| Fresh analyst day | 200 authenticated ASGI actions from empty workspace through next-day work; 3 cases, 3 report revisions, 1 closure. 76 protected files unchanged; 4 manifest bindings, 61 package-member hashes and 3 source-capture hashes verified. |
| Report matrix | 12 full/compact variants with matching PDF and LibreOffice page counts; six full-edition texts unchanged; all citations/appendix counts retained. |
| Protected content | Approved-template module byte-identical to baseline commit 4ea6759; historical source and certified files retained. |

Python validation runtime: **3.14.10**, SQLite **3.53.1**, Linux x86-64.
Backend source fingerprints, exact shard file lists, JUnit records, final logs,
dependency results, migration comparisons and synthetic reports are in the separate
validation ZIP. Installer extraction and source-archive verification are recorded
there after packaging; this source document does not embed a self-referential
package checksum.

The initial full run passed 2,933 tests and skipped the NSIS compiler smoke
check because its binary was outside PATH. That exact test passed when rerun with
the locally installed compiler configured; all source hashes remained unchanged.
The final total therefore covers all 2,934 collected tests with no unresolved skips.

## Integration defects closed

The implementation pass found and fixed exact-condition approval leakage,
immutable-ledger replacement writes, historical-owner attribution refresh/pruning,
new-subdomain pre-transfer and undated-report replay admission, cross-owner
DarkMatter attribution, merge-after-transfer proof recovery, case/render
concurrency, stale orphan-certification activation, and a cross-store health
snapshot race, indexed inherited-root ownership resolution, and capture terminal-status
publication before cleanup. New constraints also exposed obsolete corruption/crash fixtures;
those now model actual historical schemas or lost commits without weakening the
production guards. Word master tests retain exact standalone artwork checks while
recognizing that embedded font resources are shared in new DOCX packages.

The first full preflight ran while integration was still being finalized. Its
failures and an initial shard harness `conftest` collection collision are not
counted as passing checks. The final suite uses a separate process for the
standalone Attribution package and verifies source bytes remain fixed throughout.

## Platform and scale limits

- Native Windows installation/runtime, workstation security-provider behavior,
  browser interaction and Microsoft Word layout were not executed for this exact
  build. LibreOffice is an independent DOCX renderer, not native Word.
- The environment intercepted local HTTP with a proxy-generated HTML 200 response.
  The workday used normal authenticated ASGI routes and actual application services,
  storage and renderers. Providers and outreach outcomes were synthetic; no messages
  were sent. Portable UI tests do not establish native browser usability.
- The first full graph at 50,000 synthetic observations took 20.17 s; warm views took
  approximately 35–39 ms. Full cold graph projection remains linear. Direct details
  and eligible-case queries no longer scale with unrelated history.
- This is not proof of unlimited capacity, comprehensive external-provider
  compatibility, native AMSI acceptance or a cryptographic certification.

See `docs/WORKSPACE_EVOLUTION_0110.md` for changes and measured comparisons,
`docs/DATA_MANAGEMENT.md` for health/recovery, and `HOME_VALIDATION.md` for the
remaining exact-version workstation checks.
