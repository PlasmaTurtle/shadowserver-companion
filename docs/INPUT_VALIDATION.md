# Shadowserver Eclipse — Input Validation

This reference describes the input, scanning, and evidence-retention contracts
used by the application. It is intended for maintainers changing provider adapters,
contact extraction, browser capture, or exports.

The boundaries were introduced during the 0.9.98 input-validation work. The
[historical changelog](history/releases/CHANGELOG_PRE_0.11.md#0998--input-validation) records that change;
[November 14 candidate evidence](history/validation/VALIDATION_0120.md) records
checks and acceptance limits for that source state. Use the
[maintenance workflow](DEVELOPMENT.md#maintenance-workflow) when changing these
contracts and the owning module's tracker for follow-up work.

## Required boundaries

| Boundary | Required behavior |
| --- | --- |
| Contact response | Validate bounded HTTP framing, supported media type and strict text encoding. On Windows, require a successful local AMSI scan before static extraction. Script resources are not fetched or executed. |
| Contact persistence | Accept an allowlisted structured result. Store contact values, bounded plain-text excerpts, source URL, retrieval time, HTTP status and original-response SHA-256 as derived JSON. Never retain the original webpage body. |
| Failed contact response | Retain bounded metadata and the received-response hash. Do not preserve error pages, unsupported bodies or script-only pages. |
| Registry response | Validate successful JSON against the expected registry contract before retaining its body. Rejected responses retain metadata with separate received-body and retained-body hashes. |
| Published vulnerability source | Require successful status, supported JSON representation, strict parsing and expected provider/CVE identity before accepting a captured source. |
| Browser capture | Validate the requested HTTP(S) URL and use native installed-browser loading in a fresh profile. Preserve requested/final URL and fallback provenance; validate and hash the resulting PNG before attachment. Browser resources do not pass through the application's response scanner. |
| Export | Validate the bytes actually exported. Omit legacy raw contact pages explicitly, including from old internal-report transport downloads, without rewriting certified files in place. |
| Historical records | Preserve existing certified snapshots and original imports. Missing or quarantined optional contact bodies do not silently initiate another download. |

A source SHA-256 identifies the bytes received from the server. A derived contact
artifact has its own SHA-256. These are intentionally separate; the contact extract
is not described as the original response. Source metadata is retained even when
no body is retained, so the page and observation time can still be investigated.

## Aegis contracts

The reusable primitives live in `modules/workspace/components/aegis/`. Provider schemas and contact
meaning remain in their owning adapters; the shared package uses only the Python
standard library and imports no application state or network client.

| Public helper | Contract |
| --- | --- |
| `aegis.antimalware.scan_buffer` | Scan bounded bytes with a context, representation, timeout and cancellation event; return a validated receipt or raise a typed scan error. |
| `aegis.antimalware.scan_text` | Scan canonical text using the declared UTF-16 representation before contact extraction. |
| `aegis.antimalware.validate_scan_receipt` | Validate receipt fields and the required representation; absence is accepted only when the caller explicitly permits historical unrecorded evidence. |
| `aegis.execution.bounded_security_call` | Use the one shared executor. Capacity and deadlines are bounded; a stalled native call keeps its slot until it finishes, so timeout never causes unlimited replacement threads. |
| `aegis.json.strict_json_loads` | Accept bounded bytes/text with strict UTF-8, depth and byte limits; reject duplicate keys, nonfinite/overflow numbers, malformed JSON and a non-object root when required. |
| `aegis.json.strict_json_decoder` | Provide the same bounded rules with `raw_decode` for streaming; incomplete JSON retains `JSONDecodeError` so the caller can distinguish an incomplete chunk from accepted data. |
| `aegis.text.parse_media_type` | Validate bounded MIME syntax, parameters, duplicate parameters and controls. |
| `aegis.text.decode_bounded_text` | Apply an explicit media allowlist, byte limit and strict supported charset; reject binary/control content. Partial input permits only an incomplete final codepoint. |
| `aegis.errors` | Define typed input, scan and execution failures. Scan errors carry bounded receipts; callers translate these into domain status without retaining the rejected content. |

The map checker enforces this dependency boundary, including rejection of new
third-party imports. Domain adapters must not weaken these shared checks by copying
a less restrictive decoder or silently retrying around a failed scan.

## Validation strategy

Input validation happens before persistence. Allowlists constrain formats and
fields; type, length, size, encoding, URL, identity and provenance checks constrain
the accepted representation. HTTP content types are useful but insufficient on
their own, so body parsing and semantic checks are also required. Parser limits
apply before expensive processing, and errors do not become accepted evidence.

On Windows, the local Antimalware Scan Interface (AMSI) checks the transient contact
response in memory after validated text is represented as UTF-16 for scanning. A blocked result, scan error or unavailable interface prevents
contact extraction from that response; it does not trigger a bypass or raw-file
fallback. Only bounded source metadata and the original-response hash are retained
for rejected content. Portable tests use an injected scanner and do not establish
a native Defender verdict.

UI and document output still use context-appropriate escaping. Input validation
is not a replacement for output encoding and does not establish that an external
website is harmless. This release does not claim malware detection coverage or a
clean antivirus verdict for arbitrary valid content.

The implementation follows the separation described in these primary references:

- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [OWASP Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [Microsoft Antimalware Scan Interface](https://learn.microsoft.com/en-us/windows/win32/amsi/antimalware-scan-interface-portal)

## Clean-workspace acceptance

The first acceptance pass uses a clean workspace and checks hostile-input rejection
through contact finding, storage and routine export. Historical compatibility checks
are separate; retaining old production data is not a prerequisite for testing this
release. Installer deletion/retention defaults are unchanged and no historical data
is automatically removed.

## Compatibility and limits

Existing certified files remain unchanged. A new transport export can explicitly
omit an old raw contact page while preserving certified manifest/snapshot bytes
and recording the omitted name, original digest and reason. Such an export is not
a byte-complete workspace backup. Full workspace backups remain archival transfers
and can contain historical evidence; their existing integrity rules still apply.

Website screenshots use native Edge/Chrome networking and rendering in a fresh
profile. The application does not intercept or scan each browser response, restrict
normal API methods or suppress media. The browser retains its default sandbox and
TLS validation. Screenshot classification describes the visible result; it is not
a malware verdict. Static contact parsing continues to use its separate validated,
scanned text-extraction path and does not execute JavaScript. See the
[Tools guide](../modules/tools/docs/README.md#website-loading-and-capture)
for capture behavior and verification.

Regression tests use inert synthetic responses. No flagged production page is
fetched or executed for validation. Native Windows and Microsoft Defender behavior
must be verified on the installed release; portable test results are recorded in
the [validation records](history/README.md#validation-records) without implying workstation acceptance.

