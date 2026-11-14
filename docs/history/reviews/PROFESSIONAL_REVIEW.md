# Shadowserver Eclipse — Professional Review

> **Historical record.** This document retains its original release or review scope.
> It does not describe current acceptance. See the [current documentation](../../README.md)
> or the [history index](../README.md) before using its instructions or results.

The 0.9.96 pass concentrates on production wording, predictable Windows behavior,
credential lifecycle, and release verification. The application name is
**Shadowserver Eclipse**; the ECLIPSE masthead and SHADOWSERVER COMPANION subheader
remain. Dark matter continues to describe the Observatory data concept.

## Product language and identity

Public Chaos/experimental-comparison labels and redundant descriptors were removed
from the active interface and current operating instructions. Library, scheduling
and Observatory instructions now describe the implemented behavior. Demo labels,
source limitations, missing data, errors, and accurate release status remain.
The internal evidence reader identifies its audience at the masthead. Recipient
PDF text and DOCX document XML remain unchanged by that presentation change.

The existing `ShadowserverCompanionDarkMatter` install, registry, mutex, data and
credential namespaces remain intact. Internal edition identifiers are retained for
compatibility. The new brand does not create an empty workspace or copy records.
Shortcut cleanup is limited to the known previous names for this installation and
occurs only after replacement shortcuts are created successfully.

## Startup and maintenance

The installed app and setup share an exclusive start/install gate. The launcher
registers its running handle while holding that gate; setup retains it while
replacing/removing program files and checks the existing running handle. Other
workspaces can still run after registration. Legacy running-instance protection
remains; a launcher from an older release cannot retroactively honor the new gate.

The direct shortcut loads Python, linked DLLs and early imports before registration.
That pre-registration interval is not protected by the Python gate. Launching during
replacement can still cause startup/import errors, file-in-use replacement failures,
or mixed loaded/new code. Full closure requires a bootstrap outside the replaceable
runtime or version-staged installation. Close the app and do not launch during setup;
this release does not claim complete launch/replacement exclusion.

A second launch that encounters an initializing workspace waits for bounded,
authenticated reuse of that same workspace, port and mode. It never treats an
unrelated service or an unauthenticated health response as the existing app.

Desktop and scheduled entrypoints use shared rotating diagnostics. The scheduled
entrypoint tolerates absent standard streams, captures early failures, preserves
exit codes, and logs outside the replaceable workspace. Credential-shaped values
are redacted; startup failure records omit arbitrary exception arguments.

## Credentials and orderly shutdown

NVD session-only replacement now removes an older remembered key. Vault/session
operations are serialized so concurrent save/forget cannot resurrect a credential.
A vault failure leaves the previous configuration intact and returns a sanitized
error. Saved API credentials continue to use Windows Credential Manager.

Shutdown stops scheduling before acquisition, drains the acquisition producer
before closing intake, and closes the reference catalog last. Other cleanup callbacks
still execute when one fails. This corrects lifecycle ordering; it is not a claim
that prior versions were demonstrated to lose data.

## Verification and release status

The targeted security gate now discovers later session, capture, request-boundary,
privacy and restore regressions as well as the original security suites. Dependency
integrity and a fresh advisory scan are recorded separately from functional checks.
The exact tested source is compared with the installed payload after packaging.

0.9.95 Windows acceptance was confirmed by the operator. 0.9.96 is identified as a
release candidate until that changed version has workstation acceptance. Prior
acceptance cannot automatically satisfy the current-version stable gate. DarkMatter
is no longer permanently barred from stable promotion by its legacy edition name.
Neither automated tests nor packaging fabricate a Windows execution result.

See `VALIDATION.md`, `HOME_VALIDATION.md`, and `SECURITY.md` for observed results and
limits. This pass adds no data migration, new external data flow, recipient-template
rewrite, browser heartbeat shutdown, or replacement packaging framework.

