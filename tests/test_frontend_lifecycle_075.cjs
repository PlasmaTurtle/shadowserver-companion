/** Delegation, dirty guards, teardown, and cancelled startup without a browser. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');
function target(extra = {}) {
  const listeners = new Map();
  return {
    ...extra,
    addEventListener(type, listener) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(listener);
    },
    removeEventListener(type, listener) {
      listeners.get(type)?.delete(listener);
    },
    async emit(type, event) {
      for (const fn of [...(listeners.get(type) || [])]) await fn(event);
    },
    count() {
      return [...listeners.values()].reduce((n, set) => n + set.size, 0);
    },
  };
}
(async () => {
  const nodes = new Map(),
    timers = new Set(),
    calls = [];
  let confirms = 0,
    allowLeave = false;
  const node = (selector) => {
    if (!nodes.has(selector))
      nodes.set(selector, {
        textContent: '',
        innerHTML: '',
        open: false,
        dataset: {},
        classList: { toggle() {}, add() {}, remove() {} },
        focus() {},
      });
    return nodes.get(selector);
  };
  const doc = target({
    querySelector: node,
    querySelectorAll: () => [],
    body: { dataset: {}, classList: { toggle() {} } },
  });
  const win = target({ scrollTo() {}, Eclipse: { destroy() {} } });
  const context = vm.createContext({
    document: doc,
    window: win,
    console,
    URLSearchParams,
    structuredClone,
    location: { hash: '#workspace' },
    history: { replaceState() {} },
    confirm: () => {
      confirms++;
      return allowLeave;
    },
    setInterval: (fn) => {
      timers.add(fn);
      return fn;
    },
    clearInterval: (fn) => timers.delete(fn),
    setTimeout,
    clearTimeout,
    FormData: class extends Map {
      constructor(form) {
        super(form.fields);
      }
    },
  });
  const { application: app } = await loadApplication(context, { attach: false });
  const realRoute = app.actions.route;
  Object.assign(app.actions, {
    busy: async (_button, action) => action(),
    toast() {},
    saveDraft: async () => calls.push('save'),
    validateSection: async (section) => calls.push('validate:' + section),
    submitReopen: async (_form, obj) => calls.push('reopen:' + obj.reason),
  });
  app.state.editor.currentLead = { case_id: 'c1' };
  const button = (dataset = {}, id = '') => ({
    id,
    dataset,
    closest: (selector) => (selector === 'button,[data-open-lead]' ? buttonEl : null),
  });
  let buttonEl = button({ action: 'save' });
  app.attach();
  const count = doc.count() + win.count();
  app.attach();
  assert.equal(doc.count() + win.count(), count);
  await doc.emit('click', { target: buttonEl });
  assert.deepEqual(calls, ['save']);
  buttonEl = button({ action: 'validate-section', section: 'attribution' });
  await doc.emit('click', { target: buttonEl });
  assert.equal(calls.at(-1), 'validate:attribution');
  // One recognized form owner, retaining the analyst's reason exactly.
  let prevented = false;
  await doc.emit('submit', {
    target: { id: 'section-reopen-form', fields: [['reason', 'Correct company address']] },
    submitter: {},
    preventDefault() {
      prevented = true;
    },
  });
  assert(prevented);
  assert.equal(calls.at(-1), 'reopen:Correct company address');
  // Frozen adoption still stops before fetching or changing selected sources.
  app.actions.sectionLocked = () => true;
  app.actions.api = async () => {
    throw Error('Frozen section must not fetch for adoption');
  };
  buttonEl = button({ action: 'adopt-blocks' });
  await doc.emit('click', { target: buttonEl });
  // Tab and navigation dirty guards survive event ownership changes.
  app.state.workflow.workflowDirty = true;
  app.state.editor.tab = 'notification';
  buttonEl = button({ tab: 'contact' });
  await doc.emit('click', { target: buttonEl });
  assert.equal(app.state.editor.tab, 'notification');
  assert.equal(confirms, 1);
  app.state.navigation.currentRoute = 'case/c1';
  await win.emit('hashchange', {});
  assert.equal(app.state.navigation.currentRoute, 'case/c1');
  assert.equal(confirms, 2);
  let unloadPrevented = false;
  await win.emit('beforeunload', {
    preventDefault() {
      unloadPrevented = true;
    },
  });
  assert(unloadPrevented);
  app.destroy();
  app.destroy();
  assert.equal(doc.count() + win.count(), 0);
  await doc.emit('keydown', { ctrlKey: true, key: 's' });
  assert.equal(calls.filter((x) => x === 'save').length, 1);
  app.attach();
  buttonEl = button({ action: 'save' });
  await doc.emit('click', { target: buttonEl });
  assert.equal(calls.filter((x) => x === 'save').length, 2);
  assert.equal(doc.count() + win.count(), count);
  app.destroy();
  // Destroy during bootstrap must not write UI/state or create a polling timer.
  let resolveBootstrap,
    requests = 0;
  app.actions.api = () => {
    requests++;
    return new Promise((resolve) => {
      resolveBootstrap = resolve;
    });
  };
  const first = app.start(),
    second = app.start();
  assert.equal(first, second);
  assert.equal(requests, 1);
  app.destroy();
  resolveBootstrap({ version: 'synthetic', settings: {} });
  await first;
  assert.equal(app.state.navigation.boot, undefined);
  assert.equal(timers.size, 0);
  // Restart creates exactly one timer, and overlapping polls are coalesced.
  app.state.workflow.workflowDirty = false;
  const boot = {
    version: 'synthetic',
    release: { version: 'synthetic', channel: 'unstable' },
    settings: { appearance: 'dark', analyst_name: 'Synthetic Analyst' },
    explainers: [],
  };
  let resolvePoll,
    polls = 0;
  app.actions.api = async (url) => {
    if (url === '/api/bootstrap') return boot;
    if (url === '/api/setup') return { required: false };
    if (url === '/api/software/whats-new') return { should_show: false };
    if (url === '/api/imports') {
      polls++;
      return new Promise((resolve) => {
        resolvePoll = resolve;
      });
    }
    throw Error(url);
  };
  app.actions.applyPresentation = () => {};
  app.actions.route = async () => {};
  app.state.navigation.currentRoute = 'workspace';
  await app.start();
  await app.start();
  assert.equal(timers.size, 1);
  const poll = [...timers][0],
    pending = poll();
  await poll();
  assert.equal(polls, 1);
  app.destroy();
  resolvePoll([{ status: 'running' }]);
  await pending;
  assert.equal(timers.size, 0);
  assert.equal(doc.count() + win.count(), 0);
  // A detached Settings refresh may be aborted when the user leaves the view.
  // It must not reject globally; actual current-view failures remain visible.
  context.location.hash = '#settings';
  Object.assign(app.actions, {
    route: realRoute,
    settingsPage: async () => '<section>Settings</section>',
    loadNvdKeyStatus: async () => {},
    loadSettingsSetupStatus: async () => {},
    refreshNavigationCounts: async () => {},
  });
  const unhandled = [],
    notices = [];
  const onUnhandled = (error) => unhandled.push(error);
  process.on('unhandledRejection', onUnhandled);
  try {
    app.actions.toast = (message) => notices.push(message);
    app.actions.loadSoftwareStatus = async () => {
      throw Object.assign(new Error('The user aborted a request.'), { name: 'AbortError' });
    };
    await app.actions.route(true);
    await new Promise(setImmediate);
    assert.deepEqual(unhandled, []);
    assert.deepEqual(notices, []);
    app.actions.loadSoftwareStatus = async () => {
      throw new Error('Synthetic status failure');
    };
    await app.actions.route(true);
    await new Promise(setImmediate);
    assert.deepEqual(unhandled, []);
    assert.deepEqual(notices, ['Could not refresh software status: Synthetic status failure']);
  } finally {
    process.off('unhandledRejection', onUnhandled);
  }
  console.log(
    'Feature event dispatch, freeze/dirty guards, idempotent startup, detach/remount, and stale polling passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
