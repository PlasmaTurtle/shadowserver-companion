# 0.9.87 — Accretion

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

Accretion replaces chronological intake with a strict admission decision and a
saved, explainable outreach priority. Existing notification, attribution and
evidence workflows remain independent.

## What the audit retained

Original source bytes, hashes and row identities; bounded CSV/Excel ingestion;
jurisdiction and hostname preferences; supported report adapters and non-CVE
exceptions; root-domain grouping with contextual rows; explicit attribution;
pause, retry and reevaluation; separate Entities, Leads and notifications.

## What changed

- Filter malformed or out-of-scope rows before local catalog work. Whitespace-only
  required fields no longer pass. Vet each distinct reported CVE once per batch.
- Default admission accepts critical findings or verified known exploitation.
  Complete local CVSS coverage controls CVE-only severity in both directions;
  partial coverage retains the reported fallback. Source severity is never rewritten.
  Withdrawn-only findings cannot qualify. KEV does not bypass unsupported,
  incident-only, jurisdiction, structural or API-date gates.
- Compute separate Quality and Urgency scores, then rank by their aggregate.
  Attribution qualification remains a different state; a score never substitutes
  for an ownership finding or proves installed-version applicability.
- Save the policy, factors, local reference records, source hashes and scoring time.
  Reads, catalog updates and attribution retries do not silently change priority.
  Reevaluate an original when a fresh policy assessment is wanted.
- Carry the selected lead's snapshot into notification scope. Adding scope retains
  each source decision and displays the strongest aggregate. Supporting historical
  attribution rows do not import unrelated priorities. Certified packages preserve
  their own snapshots.
- Show subtle temperature accents and an accessible designator in Leads, Workspace
  and notification work. New finished PDF/DOCX products have a small outreach-priority
  marker, separate from TLP and CVSS. The evidence reader includes a collapsed
  explanation and a hashed JSON record.

## Provisional policy

| Score | Factor | Maximum points |
| --- | --- | ---: |
| Quality | Source identity, date and traceability | 40 |
| Quality | Specific finding and observed product/version evidence | 40 |
| Quality | Entity association | 20 |
| Urgency | Strongest finding's CVSS, or reported-severity fallback | 40 |
| Urgency | That finding's KEV membership | 35 |
| Urgency | That finding's EPSS probability | 15 |
| Urgency | Agency focus or recorded ransomware use | 10 |

Aggregate = (Quality + Urgency) / 2. Temperatures: Cool below 40; Warm 40–59.9;
Hot 60–79.9; Blazing 80–100. These are initial operating weights, not validated
probabilities. Repeated rows do not multiply the score. Signals from unrelated
CVEs are not combined into an imaginary worst-case vulnerability. Missing KEV or
EPSS remains unknown; stale snapshots are labelled.

Settings provides optional exact city and observed-product priorities. CISA KEV's
explicit known-ransomware field can earn the same ten-point factor; it does not
stack with a campaign match. Concentration anomalies, domain-size proxies and
automatic technology-risk guesses are deferred until representative leads justify
them. The central policy and saved snapshots make calibration reproducible.

## Dark Matter

Usable in-jurisdiction observations outside the admitted lead groups receive an
official `dark_matter` disposition. Malformed rows remain in original evidence
and rejection totals, without becoming field records or analyst tasks. A compact
index preserves the source identity, reason and import-policy history.

Library has a Dark Matter view; Observatory exposes disposition filters and
counts, including product/CVE observation links. A later saved root-domain entity
association can connect earlier observations without promoting them to Leads or
claiming row-specific attribution. Shared IPs never establish ownership.

Repeated policy evaluations count as one source observation in the current field.
A retained admission takes precedence over a rejected evaluation; policy history
is preserved. Old imports remain unclassified until explicitly reevaluated.
Library pages are bounded; Observatory disposition lookup is batched and capped
with a visible coverage warning. Original files remain the complete evidence.

## Upgrade and validation

Schema 12 adds score snapshots and the compact disposition index. Migration creates
a backup and preserves existing data. Older executables cannot open schema 12;
use a pre-upgrade backup to return to an older release. Existing certified artifacts
are not regenerated, and legacy leads remain visibly unscored.

Run `python tools/verify_accretion.py` for the synthetic temperature matrix, and
`python tools/verify.py --skip-browser` for repeatable non-browser verification.
See VALIDATION.md for the final results and limits. This remains the Dark Matter
Chaos unstable edition; native Windows acceptance is still required.

