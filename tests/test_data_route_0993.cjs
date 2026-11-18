/** Real router + Data renderer + upload binding: sidebar and explicit tabs agree. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');
(async () => {
  const nodes = new Map(),
    listeners = new Map();
  const node = (selector) => {
    if (selector === '#dropzone' && !nodes.get('#main')?.innerHTML.includes('id="dropzone"'))
      return null;
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
        addEventListener(event, fn) {
          listeners.set(event, fn);
        },
      });
    return nodes.get(selector);
  };
  const location = { hash: '#data' };
  const context = vm.createContext({
    console,
    URLSearchParams,
    structuredClone,
    location,
    setTimeout,
    clearTimeout,
    document: {
      querySelector: node,
      querySelectorAll: () => [],
      body: { dataset: {}, classList: { toggle() {} } },
    },
    window: {
      scrollY: 0,
      scrollTo() {},
      matchMedia: () => ({ matches: false }),
      Eclipse: { destroy() {} },
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
  app.state.navigation.boot = { workspace: '/work', settings: {} };
  app.actions.refreshNavigationCounts = async () => {};
  app.actions.api = async (url) => {
    if (url === '/api/intake/progress') return { catalog: { state: 'ready' } };
    if (url === '/api/shadowserver/status')
      return { configured: true, connected: true, subscriptions: [], types: [] };
    if (url === '/api/imports') return [];
    throw Error('Unexpected request: ' + url);
  };
  for (const hash of [
    '#data',
    '#data?tab=api',
    '#data?tab=files',
    '#data',
    '#imports',
    '#data?tab=unknown',
  ]) {
    location.hash = hash;
    listeners.clear();
    await app.actions.route(true);
    const html = node('#main').innerHTML;
    assert.doesNotMatch(html, /Unable to open this view/, hash);
    assert.match(html, /Shadowserver Data/, hash);
    assert.match(html, /id="accretion-console"/, hash);
    if (hash.endsWith('tab=files')) {
      assert.match(html, /id="dropzone"/);
      assert.deepEqual([...listeners.keys()], ['dragover', 'dragleave', 'drop']);
      let uploaded = null;
      app.actions.upload = (files) => {
        uploaded = files;
      };
      const files = ['fixture.csv'];
      listeners.get('drop')({ preventDefault() {}, dataTransfer: { files } });
      assert.equal(uploaded, files, 'File drop still reaches the importer');
    } else {
      assert.match(html, /id="shadowserver-api"/);
      assert.equal(listeners.size, 0, 'API routes must not initialize file-drop handlers');
    }
    assert.equal(node('#main').inert, false);
  }
  console.log(
    'Sidebar/default Data, API, Files, legacy imports and return navigation passed; file drops remain functional.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
