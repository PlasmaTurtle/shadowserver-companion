# Tools

Tools owns reusable application runtime tools: website capture, offline network
identity, HTTP field parsing and filesystem operations. Each tool keeps its
implementation, tests and resources here; callers
retain their domain workflow, UI, persistence and authorization.

[Architecture](../../../docs/ARCHITECTURE.md) · [Tools tracking](ISSUES.md) ·
[Investigations integration](../../investigations/docs/README.md#website-loading-and-capture)

## Start here

| Maintenance area | Start here |
| --- | --- |
| Public website capture interface | [website_capture/__init__.py](../components/website_capture/__init__.py) |
| Browser lifetime and PNG capture | [browser.py](../components/website_capture/browser.py) |
| Navigation, main-site fallback and readiness | [navigation.py](../components/website_capture/navigation.py) |
| URL normalization | [transport.py](../components/website_capture/transport.py) |
| Offline suffix extraction and IP comparison | [network_identity.py](../components/network_identity.py) |
| HTTP Retry-After field parsing | [http.py](../components/http.py) |
| Atomic publication and contained file reads | [filesystem.py](../components/filesystem.py) |
| Native browser and tool contracts | `modules/tools/tests/` in the source checkout |

## Boundary and public interface

Tools accept explicit inputs, perform one named capability and return their
result to the caller. They do not discover the calling workflow or call back into
it to change business state. Operational I/O, such as opening a browser or writing
an explicitly requested file, is part of the declared capability.

| Contract area | Standard |
| --- | --- |
| Inputs | Named, typed values and explicit options. Pass the data needed for the operation, not an application, store, request, case object or general context bag. |
| Outputs | Return a documented value or structured result. Use ordinary values for simple operations and a small named result when fields need a stable meaning. Returned streams/handles must have explicit lifetime ownership. |
| Failures | Document meaningful exception types or result states. Distinguish cancellation and partial output from success; the caller decides whether to retry, display or persist the outcome. |
| Side effects | Declare network, process and filesystem effects. The tool cleans up resources it creates unless ownership is explicitly transferred in the result; caller-owned resources remain caller-owned. No hidden database writes, workflow events or UI updates. |
| Configuration | Pass needed settings or dependencies explicitly. Document platform defaults; do not read business settings or credentials from a caller's global state. |
| Control | Accept a narrow cancellation/deadline input where work needs it. If progress is necessary, emit documented progress values; it must not become a callback for mutating the caller's workflow. |
| Reuse | One canonical implementation per capability and contract. UI presentation stays in UI; domain decisions stay with their owner. Similar code with different contracts is not automatically one tool. |
| Composition | Call ordinary public functions or small objects directly. No universal tool base class, service locator, plugin registry or generic success/error envelope is required. |

Prefer existing standard/library interfaces. Python's
[dataclasses](https://docs.python.org/3.14/library/dataclasses.html) can name
multi-field results when useful; they are not mandatory for scalar functions.
[Context managers](https://docs.python.org/3.14/library/contextlib.html) provide
established resource-lifetime patterns. Do not add wrappers around a standard
operation unless they centralize a real shared contract.

Current public interfaces remain compatible until a migration updates their
callers. The [consolidation record](TOOL_AUDIT.md) documents current implementations,
outcomes and deliberate compatibility boundaries. This contract does not authorize
changing saved data formats merely to make interfaces uniform.

### Website capture interface

Callers import `capture_website`, `web_url` and `WebsiteLoadError` from
`modules.tools.components.website_capture`. The capture signature is
`capture_website(url, *, cancel_event=None, executable=None, skip_urls=(), require_usable=False)` and returns
`(png_bytes, metadata)`. `web_url(value)` normalizes a complete HTTP(S) URL.
`require_usable=True` tries fallback candidates after partial/challenge output and
returns only a functioning page or login page. The default keeps diagnostic captures
available for case evidence. `skip_urls` avoids repeating earlier attempts when a
caller checks several reported hosts in one group. No browser starts at import time.
Loading, fallback and temporary browser cleanup
are owned by the tool; no database, case identifier or application server is needed.

Investigations calls this interface through `website_jobs.py`. It owns reported
hostname selection, queue admission, case cancellation controls and guarded evidence
attachment. Other modules can use the same tool without importing Investigations.
The tool reuses Tools' offline PSL helper and the timestamp primitive in Workspace.
It does not import intake. The registered import boundary excludes consuming
workflows, API and database dependencies.

This module is distinct from root `tools/` (verification, packaging and installer
commands) and module-specific `tools/` folders (developer utilities). Keep the
standard [module folders](../../../docs/ARCHITECTURE.md#find-the-owner); add tools
for actual reusable capabilities, without introducing a generic plugin framework.

## Shared operations

Import each capability from its named file under `modules.tools.components`.
These functions perform no application initialization or hidden business writes.

| Interface | Inputs and result | Caller responsibility |
| --- | --- | --- |
| `network_identity.extract_domain(hostname)` | Native `tldextract.ExtractResult`, using the bundled private-aware PSL without network refresh | Decide what a missing registrable root means; extraction does not validate DNS identity |
| `network_identity.root_domain(hostname)` | Registrable domain, or the original hostname when absent | Use only where retaining the original is the intended fallback |
| `network_identity.comparison_address(value)` | Standard `ip_address` inputs to an address object; IPv4-mapped IPv6 compares as IPv4 | Eligibility, zones and persisted-key policy; invalid inputs raise `ValueError` |
| `http.parse_retry_after(value, *, now)` | Header plus aware datetime to nonnegative server delay or `None` | Fallback, minimum/maximum delay, retry scheduling and deadlines |
| `filesystem.atomic_write(destination, content)` | Destination plus bytes; returns `None` after replacement, raises on failure | Create/authorize parent directory, serialize content and coordinate writers |
| `filesystem.contained_file(root, relative)` / `contained_directory(root, relative)` | Explicit root and canonical relative name to existing `Path` | Trusted root and immutable directory tree; returned paths are not open handles |
| `filesystem.read_contained_file(root, relative, *, sha256=None, max_bytes=None)` | Bytes, optionally bounded and digest-checked | Choose limit/digest and interpret content; `FileTooLarge`/`DigestMismatch` identify failures |

Atomic writes use a unique same-directory temporary file, flush/fsync, close and
`os.replace`, with failure cleanup. This is single-file publication, not a
multi-file transaction or a promise that a rename survives power loss.
Callers serialize writes to the same destination: Windows can reject simultaneous
native replacements with an access error. The helper propagates I/O failures and
cleans up; it does not add hidden retries or process-wide locks.

Contained reads preserve immutable-package path semantics; they do not protect
against another process replacing a trusted directory tree during a read.

Investigations owns manifest names, limits, JSON policy and artifact inventory.
Workspace and Settings retain their existing serialization and workflow locks.
UI presentation/request helpers remain in UI; Library owns risk interpretation.
The [consolidation record](TOOL_AUDIT.md) links implementations, research and outcomes.

## Website loading and capture

Capture uses ordinary installed Edge/Chrome in a fresh temporary profile. The
browser handles redirects, cookies created during the visit, HTTP methods, API
requests, images, video, fonts and caching. The application does not replay or
filter page requests through its own HTTP client or proxy. It does not run a
per-response AMSI gate or impose request-count/per-resource download quotas.
The browser's normal TLS and sandbox behavior apply. There is no application
public-address gate; HTTP(S) URL validation checks syntax, not destination trust.

Start with the exact reported URL. A failed load can try the other HTTP/S scheme
on that host, then the main site's apex/`www` candidates, using the existing
private-aware Public Suffix List. Keep supplied paths, queries and fragments on
same-host attempts. IP addresses, single-label names and localhost names do not
acquire invented domain fallbacks. A rendered page does not trigger an unrelated
main-site request.

[navigation.py](../components/website_capture/navigation.py) owns page loading,
render readiness and fallback. [browser.py](../components/website_capture/browser.py)
owns the temporary browser/profile and the 1440 × 900 PNG. It uses normal
[Chrome Headless](https://developer.chrome.com/docs/automation-and-testing/headless)
with the established navigation/screenshot commands in the
[DevTools Page protocol](https://chromedevtools.github.io/devtools-protocol/tot/Page/).
Wait for rendered content, visible image/video data and fonts before capture.
Main-frame rendering assets can delay readiness; background tracking frames,
scripts and persistent API traffic do not require indefinite network idleness.
Hidden password fields do not classify a public page as a login page. A video
frame or authored poster must have loaded image data before it counts as ready.
A cancelable overall wait prevents a permanently stalled page from holding the
job forever. Each navigation has its own timeout, including blank documents that
have fired a load event, so a failed first page leaves time for fallback. A blank,
failed or error response cannot become a functioning login merely because its URL
contains `/login`. Detailed timing belongs in the implementation and verification record.

The tool returns PNG bytes and metadata: `requested_url`, `final_url`, `title`,
`http_status`, `capture_status`, `redirects`, ordered `attempts` and `fallback_used`.
It does not attach evidence or decide which results belong in a notification.
Failed target loads raise `WebsiteLoadError` with `metadata` and `attempted_urls`;
browser startup, process and protocol failures remain operational exceptions.
Partial, challenge and login pages retain their actual classification. The caller
decides whether a target failure is retryable or reviewable. Completion, cancellation and exceptions close the owned
browser processes and remove the temporary profile. The personal browser profile
is not used.

Browser startup and page loading have separate cancellable budgets. A Windows
kill-on-close job owns the process tree without an arbitrary child-process ceiling;
cleanup removes the temporary profile's cache and downloads as well. Synthetic
protocol checks do not establish native browser, job or enterprise-policy acceptance;
use the [Windows checklist](../../../docs/WINDOWS_ACCEPTANCE.md) for that scope.

The normal browser behavior is covered by [ISS020](ISSUES.md#iss020-reported-host-loading-and-redirects).
Static contact extraction remains a separate Entities capability with its own
validation/scanning contract.

## Verification

Run from the repository root with the configured development environment:

```text
python -m pytest -q modules/tools/tests
```

The caller checks remain in Investigations:

```text
python -m pytest -q modules/investigations/tests/test_website_capture_0985.py modules/investigations/tests/test_website_capture_navigation_contract.py
```

`test_website_navigation.py` adds exact-host/fallback, redirect, viewport loading
and native browser behavior checks against local test servers. It uses
installed Edge/Chrome or the explicit
`CHROMIUM_EXECUTABLE` path; browser checks report skips when neither is available.
Its deterministic checks use local synthetic pages and do not use analyst data.
The tiny `fixtures/website_capture_green.webm` clip is locally generated test
content for verifying an actual decoded video frame over HTTP, including range
requests. Tests do not download external media fixtures.

The source checkout's `modules/tools/tests/fixtures/website_capture_live_urls.json` retains
ten public URLs selected before the November 21 live capture run. They are manual
examples, not offline test expectations: remote content, availability and access
challenges change. Run them through `capture_website` with the installed browser,
save PNG/metadata outside an analyst workspace,
and visually review the result. [Live validation](ISSUES.md#live-page-completeness-and-diagnostics)
records the observed limitations and evidence location.

For a loading regression, first compare the same URL in ordinary headless
Edge/Chrome under the same conditions, using its documented automation behavior.
Inspect both screenshots. If the reference renders correctly, investigate the
application's navigation/readiness integration before adding request filters,
retries or resource scheduling. A genuine site challenge must remain distinguishable
from a broken loader. Follow the shared
[implementation guidance](../../../docs/DEVELOPMENT.md#established-implementations-and-reference-behavior).

## Maintenance and tracking

Follow the [maintenance workflow](../../../docs/DEVELOPMENT.md#maintenance-workflow).
Keep current behavior here and decisions/results in [Tools tracking](ISSUES.md).
Keep consumer-specific requests and evidence contracts with their caller.
