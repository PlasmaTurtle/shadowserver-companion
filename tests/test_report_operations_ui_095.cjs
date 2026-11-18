/** Status polling is read-only, cancellation is explicit, and history is escaped. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
(async () => {
  let nextTimer = 0;
  const timers = new Map();
  const context = vm.createContext({
    console,
    setTimeout: (fn) => {
      const id = ++nextTimer;
      timers.set(id, fn);
      return id;
    },
    clearTimeout: (id) => timers.delete(id),
  });
  const mod = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../static/modules/report_operations.js'), 'utf8'),
    { context },
  );
  await mod.link(() => {
    throw Error('Unexpected import');
  });
  await mod.evaluate();
  let nodes = {},
    latest,
    resolveWork;
  const calls = [];
  let row = {
    id: 'server-operation',
    operation: 'preview',
    state: 'running',
    phase: 'Rendering PDF',
    elapsed_seconds: 2,
    cancellable: true,
  };
  const node = () => ({
    disabled: true,
    listeners: {},
    addEventListener(name, fn) {
      this.listeners[name] = fn;
    },
  });
  const ctx = {
    state: { editor: { currentLead: { case_id: 'case' } } },
    actions: {
      $: (selector) => nodes[selector],
      esc: (value) =>
        String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
      modal: (title, html) => {
        latest = { title, html };
        nodes = {};
        const id = html.match(/data-operation="(\d+)"/);
        if (id) nodes['#report-operation-status'] = { dataset: { operation: id[1] } };
        for (const name of ['cancel', 'history'])
          if (html.includes(`id="report-operation-${name}"`))
            nodes[`#report-operation-${name}`] = node();
      },
      closeModal: () => {
        nodes = {};
      },
      api: async (url, options) => {
        calls.push({ url, options });
        return url.endsWith('/cancel') ? { ...row, state: 'cancelling' } : { operations: [row] };
      },
    },
  };
  mod.namespace.install(ctx);
  const work = ctx.actions.reportOperation(
    'Preview',
    () =>
      new Promise((resolve) => {
        resolveWork = resolve;
      }),
  );
  assert(nodes['#report-operation-cancel'].disabled);
  async function tick() {
    const [id, fn] = timers.entries().next().value;
    timers.delete(id);
    await fn();
  }
  await tick();
  assert.equal(nodes['#report-operation-status'].textContent, 'Rendering PDF · 2 seconds');
  assert.equal(nodes['#report-operation-cancel'].disabled, false);
  await nodes['#report-operation-cancel'].listeners.click();
  assert.equal(calls.filter((call) => call.options.method === 'POST').length, 1);
  assert.equal(calls.at(-1).url, '/api/report-operations/server-operation/cancel');
  row = { ...row, state: 'committing', phase: 'Saving the reviewed revision', cancellable: false };
  await tick();
  assert.equal(nodes['#report-operation-cancel'].disabled, true);
  resolveWork('done');
  assert.equal(await work, 'done');
  assert.equal(timers.size, 0, 'Completed work leaves no polling timer');
  row = { ...row, state: 'interrupted', started_at: '2026-11-08', error: '<unsafe history>' };
  await ctx.actions.showReportActivity();
  assert.match(latest.html, /interrupted/);
  assert.match(latest.html, /&lt;unsafe history&gt;/);
  assert(!latest.html.includes('<unsafe history>'));
  assert.match(latest.html, /never automatically retried/);
  console.log(
    'Report status, explicit cancellation, publication boundary and recovered history UI passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
