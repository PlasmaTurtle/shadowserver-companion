# Settings

Settings owns guided setup, saved preferences and sender identity, settings
presentation, software-update checks, and update handoff. This guide covers their
maintenance and integration boundaries.

[Module issues](ISSUES.md) · [Changelog](CHANGELOG.md) · [Architecture](../../../docs/ARCHITECTURE.md) ·
[Maintenance workflow](../../../docs/DEVELOPMENT.md#maintenance-workflow) ·
[Library selection](../../../docs/DEVELOPMENT.md#library-selection)

## Start here

| Responsibility | Start here |
| --- | --- |
| Setup progress and completion | [onboarding.py](../components/onboarding.py), [onboarding.js](../static/onboarding.js) |
| Reviewed sender profile and draft adoption | [sender_identity.py](../components/sender_identity.py) |
| Release discovery, verified download and handoff | [software_updates.py](../components/software_updates.py), [software_updates.js](../static/software_updates.js) |
| Settings update adapter and presentation | [routes/settings.py](../components/routes/settings.py), [settings.js](../static/settings.js) |
| Profile choices, validation and authority references | [profile_catalog.py](../components/profile_catalog.py), [api_models.py](../components/api_models.py), [profile_fields.js](../static/profile_fields.js) |
| Setup and software-update endpoints | [routes/](../components/routes/) |

## Boundary

Settings configures the owning services. Workspace implements backup/recovery,
Accretion implements acquisition scheduling, and Library implements reference-data
behavior. Changing settings must preserve explicit adoption into existing drafts,
dirty-state handling, credential boundaries, and update-admission checks.

Profile updates read, merge and validate the current preferences inside the
Workspace write transaction. This preserves unrelated preferences committed by
overlapping saves; edits to the same field still use the last successful save.
`PUT /api/settings` applies supplied fields only. Omitted jurisdiction is retained;
an explicit empty or null jurisdiction is rejected. The explicit `outreach_mode`
is authoritative; a legacy-only `critical_only` update selects its matching mode.
Targeted mode always requires a reason. Theme shortcuts send only appearance,
and same-view preference/theme writes are serialized in submission order.
Setup profile changes and their progress record share that transaction, with
jurisdiction notifications sent after commit. Guided setup requires an explicit
profile save before finishing when identity or jurisdiction edits remain in a
retained draft; it preserves the entered schedule while the user returns to save.
Malformed saved setup flags or steps require review without changing the stored
row during status reads. Valid older records may omit optional metadata.

Guided setup reads each credential service's `configured` status and shows a
completed credential card instead of asking for an existing key. When both
Shadowserver and NVD are configured, opening setup records a missing connections
step as configured; an existing reviewed choice is retained. Detection does not
start mandatory onboarding for an established workspace; Continue explicitly
records that review. Detection does not test the remote APIs. Shadowserver's
separate `connected` status and explicit Test connection action describe live
report access. Saving one provider's key
updates its card without discarding an unfinished entry for the other provider.

Settings uses native form validation, revealing closed sections containing invalid
controls before requesting focus. NVD input remains only in the form: entering a
key activates the shared unsaved-change guards, and an earlier save/removal cannot
clear newer edits. Clear entry discards that input without deleting a stored key;
Remove key is the separate credential-service operation.

## Profile choices and outreach authority

Settings and guided setup consume one catalog through `/api/setup`: the 50 U.S.
states, DC and five territories; CISA, FBI and USSS; and the seven supported
display timezones. Agency selection determines the department. Jurisdictions use
checkboxes and require at least one selection; recognized postal abbreviations
submitted to the API normalize to full names. Timezones and report profiles use
controlled choices. Names and office are required when explicitly submitted;
email remains optional but must be one valid address. Numeric bounds, strict
boolean/numeric inputs, text length and control-character rules also apply on
the server. The timezone catalog is a supported subset, not all IANA zones.

Unsupported saved selections remain visible for explicit correction. Reading old
profiles does not migrate them, and an unrelated partial preference update does
not revalidate or rewrite their identity or jurisdiction. A full onboarding
profile save validates profile fields, without changing unrelated legacy import
preferences. Existing sender snapshots and certified reports retain their values.

Targeted outreach requires a specific explanation of how the material relates to
the selected agency's mission. Its authority reference is derived by the server,
never accepted from the client, and stored as a versioned `targeted_authority`
snapshot alongside `targeted_reason`. Changing agencies requires review of the
explanation. Accretion includes the snapshot in import identity and retains it as
`override_authority` beside the eligibility reason; later changes do not rewrite
earlier imports. Recipient-facing report wording is unchanged.

The three profiles are the application's supported baseline, not an exhaustive
legal list of authorized agencies. References were checked on November 22, 2026:

- CISA's [6 U.S.C. §659](https://uscode.house.gov/us/usc/t6/s659/) references
  cybersecurity assistance, information sharing and coordinated disclosure.
  [Section 650(25)](https://uscode.house.gov/us/usc/t6/s650/) defines a vulnerability;
  it does not independently grant powers.
- FBI references include [28 U.S.C. §533](https://uscode.house.gov/us/usc/t28/s533/)
  and [28 C.F.R. §0.85](https://www.ecfr.gov/current/title-28/chapter-I/part-0/subpart-P/section-0.85).
  Its priority under [18 U.S.C. §1030(d)(2)](https://uscode.house.gov/us/usc/t18/s1030/)
  concerns specified national-security offenses. PPD-41 is identified separately
  as incident-coordination policy.
- USSS references [18 U.S.C. §3056(b)(3)](https://uscode.house.gov/us/usc/t18/s3056/)
  and [§1030(d)(1)](https://uscode.house.gov/us/usc/t18/s1030/); the PATRIOT Act
  §105 note concerns electronic-crime task forces. These references are not a
  finding that every exposed computer is an offense within an agency's authority.

The catalog owns precise descriptions, source links and revision identity.
Review the sources before changing it; selecting a profile does not establish
the factual connection required for particular outreach.
The architecture registry permits request models to import this pure catalog;
both remain forbidden from loading application services or network/storage APIs.

`onboarding.py` owns setup progress and completion rules. `sender_identity.py`
pins the reviewed sender profile into drafts. `software_updates.py` owns release
discovery, verified downloads and installer handoff. Their routes expose those
services; their browser files own presentation and lifecycle. Keeping these
concerns separate preserves their different persistence and trust boundaries.

The [software-update reference](SOFTWARE_UPDATES.md) owns distribution setup,
integrity, recovery and release-notice behavior.
Installer tooling owns the native [guarded-launch and repair protocol](../../../tools/windows_installer/REFERENCE.md#guarded-launch-and-maintenance).
Settings hands off to verified setup and does not replace program files itself.
Keep restart after the readiness commit, and preserve the older-launcher
first-upgrade policy when changing handoff behavior.

Release-notice acknowledgement uses [Tools atomic file publication](../../tools/components/filesystem.py).
Settings supplies the destination and already encoded JSON, retaining its version
check, lock, timestamp and platform newline. Tools flushes the bytes and replaces
the destination using a unique temporary file, cleaning it up on failure.
Installer verification and launch remain Settings workflows.

`components/api_models.py` owns settings-update validation, including sender
identity fields. `routes/settings.py::register(app, *, store)` owns profile updates
and notifies Accretion when jurisdiction changes; Workspace explicitly registers
this adapter. See [Workspace ISS029](../../workspace/docs/ISSUES.md#iss029-workspace-file-ownership-and-consolidation).
Reference editing belongs to Library's `resources.js` and
`library_events.js`; Settings consumes the supplied actions. UI installs
Settings, Library's catalog/editor and Workspace Health explicitly once each.
Do not restore hidden feature installation inside the Settings installer.

## Verification

Recorded schedule instants use UI's selected display-timezone formatter; this
does not change the schedule's execution timezone. Diagnostics and backup actions
pass their Blob/filename to UI's download helper and retain fetching, confirmation
messages and refresh behavior. See the
[shared browser contract](../../ui/docs/README.md#shared-browser-capabilities)
and [ISS026](../../tools/docs/ISSUES.md#iss026-reusable-tools-and-duplicate-capabilities).

Use the [project development setup](../../../docs/DEVELOPMENT.md#windows-ide-setup).
From the repository root:

```text
python -m pytest -q modules/settings/tests
node --experimental-vm-modules modules/settings/tests/test_software_updates_ui_0120.cjs
python tools/verify.py --only-browser --browser-suite setup --report build/setup-browser.json
```

The setup browser group checks guided setup in a synthetic workspace. Software
update installation, file locking and restart still require the
[Windows acceptance checklist](../../../docs/WINDOWS_ACCEPTANCE.md). Use
[project verification](../../../docs/DEVELOPMENT.md#verification) for all registered
frontend and browser suites.

## Maintenance and tracking

Use [Settings issues](ISSUES.md) for feature extraction and links to shared release
work. Check callers in the service-owning module before changing settings or
admission behavior. Follow the [project maintenance workflow](../../../docs/DEVELOPMENT.md#maintenance-workflow),
and update this guide or the software-update reference with any changed contract.
