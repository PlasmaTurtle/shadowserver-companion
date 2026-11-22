/** Field depth follows meaningful chronology, independently of density and priority. */
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');

(async () => {
  const { graphLayout } = await import(
    pathToFileURL(path.resolve(__dirname, '../static/eclipse_model.js'))
  );
  const graph = {
    recency_range: { newest: '2026-11-13T00:00:00Z', oldest: '2026-10-01T00:00:00Z' },
    nodes: [
      {
        id: 'old',
        type: 'entity',
        fresh_at: '2026-10-01T00:00:00Z',
        last_seen: '2026-11-13',
        observation_count: 90000,
        asset_count: 2000,
        temperature: 'blazing',
      },
      {
        id: 'new',
        type: 'entity',
        fresh_at: '2026-11-13T00:00:00Z',
        last_seen: '2026-11-13',
        observation_count: 1,
        asset_count: 1,
        temperature: 'cool',
      },
      { id: 'middle', type: 'entity', fresh_at: '2026-11-01T00:00:00Z', last_seen: '2026-11-12' },
      { id: 'undated', type: 'entity', last_seen: 'not a date', observation_count: 99999 },
      { id: 'endpoint', type: 'asset', last_seen: '2026-11-12' },
    ],
    edges: [{ source: 'new', target: 'endpoint' }],
  };
  const before = structuredClone(graph);
  const layout = graphLayout(graph, 'organization');
  assert.deepEqual(
    layout.hubs.map((node) => node.id),
    ['new', 'middle', 'old', 'undated'],
  );
  assert.equal(layout.hubs[0].depth, 1);
  assert.equal(layout.hubs[2].depth, 0);
  assert.equal(layout.hubs[3].depth, 0);
  assert(layout.hubs[1].depth > layout.hubs[2].depth);
  assert.equal(layout.hubs[3].recency_at, '');
  assert.equal(layout.hubs[0].x, 600);
  assert.equal(layout.hubs[0].y, 380);
  assert(layout.hubs[2].revealRank > layout.hubs[0].revealRank);
  assert.equal(new Set(layout.nodes.map((node) => node.revealRank)).size, graph.nodes.length);
  assert.deepEqual(graph, before, 'Layout never mutates source facts');

  const changedCounts = graphLayout(
    {
      ...graph,
      nodes: graph.nodes.map((node) => ({
        ...node,
        observation_count: 12345,
        density_count: 999999,
        temperature: 'hot',
      })),
    },
    'organization',
  );
  assert.deepEqual(
    changedCounts.nodes.map(({ id, x, y, depth, r, revealRank }) => ({
      id,
      x,
      y,
      depth,
      r,
      revealRank,
    })),
    layout.nodes.map(({ id, x, y, depth, r, revealRank }) => ({ id, x, y, depth, r, revealRank })),
    'Repeat volume and outreach priority cannot move bodies, alter depth, enlarge cores or change discovery order',
  );
  const nextPage = graphLayout(
    { ...graph, nodes: graph.nodes.filter((node) => node.id === 'middle'), edges: [] },
    'organization',
  );
  assert.equal(
    nextPage.nodes[0].depth,
    layout.hubs[1].depth,
    'Page boundaries do not redefine age depth',
  );

  const tied = graphLayout(
    {
      nodes: [
        { id: 'z', type: 'entity', fresh_at: '2026-11-01T00:00:00Z', last_seen: '2026-11-10' },
        { id: 'b', type: 'entity', fresh_at: '2026-11-01T00:00:00Z', last_seen: '2026-11-13' },
        { id: 'a', type: 'entity', fresh_at: '2026-11-01T00:00:00Z', last_seen: '2026-11-01' },
      ],
      edges: [],
    },
    'organization',
  );
  assert.deepEqual(
    tied.hubs.map((node) => node.id),
    ['a', 'b', 'z'],
  );
  const repeated = graphLayout(
    {
      nodes: tied.nodes.map((node, i) => ({
        ...node,
        last_seen: `2026-11-${28 - i}`,
        observation_count: 1000000,
      })),
      edges: [],
    },
    'organization',
  );
  const positions = (model) =>
    model.nodes.map(({ id, x, y, depth, revealRank }) => ({ id, x, y, depth, revealRank }));
  assert.deepEqual(
    positions(repeated),
    positions(tied),
    'Unchanged repeat sightings do not reshuffle discovery peers',
  );

  const unresolved = graphLayout(
    {
      nodes: [
        {
          id: 'unknown-old',
          type: 'asset',
          field_object: true,
          field_rank: 2,
          fresh_at: '2026-10-01',
        },
        {
          id: 'unknown-new',
          type: 'asset',
          field_object: true,
          field_rank: 1,
          fresh_at: '2026-11-01',
        },
      ],
      edges: [],
    },
    'organization',
  );
  assert.equal(unresolved.hubCount, 2, 'Unresolved pageable endpoints are main bodies');
  assert.deepEqual(
    unresolved.hubs.map((node) => node.id),
    ['unknown-new', 'unknown-old'],
  );
  assert.equal(unresolved.hubs[0].x, 600);
  assert.equal(unresolved.hubs[0].y, 380);
  assert.equal(unresolved.hubs[0].depth, 1);
  assert.equal(unresolved.hubs[1].depth, 0);

  const breadthGraph = {
    nodes: [
      {
        id: 'compact',
        type: 'entity',
        fresh_at: '2026-11-01',
        total_assets: 2,
        observation_count: 1000000,
      },
      {
        id: 'broad',
        type: 'entity',
        fresh_at: '2026-11-01',
        total_assets: 500,
        observation_count: 500,
      },
      ...['compact-a', 'compact-b', 'broad-a', 'broad-b'].map((id) => ({ id, type: 'asset' })),
    ],
    edges: ['compact', 'broad'].flatMap((id) =>
      ['a', 'b'].map((suffix) => ({ source: id, target: `${id}-${suffix}` })),
    ),
  };
  const breadthLayout = graphLayout(breadthGraph, 'organization');
  const compact = breadthLayout.hubs.find((node) => node.id === 'compact');
  const broad = breadthLayout.hubs.find((node) => node.id === 'broad');
  assert(
    broad.footprintScale > compact.footprintScale,
    'Distinct endpoint breadth expands sampled satellite orbits',
  );
  assert(
    broad.footprintRadius > compact.footprintRadius,
    'Repeated sightings of two endpoints stay compact',
  );
  assert(broad.footprintScale <= 1.65 && compact.footprintScale >= 1);
  assert.equal(
    breadthLayout.nodes.length,
    6,
    'Breadth never invents satellites for omitted endpoints',
  );
  const broader = graphLayout(
    {
      ...breadthGraph,
      nodes: breadthGraph.nodes.map((node) => ({ ...node, total_assets: 1000000 })),
    },
    'organization',
  );
  assert.deepEqual(
    broader.hubs.map(({ id, x, y }) => ({ id, x, y })),
    breadthLayout.hubs.map(({ id, x, y }) => ({ id, x, y })),
    'Bounded breadth changes preserve body centers',
  );
  assert(broader.hubs.every((node) => node.footprintScale === 1.65));
  const distance = Math.hypot(broad.x - compact.x, (broad.y - compact.y) / 0.72);
  assert(
    distance > broad.footprintRadius + compact.footprintRadius,
    'Reserved spacing separates constellation footprints',
  );

  const hubs = Array.from({ length: 100 }, (_, i) => ({ id: 'hub-' + i, type: 'entity' }));
  const assets = Array.from({ length: 200 }, (_, i) => ({ id: 'asset-' + i, type: 'asset' }));
  const edges = assets.flatMap((asset, i) =>
    Array.from({ length: 3 }, (_, j) => ({
      source: asset.id,
      target: hubs[(i + j) % hubs.length].id,
    })),
  );
  const large = graphLayout({ nodes: [...hubs, ...assets], edges }, 'organization');
  assert.equal(large.nodes.length, 300, 'All bounded server nodes remain visible');
  assert.equal(large.edges.length, 600, 'All bounded server edges remain reachable');
  assert(large.nodes.every((node) => Number.isFinite(node.x) && Number.isFinite(node.y)));
  assert(
    large.edges.every((edge) => large.nodes.includes(edge.from) && large.nodes.includes(edge.to)),
  );

  const focusGraph = {
    nodes: [hubs[0], ...assets.slice(0, 120)],
    edges: assets.slice(0, 120).map((asset) => ({ source: asset.id, target: hubs[0].id })),
  };
  const overview = graphLayout(focusGraph, 'organization');
  const focused = graphLayout(focusGraph, 'organization', { focused: true });
  assert.equal(overview.focused, false);
  assert.equal(
    focused.focused,
    true,
    'A fetched constellation explicitly carries its inspection level',
  );
  assert.equal(focused.nodes.length, 121);
  const radius = (model) =>
    Math.max(
      ...model.nodes
        .filter((node) => node.type === 'asset')
        .map((node) => Math.hypot(node.x - model.hubs[0].x, node.y - model.hubs[0].y)),
    );
  assert(
    radius(focused) > radius(overview) * 1.2,
    'Focused constellations spread retained assets beyond the breadth-scaled overview',
  );
  assert.equal(new Set(focused.nodes.map((node) => `${node.x}:${node.y}`)).size, 121);
  assert(
    focused.nodes.every(
      (node) =>
        node.x >= focused.bounds.minX &&
        node.x <= focused.bounds.maxX &&
        node.y >= focused.bounds.minY &&
        node.y <= focused.bounds.maxY,
    ),
  );
  console.log(
    'Chronological Field depth, stable density-independent geometry, full server pages and focused asset spread passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
