# UI issues and planned work

This register owns UI issues and their completion evidence. Last reviewed:
**2026-11-21**. [UI maintenance guide](README.md) describes current contracts;
the [project issue index](../../../docs/ISSUES.md) links shared work and other owners.
Follow the [tracking rules](../../../docs/ISSUES.md#maintaining-this-register).

[ISS026 reuse audit](../../tools/docs/ISSUES.md#iss026-reusable-tools-and-duplicate-capabilities)
tracks shared formatting, timestamp display, Blob downloads and JSON request
mechanics. These remain UI-owned capabilities; Tools coordinates the inventory.

| ID | Work | Status | Owner and collaborators |
| --- | --- | --- | --- |
| ISS002 | [Shared rendering deadline dependency](#iss002-shared-rendering-deadline-dependency) | Resolved | UI; Investigations |
| ISS012 | [Browser composition interfaces](#iss012-browser-composition-interfaces) | Deferred | UI; Observatory |
| ISS013 | [Rendering resource inputs](#iss013-rendering-resource-inputs) | Deferred | UI; Investigations |
| ISS018 | [Command-palette focus after search](#iss018-command-palette-focus-after-search) | Resolved | UI |
| ISS047 | [Command palette reopen lifecycle](#iss047-command-palette-reopen-lifecycle) | Resolved | UI |


Shared checks for this completed batch are recorded in the [November 21 validation](../../../docs/history/validation/maintenance-2026-11-21.md).
Individual entries retain their module benefit, scope and focused evidence.

## ISS002 Shared rendering deadline dependency

Shared layout and exhibit rendering imported Investigations' report-operation
deadline check. In a fresh Python 3.14.10 process, importing `vector_layout` and
wrapping plain text loaded three Investigations modules and 110
FastAPI/Starlette/Pydantic modules. That made reusable text layout require the
application's report workflow and web dependencies.

**Module benefit:** callers can use shared text layout without Investigations or
the web framework and supply their own cancellation/deadline policy. UI owns the
checkpoint interface; Investigations retains report state and publication policy.

**Done when:** layout actually renders with domain/web imports unavailable, a
caller-supplied checkpoint can stop rendering, and before-and-after import evidence
demonstrates the removed dependency. Report cancellation, timeout, publication,
context cleanup and child-process supervision retain their contracts. This does
not claim independence for the entire exhibit renderer or a performance gain.

**Resolved 2026-11-21.** The local ISS002 change adds
[`render_control.py`](../helpers/render_control.py), updates the layout/exhibit
callers, and binds Investigations' existing policy inside `ReportOperations.run`.
The [rendering-control contract](README.md#rendering-control) defines ownership
and scope. These changes are uncommitted on the reorganized source checkout;
the baseline Git revision is `efccc0a0f476bf83078b26694afa8fad0372047c`.

**Demonstrated improvement:** independent replay against the saved source baseline
reduced layout's Investigations imports from 3 to 0 and web-framework imports
from 110 to 0. Baseline execution fails when those imports are unavailable; the
updated source and installed file set both render successfully. Six representative
wrapping cases produce identical results and font hashes match. Callers can supply
their own stop policy without constructing report operations. Registry rules now
protect the dependency direction.

**Verification:** Windows 10, Python 3.14.10, `PYTHONUTF8=1`, with the existing
Poppler tools on `PATH`. Commands ran from the repository root:

```text
python -m pytest -q modules/ui/tests modules/investigations/tests/test_report_operations_080.py modules/investigations/tests/test_report_operations_095.py
python -m pytest -v --junitxml=backend.xml
```

- Focused selection: 60 distinct tests passed, 2 skipped, including 12 new
  regressions for independent use, caller cancellation, context restoration,
  report states and publication. One initial missing-`pdftotext` environment
  failure passed unchanged after correcting `PATH`.
- Complete backend: 3,117 passed, 18 skipped, 162 subtests passed, 1 dependency
  deprecation warning and 3 failures in 1,596.74 seconds. The failures are exactly
  the existing [ISS001 capture-test mismatches](../../investigations/docs/ISSUES.md#iss001-capture-test-expectations).
  No new regression failures were observed; that historical run was non-green.
  ISS001 and the complete backend are now covered by the shared November 21 record.
- Changed-file Ruff lint/format, architecture checks, source/installed file
  inclusion and local document-link checks passed. Native Windows release
  acceptance was not performed. Full skip reasons and execution logs remain in
  the Codex workspace's `validation/issues-001-002` evidence bundle.

## ISS012 Browser composition interfaces

Browser actions are dynamically composed and ECLIPSE uses a global renderer.
Independent component reuse would need explicit render/action and lifecycle
interfaces beyond the current folder boundaries.

**Done when:** a selected reuse need has explicit inputs, state and mount/unmount
contracts, with navigation, cancellation and listener cleanup verified. This is
deferred until a concrete reuse or maintenance need warrants extraction; separate
component packaging is not a release requirement.

**Review 2026-11-21:** the concrete maintenance slice in ISS005–007 now composes
Entities, Accretion and Library explicitly and gives feature handlers a common
optional disposer. UI detaches all listeners/disposers even after a cleanup
failure; entity lookups and intake drop listeners have actual teardown coverage.
See the [interaction lifecycle](README.md#interaction-lifecycle) for that contract
and the owning issue entries for its evidence. This addresses current lifecycle
coupling without adding a second application framework.

The separate global-renderer extraction remains deferred: no independent
Observatory consumer has been identified. Its state/render contract and potential
reuse require a concrete consumer before changing the existing renderer. The
completed lifecycle slice does not claim independent renderer packaging.

## ISS013 Rendering resource inputs

Rendering depends on workspace asset paths and bundled fonts. A separately
reusable document library would need an explicit resource resolver.

**Done when:** a concrete independent consumer justifies the extraction, resources
arrive through a documented interface, and PDF/DOCX output, font embedding and
certified historical artifacts retain their contracts. This is deferred until
that consumer exists; independent library extraction is not a release requirement.

**Reviewed 2026-11-21.** ISS002 provides independent layout cancellation without
moving assets or changing resource lookup. The current consumers remain the
application's bundled renderers; no separate document-library consumer has been
identified. Keep font provenance, packaged paths and certified bytes stable.
Adding a resolver framework now would introduce an interface without a concrete
consumer or demonstrated improvement, so this item remains deferred.

## ISS018 Command-palette focus after search

**Owner:** UI. Found during ISS008's real keyboard-browser review.

An asynchronous search result repaints the command palette while an existing
destination is focused. Replacing its DOM removes focus, interrupting keyboard
navigation. A controlled delayed `/api/search` response reproduces the failure
with the Workspace destination focused; this is a product defect, separate from
the obsolete test expectations repaired in ISS008.

**Module benefit and done when:** asynchronous result updates preserve the
matching focused destination by stable kind/id/href. If that destination vanishes,
return focus to the query only when focus was inside the palette results. Do not
steal focus from another control or reopen a closed palette. Verify those cases
with delayed-response DOM and actual keyboard-browser checks.

**Resolved 2026-11-21.** The owning
`command_palette.js` now preserves destination focus across delayed result
repaints and reorderings. Four focused DOM cases cover matching, removed, outside
and closed-palette focus. The actual Chromium keyboard check reproduces the
baseline loss and passes with the fix; the complete portable frontend runner
also passes. This restores continuous keyboard navigation during asynchronous
search. Baseline reproduction, source hashes and command logs are in the Codex
workspace's `validation/maintenance-batch-02/browser008-*` bundle, based on
uncommitted revision `efccc0a0f476bf83078b26694afa8fad0372047c`.

## ISS047 Command palette reopen lifecycle

**Resolved 2026-11-21.** The full verifier exposed an intermittent palette-search
timeout after choosing a destination. A deterministic native `close()` → reopen →
type sequence independently reproduced the lifecycle defect: the queued close
event disposed the newly opened palette and removed its presentation state.
The [HTML dialog close algorithm](https://html.spec.whatwg.org/multipage/interactive-elements.html#close-the-dialog)
queues that event, so cleanup cannot assume the current dialog is still closed.

**Module benefit:** reopening search keeps the new query and its pending request
usable. UI's close listener now preserves a currently open palette while retaining
cleanup for genuinely closed dialogs and replacement content. No transport or
modal framework was introduced.

**Verification:** the new native regression failed before the runtime repair and
passed afterward. The complete focused navigation browser group passed all three
scripts; the palette's seven checks retain every original search, focus, exact
destination, deep-link and privacy assertion, with zero JavaScript errors or
external requests. Existing portable palette and frontend lifecycle suites also
passed. The browser deadline and launch flags were unchanged; failure diagnostics
now retain synthetic request and UI state. This is focused evidence, not a full
build or installed-acceptance result.

The Codex workspace's `validation/full-build-20261121/palette-fix.json` records
source hashes and commands; `palette-fix.patch`, `palette-close-race-before.*`
and `palette-repaired.*` retain the change and before/after results. The original
full-verifier timeout remains in `verification-baseline.*`.

Subsequent combined results and limits are in the
[full-build record](../../../docs/history/validation/full-build-2026-11-21.md).

## Shared work affecting UI

- [ISS003 Shared test fixtures](../../../docs/ISSUES.md#iss003-shared-test-fixtures)
- [ISS008 Browser suite coverage](../../../docs/ISSUES.md#iss008-browser-suite-coverage)
- [ISS009 Explicit resource encoding](../../../docs/ISSUES.md#iss009-explicit-resource-encoding)
- [ISS014 Current version Windows acceptance](../../../docs/ISSUES.md#iss014-current-version-windows-acceptance)

Status and completion evidence for shared items stay at their linked home.
