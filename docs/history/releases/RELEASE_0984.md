# 0.9.84 — Products, versions and proactive outreach

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

Dark Matter now brings the local catalog into everyday notification work. Library
opens on affected products with Critical selected. Product dossiers show the
published affected-version rules, associated CVEs, known exploitation and your
observed entities. Critical + KEV and KEV at any severity remain separate scopes.

## Report work unblocked

The adopted-source save/freeze failure had two causes: Python and browser JSON
represented whole-number scores differently, and an immediately completed local
retrieval did not register its selections until polling. Both paths now preserve
the same source identity. Published wording and metric edits still require an
official-text fallback; unchanged retrieved material saves and freezes normally.

The notification builder retrieves locally first and offers local CVE search.
Only CVEs already reported for that notification can be adopted. Explicit refresh
remains available. Newly selected sources retain their hashes, publisher, dates
and local-catalog provenance. Reference updates do not rewrite frozen reports.

## Library and Observatory

- Products retain original source names and version rules. Conservative identity
  normalization avoids silently merging different vendor products.
- Version comparisons are research candidates. Custom version schemes, required
  platforms/configurations and conditional exceptions remain unresolved where
  the source data cannot justify a match.
- CVE details show all available CVSS assessments, including source, vector and
  version, alongside dated EPSS probability/percentile and CISA KEV data.
- Fields shows catalog distributions and missingness with a CVE drilldown.
  Counts describe the selected public catalog records, not internet prevalence.
- Changes records material revisions seen after this index is introduced.
  It does not invent historical revisions from before installation.
- Saved views retain research selections locally in the browser. View links carry
  product, scope and version selections.
- Observed here separates explicit reported-CVE associations from product-name
  research candidates. Counts distinguish observations, endpoints and entities.
- Observatory retains the selected product/CVE and filters Critical, Critical +
  KEV or KEV using the relevant finding. An unrelated CVE on the host cannot
  supply the selected product's urgency. Readiness remains saved workflow state.

The additive index builds in the background and resumes after interruption. An
existing 0.9.83 catalog remains usable and needs no new annual-feed download.
Indexes and reference feeds remain outside working-record backups; selected
evidence stays in those backups. The installer does not embed the large catalog.

## Daily reference updates

EPSS and KEV use independent bulk feeds stored locally in `risk.sqlite3` beside
`catalog.sqlite3`. NVD failures do not block their updater. Existing enabled
catalog installations gain daily risk updates; the Library daily control governs
future scheduled work. Manual risk sync is also available.

Updates run while the app is open and catch up after reopening. A closed app or
sleeping computer cannot update. Cancellation and unsuccessful imports retain
the prior complete feed. Feed records and provenance are read consistently across
concurrent updates. A freshly downloaded old EPSS score date is still stale.

The EPSS and KEV bulk feeds require no API key. CVSS assessments are already part
of the public CVE data; this release indexes them rather than querying each score.

## Entity connections and visual field

Opening Connections resolves the registrable root of reported subdomains through
the existing public DNS resolver, with cached A/AAAA results, CNAMEs, timestamps
and raw-response hashes. Lookups run in the background within request/time limits.
Current DNS has a separate visual treatment and never changes saved attribution
or claims ownership. One Refresh control is available.

The main Workspace card now says **See the Dark Matter**. Generated cosmic/data
artwork gives the shell and Observatory depth through sparse stars, orbital data
traces and the immense cropped limb of an eclipse. The dark body extends beyond
the frame. Distorted cyber arcs and a fragmented violet/cyan corona reveal the
hidden mass. Four sparse packets follow bending, stretching trajectories while
the mass stays nearly still. Shared color tokens follow the artwork while
keeping status colors distinct. Reduced-motion settings retain a still backdrop. Report pages keep their established appearance.

## Upgrade

Install 0.9.84 over Dark Matter with **Retain existing data** selected. Working/demo
ports remain 8881/8882. The prior launch fix is retained. Attribution 0.2.4 is
included in the installed wheel and the source wheelhouses. 0.9.8 and 0.9.81 remain
separate editions. This release remains unstable pending native Windows review.

## Reference sources

- [NVD data feeds](https://nvd.nist.gov/vuln/data-feeds)
- [NVD CVE API](https://nvd.nist.gov/developers/vulnerabilities)
- [FIRST EPSS data](https://www.first.org/epss/data)
- [CISA KEV catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)
- [CISA official KEV mirror](https://github.com/cisagov/kev-data)

This product uses data from the NVD API but is not endorsed or certified by the NVD.
See VALIDATION.md for executed checks and HOME_VALIDATION.md for workstation review.

