# Validation — 0.12.0 Guided Setup

> Recorded build evidence for the 0.12.0 candidate, prepared November 14, 2026.
> These results describe that build and execution environment; they are not live
> GitHub Actions status or acceptance of subsequent commits. Use the
> [Windows checklist](../../WINDOWS_ACCEPTANCE.md) for outstanding workstation acceptance.

This is an unsigned release candidate. It modernizes Windows installation,
guided setup, Settings, jurisdiction-aware acquisition and map context, and
software-update controls. Exact-version native Windows and rendered-browser
acceptance remain outstanding.

## Completed verification

- All **3,046 current backend test nodes** across 223 files have passing evidence,
  with **151 passing subtests**, on CPython 3.14.10. Four complete collection-based
  shards covered the suite. Nine initial failures and one compiler skip were
  investigated and resolved through explicit follow-up runs; the evidence keeps
  those initial results instead of hiding them.
- The broader run exposed a real DNS status race: completion could be paired
  with the prior cached result. A deterministic barrier test reproduces the
  interleaving and verifies the coherent result. Remaining initial failures were
  outdated uninstall-inventory parsing and startup fixtures; their assertions
  now cover the new deletion guards and bound graceful shutdown callback.
- All **63 portable frontend suites** passed, including guided setup, retained
  drafts and offline schedule choices, jurisdiction filtering, unsaved-work
  guards, update controls, and independent Library daily-update status.
- Release identity, dependency hashes, module boundaries, Ruff format/lint,
  frontend syntax, Prettier and whitespace checks passed. The generated source
  map covers 373 modules and 21 components without ownership errors or cycles.
- The actual NSIS smoke compilation passed. Installer tests cover a missing or
  broken old Python runtime, generated cache residue, recognized partial-install
  repair, unknown-file protection, edition/downgrade boundaries and retained data.
- Update and data-operation admission tests cover active work, independent
  catalog/risk/index/DNS starts, cancellation recovery and lock ordering. The
  writer reservation remains held throughout backup/staging.
- Authenticated application tests cover first-run/manual completion, resume,
  profile persistence, API credential isolation, jurisdiction changes, stale
  schedule rejection, restart behavior and versioned release notices.

The machine-readable backend report reconciles the final node inventory with
all shard and follow-up JUnit results. The accompanying validation bundle retains
that report, its source logs, the portable verification report and packaging
checks. No working case records or credentials are included.

## Distribution checks

The source builder verifies every archived source digest and archive CRC. The
installer builder verifies its pinned runtime and Windows wheel hashes. Final
packaging checks extract the actual EXE, verify every payload digest, compare
installed application bytes with the source package, confirm the new setup and
update assets are present, and reject the retired Carolinas-only geography.
SHA-256 values and the update manifest are retained with the validation bundle.
These are integrity checks, not publisher signing or native execution evidence.

The release retains database schema 20. Setup progress uses existing settings
storage; no new schema migration is introduced. The approved report template,
report-generation modules and dependency pins/hashes were not changed.

## Explicit limits and remaining release steps

- Chromium could not start in this execution environment: its Unix socket call
  was denied before any page loaded. The fresh-workspace browser scenario is
  registered in `tools/verify.py`, but visual, keyboard and browser interaction
  acceptance must still be run on a permitted host. Portable DOM tests are not
  a substitute for that acceptance.
- Windows install, update restart, repair, uninstall/reinstall, Credential
  Manager, Task Scheduler and DPI acceptance were not executed here. Follow
  `HOME_VALIDATION.md`. The earlier operator-confirmed 0.9.96 baseline is separate
  from this candidate's acceptance.
- The installer remains unsigned; no publisher certificate was supplied.
- Live software delivery requires an accessible published release feed. The
  configured GitHub repository is private and has no releases. The client reports
  that state honestly. No repository visibility or publication change was made;
  see `modules/settings/docs/SOFTWARE_UPDATES.md` for activation and the trust boundary.
- Program-file replacement supports repair after interruption rather than an
  atomic application rollback. Working records remain separate and retained.

## Reproduction

```sh
python tools/verify.py --report verification.json
```

On a supported development host this runs backend, frontend and registered browser
checks. The complete backend collection can also be split by file using pytest's
`--deselect` options after default collection, preserving the existing conftest
import order. Do not count deselected nodes as tested or omit failing nodes.
The verification reports explicitly distinguish partial toolchain runs from a
complete run and keep native Windows acceptance false until separately recorded.
