# Shadowserver Companion 0.9.7 — Contact discovery

This update uses the ten-company Fortune 500 evaluation to reduce time spent
finding an appropriate outreach route. It improves the website paths that can
be checked, the meaning of a published contact, and the record of unsuccessful
checks. It retains the 0.9.6 report explainers and name-only sender support.

## What changed

| Observed failure | Change | Operational meaning |
| --- | --- | --- |
| Nine default runs stopped at a www redirect | The attributed company domain and its www counterpart form one normal website scope | A routine website redirect no longer requires a separate failed run and checkbox change |
| Ingram's explicit cybersecurity sentence was labeled General | Local contact purpose and nearby heading/card context are retained | A published cyber-reporting address can be distinguished from customer support |
| Kiewit's Webmaster form choice was lost | Form-routing labels and options are retained | The operator can see which inquiry choice to use, without the app submitting a form |
| J.B. Hunt support headings disappeared; Williams' emergency number looked general | Product support and unrelated departments have explicit purposes; emergency routes are excluded from routine suggestions | A technical referral remains a referral, and an emergency line does not become a cyber contact |
| Disclosure links, company portals and external forms were missed | Prioritize explicit reporting links and allow one additional relevant link level within the run budget | Published reporting destinations become visible with the page that referred to them |
| Blocks, large responses and script-rendered pages obscured what was checked | Dated coverage and next steps distinguish checked pages from unreadable or unvisited destinations | The saved result tells the next analyst where work has already been done and where a manual check is still needed |

There are no company-specific inbox guesses or hard-coded Fortune 500 contact
addresses in the discovery rules. The failure cases are regression examples,
not a lookup directory.

## Reading the result

The best available route is shown with its published purpose and review state.
A dedicated security route, an IT/webmaster referral and product technical
support are different results. Privacy, recruiting, media, investor, compliance
and physical-emergency contacts retain their actual purposes. A contact published
on the company website is not automatically suitable for this notification.

Expand the coverage record to see URLs, check times and outcomes. A completed
page with no suitable route means only that nothing suitable was found on that
page. A blocked response, incomplete capture, unreadable script-dependent page or
unvisited reporting link means the check is still unresolved. None of these is
proof that the company has no contact.

Existing confirmed and preferred routes retain their review dates and recorded
usability. A bounce or explicit unusable decision remains separate from whether
the address is still published. Discovery, human review, delivery and
acknowledgement remain separate steps.

## Keeping it lightweight

Each run has a hard ceiling of eight HTTP requests: up to six ordinary requests
and two redirect-follow requests. The earlier evaluation used six requests total;
comparisons must account for the changed redirect allowance. The total deadline
remains 30 seconds, with at most eight seconds per request, 1 MiB per normal
response, 3 MiB per run and 50 candidates. Error-response evidence has a separate
64 KiB capture cap so a large error page cannot consume most of the allowance.

Discovery uses verified HTTPS and public-address checks. Only the approved
company domain and its www counterpart are fetched. An explicitly published
subdomain or external reporting destination is retained as a reviewable pointer,
with its referring page and original URL; it does not authorize a wider crawl.
Known tracking parameters may be removed for a company-page request while the
original link remains available. Unknown query destinations require review.

Oversized pages remain incomplete. Only safely completed link evidence from a
captured prefix is eligible for limited extraction, with an explicit partial
capture and the hash of the bytes actually saved. No full-page hash is implied.
Bot blocks are terminal; the module does not switch identities or bypass them.
There is no browser-rendering crawler, broad subdomain search or form submission.

## Specific-page follow-up

Use the specific-page check for a URL within the approved website pair when you
already know a promising company page. It inspects that source without repeating
the normal site search. A focused check does not mark unrelated saved contacts
as missing. Outside reporting destinations can be opened and reviewed manually;
the app retains the publication trail and the user's existing review controls.

## Evaluation and acceptance

The accompanying guide and evidence distinguish diagnostic fixtures from live
website results. The original evaluation did not redistribute complete captured
HTML, so reconstructed tests are labeled diagnostic examples rather than replayed
website snapshots. Live retrieval through the evaluation's managed-proxy adapter
is separate from production DNS/public-IP-pinning transport validation.

See VALIDATION.md for executed checks and HOME_VALIDATION.md for Windows checks.
Version 0.9.7 remains unstable pending exact-build workstation acceptance; the
installer is unsigned. No company was contacted and no report was submitted.
