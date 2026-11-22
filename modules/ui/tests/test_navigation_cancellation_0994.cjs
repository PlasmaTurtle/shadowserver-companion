/** Real shared transport and router: abandoned views stop, submitted jobs survive. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('../../../tests/frontend_harness.cjs');

(async () => {
  const nodes = new Map();
  const node = (selector) => {
    if (!nodes.has(selector))
      nodes.set(selector, {
        innerHTML: '',
        textContent: '',
        dataset: {},
        open: false,
        setAttribute() {},
        removeAttribute() {},
        focus() {},
        classList: { toggle() {}, add() {}, remove() {} },
      });
    return nodes.get(selector);
  };
  const calls = [];
  const timers = new Set();
  const location = { hash: '#entities' };
  let renders = 0;
  const context = vm.createContext({
    console,
    AbortController,
    URLSearchParams,
    structuredClone,
    location,
    setTimeout(fn, milliseconds) {
      const timer = { fn, milliseconds };
      timers.add(timer);
      return timer;
    },
    clearTimeout(timer) {
      timers.delete(timer);
    },
    clearInterval,
    FormData: class {},
    fetch(url, options) {
      // Intentionally ignores abort: the application must reject late bodies too.
      return new Promise((resolve, reject) => calls.push({ url, options, resolve, reject }));
    },
    document: {
      querySelector: node,
      querySelectorAll: () => [],
      body: { dataset: {}, classList: { toggle() {} } },
    },
    window: {
      scrollY: 0,
      scrollTo() {},
      matchMedia: () => ({ matches: false }),
      Eclipse: {
        destroy() {},
        loading: () => 'Loading field',
        render: () => {
          renders++;
          return 'STALE';
        },
        mount() {},
      },
    },
    history: {
      replaceState(_a, _b, hash) {
        location.hash = hash;
      },
    },
    localStorage: { getItem: () => null, setItem() {} },
    confirm: () => true,
  });
  const { application: app } = await loadApplication(context, { attach: false });
  app.state.navigation.boot = { settings: {} };
  app.actions.refreshNavigationCounts = async () => {};
  app.actions.dashboard = async () => 'Workspace ready';
  app.actions.entitiesPage = async () => {
    await app.actions.api('/api/entities');
    renders++;
    return 'STALE';
  };
  let stopped = 0;
  for (const name of [
    'stopContactDiscoveryPolling',
    'stopApiAcquisitionPolling',
    'stopAssetAttributionPolling',
    'stopWebsiteCapturePolling',
    'stopCatalogPolling',
  ])
    app.actions[name] = () => stopped++;
  const sourceWatch = { running: true };
  app.state.editor.pendingCveRefresh = sourceWatch;
  const oldRoute = app.actions.route();
  const old = calls.shift();
  assert.equal(old.url, '/api/entities');
  assert.equal(old.options.signal.aborted, false);
  location.hash = '#workspace';
  await app.actions.route();
  assert.equal(old.options.signal.aborted, true);
  old.resolve({ ok: true, json: async () => ({}) });
  await oldRoute;
  assert.equal(node('#main').innerHTML, 'Workspace ready');
  assert.equal(renders, 0, 'Never render an obsolete entity response');
  assert.equal(sourceWatch.detached, true);
  assert.equal(sourceWatch.running, false);
  assert.equal(stopped, 10, 'Both view transitions detach all view pollers');

  const mutation = app.actions.api('/api/imports', {
    method: 'POST',
    body: { file: 'source.csv' },
  });
  const submitted = calls.shift();
  assert.equal(submitted.options.signal, undefined, 'Navigation must not abort a submitted job');
  assert.equal(timers.size, 0, 'Writes do not acquire an implicit timeout');
  app.actions.beginViewRequests();
  submitted.resolve({ ok: true, json: async () => ({ id: 'queued' }) });
  await assert.rejects(mutation, (error) => error.code === 'VIEW_CHANGED');

  const background = app.actions.api('/api/imports/status', { background: true });
  const independent = calls.shift();
  app.actions.beginViewRequests();
  independent.resolve({ ok: true, json: async () => ({ running: true }) });
  assert.equal((await background).running, true);

  const external = new AbortController();
  const cancelled = app.actions.api('/api/test', { signal: external.signal, timeoutMs: 10000 });
  const combined = calls.shift();
  external.abort();
  assert.equal(
    combined.options.signal.aborted,
    true,
    'Timeout must not replace caller cancellation',
  );
  combined.resolve({ ok: true, json: async () => ({}) });
  await assert.rejects(cancelled, (error) => error.name === 'AbortError');

  let finishBody, bodyStarted;
  const bodyReady = new Promise((resolve) => {
    bodyStarted = resolve;
  });
  const bodyRead = app.actions.api('/api/body');
  calls.shift().resolve({
    ok: true,
    json: () =>
      new Promise((resolve) => {
        finishBody = resolve;
        bodyStarted();
      }),
  });
  await bodyReady;
  app.actions.beginViewRequests();
  finishBody({ stale: true });
  await assert.rejects(bodyRead, (error) => error.code === 'VIEW_CHANGED');

  const stalled = app.actions.api('/api/bootstrap', { background: true });
  const stalledCall = calls.shift();
  stalledCall.options.signal.addEventListener('abort', () => {
    const error = Error('Aborted fetch');
    error.name = 'AbortError';
    stalledCall.reject(error);
  });
  assert.equal(timers.size, 1);
  assert.equal([...timers][0].milliseconds, 30000, 'Reads have a bounded default deadline');
  const timeoutFailure = assert.rejects(stalled, (error) => error.code === 'REQUEST_TIMEOUT');
  [...timers][0].fn();
  await timeoutFailure;
  assert.equal(timers.size, 0, 'A timed-out read releases its timer');

  const preview = app.actions.api('/api/preview.pdf', { timeoutMs: 120000 });
  assert.equal([...timers][0].milliseconds, 120000, 'Explicit long-running read deadlines survive');
  calls.shift().resolve({ ok: true, json: async () => ({ ready: true }) });
  assert.equal((await preview).ready, true);
  assert.equal(timers.size, 0);
  app.actions.stopViewRequests();
  console.log(
    'Navigation cancellation, late bodies, composed timeout signals, poll teardown and independent jobs passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
