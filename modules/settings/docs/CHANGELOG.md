# Settings changelog

## Unreleased

## 0.12.1

- Guided setup recognizes existing Shadowserver and NVD credentials. Both keys
  complete the connections step, and a missing key has its own entry form.
  Saving one key preserves an unfinished entry for the other service and any
  saved manual-import choice. Shadowserver access can be tested explicitly.
  [Credential detection](ISSUES.md#iss057-recognize-configured-keys-in-onboarding)

## 0.12.0

- Added resumable setup for API connections, agency identity, jurisdiction and
  optional scheduled retrieval. Agency presets and custom agencies support
  name-only senders.
- Added in-app update checks, verified downloads and version-specific release
  notes. Install and restart checks the version, channel and installer digest
  the operator reviewed. [Software update review](ISSUES.md#iss040-reviewed-software-update-identity)
- Appearance changes preserve a newer profile edit, and unsaved credential
  entries remain protected when the operator navigates away.
