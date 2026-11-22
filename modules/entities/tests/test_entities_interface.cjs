/** Entity views and edit lifecycle do not require installing Leads or Workspace. */
const assert = require('node:assert/strict');
const test = require('node:test');

const escape = (value) =>
  String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('"', '&quot;');

test('Entities owns functional directory and dossier interfaces independently', async () => {
  const { install } = await import('../static/entities.js');
  const ctx = {
    state: {
      entities: {},
      contacts: { entityNames: new Map() },
      navigation: { renderId: 1, currentRoute: 'entities' },
    },
    actions: {
      esc: escape,
      num: String,
      icon: () => '',
      date: String,
      stamp: String,
      heading: (title) => `<h1>${title}</h1>`,
      empty: (title) => `<p>${title}</p>`,
      linkButton: () => '',
    },
  };
  const api = install(ctx);
  assert.equal(ctx.actions.pendingLeadPage, undefined);
  assert.equal(ctx.actions.dashboard, undefined);
  const entity = {
    id: 'one',
    company: 'Example <Inc>',
    domain: 'example.com',
    entity_profile: { contact_email: 'it@example.com' },
    entries: [{ hostname: 'mail.example.com', ip: '8.8.8.8', tag: 'CVE-2026-1234' }],
  };
  ctx.actions.api = async (url) => {
    assert.match(url, /^\/api\/entities\?/);
    return [entity];
  };
  const html = await api.entitiesPage(new URLSearchParams({ q: 'Example' }));
  assert.match(html, /Example &lt;Inc>/);
  assert.match(html, /it@example.com/);
  assert.match(html, /href="#entity\/one/);
  const model = api.entityDossierModel(entity);
  assert.equal(model.hostCount, 1);
  assert.equal(model.ipCount, 1);
  assert.equal(model.connectionCount, 1);
});

test('Entity teardown cancels scheduled lookups and rejects detached responses', async (t) => {
  const { createHandlers } = await import('../static/entities_events.js');
  const timers = new Map();
  let timerSequence = 0;
  const originalSet = global.setTimeout,
    originalClear = global.clearTimeout;
  global.setTimeout = (callback) => {
    timers.set(++timerSequence, callback);
    return timerSequence;
  };
  global.clearTimeout = (id) => timers.delete(id);
  t.after(() => {
    global.setTimeout = originalSet;
    global.clearTimeout = originalClear;
  });
  let calls = 0,
    resolveLookup;
  const options = { innerHTML: 'Current choices' };
  const ctx = {
    state: { entities: { dirty: false, changedForms: new Set() }, navigation: { renderId: 1 } },
    actions: {
      $: (selector) => (selector === '#entity-city-options' ? options : null),
      esc: escape,
      api: () => {
        calls++;
        return new Promise((resolve) => {
          resolveLookup = resolve;
        });
      },
    },
  };
  const form = {
    id: 'entity-details-form',
    isConnected: true,
    elements: { city: { value: 'City' }, state: { value: 'State' } },
  };
  const input = { target: { name: 'city', closest: () => form } };
  let handlers = createHandlers(ctx);
  handlers.input(input);
  assert.equal(timers.size, 1);
  handlers.dispose();
  handlers.dispose();
  assert.equal(timers.size, 0);
  assert.equal(calls, 0);

  handlers = createHandlers(ctx);
  handlers.input(input);
  const pending = [...timers.values()][0]();
  assert.equal(calls, 1);
  handlers.dispose();
  resolveLookup({ cities: [{ city: 'Stale choice', state: 'State' }] });
  await pending;
  assert.equal(options.innerHTML, 'Current choices');
  assert.equal(timers.size, 0);
});
