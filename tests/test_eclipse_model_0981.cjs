/** Relationship layouts preserve real support; decoration never enters the model. */
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
(async () => {
  const m = await import(pathToFileURL(path.resolve(__dirname, '../static/eclipse_model.js')));
  const rows = [
    {
      id: 'a',
      hostname: 'alpha.test',
      ip: '8.8.8.8',
      ip_valid: true,
      entity_id: 'e1',
      entity_name: 'Alpha',
      protocol: 'tcp',
      port: '0443',
      product: 'TLS',
      tag: 'CVE-2021-44228;eol-tls',
      version: '1.0',
      observed_day: '2026-01-01',
      status: 'qualified',
      latitude: 0,
      longitude: 0,
    },
    {
      id: 'b',
      hostname: 'beta.test',
      ip: '8.8.8.8',
      entity_id: 'e2',
      entity_name: 'Beta',
      protocol: 'TCP',
      port: '443',
      product: 'TLS',
      tag: 'CVE-2021-44228',
      version: '2.0',
      observed_day: '2026-01-04',
      status: 'review',
      latitude: null,
      longitude: null,
    },
    {
      id: 'c',
      hostname: 'undated.test',
      ip: '1.1.1.1',
      tag: 'eol-tls',
      observed_day: '',
      status: 'pending',
      latitude: 35,
      longitude: -80,
    },
  ];
  assert.equal(
    m.filterRows(rows, { cutoff: '2026-01-01' }).length,
    2,
    'Undated rows remain included in cutoff counts',
  );
  assert.equal(m.filterRows(rows, { search: 'CVE-2021-44228' }).length, 2);
  assert.equal(m.filterRows(rows, { unplaced: true }).length, 1);
  assert.equal(m.point(rows[0]), true, 'Zero coordinates are valid');
  assert.equal(
    m.observationKeys(rows[0], 'service')[0].key,
    m.observationKeys(rows[1], 'service')[0].key,
    'Service identity normalizes protocol and numeric port',
  );
  assert.notEqual(
    m.observationKeys(rows[0], 'version')[0].key,
    m.observationKeys(rows[1], 'version')[0].key,
  );
  assert.deepEqual(
    m.timeline(rows).bins.map((b) => b.day),
    ['2026-01-01', '2026-01-04'],
  );
  const graph = {
    nodes: [
      { id: 'asset:a', type: 'asset', label: 'Alpha', observation_count: 2 },
      { id: 'asset:b', type: 'asset', label: 'Beta', observation_count: 1 },
      { id: 'ip:x', type: 'ip', label: '8.8.8.8', asset_count: 2 },
    ],
    edges: [
      { id: 'e1', source: 'asset:a', target: 'ip:x' },
      { id: 'e2', source: 'asset:b', target: 'ip:x' },
      { id: 'bad', source: 'absent', target: 'ip:x' },
    ],
  };
  const one = m.graphLayout(graph, 'ip'),
    two = m.graphLayout(graph, 'ip');
  assert.deepEqual(one.nodes, two.nodes, 'Layout is stable; no random drift');
  assert.equal(one.edges.length, 2, 'Only supplied edges with both endpoints are drawn');
  assert.equal(one.nodes.length, 3, 'Ambient stars cannot enter source graph counts');
  assert(
    !one.edges.some((e) => e.from.id === 'asset:a' && e.to.id === 'asset:b'),
    'Shared IP does not imply an ownership edge',
  );
  assert(one.nodes.every((n) => Number.isFinite(n.x) && Number.isFinite(n.y)));
  const atlas = m.atlasLayout(rows);
  assert.equal(atlas.nodes.length, 2);
  assert.equal(atlas.unplaced, 1);
  const polar = m.atlasLayout([{ id: 'pole', latitude: -90, longitude: 0 }]);
  assert(
    Number.isFinite(polar.nodes[0].y),
    'Polar coordinates cannot make the Mercator scene infinite',
  );
  assert.equal(polar.polarRows, 1);
  const many = Array.from({ length: 2200 }, (_, i) => ({
    id: 'r' + i,
    latitude: 30 + i / 10000,
    longitude: -80,
  }));
  const largeAtlas = m.atlasLayout(many);
  assert.equal(largeAtlas.nodes.length, 1800);
  assert.equal(
    largeAtlas.omittedLocations,
    400,
    'Bounded map marks omissions without changing source denominator',
  );
  const hist = m.histogramBins(
    Array.from({ length: 2000 }, (_, i) => ({ day: String(i), count: 2 })),
  );
  assert(hist.length <= 120);
  assert.equal(
    hist.reduce((sum, b) => sum + b.count, 0),
    4000,
  );
  const pulse = m.pulseLayout(rows, 'ip');
  assert.equal(
    pulse.nodes.reduce((sum, n) => sum + n.rows.length, 0),
    2,
  );
  assert.equal(pulse.undated, 1);
  assert(
    pulse.nodes.find((n) => n.day === '2026-01-04').x >
      pulse.nodes.find((n) => n.day === '2026-01-01').x,
  );
  const links = m.sourceLinks([{ entity_id: 'e/1', case_id: 'c1', lead_id: 'l1' }]);
  assert(links.some((l) => l.href === '#workspace/notifications/c1'));
  assert(links.some((l) => l.href === '#entity/e%2F1'));
  assert.equal(m.safeLocalURL('https://attacker.test/file', '/api/imports/'), '');
  assert.equal(m.esc('<img>'), '&lt;img&gt;');
  console.log(
    'Eclipse0981 deterministic bounded layouts, actual edge provenance, unplaced/undated preservation, contextual lenses, escaping and canonical routes passed.',
  );
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
