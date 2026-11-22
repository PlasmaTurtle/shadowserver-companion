# Software updates and release notices

This reference owns the update protocol, distribution procedure and recovery
contract for maintainers. Use the [module guide](README.md) for entry points and
verification, [Settings tracking](ISSUES.md) for open work, and the
[user guide](../../../docs/USER_GUIDE.md#14-protect-your-work-and-end-the-day) for
analyst update instructions.

Settings → Software provides an explicit check, download, review, and install flow.
Checking never installs software. A completed download is verified before the
installation action becomes available. Installing closes the workspace, runs the
Windows installer in update mode, retains the workspace, and restarts the normal
application after success. Save or discard pending edits first. Active imports,
API jobs, workspace changes, and other requests prevent the handoff.

The install-review dialog captures the candidate's version, channel and installer
SHA-256. `POST /api/software/install` requires those three fields, and the service
compares them with the verified candidate under its lock before reserving the
workspace. A changed candidate returns 409 and must be reviewed again; missing or
malformed review data returns 422. Older cached clients must reload to use this
explicit review contract. Status includes the candidate's `installer_sha256` for
this purpose; it does not allow the caller to supply an installer path or URL.

Browser status requests are ordered within the current view lifetime. Obsolete
responses and failures cannot replace a newer operation's state or cancel its
polling; a newly active view obtains current server status before presenting it.

The installed release's What's New notice comes from its bundled `CHANGELOG.md`.
It appears once per version after setup is complete and can be reopened from
Settings. Release notes are displayed as plain text, never executable markup.

## Distribution source and recorded status

As reviewed on November 14, 2026, `PlasmaTurtle/shadowserver-companion` is a private
repository with no published releases. The current anonymous update client cannot
read that private feed. It reports an inaccessible feed, or no compatible
published release when the feed is readable but empty. Neither state means that
the installation has been confirmed current.

That repository observation is dated evidence, not a live availability check.
Before planning a distribution, verify the configured source and its accessibility
for the intended installed client. Record the result with the release acceptance
evidence tracked by [ISS014](../../../docs/ISSUES.md#iss014-current-version-windows-acceptance).

Activation requires a publicly readable release repository or a separately
designed authenticated distribution service. Making the source repository public
is not required: a dedicated public repository may distribute only approved
installer artifacts. Selecting a new distribution repository requires changing
the compiled `REPOSITORY` constant in `modules/settings/components/software_updates.py` and verifying
the new release source. A workspace preference or remote manifest cannot change
the trusted download source. This implementation does not publish releases,
change repository visibility, or embed private GitHub credentials.

## Publishing a compatible release

1. Build and validate the Windows installer for the selected release, edition,
   and variant. Complete the usual Windows acceptance checks before promoting a
   candidate to stable.
2. Generate the manifest from the exact installer to be distributed:

   ```text
   python tools/build_update_manifest.py dist/ShadowserverEclipse-0.12.0-guided-setup-rc-Setup-x64.exe dist/software-update-ShadowserverCompanionDarkMatter.json
   ```

3. Attach both files to the same draft GitHub release. The manifest filename is
   tied to the installation's existing app ID; Eclipse retains the
   `ShadowserverCompanionDarkMatter` identity. The manifest contains the installer
   filename, byte count, SHA-256 digest, version, channel, edition, variant, and
   plain-text changes from the bundled changelog.
4. Use a matching version tag, such as `v0.12.0`. Mark candidate and unstable
   releases as prereleases. Stable releases must not be prereleases.
5. Confirm that GitHub reports each uploaded asset as `uploaded` with a SHA-256
   `digest` and correct `size`, then publish the release. Attach the complete
   artifact set before publishing. GitHub immutable releases can prevent later
   replacement of published assets and tags.
6. Check from an older installed copy through the actual distribution network.
   Verify download, checksum failure/retry, busy-workspace rejection, successful
   replacement, preserved records/settings, and normal desktop restart.

The client considers at most the first 100 published releases. Stable clients
accept stable releases; candidate clients accept candidate or stable; unstable
clients accept all three. It never offers an older version. Promotion to a more
stable channel at the same version is eligible. Installation is available only
in a recognized Windows-installed copy with a running desktop server.

## Integrity and recovery

- Metadata and downloads use HTTPS and a fixed project namespace. Initial asset
  paths must identify the exact release and filename; redirects are limited to
  GitHub's release asset hosts. Download sizes and operation durations are bounded.
- Both the manifest and installer must match the SHA-256 and size supplied by
  GitHub's asset metadata. The manifest's installer digest must also agree. A
  mismatched edition, variant, app ID, tag, channel, filename, or checksum is
  rejected. No request can supply an installer command or arbitrary download URL.
- SHA-256 provides integrity within the trusted GitHub distribution boundary. It
  is not a claim that the installer carries an Authenticode signature. Publisher
  signing and a separately pinned signing identity remain additional release
  hardening options.
- Downloads are staged outside the workspace. Partial or corrupted downloads
  can be retried. The verified file is checked again before reserving the
  workspace and immediately before launch. If launch fails, the workspace is
  released and the update can be retried without restarting the app.
- The installer receives `/UPDATE /RESTART`, waits for the running application
  to release its Windows mutex, and preserves the existing data. No old Python
  helper process stays alive while program files are replaced. Installer errors
  remain visible; reopening the app after resolving an error uses the retained
  workspace.

Early interpreter/DLL loading precedes cooperative launcher registration. The
remaining overlap limitation and required native verification are tracked in
[ISS015](ISSUES.md#iss015-pre-registration-upgrade-race); do not launch another
instance during installation.

The module's update and admission tests exercise source restrictions, malicious metadata, edition and
channel mismatch, checksum failures, retry, reservation rollback, release-note
persistence, lifecycle cancellation, and UI protections. These tests do not
substitute for native Windows installation, SmartScreen, file-lock, and restart
acceptance checks. Keep automated results and the
[Windows acceptance record](../../../docs/WINDOWS_ACCEPTANCE.md) distinct, and
update this reference when the trusted source or handoff protocol changes.

References: [GitHub release API](https://docs.github.com/en/rest/releases/releases),
[release asset API](https://docs.github.com/en/rest/releases/assets), and
[immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).
