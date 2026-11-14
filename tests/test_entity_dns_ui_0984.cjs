/** Root DNS is a separate, automatically loaded supplement and never rewrites entity edits. */
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
(async () => {
  const { install } = await import(pathToFileURL(path.resolve('static/modules/entity_leads.js')));
  const { createHandlers } = await import(
    pathToFileURL(path.resolve('static/modules/entity_leads_events.js'))
  );
  const region = { innerHTML: '' },
    calls = [];
  const esc = (v) =>
    String(v ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;');
  const source = {
    snapshot_id: 'saved-dns',
    body_sha256: 'abc123',
    retrieved_at: '2026-11-10T01:00:00Z',
    resolver: 'Google Public DNS',
  };
  const connections = {
    total_roots: 1,
    roots_remaining: 0,
    needs_lookup: false,
    running: false,
    roots: [
      {
        root_domain: 'navarac.com',
        reported_hostnames: ['mail.navarac.com'],
        lookup: {
          checked_at: '2026-11-10T01:01:00Z',
          answers: [
            { record_type: 'A', addresses: ['8.8.8.8'], cname_chain: ['edge.example.com'], source },
          ],
        },
      },
    ],
    job: { status: 'complete' },
  };
  const entity = {
    id: 'entity-one',
    domain: 'navarac.com',
    company: 'Navarac',
    hostnames: ['mail.navarac.com'],
    entries: [{ id: 'one', hostname: 'mail.navarac.com', ip: '1.1.1.1', version: '1.0' }],
    dns_connections: connections,
  };
  const ctx = {
    state: {
      entities: {
        current: structuredClone(entity),
        dirty: true,
        changedForms: new Set(['entity-details-form']),
        tab: 'overview',
      },
      navigation: { renderId: 4, returns: new Map() },
      editor: {},
    },
    actions: {
      esc,
      num: String,
      stamp: String,
      icon: () => '',
      date: String,
      statusBadge: String,
      $: (selector) => (selector === '[data-entity-dns]' ? region : null),
      api: async (url, options) => {
        calls.push([url, options]);
        return structuredClone(connections);
      },
    },
  };
  install(ctx);
  const before = JSON.stringify(entity);
  const model = ctx.actions.entityDossierModel(entity);
  assert.equal(model.entryCount, 1);
  assert.equal(model.ipCount, 1);
  assert.equal(model.connectionCount, 1);
  assert.deepEqual(
    model.edges.map(({ host, ip }) => [host, ip]),
    [['mail.navarac.com', '1.1.1.1']],
  );
  const markup = ctx.actions.entityConstellationMarkup(entity);
  assert(markup.includes('data-root-link') && markup.includes('data-dns-link'));
  assert(markup.includes('stroke-dasharray="5 5"'));
  assert(
    markup.includes('mail.navarac.com') &&
      markup.includes('navarac.com') &&
      markup.includes('8.8.8.8'),
  );
  assert(markup.includes('edge.example.com') && markup.includes('abc123'));
  assert(markup.includes('2026-11-10T01:00:00Z') && markup.includes('public recursive resolver'));
  assert(markup.includes('do not establish common ownership'));
  assert.equal(JSON.stringify(entity), before);
  const tainted = structuredClone(entity);
  tainted.dns_connections.roots[0].root_domain = '<script>bad</script>';
  tainted.dns_connections.roots[0].lookup.answers[0].source.source_url = 'javascript:alert(1)';
  const escaped = ctx.actions.entityDnsMarkup(tainted);
  assert(!escaped.includes('<script>') && !escaped.includes('href="javascript:'));
  assert(escaped.includes('&lt;script&gt;'));
  await ctx.actions.refreshEntityDns(false);
  assert.equal(calls[0][0], '/api/entities/entity-one/connections/dns');
  assert.deepEqual(calls[0][1], { method: 'POST', body: { refresh: false } });
  assert(region.innerHTML.includes('Root DNS'));
  assert(ctx.state.entities.dirty && ctx.state.entities.changedForms.has('entity-details-form'));
  const handlers = createHandlers(ctx);
  await handlers.actions['entity-dns-refresh']();
  assert.equal(calls.at(-1)[1].body.refresh, true);
  ctx.state.entities.current.dns_connections.disabled = true;
  const length = calls.length;
  await ctx.actions.refreshEntityDns();
  assert.equal(calls.length, length);
  assert(
    ctx.actions.entityDnsMarkup(ctx.state.entities.current).includes('Demonstration · offline'),
  );
  ctx.state.entities.current = structuredClone(entity);
  let resolve;
  ctx.actions.api = () =>
    new Promise((r) => {
      resolve = r;
    });
  const pending = ctx.actions.refreshEntityDns();
  ctx.state.navigation.renderId++;
  ctx.state.entities.current = { id: 'different-entity' };
  region.innerHTML = 'Other entity';
  resolve(connections);
  await pending;
  assert.equal(region.innerHTML, 'Other entity');
  assert(!ctx.state.entities.current.dns_connections);
  console.log(
    'Root DNS graph distinguishes observed and current relationships, escapes source data, preserves unsaved edits, refreshes once and rejects stale navigation responses.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
