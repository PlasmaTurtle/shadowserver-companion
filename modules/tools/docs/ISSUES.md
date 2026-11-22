# Tools tracking

This tracker owns reusable runtime-tool maintenance. Last reviewed: **2026-11-21**.
Use the [module guide](README.md) for operation and interfaces and the
[project index](../../../docs/ISSUES.md) for shared work. Follow the
[issue lifecycle](../../../docs/ISSUES.md#maintaining-this-register).

| ID | Work | Status |
| --- | --- | --- |
| ISS020 | [Reported-host loading and redirects](#iss020-reported-host-loading-and-redirects) | Resolved |
| ISS026 | [Reusable tools and duplicate capabilities](#iss026-reusable-tools-and-duplicate-capabilities) | Resolved |

## ISS026 Reusable tools and duplicate capabilities

**Owner:** Tools coordinates; UI and each domain owner retain their own contracts.
**Status:** resolved, 2026-11-21; all ten findings implemented and verified.

The user requested an audit of reusable code and duplicate capabilities, with
explicit inputs/results returned to callers. The [tool contract](README.md#boundary-and-public-interface)
defines the common boundary; the [audit](TOOL_AUDIT.md) is the canonical inventory
of implementations, research baselines and deliberate compatibility boundaries.

All ten audit findings now have canonical implementations and migrated consumers.
Tools owns offline suffix/IP comparison, atomic publication, contained reads and
Retry-After parsing. UI owns formatting, downloads and request mechanics. Library
owns risk aliases; Investigations owns manifest interpretation. The obsolete
implementations are removed; independent packaging and historical saved identities
retain explicit compatibility boundaries.

**Demonstrated benefit:** capture no longer imports intake; Contacts agrees with
Attribution on internationalized DNS destinations; failed publication preserves
the prior file without leaving a temporary file; manifest readers agree; timestamps
honor the selected timezone; request errors retain structured HTTP detail; risk
feeds distinguish a server deadline from fallback policy. Original bytes and stored
identity examples remain unchanged. See the audit for before/after examples.

Evidence is in `validation/tool-consolidation-01/` in the Codex task workspace:
source snapshot, network/runtime/frontend comparisons, focused checks and final
integration logs. The original read-only audit remains in `validation/tool-audit-01/`.
Research and current interfaces live in the owning guides, not in transient logs.

**Validation:** 68 portable frontend suites and installed Edge Observatory
acceptance passed, including actual module loading and inspected desktop/narrow
output. The single complete backend run recorded **3,455 passed, 22 skipped,
207 subtests passed and 12 failures**. Ten failures predated these changes:
three documented API additions missing from one expectation, five queries
against the retired intake table, and four legacy fixtures using modern startup.
The other two were an uncoordinated same-target Windows replacement test exceeding
the documented caller-lock contract, and a test patching the manifest limit's old
owner. Native replacement comparisons and retained read-before-allocation checks
established the corrections; no production retry/compatibility workaround was added.

Complete affected files then passed **69 tests**, with three symlink-privilege
skips already represented in the full run. All 12 failures are covered by these
rechecks; the invalid concurrency test became two checks for distinct-target
publication and caller-locked same-target publication. Final collection is 3,490
tests. No runtime behavior changed after the combined run; formatting cleanup
preserved Python ASTs. The initial failed result remains in the evidence rather
than being relabeled a clean full run.

Program-map/import checks, Python lint/format, frontend syntax/format, local
documentation links and the release-identity gate passed. Independent code and
documentation reviews found no remaining blocker. Manifest compatibility examples
are synthetic; Windows symlink skips are explicit. No installer was built, and
current-version Windows release acceptance remains separate from these checks.

**Done when:** confirmed candidates have one appropriate implementation and their
real callers use it; obsolete copies are removed. Before/after output and failure
behavior must satisfy each consumer, including historical data contracts. Record
deliberate non-merges. Passing tests, moving files or adding wrappers alone does
not establish consolidation. Work proceeds one capability at a time without a
universal tool framework or changes to unrelated workflow policy.

## ISS020 Reported-host loading and redirects

**Owner:** Tools; Investigations owns the case integration. **Status:** Resolved — native browser loading.

**Problem:** the custom HTTP request broker prevented ordinary browser behavior.
It blocked methods and media, replaced headers/cookies, imposed short per-resource
waits and resource quotas, and recreated browser scheduling. Earlier repairs
improved redirects and some assets but still produced four incomplete live pages.
Those restrictions defeated the feature's purpose.

**Direction, 2026-11-21:** the user explicitly replaced the old capture constraints.
Build a functioning normal screenshot tool first, then evaluate security, data
and speed changes separately. The previous capture-specific network/scanning
policy is superseded; it does not constrain this implementation. Contact
extraction and unrelated Aegis callers retain their own existing contracts.

**Done when:** load the reported hostname first and use the main site only after
an actual load failure. Let the installed browser handle redirects, temporary
cookies, API requests, media, caching and connection reuse. Capture a rendered
viewport with correct original/final URL and fallback provenance. Confirm the
previously missing museum artwork/video and API-driven content using actual
images. Compare site access challenges with ordinary browser behavior rather
than labeling a blocked destination as a successfully loaded business page.
Failed loads must remain distinguishable, and cancellation/completion must clean
up the owned browser and profile. Test results support the visible improvement.

The replacement uses ordinary Chromium navigation and screenshot commands.
The request broker and deny-only proxy are retired, and URL handling supports
normal HTTP(S) addresses, ports, queries, fragments, IPs and IDNs. Browser
lifetime, loading and evidence attachment remain separate responsibilities.
No new runtime automation dependency is introduced.

**Maintenance lesson:** the ordinary browser reference rendered the museum
artwork/video and bookstore page that the custom broker left incomplete. Keeping
that broker and adjusting limits/tests prolonged the defect. The replacement
restored native browser behavior; comparing actual images then exposed and fixed
the separate background-frame readiness mistake. Future changes use the
[shared implementation guidance](../../../docs/DEVELOPMENT.md#established-implementations-and-reference-behavior)
and preserve these representative examples instead of tuning the loader to a
passing synthetic result.

**Native-loading verification before relocation:** 65 focused tests passed with no failures or skips on installed
Edge, covering native redirects/cookies, preflight/POST, a large decoded image,
HTTP video playback, embedded pages, slow CSS artwork, background-frame waits,
fallback, cancellation, profile cleanup and attachment identity. The UI provenance
and unsaved-draft check passed. Removing the retired capture-only transport-pool
extension restored the prior contact transport exactly; nine focused contact
checks passed. Source-map ownership, lint, formatting and documentation links
were checked separately. No application or installer build was run.

### Live-page completeness and diagnostics

The same ten public URLs in the source checkout's
`modules/tools/tests/fixtures/website_capture_live_urls.json` remain the manual
examples. They came from available public search results when direct
Google access was unavailable; they were not actual Google "I'm Feeling Lucky"
results. No failing site is replaced to improve the score.

The prior implementation and its screenshots are retained in
`validation/capture-live-repair-01/`. Its last pass produced five complete visible
viewports, four partial pages and a rate-limit response. The earlier 178-pass /
one-failure combined test run and isolated passing replay remain recorded there;
they do not certify the replacement.

`validation/capture-native-loading-01/` retains the exact before-source snapshot,
normal-browser reference captures, replacement checks and live comparison.
References use existing development Playwright with installed Edge; the actual
application uses its installed browser directly. Validation files remain outside
the maintained source and do not attach evidence to analyst cases. Live content
and access responses can change between runs, so visual comparison accompanies
status counts.

**Observed result:** the final `live-02/` pass captured all ten URLs in 87.90
seconds: nine complete visible pages and one genuine Cloudflare verification
page, with no partial results or failed captures. Every PNG was inspected. Korea's
museum artwork, Oklahoma's playing video, the bookstore hero, CoffeeRoast's
product grid and Kaldi's product badges now render. Boston and Roundabout no
longer wait for background tracking frames before saving the visible page.
Capture source hashes stayed unchanged throughout the run.

Bookshop's map was unavailable because both the independent native reference and
application reached Cloudflare verification. The saved image and challenge status
describe that actual result. Normal cross-origin preflight/POST and API rendering
are verified against a controlled local site; no website access control is bypassed.

The initial native `live-01/` pass was stopped after background-frame waiting was
reproduced twice; its five completed receipts remain diagnostic evidence. The
corrected final pass removed every capture profile and closed every owned browser.
The validation receipts distinguish profile cleanup from auxiliary files written
by Edge outside its profile. No validation run attached evidence to analyst cases
or changed their saved data.

### Reusable tool ownership

The user selected a shared Tools module on 2026-11-21. The native browser package,
its pure tests and fixtures moved together. Investigations retains its job service,
UI and evidence attachment tests and imports only the tool's public interface.
The browser loading algorithm, PNG dimensions and stored metadata contracts are
unchanged. Release selection and upgrade inventory explicitly include the new
owner; synthetic test fixtures belong only in source distributions.

**Relocation verification:** all 65 tool/case integration checks passed with no
failures or skips on installed Edge. Five packaging checks passed, including a
real import from the copied installed layout, source-only test fixtures and
upgrade inventory admission. The six browser implementation files and both
fixtures are byte-identical to the accepted native implementation; test bodies
and assertions were preserved. The tool's public interface imports without
loading Investigations. No public-site rerun or full app/installer build was needed.

Commands, hashes and results are in the Codex workspace's
`validation/capture-tool-relocation-01/` bundle. The Tools import boundary passes.
Global map regeneration remains blocked by five existing import-rule violations
from `modules.accretion.components.intake.filtering` to other Accretion, Library
and Workspace components. The map generator left the previous map intact; its
rules were not relaxed to make this relocation pass.

