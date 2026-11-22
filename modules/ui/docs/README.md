# UI

UI owns the application shell, navigation, delegated events, shared frontend
state/session helpers, theme/accessibility primitives, fonts, and shared document
geometry/rendering utilities. This guide is for maintaining those shared contracts.

[Module issues](ISSUES.md) · [Changelog](CHANGELOG.md) · [Architecture](../../../docs/ARCHITECTURE.md) ·
[Maintenance workflow](../../../docs/DEVELOPMENT.md#maintenance-workflow)

## Start here

| Responsibility | Start here |
| --- | --- |
| Shell markup and application lifecycle | [index.html](../static/index.html), [app.js](../static/app.js) |
| Navigation, delegated actions and frontend state | [navigation.js](../static/navigation.js), [events.js](../static/events.js), [state.js](../static/state.js) |
| Shared document geometry and typeface selection | [vector_layout.py](../components/vector_layout.py), [document_fonts.py](../components/document_fonts.py) |
| Caller-supplied rendering cancellation and deadline checks | [render_control.py](../helpers/render_control.py) |
| Word font embedding and licensed assets | [helpers/fonts.py](../helpers/fonts.py), [fonts/](../fonts) |

## Boundary

Feature-specific browser code and styling live with the feature. UI owns reusable
presentation and lifecycle; domain modules own entity, qualification, report and
provider policy. Application startup composes feature actions without duplicating
their business logic.

## Retained responsibilities

### Shared browser capabilities

[format.js](../static/format.js) owns pure HTML escaping, count formatting and
timestamp formatting. The shell's `stamp` adapter supplies the analyst's selected
display timezone; calendar dates and schedule execution zones remain separate.
Settings, Data and Workspace health use that adapter for recorded instants.
Observatory uses the same encoder/count formatter; its classic synchronous
`Eclipse.render(data, escapeHTML)` receives the encoder from navigation.

[request.js](../static/request.js) provides `requestJSON(url, options)` and
`requestBlob(url, options)` over native Fetch. Request options retain native
headers/body/credentials plus optional `timeoutMs`, `signal` and a `signals`
list for composed cancellation. Results are decoded data; HTTP errors preserve
`status`, `detail` and `body`, timeouts use `REQUEST_TIMEOUT`, and cancellation
uses `AbortError`. Timers/listeners are released on completion or cancellation.
No navigation, token, retry or domain state lives in this transport.

An interrupted Fetch reports a `ConnectionError` with local app recovery
instructions. A submitted write may already have reached the service. The UI
asks the analyst to check its status before sending it again. If bootstrap
fails, **Reload app** reloads the current URL so the browser can reuse its
session cookie, fetch the bootstrap data and start normal navigation and polling.

The `api` adapter in [shared.js](../static/shared.js) supplies mutation-token
headers, JSON request encoding, navigation cancellation and the existing read
deadline. Submitted writes continue independently of the abandoned view.
Observatory supplies its own view/detail deadlines and retains revision recovery.
Session bootstrap remains independent of application state.

[download.js](../static/download.js) accepts a Blob and filename, initiates the
native browser download and releases the object URL after the click. It does not
confirm that a file was saved. Settings owns fetching, filenames and feedback;
Investigations retains its separate PDF-preview lifetime.

These thin capabilities follow native
[Fetch](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch),
[Intl.DateTimeFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat)
and [object-URL ownership](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Resource_management).
Run `node --experimental-vm-modules modules/ui/tests/test_shared_frontend_helpers.cjs`
for cross-module timestamps, risk meaning, download cleanup and actual local HTTP
responses; use navigation and Observatory suites for workflow behavior. Progress
for this consolidation is tracked in [ISS026](../../tools/docs/ISSUES.md#iss026-reusable-tools-and-duplicate-capabilities).

### Rendering control

Shared layout and SVG/PNG rendering call `check_rendering()` from
`helpers/render_control.py`. A caller supplies its cancellation/deadline policy
with `rendering_checks(check)`, where `check` takes no arguments and raises to
stop work. Exceptions propagate unchanged. Without a supplied policy, the
checkpoint is a no-op. Nested scopes restore the previous callback on exit,
including failures, and the callback belongs to the current execution context.

Investigations binds its existing `check_deadline` inside `ReportOperations.run`.
It continues to own report status, cancellation admission and the irreversible
publication boundary. The private render subprocess has no inherited callback;
its parent supervises timeout/cancellation and terminates it as before. Callers
that create other threads or processes must arrange their own control explicitly.

Vector layout can run without Investigations or the web framework. The exhibit
renderer still composes Investigations-specific layouts; this control interface
does not make the entire renderer an independent library. Layout geometry,
font selection and output formats retain their existing contracts.

### Fonts and formats

`helpers/fonts.py` owns shared Word font obfuscation and package relationships.
`document_fonts.py` selects report typefaces; `unicode_fonts.py` chooses Unicode
fallback runs. Their selection and font-family XML remain separate from the
common embedding mechanism.

Vector, PDF, Word and browser renderers retain their format-specific behavior.
TTF and WOFF assets serve different consumers; regular/bold faces, licenses and
provenance remain alongside the fonts. Navigation, delegated events and session
state are distinct shell responsibilities.

## Verification

Use the [project development setup](../../../docs/DEVELOPMENT.md#windows-ide-setup).
From the repository root, check Python rendering behavior and the portable DOM
suite used by the shared shell and its feature callers:

```text
python -m pytest -q modules/ui/tests
npm test
```

`npm test` covers registered portable suites across all modules; it is not a
browser run. Follow [project verification](../../../docs/DEVELOPMENT.md#verification)
for the registered browser groups and complete application checks. A rendering
change also needs the affected Investigations report regressions and the relevant
native Word checks from [Windows acceptance](../../../docs/WINDOWS_ACCEPTANCE.md).

## Command-palette browser verification

The maintained navigation group covers entity DNS, navigation and the command
palette with a fresh synthetic workspace:

```text
python tools/verify.py --only-browser --browser-suite navigation --report build/navigation-browser.json
```

Set `CHROMIUM_EXECUTABLE` when using an existing browser instead of Playwright's
installed Chromium. The verifier owns fixture startup, fresh authentication and
cleanup. Checks cover navigation, focus return, delayed search repaint and absence
of search queries/authentication tokens from browser persistence. Asynchronous
palette updates preserve the focused destination by identity, or return to the
query if that destination disappears; they must not steal outside focus.

Native dialog close events are queued. A close event from the previous palette
must not dispose a newly reopened palette's search, debounce or presentation.
The close listener still disposes work when the dialog is closed or its content
has been replaced. [ISS047](ISSUES.md#iss047-command-palette-reopen-lifecycle)
records the deterministic native close/reopen regression and retained checks.

The focused `keyboard` group and artifact-specific package-shell check have
their maintained setup in `python tools/verify.py --list-browser`. That catalog
also distinguishes the exploratory Field-density fixture from acceptance checks.
See [project registration](../../../docs/DEVELOPMENT.md#working-in-a-module);
local launcher metadata is test session material, not release documentation.

## Interaction lifecycle

Frontend interaction changes start in the owning feature's `editor_events.js`,
`workflow_events.js`, `entities_events.js`, `intake_events.js`, `library_events.js`,
`attribution.js` or `settings_events.js`. Export handlers rather than adding a
second document listener. `install(ctx)` registers the owner's actions on `ctx.actions`;
it must not secretly install another feature. UI composes each owner once and
owns shared navigation and generic `data-submit-filter` submission.

`events.js` owns the shell's `global-search-form`; Attribution's
`attribution.js::createHandlers(ctx)` owns attribution review clicks and forms.
There is no Workspace event facade between them. See
[Workspace ISS029](../../workspace/docs/ISSUES.md#iss029-workspace-file-ownership-and-consolidation)
for the ownership change.

`createHandlers(ctx)` returns the existing action/form handlers and may supply
`dispose()` for owned timers or listeners. `events.js` rejects duplicate action/form names, and
`createApplication().destroy()` is the cleanup boundary for delegated listeners
and app polling. Detaching is idempotent: it removes every delegated listener and
invokes every feature disposer even when one fails, then raises `AggregateError`.
Application cleanup still runs in that case. Existing backend commands continue
independently after teardown. Feature installers start no work; mount-specific
resources are acquired explicitly and released through the same owner.

## Maintenance and tracking

Use [UI issues](ISSUES.md) for shared rendering and browser-interface work. For
each change, identify the affected feature callers and preserve event teardown,
keyboard behavior, cancellation and unsaved-change handling. Update this guide
when a shared contract changes, and update the owning issue with the checks that
establish completion. Follow the [project maintenance workflow](../../../docs/DEVELOPMENT.md#maintenance-workflow)
for scope, evidence and review.
