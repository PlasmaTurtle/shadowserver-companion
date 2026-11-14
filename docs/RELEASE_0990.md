# 0.9.90 — Component versions and intake date separation

Vulnerable HTTP reports can carry their software versions in `component_version`
while leaving `version` blank. Accretion previously read only `version`. A second
defect required an API narrative-date confirmation before admission, rejecting
every otherwise eligible API row when that confirmation was absent.

## Changes

- Select meaningful `component_version` evidence for software profiles, with
  `version` as the fallback. Parse explicit product/version pairs from both
  columns and retain each pair's source field. Protocol-version profiles keep
  their protocol interpretation.
- Carry the selected version into quality scoring, lead and entity views,
  Observatory, Dark Matter, asset inventories, narrative groups and findings.
  Preserve every original column and the original downloaded file.
- Remove narrative-date admission/readiness gates and the import date-policy
  control. Source report dates and retrieval times remain acquisition provenance.
- New notification narratives use the case's recorded start date in office time
  and say that the agency began reviewing the observations on that date. Editing
  the document date or rendering on another day does not move the narrative date.
- Preserve existing narrative revisions and frozen/certified evidence. Existing
  drafts can adopt the current presentation through the established builder action.
- Increment the import policy and adapter versions so retained originals can be
  re-evaluated without deleting the previous decision history.

## Install and recover the rejected import

Close DarkMatter, run the 0.9.90 installer, and keep **Retain existing data** selected.
In **Shadowserver Data**, open the rejected import and choose
**Re-evaluate with current policy**. This reuses its retained original; downloading
the report again or changing its spreadsheet columns is unnecessary.

Schema 12, scoring weights, dependency pins and the 0.9.89 download compatibility
fix are retained. Native Windows installation remains a workstation acceptance check.

## Live report replay

The same 4,313-row Vulnerable HTTP report was processed through the actual intake
service in an isolated North Carolina workspace. Before the fix, 436 rows survived
structural filtering and all 436 failed the narrative-date gate. After the fix,
1,401 observations entered qualification across 404 root-domain groups; 1,022
admitted observations used component versions and explicit product/version pairs.

The remaining exclusions were 1,299 missing required values, 1,543 outside the
configured jurisdiction, 46 invalid hostnames, 23 malformed CVE identifiers and
one missing required version. Counts are exclusive and total 4,313.

This replay used an empty isolated local CVE catalog and a no-network attribution
stub. These are intake acceptance counts, not verified entity attributions or a
calibration of the user's temperatures. Original bytes and source columns were
verified unchanged. Only aggregate results are distributed; no report rows,
credentials, download capabilities or private workspace data are included.

See VALIDATION.md for executed automated checks and their limits.
