/** Intake renders and manages uploads without the Workspace installer. */
const assert = require('node:assert/strict');
const test = require('node:test');

test('Accretion owns intake status and rejects duplicate dropzone registration', async () => {
  const { install } = await import('../static/intake.js');
  const { createHandlers } = await import('../static/intake_events.js');
  const listeners = new Map(),
    classes = new Set(),
    uploads = [];
  const dropzone = {
    classList: { add: (value) => classes.add(value), remove: (value) => classes.delete(value) },
    addEventListener(type, listener) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(listener);
    },
    removeEventListener(type, listener) {
      listeners.get(type)?.delete(listener);
    },
  };
  const ctx = {
    state: { navigation: { boot: { settings: {} } } },
    actions: {
      $: (selector) => (selector === '#dropzone' ? dropzone : null),
      esc: String,
      num: (value) => String(value || 0),
      icon: () => '',
      statusBadge: String,
    },
  };
  const api = install(ctx);
  assert.equal(ctx.actions.dashboard, undefined);
  assert.equal(ctx.actions.leadTable, undefined);
  const html = api.accretionIntakeMarkup({
    catalog: { state: 'missing' },
    current: { name: 'Synthetic.csv', status: 'done', progress: { phase: 'complete' }, stats: {} },
  });
  assert.match(html, /data-stage="filter"/);
  assert.match(html, /data-stage="qualify"/);
  assert.match(html, /CVE catalog not downloaded/);
  ctx.actions.upload = (files) => uploads.push(files);
  api.wireDropzone();
  api.wireDropzone();
  assert.equal(
    [...listeners.values()].reduce((sum, set) => sum + set.size, 0),
    3,
  );
  const files = [{ name: 'Synthetic.csv' }];
  for (const handler of listeners.get('drop'))
    handler({ preventDefault() {}, dataTransfer: { files } });
  assert.deepEqual(uploads, [files]);
  classes.add('drag');
  const events = createHandlers(ctx);
  events.dispose();
  events.dispose();
  assert.equal(
    [...listeners.values()].reduce((sum, set) => sum + set.size, 0),
    0,
  );
  assert.equal(classes.has('drag'), false);
  api.wireDropzone();
  assert.equal(listeners.get('drop').size, 1);
  events.dispose();
});
