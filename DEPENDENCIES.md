# Dependencies and bundled assets

This reference explains the Windows runtime, package locks and asset provenance.
Use [Development](DEVELOPMENT.md) for setup and audit commands, and
[Validation](VALIDATION.md) for recorded results and their limits.

## Runtime and package sources

The `.exe` installer includes CPython 3.14 x64 and the application's Windows
dependencies. The exact interpreter patch version, download and hash are pinned in
[`tools/windows_installer/runtime-lock.json`](tools/windows_installer/runtime-lock.json).
The independently runnable source archive requires a separately installed
64-bit Python 3.14 interpreter before setup. The installed edition does not.

Both editions share [`requirements-windows.txt`](requirements-windows.txt),
[`wheelhouse-sha256.json`](wheelhouse-sha256.json), and the `wheelhouse` directory
as their dependency artifacts. Use these files for the exact current inventory;
package counts and archive sizes change when the bundle changes.

`wheelhouse` contains the complete application dependency set for **Windows x64 CPython 3.14**. Setup uses `--no-index --require-hashes`: it installs only bundled wheels whose SHA-256 matches `requirements-windows.txt`. `wheelhouse-sha256.json` provides the filename/hash mapping.

Package licenses and notices are retained inside each wheel's metadata. The
application's bundled PDF fonts have their license in `fonts/LICENSE.txt`.

`requirements-constraints.txt` pins the selected versions for source/development installs. `requirements.txt` installs the Attribution Module from this checkout; Windows installs its included wheel. The package's source is under `components/attribution`.

The recorded dependency review evaluated each wheel's `Requires-Dist` metadata
for Windows x64 Python 3.14, including the `httpx[socks]` extra. Repeat that closure
review when changing the locks. Native Windows wheels must match the selected
interpreter and platform.

Windows is the application distribution target. Developer checks run on another
operating system require native packages for that host; bundled Windows wheels
cannot be used as portable binaries. Such checks do not establish support for
another desktop platform.

DNS resolution uses dnspython. Its exact version is retained in the dependency
locks; the standalone Attribution Module remains independently installable.

## Release verification

Run `python tools/check_dependencies.py` to verify the wheel hashes, Windows
requirements, development constraints, standalone module pins, and module source
version against the bundled artifacts. Extra, missing or changed wheels fail the
check. The DNS parser regression test checks the compression-chain limit using
only a 35-byte offline fixture.

Run `python tools/check_dependencies.py --audit --audit-python <tool-python>
--output <result.json>` with an isolated interpreter containing `pip-audit`.
This audits the exact public versions derived from the verified wheels, without
installing or resolving dependencies. Only public package names and versions are
sent to the advisory service; the command never reads case data. An advisory,
incomplete scan, skipped package, timeout or tool error fails the check. The
internal Attribution Module is reviewed as application source rather than queried
under a public package identity. Absence of an advisory is not proof of safety.

Native codec and CPython advisories require separate review from the Python-wheel
audit. Do not infer FIPS compliance or absence of runtime vulnerabilities from a
successful package scan.

### Historical runtime review: November 7, 2026

The recorded review retained CPython 3.14.10 and found no official 3.14.11 Windows
runtime artifact at the release endpoint checked that day. It tracked
CVE-2026-119170 (conditional on OpenSSL FIPS mode) and CVE-2026-116566 (embedded
NUL address resolution), with application input guards tested to reject NUL.
This is a dated review record, not a current advisory scan or a statement about
what Python releases are available today. Recheck the interpreter and native
libraries during release review. Original references:

- https://github.com/rthalley/dnspython/security/advisories/GHSA-45c3-73f7-pv4m
- https://dnspython.readthedocs.io/en/latest/whatsnew.html
- https://mail.python.org/archives/list/security-announce@python.org/thread/PXVTTOBPUMFJSSUXN6XCS7FC5DZOSZXK/
- https://mail.python.org/archives/list/security-announce@python.org/thread/HCHE62VYTPYI6WOPJQDWUBR4CINBPSM7/

## Local visualization assets

ECLIPSE bundles D3 7.9.0 in `static/vendor/d3.min.js` under the ISC license;
the full notice is in `static/vendor/D3-LICENSE.txt`. Its published bundle
was obtained from https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js.

Local state geometry and city reference points come from the U.S. Census
Bureau's 2025 cartographic boundaries and national Places Gazetteer. Source URLs,
archive SHA-256 values, coverage and limitations are documented in
`static/geo/README.txt` and the bundled data. `tools/build_observatory_geography.py`
rebuilds both assets from those archives. No external tile service is required.

These assets add no Python dependencies, Node runtime requirement or
external browser connections.

The local `static/geo/places.json` covers all 50 states, the District of Columbia
and Puerto Rico using unambiguous state/place names from the 2025 national
gazetteer. Duplicate city names within the same state are excluded. These points
support explicitly labeled approximate reported-city placement, not verified
physical asset locations. The current point count, source URL and SHA-256 are
retained with the asset metadata and `static/geo/README.txt`. Source:
https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_place_national.zip

## Report exhibits, fonts and field inventory

The exhibit/appendix implementation adds no runtime package. ReportLab renders native PDF graphics and text; Pillow provides compatible PNG fallbacks; python-docx/lxml embeds SVG plus fallback and native report text. The installed runtime does not require a browser automation engine, Node, Word, LibreOffice, or cloud AI for document generation.

`schemas/shadowserver-reports.json` is the official Shadowserver field inventory pinned at commit `6724d55d95e08338c50bb78d96b8a7eefb6f3bb4`. The adjacent metadata contains its complete source URL, actual retrieval time, and SHA-256. This is a field inventory, not a universal validation schema. 177 definitions/745 fields describe this snapshot; implemented notification adapters are listed by capability.

The document font bundle includes a static Noto Sans SC derivative and WOFF versions for self-contained SVG exports. The OFL notice and exact source/hash/conversion provenance are under `fonts/`. The variable-font conversion input is a development-only asset and is excluded from releases. Font conversion does not add a runtime dependency.

## Runtime alignment and older source environments

`tools/windows_installer/runtime-lock.json` is the interpreter baseline for installed and source
editions. The build derives the ABI and isolated import-path filename from
that record. Source `Setup.cmd` uses `tools/setup_environment.py` to select
the same Python minor version and install the same hash-locked dependencies.
The launchers read the application version from `VERSION`; no release number
is duplicated in their commands.

If upgrading a source checkout with a Python 3.12 `.venv`, close the app and
rename that environment before running setup with Python 3.14 installed. Keep
the `data` folder unchanged. Installed-edition workspaces retain their original
location and do not require this source-checkout step.

Record the actual interpreter, platform and dependency versions with each
verification run. Results from one development host do not establish native
Windows installer acceptance; follow [the Windows acceptance checklist](HOME_VALIDATION.md)
for the candidate being distributed.

