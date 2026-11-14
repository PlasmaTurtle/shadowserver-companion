# Shadowserver Companion 0.9.6 - Report explainers

This update adds the approved shared Information page and ten plain-English
report-family pages. Each family explains what the source report generally
observes, why it supports outreach, and where an owner, outside provider or
internal IT team can begin. Technical finding snippets remain separate from
whole-page explainers. Recipient copy contains no mockup or testing labels.

## Where to spend review time

These are workload recommendations for this outreach program. They do not
replace the severity, confidence or evidence supplied in an individual row.

| Requested report | Recommendation | Basis |
| --- | --- | --- |
| Vulnerable HTTP | Priority | Specific web-service weaknesses; inspect the actual CVE or finding tag. |
| Vulnerable SMTP | Priority | Mail-server vulnerability observations; confirm vendor patches and banner accuracy. |
| Vulnerable ISAKMP | Include; rank by finding | Critical VPN CVEs can be high value; amplification-only observations are a different concern. |
| Accessible RDP | Targeted exposure review | Public remote desktop is worth reviewing; reachability does not prove a successful sign-in. |
| Open MongoDB Service | Prioritize no-auth or CVE findings | Distinguish database visibility, missing authentication and version-based vulnerability tags. |
| Accessible GPRS Tunnel | Defer routine business outreach | Telecom-specific exposure; retain for a focused operator review when relevant. |
| Vulnerable Exchange Server | Priority | Specific business-email server concerns; retain possible-vulnerability qualifiers. |
| Badsecrets | Priority | Known or weak application cryptographic keys; a CVE is not required for a useful finding. |
| Compromised Website | Prompt incident review | Potentially existing misuse; evaluate exact tags, confidence and source details before outreach. |
| Compromised IoT Device | Prompt incident review | Device-related compromise indicators; a public gateway may represent another device behind it. |
| Accessible MS-RPC Service | Targeted exposure review | Public Windows RPC exposure merits a specific network/service review. |
| IPv6 Vulnerable HTTP | Priority; shared HTTP page | Same report family, with the exact IPv6 source identity retained. |
| IPv6 Vulnerable Exchange Server | Priority; shared Exchange page | Same report family, with the exact IPv6 source identity retained. |
| Accessible HTTP | Defer standalone outreach | Ordinary public web-service inventory; the report does not identify vulnerabilities. |
| Accessible NTRIP | Defer routine outreach | Correction-data services may be intentionally public; no vulnerability check is performed. |
| Accessible ISAKMP | Defer standalone outreach | Informational VPN-service inventory, distinct from Vulnerable ISAKMP. |
| IPv6 Accessible ISAKMP | Defer standalone outreach | Same informational inventory basis as IPv4. |

The 12 included names in the requested list reduce to ten page families because
the two requested IPv6 vulnerability variants share their family's explanation.
The bank also recognizes official IPv6 counterparts of the other included
families. It never interprets ordinary Accessible HTTP as Vulnerable HTTP.

## Using the update

New notification cases select relevant pages from retained, exact source report
types. Manual imports can use a recognized source filename, explicit row identity
or the configured Report profile. An offline API receipt supplies its exact
report type. Unknown source types remain available for research and deliberate
classification; generic HTTP columns alone do not establish a vulnerability
report's identity.

The existing jurisdiction, hostname, attribution and reported-severity controls
remain. Badsecrets and ordinary MongoDB, RDP and MS-RPC observations commonly
carry a high source severity; their priority here does not make them eligible
under critical-only intake. The default critical-only mode is not broadened. Use targeted outreach
with a recorded reason for noncritical work, then select the targeted-outreach
narrative in the report editor before validation. Any included compromise
indicator also requires that deliberate narrative choice, including incident
context retained alongside a critical HTTP finding. RDP, MS-RPC and incident families
require deliberate targeted review even if a row carries a critical label.
MongoDB's ordinary exposure observations and VPN amplification findings should
not receive the priority of a specific critical vulnerability merely because
they share a report family. Existing saved imports are not silently reprocessed.

