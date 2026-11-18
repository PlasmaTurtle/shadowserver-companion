/** Missing reference data is explicit; entity retrieval never restarts the page. */
const assert = require('node:assert/strict');
(async () => {
  const { install: queues } = await import('../static/modules/queues.js');
  const { install: entities } = await import('../static/modules/entity_leads.js');
  const escape = (v) =>
    String(v ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('"', '&quot;');
  let catalog = { state: 'missing' };
  const ctx = {
    state: {
      navigation: {
        renderId: 1,
        currentRoute: 'entities',
        boot: { workspace: '/work', settings: {} },
      },
      contacts: { entityNames: new Map() },
      entities: {},
    },
    actions: {
      esc: escape,
      num: (v) => String(v || 0),
      icon: () => '',
      heading: (v) => `<h1>${v}</h1>`,
      loadApiAcquisition: async () => {},
      apiAcquisitionMarkup: () => '<form>API reports</form>',
      api: async (url) =>
        url === '/api/intake/progress'
          ? {
              catalog,
              current: {
                name: 'Report',
                status: 'done',
                stats: {},
                progress: { phase: 'complete' },
                catalog_at_scoring: { state: 'missing' },
              },
            }
          : [],
    },
  };
  queues(ctx);
  for (const tab of ['files', 'api']) {
    const html = await ctx.actions.importsPage(new URLSearchParams({ tab }));
    assert.match(html, /CVE catalog not downloaded/);
    assert.match(html, /href="#library"/);
    assert.match(html, /data-stage="filter"/);
    assert.match(html, /data-stage="qualify"/);
    assert.match(html, /data-stage="urgency"/);
    assert.match(html, /data-stage="associate"/);
    assert.match(html, /Scored with limited local CVE coverage/);
  }
  catalog = { state: 'ready' };
  const ready = await ctx.actions.importsPage();
  assert.doesNotMatch(ready, /CVE catalog not downloaded/);
  assert.match(
    ready,
    /Scored with limited local CVE coverage/,
    'Downloading later must not relabel earlier scoring',
  );
  entities(ctx);
  const row = {
    id: 'entity1',
    company: 'Example <Inc>',
    domain: 'example.com',
    entity_profile: { address: '123 Main St', contact_email: 'it@example.com' },
  };
  ctx.actions.api = async () => [row];
  let html = await ctx.actions.entitiesPage();
  assert.match(html, /Example &lt;Inc>/);
  assert.match(html, /123 Main St/);
  assert.match(html, /it@example.com/);
  assert.match(html, />Find missing contacts</);
  assert.match(html, />Refresh contacts</);
  assert.doesNotMatch(html, /checkbox|data-contact-select|Find contacts for multiple/);
  global.document = { activeElement: null };
  const cell = { innerHTML: 'original', contains: () => false };
  ctx.actions.$ = () => cell;
  let release,
    calls = 0;
  ctx.actions.api = async () => {
    calls++;
    return await new Promise((resolve) => {
      release = resolve;
    });
  };
  const pending = ctx.actions.loadEntityContactOverviews();
  await ctx.actions.loadEntityContactOverviews();
  assert.equal(calls, 1, 'Only one retrieval generation runs');
  ctx.state.navigation.renderId++;
  release({ entity1: { email: 'new@example.com', status: 'found' } });
  await pending;
  assert.equal(cell.innerHTML, 'original', 'Late retrieval cannot overwrite another screen');
  ctx.actions.api = async (url) =>
    url.startsWith('/api/contact-discovery/overviews?')
      ? { entity1: { email: 'new@example.com', status: 'found' } }
      : {};
  await ctx.actions.loadEntityContactOverviews();
  assert.match(ctx.actions.directoryContactMarkup(row), /new@example.com/);
  assert.match(ctx.actions.entityGapsMarkup(row), /Details available/);
  const partial = { ...row, company: 'example.com', entity_profile: {} };
  ctx.state.entities.contactOverviews.set(row.id, { status: 'not_found' });
  assert.match(ctx.actions.entityGapsMarkup(partial), /Business name missing/);
  assert.match(ctx.actions.entityGapsMarkup(partial), /Address missing/);
  assert.match(ctx.actions.entityGapsMarkup(partial), /No email or phone/);
  delete global.document;
  console.log(
    'Catalog warnings, retained scoring limitations, contact-first directory, retrieval single-flight and stale response isolation passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
