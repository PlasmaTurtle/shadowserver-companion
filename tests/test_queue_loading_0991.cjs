/** Opening feedback, stale navigation, and one-click attribution decisions. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');
(async () => {
  const nodes = new Map(),
    classes = new Set();
  const node = (selector) => {
    if (!nodes.has(selector))
      nodes.set(selector, {
        innerHTML: '',
        textContent: '',
        dataset: {},
        open: false,
        setAttribute() {},
        focus() {},
        classList: { toggle() {} },
      });
    return nodes.get(selector);
  };
  const location = { hash: '#eclipse' };
  const mounts = [];
  const context = vm.createContext({
    console,
    URLSearchParams,
    structuredClone,
    location,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    document: {
      querySelector: node,
      querySelectorAll: () => [],
      body: {
        dataset: {},
        classList: {
          toggle(name, on) {
            on ? classes.add(name) : classes.delete(name);
          },
        },
      },
    },
    window: {
      scrollY: 0,
      scrollTo() {},
      matchMedia: () => ({ matches: false }),
      Eclipse: {
        destroy() {},
        loading: () => '<section>Loading Observatory</section>',
        render: () => '<section>Loaded field</section>',
        mount(container, data) {
          mounts.push({ container, data });
        },
      },
    },
    history: {
      replaceState(_s, _t, url) {
        location.hash = url;
      },
    },
    localStorage: {
      getItem() {
        return null;
      },
      setItem() {},
    },
    confirm: () => true,
  });
  const { application: app } = await loadApplication(context, { attach: false });
  app.actions.api = async () => {
    throw Error('The Observatory controller owns its scoped request, not the router');
  };
  app.actions.refreshNavigationCounts = async () => {};
  app.actions.dashboard = async () => '<h1>Workspace</h1>';
  const opening = app.actions.route();
  assert.match(node('#main').innerHTML, /Loaded field/);
  assert.equal(node('#main').inert, false, 'Navigation stays usable during loading');
  await opening;
  assert.equal(mounts.length, 1, 'Router mounts the frame without waiting for data');
  assert.equal(mounts[0].data.observations.length, 0, 'No duplicate initial snapshot retrieval');
  location.hash = '#workspace';
  await app.actions.route();
  assert.match(node('#main').innerHTML, /Workspace/);
  assert(!classes.has('observatory-loading'));
  location.hash = '#eclipse';
  context.window.Eclipse.render = () => {
    throw Error('Temporary rendering failure');
  };
  await app.actions.route();
  assert.match(node('#main').innerHTML, /Try again/);
  assert.equal(node('#main').inert, false);
  assert(!classes.has('observatory-loading'));
  context.window.Eclipse.render = () => '<section>Loaded field</section>';
  await app.actions.route(true);
  assert.match(node('#main').innerHTML, /Loaded field/);
  // The sorted displayed match must retain its original evidence index.
  const match = (value, words) => ({
    source_name: 'ARIN',
    ip: '8.8.8.8',
    match: { value, field_type: 'organization_name' },
    details: { matched_words: words },
  });
  app.actions.api = async () => [
    {
      id: 'g1',
      domain: 'example.com',
      observations: 1,
      assets: 1,
      attribution_result_id: 'a'.repeat(32),
      matches: [
        match('Example', ['example']),
        match('Example Medical Center', ['example', 'medical', 'center']),
      ],
    },
  ];
  const html = await app.actions.reviewsPage();
  assert.match(html, /data-evidence-index="1"/);
  assert.match(html, /data-attribution-decision="accept"/);
  assert.match(html, /data-attribution-decision="dismiss"/);
  const mod = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../static/modules/queues_events.js'), 'utf8'),
    { context },
  );
  await mod.link(() => {
    throw Error('Unexpected dependency');
  });
  await mod.evaluate();
  const handler = mod.namespace
    .createHandlers(app)
    .click.find((h) => h.matches({ dataset: { attributionDecision: 'accept' } }));
  let removed = false,
    sent,
    fail = false,
    routed = 0;
  const controls = [{ disabled: false }, { disabled: false }, { disabled: false }];
  const row = {
    dataset: {},
    querySelectorAll: () => controls,
    remove() {
      removed = true;
    },
  };
  const button = controls[0];
  button.dataset = {
    attributionDecision: 'accept',
    attributionGroup: 'g1',
    result: 'a'.repeat(32),
    evidenceIndex: '1',
  };
  button.closest = () => row;
  node('[data-review-total]').textContent = '12';
  app.actions.busy = async (_el, fn) => await fn();
  app.actions.route = async () => {
    routed++;
  };
  app.actions.api = async (url, request) => {
    sent = [url, request];
    assert(controls.every((b) => b.disabled));
    if (fail) throw Error('Stale result');
  };
  await handler.run(button);
  assert.equal(sent[1].body.evidence_index, 1);
  assert.equal(sent[1].body.result_id, 'a'.repeat(32));
  assert(removed);
  assert.equal(node('[data-review-total]').textContent, '11');
  assert.equal(routed, 0);
  assert(controls.every((b) => !b.disabled));
  fail = true;
  removed = false;
  await assert.rejects(handler.run(button), /Stale result/);
  assert(!removed);
  assert.equal(node('[data-review-total]').textContent, '11');
  assert(controls.every((b) => !b.disabled));
  console.log(
    'Observatory immediate shell, route retry, displayed evidence and quick-review checks passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
