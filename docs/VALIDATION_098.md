# 0.9.8 validation

Release remains unstable pending version-specific workstation acceptance.
Checks below use synthetic workspaces unless explicitly marked public-site.
They do not establish native Windows, desktop Word or live Shadowserver account
acceptance. Prior 0.9.7 results are retained in docs/VALIDATION_097.md.

## Automated regression

Final verification results are recorded in the accompanying validation evidence.
Python 3.14.10 and the pinned dependencies are used. No runtime dependency upgrade
is included. The standalone API module source is unchanged and manifest-pinned.

## Executed acceptance

- All five section freezes persist content, author/time and hashes while renderer
  entry points are forbidden. Fifteen local HTTP freezes across three independent
  synthetic cases took 0.114–0.277 seconds each, with zero renderer calls and
  zero new artwork files. These are Linux observations, not Windows timing. Legacy artwork-bearing
  snapshots remain readable; projection tests preserve original bytes and hashes.
- Compact appendix: full synthetic specimen 22 to 3 pages; empty specimen 5 to 0;
  100 repeated observations fit one page with counts, dates and source-row ranges.
  All distinct resource URLs and original evidence are retained. PDF and a
  LibreOffice conversion of the DOCX each produce nine total pages; appendix
  images were visually checked. This is not desktop Microsoft Word acceptance.
- Evidence reader: 24 records, 49 initially collapsed details, valid fragment links,
  functional expansion and no horizontal overflow at 1280px and 390px. The
  portable file was visually inspected in real Chromium. Original JSON/files
  remain available alongside readable summaries.
- Upgrade and restore: a 0.9.7 synthetic workspace upgraded to schema 10 and was
  restored into a separate folder. All 258 protected files and legacy table
  fields remained unchanged, all 15 historical download hashes matched per
  phase, and all 15 historical frozen sections remained validated. New case
  identity snapshots match their original projections.
- Navigation browser checks cover independent entity save/review, no unintended
  case creation, explicit lead start, canonical Workspace report ownership,
  URL refresh, legacy aliases, Back/filter behavior and responsive layout.
- Contact browser checks cover independent entity discovery, immediate blank-field
  autocomplete, preserving typed values, known-contact reuse without a lookup,
  collapsed details/focus, evidence download and desktop/mobile light/dark views.
- API browser checks cover connect, listing, selected import, deduplication,
  cancellation and credential removal. Synthetic requests produce no external
  traffic. Credentials are cleared from inputs and never stored in browser
  persistence. Backend checks cover redaction, CSRF/origin controls, maintenance
  exclusion, cancellation and orderly shutdown.

Browser automation used Debian Chromium headless shell 150 through a wrapper
with no-zygote/single-process flags required by this test host. The application
itself does not require those flags. Tests run a local synthetic fixture and
browser in the same process tree. This is not native Windows browser acceptance.

## Public-site contact checks

Final-source runs cover Wasabi and the ten-company comparison set. Wasabi
returns security@wasabi.com and support@wasabi.com from complete HTTP 200
captures in six requests (24.677 seconds on this host). Its overall run remains
partial because additional published pages exceed the bounded request budget;
that does not hide the contacts already found.

Other outcomes include an Ingram security contact, Kiewit referral, Tractor Supply
reporting route, and JB Hunt product-support referral. Blocked, timeout and
incomplete outcomes remain explicit. These checks used a managed-proxy adapter;
production DNS/public-address pinning, native TLS/proxy behavior and workstation
connectivity are not established. Workday timed out live; a retained-page replay
separately recovered its security portal. Some lower-priority department labels
remain imperfect. The tool is a lightweight finder, not a completeness claim.

Budgets: 4 MiB/page, 12 MiB/run, six ordinary page requests plus two redirect
requests, 30-second overall limit. HTTP status, capture completeness and extraction
outcome are distinct; intact contacts are retained from partial captures.

## Remaining acceptance

Native installation/upgrade/launch, Windows credential storage, desktop Word,
actual browser zoom/screen reader and issued Shadowserver account access remain
pending. The installer is unsigned. See HOME_VALIDATION.md. Neither test passage
nor a successful cross-platform build promotes the release to stable.
