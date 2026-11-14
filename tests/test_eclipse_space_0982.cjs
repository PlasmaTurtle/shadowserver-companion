/** Screen-space detail preserves observed membership across zoom and selection. */
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');

(async () => {
  const s = await import(pathToFileURL(path.resolve(__dirname, '../static/eclipse_space.js')));
  const m = await import(pathToFileURL(path.resolve(__dirname, '../static/eclipse_model.js')));
  const locations = [
    {
      id: 'a',
      x: 0,
      y: 0,
      label: 'Charlotte',
      rows: [{ id: 'a1' }, { id: 'a2' }],
      approximate: true,
    },
    { id: 'b', x: 20, y: 0, label: 'Charlotte', rows: [{ id: 'b1' }] },
    { id: 'c', x: 400, y: 0, label: 'Raleigh', rows: [{ id: 'c1' }] },
  ];
  const before = JSON.stringify(locations);
  const near = s.clusterLocations(locations, { k: 1, x: 20, y: 30 });
  assert.equal(near.length, 2);
  assert.equal(near[0].location_count, 2);
  assert.equal(near[0].observation_count, 3);
  assert.equal(near[0].approximate, true);
  assert.equal(near[0].label, 'Charlotte');
  assert.deepEqual(
    near[0].members.map((n) => n.id),
    ['a', 'b'],
  );
  assert.deepEqual(
    near[0].rows.map((r) => r.id),
    ['a1', 'a2', 'b1'],
  );
  assert.equal(near[0].x, 0, 'A cluster stays at its actual representative location');
  assert.equal(near[0].sx, 20);
  assert.equal(JSON.stringify(locations), before, 'Clustering must not mutate source locations');
  assert.deepEqual(s.clusterLocations(locations, { k: 1, x: 20, y: 30 }), near);
  const far = s.clusterLocations(locations, { k: 4, x: 20, y: 30 });
  assert.equal(far.length, 3, 'Zoom reveals distinct reported locations');
  assert.deepEqual(far.flatMap((n) => n.rows.map((r) => r.id)).sort(), ['a1', 'a2', 'b1', 'c1']);
  assert(
    far.every((n) => !('edges' in n)),
    'Geographic proximity must not create relationships',
  );
  const mixed = s.clusterLocations(
    locations.map((n) => ({ ...n, x: 0 })),
    { k: 1, x: 0, y: 0 },
  );
  assert.equal(mixed[0].label, '3 reported locations');
  assert.equal(mixed[0].observation_count, 4);
  assert.deepEqual(s.clusterLocations([], { k: 1, x: 0, y: 0 }), []);

  const bulk = Array.from({ length: 12000 }, (_, index) => ({
    id: 'bulk-' + index,
    latitude: 10 + Math.floor((index % 2000) / 100) / 10,
    longitude: -100 + (index % 100) / 10,
  }));
  const atlas = m.atlasLayout(bulk);
  assert.equal(atlas.nodes.length, 1800);
  assert.equal(atlas.omittedLocations, 200);
  const zoomedOut = s.clusterLocations(atlas.nodes, { k: 0.1, x: 0, y: 0 });
  const zoomedIn = s.clusterLocations(atlas.nodes, { k: 10, x: 0, y: 0 });
  assert(zoomedOut.length < zoomedIn.length);
  assert(zoomedIn.length <= 1800, 'Zoom cannot exceed the bounded source map');
  const retainedIds = atlas.nodes.flatMap((n) => n.rows.map((r) => r.id)).sort();
  for (const clusters of [zoomedOut, zoomedIn]) {
    assert.equal(
      clusters.reduce((sum, n) => sum + n.location_count, 0),
      1800,
    );
    assert.equal(
      clusters.reduce((sum, n) => sum + n.observation_count, 0),
      10800,
    );
    assert.deepEqual(clusters.flatMap((n) => n.rows.map((r) => r.id)).sort(), retainedIds);
    assert(clusters.every((n) => [n.x, n.y, n.sx, n.sy].every(Number.isFinite)));
  }
  assert.equal(s.semanticLevel(0), 'overview');
  assert.equal(s.semanticLevel(1.34999), 'overview');
  assert.equal(s.semanticLevel(1.35), 'endpoints');
  assert.equal(s.semanticLevel(2.64999), 'endpoints');
  assert.equal(s.semanticLevel(2.65), 'sources');

  const canonical = {
    id: 'first',
    hostname: ' Example.TEST. ',
    ip: ' 1.1.1.1 ',
    protocol: 'tcp',
    port: '0443',
    product: ' TLS ',
    observed_day: '2026-01-01',
  };
  const repeated = {
    ...canonical,
    id: 'second',
    hostname: 'example.test',
    ip: '1.1.1.1',
    protocol: 'TCP',
    port: '443',
    product: 'tls',
    observed_day: '2026-01-03',
  };
  assert.equal(m.endpointKey(canonical), m.endpointKey(repeated));
  assert.equal(
    m.endpointKey({ ...canonical, product: '', service: ' TLS ' }),
    m.endpointKey(canonical),
  );
  for (const change of [
    { hostname: 'other.test' },
    { ip: '8.8.8.8' },
    { protocol: 'udp' },
    { port: '80' },
    { product: 'http' },
  ]) {
    assert.notEqual(m.endpointKey(canonical), m.endpointKey({ ...canonical, ...change }));
  }
  assert.equal(
    m.endpointKey({ ...canonical, ip: 'malformed', ip_valid: false }),
    m.endpointKey({ ...canonical, ip: '' }),
  );
  assert.notEqual(m.endpointKey({ id: 'anonymous-a' }), m.endpointKey({ id: 'anonymous-b' }));
  const unknown = { id: 'unknown', ip: 'not-an-ip', ip_valid: false };
  assert.notEqual(m.endpointKey(unknown), m.endpointKey({ ...unknown, id: 'another' }));

  const graph = {
    nodes: [
      { id: 'asset:a', type: 'asset', observation_ids: ['first'], observation_count: 2 },
      { id: 'asset:missing', type: 'asset', observation_ids: ['missing'] },
      {
        id: 'ip:hub',
        type: 'ip',
        observation_ids: ['first', 'second'],
        asset_count: 2,
        entity_count: 2,
        day_count: 2,
        observation_count: 2,
      },
      {
        id: 'service:single',
        type: 'service',
        observation_ids: ['other'],
        asset_count: 1,
        entity_count: 1,
        day_count: 1,
        observation_count: 1,
      },
    ],
    edges: [{ id: 'edge', source: 'asset:a', target: 'ip:hub' }],
  };
  const sourceModel = m.graphLayout(graph, 'ip');
  const edgeIds = sourceModel.edges.map((e) => e.id);
  m.attachSources(sourceModel, [
    canonical,
    repeated,
    { ...canonical, id: 'other', hostname: 'other.test' },
  ]);
  const asset = sourceModel.nodes.find((n) => n.id === 'asset:a');
  assert.deepEqual(
    asset.rows.map((r) => r.id),
    ['first', 'second'],
    'A bounded example ID expands to all matching retained endpoint observations',
  );
  assert.deepEqual(asset.days, ['2026-01-01', '2026-01-03']);
  assert.deepEqual(
    sourceModel.nodes.find((n) => n.id === 'asset:missing').rows,
    [],
    'Missing provenance must remain empty',
  );
  assert.deepEqual(
    sourceModel.edges.map((e) => e.id),
    edgeIds,
    'Source attachment cannot invent graph edges',
  );
  assert.deepEqual(
    s.membershipForObservation(sourceModel, 'second').map((n) => n.id),
    ['asset:a', 'ip:hub'],
  );
  assert.deepEqual(s.membershipForObservation(sourceModel, 'absent'), []);
  assert.deepEqual(s.sharedSupport(graph), [
    { id: 'ip:hub', shared: true, recurring: true, rows: 2, assets: 2, entities: 2, days: 2 },
    {
      id: 'service:single',
      shared: false,
      recurring: false,
      rows: 1,
      assets: 1,
      entities: 1,
      days: 1,
    },
  ]);
  assert.deepEqual(s.sharedSupport({}), []);

  const ordinary = Array.from({ length: 26 }, (_, i) => ({
    id: 'ordinary-' + i,
    ip: '192.0.2.' + (1 + Math.floor(i / 2)),
    observed_day: i % 2 ? '2026-02-02' : '2026-02-01',
  }));
  const selected = { id: 'selected', ip: '198.51.100.99', observed_day: '2026-02-03' };
  const timelineRows = [
    ...ordinary,
    selected,
    { id: 'undated', ip: '192.0.2.1', observed_day: '' },
  ];
  const initial = m.pulseLayout(timelineRows, 'ip');
  assert.equal(initial.lanes.length, 12);
  assert.equal(initial.omittedLanes, 2);
  assert(!initial.nodes.some((n) => n.rows.includes(selected)));
  const focused = m.pulseLayout(timelineRows, 'ip', selected);
  assert.equal(focused.lanes.length, 12);
  assert.equal(focused.omittedLanes, 2);
  assert.equal(focused.undated, 1);
  assert.equal(focused.lanes[0].key, selected.ip);
  assert(
    focused.nodes.some((n) => n.rows.includes(selected)),
    'Selected source remains reachable when its lane is outside the ordinary top twelve',
  );
  assert.deepEqual(
    focused.edges,
    [],
    'Repeated observations do not imply temporal relationship edges',
  );
  assert(
    focused.nodes.every((n) =>
      n.rows.every((row) => timelineRows.includes(row) && row.observed_day === n.day),
    ),
  );
  assert.equal(initial.nodes.filter((n) => n.rows.some((r) => r.id === 'undated')).length, 0);
  console.log(
    'Eclipse0982 zoom aggregation, exact source membership, 12k-row map bounds, semantic detail, normalized endpoints and selected timeline lanes passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
