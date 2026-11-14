# Security and stability review — 0.9.85

Scope: the full supplied 0.9.84 application source and 0.9.85 changes, dependency
locks, local HTTP boundary, external acquisition, report/evidence handling,
backup restore, worker lifetime, UI injection boundaries and release packaging.
This is a source/dependency/regression review on Linux; it is not a native Windows
penetration test, FIPS validation or signed security certification.

## Findings and disposition

| Area | Finding | Change or disposition |
|---|---|---|
| Request intake | Route-level size checks happened after framework parsing/spooling. | Added streamed request ceilings, including requests without Content-Length; oversized multipart parsing closes partial files and returns 413. Existing per-file limits remain. |
| Image integrity | New previews were not anchored to an acquisition-time digest. | Record preview SHA-256 and check it for viewing, snapshot/certification and backup restoration. Preserve legacy originals and certified manifests. |
| API responsiveness | Uploaded image decoding/encoding ran on the async request loop. | Move decoding and PNG encoding to the worker thread pool; prepare files before the short guarded transaction and clean up on rejection. |
| Worker lifetime | An exception across lifespan yield could skip cleanup. | ExitStack closes every registered service even when startup, shutdown or another closer raises. |
| Runtime policy | Vendor advisory CVE-2026-119170 affects CPython 3.14.10 in OpenSSL FIPS mode. | Fail closed in that configuration; do not disable FIPS or downgrade the runtime. Ordinary pinned runtime retained. Corrected approved runtime still required for FIPS deployment. |
| Website capture | New browser execution adds network, resource and concurrency risk. | Report-bound hostname selection, private profile, default sandbox/TLS, public DNS validation plus IP-pinned GETs, deny-only proxy, no downloads/auth/cookies/POSTs, resource/time/process budgets, cancellation and completion-time freeze checks. |
| Capture UI | Completion initially read the wrong case-version field in the dirty-draft merge. | Corrected and covered by an unsaved-text regression. No narrative replacement on background completion. |
| Background | Previous raster and overlays had separate motion, and repeated blur is expensive. | Shared camera registration, 30 fps ceiling, sampled paths, bounded glow region, one outer frost plane, paused hidden/reduced/light/Observatory states and explicit teardown. Actual GPU profiling remains pending. |
| Catalog URLs | Initial suspicion of unchecked reference URLs. | Traced to an existing upstream HTTP(S) filter; false alarm, no speculative change. |

## Review evidence

- Exact bundled Python dependency pins and artifact hashes verified. Advisory scan
  covered all 33 public distributions; zero reported advisories. The internal
  Attribution wheel is checked against its source rather than a public registry.
- npm development-dependency advisory scan reported zero vulnerabilities.
- Bandit inspected application/launcher code without parse errors: 0 high,
  28 medium and 17 low review items. These are scanner findings, not confirmed
  vulnerabilities. SQL items use fixed identifier lists or parameter placeholders;
  the build URL is a pinned vendor URL followed by SHA-256 verification. Low items
  cover controlled subprocess argument arrays, offline smoke-test asserts,
  XML escaping imports, a whitespace token falsely identified as a password and
  best-effort failure-event logging. WebSocket SHA-1 is the protocol handshake,
  explicitly marked non-security use; evidence integrity uses SHA-256.
- Reviewed local launcher credentials, session cookies, same-origin/CSRF controls,
  loopback binding, query bounds, path confinement, archive/member integrity and
  raw-original versus presentation-image handling. Existing protections retained.
- Focused tests exercise authenticated capture scope, public/private DNS rejection,
  redirect/resource coordination, exact PNG retention, provenance immutability,
  preview tampering, incomplete-page classification, cancellation, freeze races,
  request streams, worker cleanup and reduced-motion lifecycle.
- 0.9.84 upgrade and restore harness preserved all 109 protected files, three
  historical report packages, fifteen section validations and fifteen downloads
  in each upgrade/restore phase. No catalog re-download or schema migration is
  required by this release.
- Final regression counts and distribution verification are in `VALIDATION.md`
  and the companion validation archive. Earlier failed development runs are not
  represented as successful release checks.

## Practical limits retained

The unsigned installer and native Windows behaviors need workstation acceptance.
The current user's OS account and storage permissions remain the data boundary;
local hashes are not independent signed attestations. Legacy screenshot previews
without a historical acquisition hash cannot retroactively gain one. Reference
catalog updates remain separate from frozen report evidence.

Real Edge rendering, enterprise policy, Windows Job Objects and GPU performance
were not established on this host. No sandbox or certificate checks were disabled
to obtain a passing capture. Resource ceilings can produce partial pages; their
status is retained instead of being presented as confirmed business content.

## Primary references consulted

- [Python 3.14.10 release](https://www.python.org/downloads/release/python-31410/)
- [CPython FIPS advisory](https://mail.python.org/archives/list/security-announce%40python.org/message/PXVTTOBPUMFJSSUXN6XCS7FC5DZOSZXK/)
- [DevTools protocol](https://chromedevtools.github.io/devtools-protocol/)
- [Fetch interception and fulfillment](https://chromedevtools.github.io/devtools-protocol/tot/Fetch/)
- [Viewport capture](https://chromedevtools.github.io/devtools-protocol/tot/Page/#method-captureScreenshot)
- [Browser download policy](https://chromedevtools.github.io/devtools-protocol/tot/Browser/#method-setDownloadBehavior)
