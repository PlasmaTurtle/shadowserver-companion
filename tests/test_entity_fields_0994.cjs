/** Manual assets preserve entity edit boundaries; resolver disagreement stays explicit. */
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
(async () => {
  const { createHandlers } = await import(
    pathToFileURL(path.resolve('static/modules/entity_leads_events.js'))
  );
  const { install } = await import(pathToFileURL(path.resolve('static/modules/entity_leads.js')));
  const calls = [];
  const esc = (v) =>
    String(v ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('"', '&quot;');
  const entity = {
    id: 'entity-one',
    domain: 'example.com',
    entity_revision: 4,
    associated_assets: [{ hostname: 'example.org', association_basis: 'manual' }],
    hostnames: [{ name: 'example.com' }, { name: 'example.org' }],
    entries: [],
    dns_connections: {
      total_roots: 1,
      roots: [
        {
          root_domain: 'example.org',
          reported_hostnames: [],
          lookup: {
            comparison: { status: 'disagreement' },
            answers: [
              {
                record_type: 'A',
                addresses: ['8.8.8.8'],
                source: { resolver: 'Google Public DNS' },
              },
              { record_type: 'A', addresses: ['1.1.1.1'], source: { resolver: 'Cloudflare DNS' } },
            ],
          },
        },
      ],
    },
  };
  const ctx = {
    state: {
      entities: {
        current: entity,
        dirty: true,
        changedForms: new Set(['entity-asset-form']),
        tab: 'assets',
      },
      navigation: { renderId: 1, returns: new Map() },
      editor: {},
    },
    actions: {
      esc,
      num: String,
      date: String,
      stamp: String,
      icon: () => '',
      api: async (...args) => {
        calls.push(args);
        return entity;
      },
      route: async () => calls.push(['route']),
      toast: () => {},
      entityReviewField: () => '',
      field: () => '',
      activities: () => '',
      attributionCard: () => '',
    },
  };
  install(ctx);
  const canonical = {
    ...entity,
    entries: Array(20).fill({ tag: 'duplicate' }),
    awareness: {
      observations: 2,
      approved_observations: 1,
      dark_matter_observations: 1,
      findings: 1,
      hostname_count: 2,
      ips: 1,
    },
    awareness_findings: [
      {
        id: 'finding-one',
        condition: 'CVE-2026-10000',
        observation_count: 1,
        hostname: 'example.com',
        version: '2',
      },
    ],
    awareness_connections: [
      {
        host: 'example.com',
        ip: '8.8.8.8',
        count: 2,
        approved_count: 1,
        dark_matter_count: 1,
        entry_ids: ['canonical-observation'],
      },
    ],
  };
  const model = ctx.actions.entityDossierModel(canonical);
  assert.equal(model.entryCount, 2);
  assert.equal(model.findings.length, 1);
  assert.equal(model.findings[0].id, 'finding-one');
  assert.equal(model.darkMatterCount, 1);
  const markup = ctx.actions.independentEntityMarkup();
  assert(markup.includes('entity-asset-form') && markup.includes('example.org'));
  assert(markup.includes('Resolver answers differ') && markup.includes('Cloudflare DNS'));
  const { install: installAttribution } = await import(
    pathToFileURL(path.resolve('static/modules/attribution.js'))
  );
  ctx.actions.timeMarkup = String;
  installAttribution(ctx);
  const reused = ctx.actions.attributionCard({
    root_domain: 'example.com',
    supported: true,
    validated_at: '2026-11-01T00:00:00Z',
    retrieved_at: '2026-10-31T00:00:00Z',
    reuse: { fresh_lookup: false, recognized_at: '2026-11-13T00:00:00Z' },
  });
  assert(reused.includes('Historical association reused · no fresh lookup'));
  assert(reused.includes('2026-11-01T00:00:00Z') && reused.includes('2026-10-31T00:00:00Z'));
  const handler = createHandlers(ctx).forms['entity-asset-form'];
  ctx.state.entities.changedForms.add('entity-details-form');
  await assert.rejects(
    () =>
      handler(
        { id: 'entity-asset-form', dataset: { entity: entity.id } },
        { hostname: 'example.org' },
      ),
    /Save the other/,
  );
  assert.equal(calls.length, 0);
  ctx.state.entities.changedForms.delete('entity-details-form');
  await handler(
    { id: 'entity-asset-form', dataset: { entity: entity.id } },
    { hostname: 'example.org' },
  );
  assert.equal(calls[0][0], '/api/entities/entity-one/assets');
  assert.deepEqual(calls[0][1].body, { hostname: 'example.org', expected_revision: 4 });
  assert.equal(ctx.state.entities.dirty, false);
  console.log(
    'Manual asset linking respects unsaved edits and displays both DNS resolver answers.',
  );
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
