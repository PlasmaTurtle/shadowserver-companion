# Validation · Shadowserver Companion 0.9.7 · UNSTABLE

Executed November 10, 2026 (America/New_York), using Linux Python 3.14.10 and
synthetic workspaces. This is the contact-discovery upgrade based on 0.9.6.
Historical 0.9.6 validation is preserved in docs/VALIDATION_096.md.

## Final automated checks

The final integrated run passed **278 tests** covering contact extraction,
transport and scope, jobs, API and persistence, evidence integrity, review and
adoption, delivery outcomes, workspace backup/recovery, schema, API contracts,
module boundaries and release packaging safeguards. This is a focused regression,
not a repeat of the full 0.9.6 application suite. The original 0.9.6 test counts
remain historical.

All **18 frontend module suites** passed. Python Ruff format/lint, frontend
Prettier/syntax, release identity and the program map passed: 17 components,
219 owned modules, no dependency cycles. No runtime dependency was added or
upgraded; the 34 pinned Windows dependency artifacts are unchanged.

Independent review passed **32 boundary checks**. These include HTTPS/public
scope restrictions, external URLs retained without fetching, exact prefix hashes,
64 KiB error capture, closed-link extraction from incomplete HTML, adjacent
contact isolation, conflicting-purpose suppression, duplicate-URL coverage and
an eight-request ceiling. Additional production tests cover private/public
suffix boundaries, so a business literally named www cannot authorize a parent
public suffix or shared hosting suffix.

## Evidence-based comparison

The supplied Fortune 500 evaluation contained request/source hashes and excerpts,
not complete captured HTML. The diagnostic comparison therefore reconstructs
narrow failure examples and labels them as reconstructions. Its baseline and
upgrade results are retained separately; they are not a population estimate or
live-contact recall measurement.

A fresh default bounded run was performed for each of the same ten companies.
These live checks use the earlier evaluation's test-only managed-proxy adapter;
they do not validate production DNS/public-IP pinning or native Windows transport.
They make no contact attempt or form submission. The new budget permits at most
six ordinary requests plus two redirects; the original evaluation had six total
requests. Time and byte limits remain unchanged.

Live review exposed additional markup differences beyond the first fixtures:
J.B. Hunt uses short bold paragraphs for Tech Support labels, while Workday's
security-portal link has a descriptive accessible label but visible Learn More
text. The final parser handles both, excludes demonstration/sales forms, and
keeps ordinary security-information pages as crawl links rather than contact
candidates. All 29 successful captured pages were reparsed with the final parser.
Separate final-source default live confirmation runs cover J.B. Hunt and Workday.

The first ten-company live process loaded an earlier same-turn revision before
three final refinements: failed-attempt metadata, public-suffix scope protection,
and form/heading/accessible-label parsing. Its original source hashes and results
are preserved. Final parser checks, focused live confirmations and automated
regressions are recorded separately; no earlier run is relabeled as an exact
final-build run. Raw website bodies are not redistributed in the evidence archive.

A published route is not proof of deliverability or suitability for this
notification. Blocked and incomplete checks remain unresolved. Workday's portal
can be surfaced as a published pointer; no hidden HackerOne destination is
inferred, and no JavaScript-rendering crawler was added.

## Upgrade preservation

An unmodified 0.9.6 source checkout created an isolated synthetic workspace with
three certified reports and 15 frozen section reviews. Opening it with 0.9.7
and reopening its backup in another folder both passed. Protected records,
saved settings, frozen review status and report/source files were unchanged;
each path verified 15 historical download hashes. Contact-specific regressions
also cover legacy scope, saved decisions, routing metadata, confirmed/preferred
contacts, known bounces and export/restore integrity. There is no schema migration.

The report narrative, explainer banks and rendering modules remain unchanged
from 0.9.6. No user database was used.

## Distribution and acceptance limits

The installer and source ZIP contain allowlisted application files and synthetic
fixtures. Build evidence records artifact hashes, source parity, extracted
installer payload hashes and compilation. The official embedded Python 3.14.10
runtime is checked against its pinned SHA-256. The local NSIS/7zip tools were
obtained from signed Debian repository metadata and verified package hashes.
The installer remains unsigned.

Interactive browser tests could not run: the Playwright browser download
repeatedly returned an invalid or truncated archive. No real-browser UI pass is
claimed for this build. The contact browser tests were updated, and all frontend
VM suites passed. The tooling report records backend/browser checks as skipped
because backend results are separate and browser execution was unavailable.
Its complete:false field is not represented as full workstation verification.

Native Windows fresh install, retain-data upgrade, reset, desktop Word and
interactive UI acceptance remain pending in HOME_VALIDATION.md. Live API account
behavior and actual outreach delivery were not tested. Version 0.9.7 remains
unstable until exact-build workstation acceptance.

TLP:AMBER
