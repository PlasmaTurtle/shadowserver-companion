/** Reviewed lifecycle actions reject stale dialogs and preserve newer views. */
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
(async () => {
  const { createHandlers } = await import(
    pathToFileURL(path.resolve('modules/entities/static/entities_events.js'))
  );
  let revision = 0,
    html = '',
    closed = 0,
    routes = 0,
    resolve;
  const entity = { id: 'source', entity_revision: 3, company: 'Original business' };
  const ctx = {
    state: { entities: { current: entity, dirty: false }, navigation: { renderId: 1 } },
    actions: {
      currentModalRevision: () => revision,
      esc: (v) => String(v ?? '').replaceAll('<', '&lt;'),
      modal: (_title, value) => {
        html = value;
        revision++;
      },
      closeModal: () => {
        closed++;
        revision++;
      },
      route: async () => {
        routes++;
      },
      refreshNavigationCounts: async () => {},
      toast: () => {},
      api: () =>
        new Promise((r) => {
          resolve = r;
        }),
    },
  };
  const handlers = createHandlers(ctx);
  const plan = {
    entity_id: 'source',
    entity_revision: 3,
    review_token: 'a'.repeat(64),
    finding: { condition: 'CVE-2026-10000', hostname: 'mail.example.com' },
    restored_observations: 1,
    sources: [{ observed_at: '2026-11-01', ip: '8.8.8.8', sheet: 'CSV', row_number: 2 }],
  };
  let task = handlers.actions['reactivate-entity-finding']({ dataset: { finding: 'finding-one' } });
  ctx.state.entities.current = { id: 'other', entity_revision: 3 };
  resolve(plan);
  await task;
  assert.equal(html, '', 'A late review cannot replace another business view');
  ctx.state.entities.current = entity;
  task = handlers.actions['reactivate-entity-finding']({ dataset: { finding: 'finding-one' } });
  revision++;
  resolve(plan);
  await task;
  assert.equal(html, '', 'A late review cannot replace a newer modal');
  task = handlers.actions['reactivate-entity-finding']({ dataset: { finding: 'finding-one' } });
  resolve(plan);
  await task;
  assert(html.includes('retained approved') && html.includes('required'));
  let posted;
  ctx.actions.api = (url, opts) => {
    posted = { url, opts };
    return new Promise((r) => {
      resolve = r;
    });
  };
  const form = { dataset: { entity: 'source' }, isConnected: true };
  task = handlers.forms['entity-lifecycle-confirm-form'](form, { reason: 'Mistaken dismissal' });
  assert.equal(posted.opts.body.expected_revision, 3);
  assert.equal(posted.opts.body.review_token, plan.review_token);
  form.isConnected = false;
  revision++;
  resolve({});
  await task;
  assert.equal(closed, 0);
  assert.equal(routes, 0);
  await assert.rejects(
    () => handlers.forms['entity-lifecycle-confirm-form'](form, { reason: 'again' }),
    /no longer current/,
  );
  ctx.state.entities.dirty = true;
  await assert.rejects(
    () => handlers.actions['transfer-entity-asset']({ dataset: { hostname: 'example.com' } }),
    /Save entity changes/,
  );
  console.log(
    'Lifecycle reviews preserve exact revisions, reasons, and newer modal/navigation state.',
  );
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
