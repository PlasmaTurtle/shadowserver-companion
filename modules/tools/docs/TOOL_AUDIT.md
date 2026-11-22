# Shared capability consolidation

Implemented **2026-11-21** in the Desktop repository, based on revision
`efccc0a0f476bf83078b26694afa8fad0372047c` with existing uncommitted work.
[ISS026](ISSUES.md#iss026-reusable-tools-and-duplicate-capabilities) owns completion
evidence and verification limits; the [tool contract](README.md#boundary-and-public-interface)
owns interface rules. This record replaces the initial list of proposed extractions.

## Results and ownership

All ten findings have implementations and real consumers. Deliberately different
contracts remain explicit below; shared code has not become a universal tool framework.

| ID | Canonical implementation | Result |
| --- | --- | --- |
| A01 | Tools [network_identity.py](../components/network_identity.py) | One offline private-aware PSL configuration serves capture, intake, Entity DNS/contact scope, ownership and Leads provider policy. External consumers no longer import intake for domain lookup. |
| A02 | UI [format.js](../../ui/static/format.js), exposed through the existing stamp action | Settings automation, Data schedules/history and Workspace health use the selected display timezone. Calendar dates and scheduling zones remain separate. |
| A03 | UI [format.js](../../ui/static/format.js) | One HTML encoder/count formatter serves UI and Observatory. Navigation supplies the encoder explicitly to the synchronous classic Observatory facade. |
| A04 | UI [download.js](../../ui/static/download.js) | Settings diagnostics and backup share Blob download initiation and URL cleanup, including a failed click. |
| A05 | Tools [filesystem.py](../components/filesystem.py) | Workspace and Settings publish serialized bytes through unique temporary files, fsync, replacement and cleanup. Recovery uses Workspace's public write_state_json adapter. |
| A06 | Investigations [package_files.py](../../investigations/components/package_files.py); generic reads in Tools filesystem | Registry, inventory, closure recovery and migration use one bounded manifest parser. Workspace uses generic contained-path operations directly. |
| A07 | Tools [http.py](../components/http.py); Library [transport](../../library/components/cve_catalog/transport.py) and [risk](../../library/components/cve_catalog/risk.py) callers | One Retry-After parser returns server guidance independently of provider defaults. The competing risk parser is removed. |
| A08 | Existing [Attribution DNS parser](../../attribution/components/engine/src/attribution/matching.py), Tools mapped-IP comparison | Contacts shares live DNS normalization with Attribution; application address-comparison consumers use one mapped-IPv6 fold. Stored identity contracts remain unchanged. |
| A09 | Library [risk.js](../../library/static/risk.js) | Library and Observatory share one known-ransomware alias predicate without changing unknown/unassessed or finding-level meaning. |
| A10 | UI [request.js](../../ui/static/request.js) | UI and Observatory share native Fetch decoding, cancellation and timeout mechanics. Errors retain HTTP status and parsed detail; callers retain workflow state. |

## Established implementations and observed improvements

### Network identity: A01 and A08

The [tldextract documentation](https://github.com/john-kurkowski/tldextract)
provides offline snapshot configuration and private-domain support. Tools uses
that existing library directly and returns its native result. The root_domain
convenience function preserves the original hostname when no root exists; strict
consumers use extract_domain and retain their own missing-root decision.
A fresh-process check blocks network access and confirms capture imports no
Accretion module while resolving tenant boundaries correctly.

Contacts delegates DNS syntax to the existing standalone parser, using
[IDNA UTS46 mapping](https://github.com/kjd/idna#compatibility-mapping-uts-46).
This fixes divergent destinations: faß.de previously became fass.de in Contacts
while Attribution used xn--fa-hia.de. Both now use the latter; the contact flow
accepts that approved destination and rejects the distinct fass.de. One terminal
root dot is normalized; repeated dots remain invalid. Greek final sigma likewise
uses the canonical IDNA mapping.

Mapped-IP comparison uses Python's
[IPv4-mapped IPv6 property](https://docs.python.org/3.14/library/ipaddress.html#ipaddress.IPv6Address.ipv4_mapped).
Public-address eligibility, company scope and browser URL acceptance remain caller
policy. Eleven IP projections, six root-fallback examples and four saved
asset/finding identities retained their outputs in the compatibility comparison.
Awareness/finding key normalization intentionally retains its historical IDNA and
address-family behavior; no persisted records or engine package were rewritten.

### UI formatting, downloads and risk: A02–A04 and A09

Formatting uses native
[Intl.DateTimeFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat).
For the same instant with Asia/Tokyo selected, Settings previously showed the
browser's New York time; the new output matches the independent Intl reference
with GMT+9 visible. Missing timestamps, DST and date-only behavior are covered.

HTML encoding/count functions were moved from existing duplicate implementations,
not replaced with a new rendering system. Library's three risk aliases now have
one domain-owned interpretation. The
[browser resource-lifetime guidance](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Resource_management)
informs Blob URL cleanup: downloadBlob initiates the download and schedules
revocation even if the click throws. It does not claim the file finished saving.
Investigations' PDF preview retains its longer, explicitly disposed lifetime.

### File publication and manifests: A05 and A06

The implementation uses documented
[NamedTemporaryFile](https://docs.python.org/3.14/library/tempfile.html#tempfile.NamedTemporaryFile),
[fsync](https://docs.python.org/3.14/library/os.html#os.fsync),
[os.replace](https://docs.python.org/3.14/library/os.html#os.replace) and
[resolved paths](https://docs.python.org/3.14/library/pathlib.html#pathlib.Path.resolve).
Callers supply paths/bytes, choose read limits/digests and retain serialization,
locks and transaction decisions. Filesystem operations import only the standard
library.

A reproduced replacement failure previously left Workspace's status.tmp behind.
The shared writer preserves the prior target and removes its temporary file.
Concurrent writers use distinct temporary files. Workspace JSON and Settings'
platform-specific newline retain their exact byte contract.
Native Windows replacement can reject uncoordinated writes to one destination;
caller-locked native and tool writes passed the same comparison. Verification
covers both caller-locked publication and simultaneous writes to different files
whose old fixed temporary names collided. No retry mechanism was introduced.

Investigations keeps the manifest name, 20 MiB policy, strict object parsing,
inventory/cache and artifact identity. Six representative synthetic legacy/current
formats preserve their raw bytes. Overflow, invalid Unicode and excessive nesting
no longer receive different acceptance from different readers. Compatibility was
checked against fixture/producer formats, not a production-record corpus.

Contained reads retain existing immutable-package path semantics, not a hostile
filesystem sandbox. Atomic replacement is single-file publication, not a multi-file
transaction or a power-loss rename guarantee. Standalone Attribution and installer
bootstrap retain their independent packaging; the legacy CLI retains its existing
atomic writer rather than acquiring an application publication policy.

### Retry guidance: A07

[HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3)
defines integer-second and date guidance. The shared parser uses Python's
[parsedate_to_datetime](https://docs.python.org/3.14/library/email.utils.html#email.utils.parsedate_to_datetime),
takes an explicit aware clock and returns a finite nonnegative delay or None.
It preserves NVD's accepted forms, including obsolete asctime dates in GMT.

Risk feeds now recognize that GMT date form instead of falling back to an hour.
Invalid fractions/nonfinite values use the documented one-hour local fallback and
are no longer labeled server-requested deadlines. Valid zero still receives the
risk provider's 60-second minimum. Provider waits, retry budgets and persistence
remain in Library; standalone/vendored clients do not acquire app dependencies.
Checks exercise the actual feed caller and verify the error body stays unread and
the response closes.

### Requests: A10

Native [Fetch](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)
and [AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController/abort)
remain the transport. The small request helper accepts URL/options, returns decoded
JSON/Blob data, and releases its timers/listeners. A real local HTTP 409 previously
became an uninformative object string in the UI API; it now retains status 409 and
detail.code=field_revision_changed.

The UI adapter retains mutation tokens, body encoding and navigation behavior.
Observatory retains selection generations, revision recovery, slow-load messages
and separate 120-second view/20-second detail waits. Session bootstrap remains
independent of the application token. Installed Edge acceptance exercised actual
app routes and transitive ES modules, including the classic renderer injection;
desktop and narrow-screen output were inspected.

## Verification and continued maintenance

The initial audit structurally inspected 352 first-party Python files plus targeted
frontend/network/runtime callers. Its raw evidence remains in the Codex task
workspace's `validation/tool-audit-01/`. Implementation evidence is in
`validation/tool-consolidation-01/`: source snapshot, before/after comparisons,
focused tests, frontend acceptance and combined verification. See ISS026 for final
counts and limits rather than duplicating a changing verification record here.

Existing shared HTTP/DNS providers, UI rendering/fonts and standard hashing remain
in use. Historical narrative versions, distinct process lifetimes, workflow polling
and independent package boundaries are intentional separations. No second image
decoder was found to consolidate. These are not unfinished migrations.

For future reuse, compare real input/output/failure contracts, select the owning
module, switch callers and remove superseded implementations together. Use the
platform or maintained library first. Preserve small domain/compatibility adapters
when they explain a real difference; do not hide them in a generic context object.
