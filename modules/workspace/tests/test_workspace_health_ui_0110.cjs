const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

(async () => {
  const { formatTimestamp } = await import('../../ui/static/format.js');
  const context = vm.createContext({ console, setTimeout });
  const module = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../static/workspace_health.js'), 'utf8'),
    { context },
  );
  await module.link(() => {
    throw Error('Unexpected import');
  });
  await module.evaluate();
  let panel = { innerHTML: '' };
  let modal = null;
  let calls = [];
  let result = {
    lookup_pointers: 2,
    estimated_payload_bytes: 20,
    cutoff: 1,
    token: 'a'.repeat(64),
    policy: 'Preserve evidence',
    disk_space_note: 'No physical reclamation yet',
  };
  const ctx = {
    actions: {
      stamp: formatTimestamp,
      esc: (text) => String(text).replaceAll('&', '&amp;').replaceAll('<', '&lt;'),
      $: () => panel,
      modal: (title, markup) => {
        modal = markup;
      },
      closeModal: () => {},
      toast: () => {},
      api: async (url, options) => {
        calls.push({ url, options });
        return result;
      },
    },
  };
  module.namespace.install(ctx);
  assert.match(ctx.actions.workspaceHealthPanel(false), /workspace_recovery/);
  assert.match(ctx.actions.workspaceHealthPanel(true), /check-workspace" disabled/);
  await ctx.actions.reviewWorkspaceCleanup();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options, undefined, 'Opening review is read-only');
  assert.match(modal, /pattern="CLEAN"/);
  assert.match(modal, /No files will be deleted/);
  const healthy = {
    checked_at: 'now',
    ok: true,
    stores: [
      {
        store: 'workspace',
        status: 'ok',
        schema: 20,
        supported_schema: 20,
        database_bytes: 100,
        wal_bytes: 50,
      },
    ],
    storage: { evidence: { bytes: 10, files: 1 } },
    free_disk_bytes: 100,
  };
  assert.match(
    ctx.actions.healthMarkup({ status: 'completed', result: healthy }),
    /Workspace checks passed/,
  );
  assert.match(ctx.actions.healthMarkup({ status: 'failed', message: '<script>' }), /&lt;script>/);
  assert.match(
    ctx.actions.healthMarkup({ status: 'running', phase: 'Hashing captures' }),
    /cancel-workspace-health/,
  );
  const incompatible = {
    ...healthy,
    ok: false,
    stores: [
      {
        ...healthy.stores[0],
        counts: {
          analytical_index: {
            available: true,
            healthy: false,
            differences: { analytical_observations: { schema_mismatch: 1 } },
          },
        },
      },
    ],
  };
  const incompatibilityMarkup = ctx.actions.healthMarkup({
    status: 'completed',
    result: incompatible,
  });
  assert.match(incompatibilityMarkup, /incompatible table layout/);
  assert.doesNotMatch(incompatibilityMarkup, /data-action="rebuild-workspace-index"/);
  let resolve;
  ctx.actions.api = () =>
    new Promise((done) => {
      resolve = done;
    });
  modal = null;
  const pending = ctx.actions.reviewWorkspaceCleanup();
  panel = { innerHTML: 'new route' };
  resolve(result);
  await pending;
  assert.equal(modal, null, 'Late cleanup review must not open after navigating away');
  console.log('Health status, safe cleanup review, escaping and stale response guards passed.');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