Protocol versions are not represented as installed software versions. Source
tags, qualifiers and full rows are retained. Exposure and incident narratives
use their own evidence wording; they are not automatically called critical
vulnerabilities. The established emailed-report narrative date remains the row
date plus one day. An unconfirmed API date basis remains a review gate.

The shared Information page appears once, followed by one page per relevant
family. Mixed-family cases can therefore need more than two information pages.
The source registry and explanatory copy are pinned with the draft and section
review. Historical frozen sections and certified report bytes remain unchanged;
updating an older draft uses the existing explicit adoption and reopen process.

In Settings, Title is optional. A name-only sender has no assumed title and no
empty title line. Existing saved titles are retained. This applies to the
notification's sender and sign-off, not the fixed recipient role.

## Technical snippets for findings without a CVE

The first technical snippet set covers end-of-life web components, PHP, IIS and
Exchange. These explanations belong in the technical findings section and are
separate from the report-family information pages. Exact report identity and
lifecycle tags select the wording; an old-looking version alone does not invent
an EOL finding or a CVE.

Each matched snippet explains the support concern, the limits of the observation,
and a concrete technical review starting point with citations. PHP vendor
backports, Windows/IIS support coverage and Exchange security-update entitlements
remain matters for verification. End of life is not treated as evidence that
every later CVE applies or that the system was compromised. The bank can accept
additional technologies later; this release deliberately keeps the initial set
small. Existing saved reports retain their earlier wording until explicit adoption.

## Evidence and sources

The bank records source URLs, titles and the November 10, 2026 review date.
Readable citations are included in the recipient pages and the retained source
register. Workload recommendations above are editorial judgments based on the
following official report descriptions:

- [Vulnerable HTTP](https://www.shadowserver.org/what-we-do/network-reporting/vulnerable-http-report/)
- [Vulnerable SMTP](https://www.shadowserver.org/what-we-do/network-reporting/vulnerable-smtp-report/)
- [Vulnerable ISAKMP](https://www.shadowserver.org/what-we-do/network-reporting/vulnerable-isakmp-report/)
- [Vulnerable Exchange Server](https://www.shadowserver.org/what-we-do/network-reporting/vulnerable-exchange-server-report/)
- [Accessible RDP](https://www.shadowserver.org/what-we-do/network-reporting/accessible-rdp-report/)
- [Open MongoDB](https://www.shadowserver.org/what-we-do/network-reporting/open-mongodb-report/)
- [Badsecrets](https://www.shadowserver.org/what-we-do/network-reporting/badsecrets-report/)
- [Compromised Website](https://www.shadowserver.org/what-we-do/network-reporting/compromised-website-report/)
- [Compromised IoT](https://www.shadowserver.org/what-we-do/network-reporting/compromised-iot-report/)
- [Accessible MS-RPC](https://www.shadowserver.org/what-we-do/network-reporting/accessible-ms-rpc-service-report/)
- [Accessible HTTP](https://www.shadowserver.org/what-we-do/network-reporting/accessible-http-report/)
- [Accessible ISAKMP](https://www.shadowserver.org/what-we-do/network-reporting/accessible-isakmp-report/)
- [Accessible GPRS Tunnel](https://www.shadowserver.org/what-we-do/network-reporting/accessible-gprs-tunneling-protocol-gtp-report/)
- [Accessible NTRIP](https://www.shadowserver.org/what-we-do/network-reporting/accessible-ntrip-report/)
- [Official source identifiers](https://github.com/The-Shadowserver-Foundation/report_schema/blob/main/types.md)

## Release boundary

This is version 0.9.6, unstable pending exact-build Windows acceptance. The
installer remains unsigned. This update does not connect a live API account,
schedule downloads, perform additional scans or send notifications. It builds
on the existing local workflow and offline API receipt handoff. See
VALIDATION.md for executed checks and HOME_VALIDATION.md for workstation checks.
