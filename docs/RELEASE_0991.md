# 0.9.91 — Current leads, clear decisions

November 12, 2026. Dark Matter / Chaos unstable comparison build.

## Working queue

- Leads contains fully attributed, qualified work only. Pending lookups and attribution review stay in their own views.
- Each entity has one current qualified lead. Complementary findings on the same observation day combine; a newer day supersedes unworked older scope. Late-arriving old reports cannot replace the current lead.
- Findings are compared by endpoint, service, tag/CVE, selected software version, reported severity, product and reported location. File names and observation dates alone do not create a new finding.
- Repeat findings retain one compact first-seen / last-seen / distinct-day summary. An unchanged finding already assigned to a notification stays outside Leads; a changed version or finding can return.
- Ignore removes current work and suppresses unchanged repeats. Refresh updates the queue. Retired attribution support does not inflate entity or Workspace pending-work counts.
- Case-owned evidence, frozen sections, certified packages and original downloads remain intact. The upgrade removes redundant unworked queue copies, not historical notification evidence.
- An explicit provider-domain list excludes ISP-owned hostnames. A customer's domain is not rejected because its ASN or IP registration belongs to an ISP.

## Attribution and contacts

- Review rows show the registry name and have Accept / Reject beside Review. Accept binds to the exact displayed saved evidence; processing removes only that row and preserves position. Failed or stale decisions leave the row in place.
- Shared IPs are dated informational associations between entities. They do not force review or merge identities. Explicit entity merging remains available.
- Establishing an entity queues one bounded background contact lookup. An eligible sourced route becomes the default, visibly pending confirmation. Existing manual/preferred contacts and case snapshots are preserved. No messages are sent.

## Interface and finished documents

- Frosted surfaces apply to individual cards and controls. Layout gaps reveal the animated field.
- Report-builder paper is excluded from the dark panel, table and input overrides.
- New PDF and Word products use a small colored dot for internal priority. No temperature names or "Outreach priority" legend appear on recipient documents. Previously certified files remain immutable; generate a new revision to change an older product.
- Observatory paints its frame immediately and shows a loading message over the existing background drift. Navigation remains usable, failed loading offers retry, and a late response cannot overwrite another view. Reduced-motion and pause preferences are honored.

## Real-schema acceptance

The complete current upstream report inventory is pinned to commit `80f11a5a47b28ae27b15ca42ddb54d0a227f8f94` with its SHA-256. The update includes `component_version` declarations.

Explicit targeted adapters now cover Accessible HTTP (IPv4/IPv6), GPRS Tunnel, NTRIP and Accessible ISAKMP (IPv4/IPv6). Accessibility alone does not become a confirmed critical vulnerability. Protocol revisions remain separate from software-version evidence. NTRIP reads `ntrip_version`; incident adapters retain reported component/device versions.

Real SMTP data exposed the valid numeric-leading condition `21nails`. It is now accepted without allowing a bare number or arbitrary prose as a finding.

The issued account exposes multiple regional subscriptions. Acceptance selected the Carolinas subscription and applied the app's North Carolina jurisdiction. Sixteen requested report types were downloaded; IPv4 MS-RPC was unavailable November 5–11, so available IPv6 MS-RPC was checked additionally. These 17 files contain 98,777 rows; 1,179 reached the attribution stage under default critical policy with an empty isolated CVE catalog. They were not presented as qualified Leads.

Sequential local checks covered receipt/original-byte integrity, import, schema normalization, filtering, local catalog vetting, score/job persistence, targeted-mode samples, Leads visibility, Library Dark Matter and Observatory. External live attribution/contact qualification and subsequent real-case certification were not completed: automatic approval review blocked sending private-report hostnames to Google's DNS resolver. Automated fixture regressions cover those workflow transitions separately; they are not described as live acceptance.

## Update and recovery

Keep **Retain existing data** selected. Schema 13 creates the current-lead and repeat-memory indexes and the durable contact queue, then reconciles older unworked leads. Migration creates a pre-upgrade database backup. Keep a full workspace export before updating; use that export with the older build if comparing or rolling back, since an older release must not open the upgraded schema.

Dependency versions, intake weights, edition identity, API credential storage and the approved background artwork remain unchanged. This installer is unsigned. Native Windows installation and actual browser/GPU appearance remain workstation acceptance checks.
