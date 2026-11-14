# Observatory acceptance

The Observatory now has one scoped response for the Field, Atlas, Pulse, product
breakdown, finding records and counts. Browser acceptance checks this shared
meaning as well as rendering. Portable checks are not a substitute for native
Windows visual acceptance.

## Repeatable checks

From the repository root with the documented development dependencies installed:

```console
python -m pytest -q tests/test_observatory_acceptance_0995.py
node --experimental-vm-modules tests/test_observatory_controller_0995.cjs
npm test
npm run test:browser
```

`npm run test:browser` delegates to `tools/verify.py --only-browser`. The verifier
creates a synthetic workspace and issues a separate one-time launcher URL for
each registered browser suite. It does not reuse a consumed launcher token.
Its report remains explicitly partial because backend and portable frontend
checks are not part of that command. Use `python tools/verify.py` for the complete
development verification sequence.

`test_observatory_browser_0995.cjs` is the registered Observatory browser suite.
It uses the normal Chromium sandbox, refuses to substitute DOM results for an
unavailable browser, and rejects external browser requests. The older
`test_eclipse_ui.cjs`, `test_eclipse_browser_0981.cjs` and
`test_eclipse_browser_0982.cjs` entry points explicitly dispatch to this current
suite; obsolete observation-equals-finding assertions are no longer counted.

## Portable acceptance covers

- The actual controller and production markup, with only DOM, canvas and
  transport IO replaced by controlled test doubles.
- A clean entity deep link, retained intentional intake preferences, and explicit
  traditional-view preference.
- Product Reset replacing the complete scope, including counts, records and
  the histogram.
- Named mass selection, scoped Locations and Products navigation, further
  product refinement, and return to the same field selection, camera and revision.
- Background response supersession, leaving the view, returning while a request
  is pending, and cancellation of source detail without a false timeout.
- Exact totals independent of the bounded sample and current records page.
- Actual API session enforcement, query bounds, semantic validation before
  expensive projection, compact payloads, pagination, historical endpoints,
  and admission separation.
- Original evidence remains available on demand; viewing does not create work,
  alter intake records, or trigger external lookup requests.

## Native Windows gate

Record this gate separately from automated portable results. A build produced in
an environment that cannot launch Chromium must leave browser and native visual
acceptance pending.

1. Open a populated synthetic workspace at 100%, 125% and 150% Windows scaling.
   Confirm readable text and controls, no clipped inspector, and no unintended
   horizontal page overflow. Check a compact window as well as the main display.
2. Open Observatory with no saved preference. The Dark Matter Field is the
   initial mode, and the workspace remains usable while data loads.
3. Select a named organization with both pointer and keyboard. Open Locations,
   Products, Assets & findings and History. Confirm the scope remains visible
   and all displayed totals refer to that scope.
4. Pan or zoom the Field, inspect a mass, then return. Confirm that the same
   object, camera position and original snapshot return without a new request
   replacing them unexpectedly.
5. Switch directly between traditional views and reload. Confirm that the
   deliberately selected preference survives without becoming an accidental
   preference after a contextual drill-down.
6. Inspect an old delivered finding followed by a newly observed CVE. The new
   CVE must remain unworked. Move the historical cutoff before an endpoint
   change and confirm that the earlier endpoint remains visible.
7. Check a dense fixture. Density halos and internal temperature markers must
   remain distinct; unadmitted observations must not look like approved findings.
8. Enable reduced motion. Camera travel and decorative motion must respect it,
   while every view and contextual action remains available.
9. Open evidence and change scope immediately. No abandoned request should
   replace the new selection with an error. Navigate away during loading and
   confirm that the abandoned view stops rendering.
10. Confirm the oversized eclipse, foreground data and floating panels compose
    correctly on the actual display. Atmosphere must not impair reading or
    obscure source evidence.
