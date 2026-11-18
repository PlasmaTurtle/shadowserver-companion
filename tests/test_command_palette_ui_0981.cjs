/** Production palette: stale requests, keyboard actions, escaping and app teardown. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');

(async () => {
  const nodes = new Map(),
    timers = new Map(),
    requests = [],
    imports = [],
    storage = [];
  let timerId = 0,
    resultNodes = [];
  const location = { hash: '#workspace' };
  function node(selector) {
    if (!nodes.has(selector)) {
      const classes = new Set(),
        attrs = new Map();
      let html = '';
      const item = {
        id: selector.slice(1),
        value: '',
        textContent: '',
        open: false,
        dataset: {},
        classList: {
          add: (name) => classes.add(name),
          remove: (name) => classes.delete(name),
          toggle(name, enabled) {
            if (enabled) classes.add(name);
            else classes.delete(name);
          },
          contains: (name) => classes.has(name),
        },
        setAttribute: (name, value) => attrs.set(name, value),
        removeAttribute: (name) => attrs.delete(name),
        getAttribute: (name) => attrs.get(name),
        focus() {},
        scrollIntoView() {},
        set innerHTML(value) {
          html = value;
          if (selector === '#command-results') {
            resultNodes = [...value.matchAll(/id="command-result-(\d+)"/g)].map((m) =>
              node('#command-result-' + m[1]),
            );
          }
        },
        get innerHTML() {
          return html;
        },
      };
      nodes.set(selector, item);
    }
    return nodes.get(selector);
  }
  const localStorage = {
    getItem: () => null,
    setItem: (...args) => storage.push(args),
    removeItem: (...args) => storage.push(args),
  };
  const context = vm.createContext({
    console,
    URLSearchParams,
    AbortController,
    structuredClone,
    location,
    setTimeout: (fn) => {
      const id = ++timerId;
      timers.set(id, fn);
      return id;
    },
    clearTimeout: (id) => timers.delete(id),
    setInterval: () => 0,
    clearInterval() {},
    localStorage,
    sessionStorage: localStorage,
    document: {
      querySelector: node,
      querySelectorAll: (selector) => (selector === '[data-palette-index]' ? resultNodes : []),
      body: { classList: { toggle() {} } },
    },
    window: { scrollTo() {}, Eclipse: { destroy() {} }, matchMedia: () => ({ matches: false }) },
    history: { replaceState() {} },
  });
  const { application: app } = await loadApplication(context, { attach: false });
  app.actions.modal = (_title, body) => {
    node('#modal').open = true;
    node('#modal-body').innerHTML = body;
  };
  app.actions.closeModal = () => {
    node('#modal').open = false;
  };
  app.actions.showImport = async (id) => imports.push(id);
  app.actions.api = (url, options) =>
    new Promise((resolve, reject) => requests.push({ url, options, resolve, reject }));
  const settle = async () => {
    await Promise.resolve();
    await Promise.resolve();
  };
  const flushTimers = async () => {
    const pending = [...timers.values()];
    timers.clear();
    for (const fn of pending) fn();
    await settle();
  };
  const result = (kind, title, id = 'entity-1') => ({
    groups: [
      {
        kind,
        label: 'Saved results',
        items: [
          {
            id,
            kind,
            title,
            detail: 'Literal <detail>',
            href: kind === 'import' ? '' : '#entity/' + id,
          },
        ],
      },
    ],
  });
  const type = (query) => {
    node('#command-query').value = query;
    app.actions.commandPaletteInput({ target: node('#command-query') });
  };
  const key = (value) => {
    let prevented = false;
    const handled = app.actions.commandPaletteKeydown({
      key: value,
      target: node('#command-query'),
      preventDefault() {
        prevented = true;
      },
    });
    assert(handled && prevented, 'Palette owns keyboard selection');
  };

  app.actions.openCommandPalette();
  assert(node('#modal').classList.contains('command-dialog'));
  assert.match(node('#modal-body').innerHTML, /role="combobox"/);
  requests.at(-1).resolve(result('entity', '<img src=x onerror=alert(1)>'));
  await settle();
  assert.match(node('#command-results').innerHTML, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert(!node('#command-results').innerHTML.includes('<img src=x'));
  key('End');
  assert.equal(node('#command-query').getAttribute('aria-activedescendant'), 'command-result-10');
  key('ArrowDown');
  assert.equal(node('#command-query').getAttribute('aria-activedescendant'), 'command-result-0');
  key('ArrowUp');
  assert.equal(node('#command-query').getAttribute('aria-activedescendant'), 'command-result-10');
  key('Home');
  assert.equal(node('#command-query').getAttribute('aria-activedescendant'), 'command-result-0');
  key('End');
  key('Enter');
  assert.equal(location.hash, 'entity/entity-1');
  assert.equal(node('#modal').open, false);

  // A query changed during debounce must never activate the previous record.
  app.actions.openCommandPalette();
  type('alpha');
  await flushTimers();
  assert(requests.at(-2).options.signal.aborted);
  requests.at(-1).resolve(result('entity', 'Alpha old record', 'alpha'));
  await settle();
  assert.match(node('#command-results').innerHTML, /Alpha old record/);
  type('beta-private');
  const before = location.hash;
  key('Enter');
  assert.equal(location.hash, before, 'Enter during debounce cannot open a stale record');
  assert.equal(node('#modal').open, true);
  await flushTimers();
  const beta = requests.at(-1);
  type('gamma-private');
  await flushTimers();
  const gamma = requests.at(-1);
  assert(beta.options.signal.aborted);
  gamma.resolve(result('entity', 'Gamma new record', 'gamma'));
  await settle();
  beta.resolve(result('entity', 'Beta stale record', 'beta'));
  await settle();
  assert.match(node('#command-results').innerHTML, /Gamma new record/);
  assert(!node('#command-results').innerHTML.includes('Beta stale record'));
  key('Enter');
  assert.equal(location.hash, 'entity/gamma');

  app.actions.openCommandPalette();
  const initial = requests.at(-1),
    count = requests.length;
  type('> settings');
  await flushTimers();
  assert(initial.options.signal.aborted);
  assert.equal(requests.length, count, 'Command-only queries do not search record APIs');
  key('Enter');
  assert.equal(location.hash, 'settings');
  app.actions.openCommandPalette();
  type('entities');
  await flushTimers();
  requests.at(-1).reject(new Error('Synthetic unavailable'));
  await settle();
  assert.match(node('#command-status').textContent, /Records unavailable/);
  key('Enter');
  assert.equal(location.hash, 'entities', 'Navigation remains usable when search fails');

  app.actions.openCommandPalette();
  type('source.csv');
  await flushTimers();
  requests.at(-1).resolve(result('import', 'Source file', 'import-1'));
  await settle();
  key('Enter');
  assert.deepEqual(imports, ['import-1']);

  app.actions.openCommandPalette();
  const pending = requests.at(-1);
  type('teardown-private-query');
  app.destroy();
  const html = node('#command-results').innerHTML;
  assert(pending.options.signal.aborted);
  assert.equal(timers.size, 0, 'App teardown clears search debounce');
  assert(!node('#modal').classList.contains('command-dialog'));
  pending.resolve(result('entity', 'After teardown', 'late'));
  await settle();
  assert.equal(
    node('#command-results').innerHTML,
    html,
    'Late request cannot repopulate disposed UI',
  );
  assert.deepEqual(storage, [], 'Search queries and records are never saved in browser storage');
  console.log(
    'Chaos command palette: keyboard wrap/open, literal output, stale Enter guard, abort+races, command-only mode, import details, failure fallback, teardown and no browser persistence passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
