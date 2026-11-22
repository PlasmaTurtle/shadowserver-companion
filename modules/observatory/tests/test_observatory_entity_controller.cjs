/** Execute the production controller against entity geography, navigation and failure contracts. */
const assert = require('node:assert/strict');
const { createHarness } = require('./eclipse_controller_harness.cjs');

const observation = (n) => ({
  id: 'o' + n,
  observation_id: 'o' + n,
  finding_id: 'f' + n,
  finding_ids: ['f' + n],
  asset_id: 'a' + n,
  entity_id: 'e' + n,
  hostname: 'host' + n + '.example',
  observed_day: '2026-11-0' + n,
  admitted: true,
  latitude: 40,
  longitude: -100,
  source: { sheet: 'CSV', row: n + 1 },
});
function envelope() {
  const rows = [observation(1), observation(2)];
  const counts = { findings: 2, observations: 2000, assets: 4, entities: 3, unplaced: 22 };
  const timeline = {
    bins: [
      { day: '2026-11-01', count: 10 },
      { day: '2026-11-02', count: 20 },
    ],
    undated: 0,
  };
  const entities = [1, 2, 3].map((n) => ({
    id: 'entity-location:e' + n,
    type: 'entity-location',
    entity_id: 'e' + n,
    entity_ids: ['e' + n],
    entity_count: 1,
    scope: { entity_id: 'e' + n },
    label: 'Entity ' + n,
    city: n < 3 ? 'Raleigh' : '',
    region: 'NC',
    latitude: n < 3 ? 35.78 : null,
    longitude: n < 3 ? -78.64 : null,
    location_basis: 'entity_city_area',
    approximate: true,
    basis: 'Current saved entity profile city area, approximate and not an asset position.',
    asset_count: 2,
    finding_count: 1,
    observation_count: 1000,
    rows: n < 3 ? [rows[n - 1]] : [],
    workflow_summary: {
      findings_by_status: { qualified: 1 },
      cases_by_stage: { in_progress: 1 },
      case_count: 1,
    },
  }));
  return {
    revision: 'r1',
    snapshot: {
      jurisdiction: { states: ['TX'], label: 'Texas' },
      observations: rows,
      findings: rows.map((r) => ({ ...r, id: r.finding_id })),
      entities: entities.map((n) => ({ id: n.entity_id, name: n.label })),
      networks: [],
      counts,
      timeline,
    },
    intelligence: {
      counts,
      timeline,
      graph: { nodes: [], edges: [], limits: { total_nodes: 0 } },
      patterns: [],
      atlas: {
        unit: 'entities',
        nodes: entities.slice(0, 2),
        unplaced_entities_list: [{ ...entities[2], unplaced_reason: 'Saved city is missing.' }],
        total_entities: 3,
        mapped_entities: 2,
        unplaced_entities: 1,
        unplaced_count: 1,
        total_nodes: 2,
        omitted_nodes: 0,
        unresolved_asset_count: 4,
      },
      pulse: { lanes: [], days: [] },
    },
    records: {
      items: rows.map((r) => ({ ...r, id: r.finding_id })),
      total: 2,
      offset: 0,
      limit: 20,
    },
  };
}
const views = (h) => h.requests.filter((r) => r.url.startsWith('/api/eclipse/view?'));
const model = (h) => h.sceneCalls.filter((c) => c.name === 'set').at(-1).args[0];
const geo = (h) => h.requests.find((r) => r.url.startsWith('/modules/observatory/static/geo/'));
async function open(data = envelope(), saved = { defaultView: 'atlas' }) {
  const h = await createHarness({ envelope: data, saved });
  return h;
}

(async () => {
  const { clusterLocations } = await import('../static/eclipse_space.js');
  let h = await open();
  try {
    assert.equal(h.element('#ec-scene-title').textContent, 'Entity map');
    assert.equal(h.element('#ec-region').disabled, false);
    assert.match(h.element('#ec-region').title, /Texas/);
    assert.equal(h.element('#ec-fit').textContent, 'Fit entities');
    assert.match(h.element('#ec-map-caption').textContent, /Context: Texas/);
    assert.equal(geo(h).url, '/modules/observatory/static/geo/states.json');
    assert(
      h.sceneCalls.some((call) => call.name === 'jurisdiction' && call.args[0]?.states[0] === 'TX'),
    );
    assert.equal(h.element('#ec-scene-subtitle').textContent, '2 of 3 entities shown');
    assert.match(h.element('#ec-space-key').textContent, /Number = entities/);
    assert.equal(h.element('#ec-density-legend').hidden, true);
    assert.equal(
      h.element('#ec-unplaced-count').textContent,
      '1',
      'Entity absence, not 22 source-unplaced observations',
    );
    assert.equal(model(h).nodes.length, 2);
    assert(
      model(h).nodes.every((n) => n.latitude === 35.78),
      'Map uses DTO entity position, never source coordinates',
    );
    assert.equal(
      h.root.querySelectorAll('[data-ec-map-entity]').length,
      3,
      'Unplaced entities are in the directory',
    );
    h.click('[data-ec-map-entity="entity-location:e1"]');
    const panel = h.element('#ec-inspector-content').innerHTML;
    assert.match(panel, /ENTITY/);
    assert.match(panel, /href="#entity\/e1"/);
    assert.match(panel, /href="#entity\/e1\?tab=details"/);
    assert.match(panel, /Current workflow/);
    assert.match(panel, /in progress notifications/);
    assert.match(panel, /<details><summary>Supporting source evidence/);
    assert.equal(h.element('#ec-selection-kind').textContent, 'Entity');
    assert.match(
      h.element('#ec-selection-support').textContent,
      /1 entities · 2 assets · 1 findings/,
    );
    h.click('[data-ec-drill="assets"]');
    const params = new URL(views(h).at(-1).url, 'http://local').searchParams;
    assert.equal(params.get('entity_id'), 'e1');
    assert.equal(params.get('asset_id'), null);
    assert.equal(params.get('location_key'), null);
    views(h).at(-1).resolve(envelope());
    await h.settle();
    h.click('#ec-records-close');
    assert.equal(h.root.dataset.view, 'atlas', 'Contextual Records close honors Back to Atlas');
    assert.equal(h.element('#ec-selection-name').textContent, 'Entity 1');
  } finally {
    h.destroy();
  }

  h = await open();
  try {
    const before = views(h).length;
    h.click('#ec-unplaced');
    assert.equal(
      views(h).length,
      before,
      'Entity directory does not apply the source-unplaced filter',
    );
    assert.equal(h.element('#ec-unplaced').getAttribute('aria-pressed'), 'false');
    assert.equal(h.root.querySelectorAll('[data-ec-map-entity]').length, 1);
    h.click('[data-ec-map-entity="entity-location:e3"]');
    assert.match(h.element('#ec-inspector-content').innerHTML, /Saved city is missing/);
    assert.match(h.element('#ec-inspector-content').innerHTML, /#entity\/e3\?tab=details/);
    assert(
      !h.sceneCalls.some((c) => c.name === 'focus' && c.args[0] === 'entity-location:e3'),
      'Unplaced profile selection does not invent a camera position',
    );
  } finally {
    h.destroy();
  }

  h = await open();
  try {
    const members = model(h).nodes;
    h.hooks.select({
      id: 'cluster:e1:e2',
      type: 'cluster',
      entity_map: true,
      label: '2 entities',
      members,
      entity_ids: ['e1', 'e2'],
      entity_count: 2,
      asset_count: 4,
      finding_count: 2,
      rows: members.flatMap((n) => n.rows),
    });
    assert.match(h.element('#ec-inspector-content').innerHTML, /Choose an entity/);
    assert.equal(h.root.querySelectorAll('[data-ec-map-entity]').length, 2);
    assert.equal(
      h.element('#ec-drill-actions').innerHTML,
      '',
      'A multi-entity cluster must not infer an observation-city drill',
    );
    h.click('[data-ec-map-entity="entity-location:e2"]');
    h.click('#ec-refresh');
    const updated = envelope();
    updated.revision = 'r2';
    views(h).at(-1).resolve(updated);
    await h.settle();
    assert.equal(h.root.dataset.hasSelection, 'true');
    assert.equal(h.element('#ec-selection-name').textContent, 'Entity 2');
    assert.equal(h.root.dataset.revision, 'r2');
    h.click('#ec-list-toggle');
    h.click('#ec-records-close');
    assert.equal(h.root.dataset.view, 'atlas');
    assert.equal(h.element('#ec-selection-name').textContent, 'Entity 2');
    assert(h.sceneCalls.some((c) => c.name === 'restoreView'));
  } finally {
    h.destroy();
  }

  h = await open();
  try {
    const cluster = clusterLocations(model(h).nodes, h.scene.captureView().camera, 56)[0];
    assert.equal(cluster.members.length, 2);
    h.hooks.select(cluster);
    const changed = envelope();
    changed.intelligence.atlas.nodes[0].asset_count = 7;
    changed.intelligence.atlas.nodes[0].finding_count = 5;
    h.click('#ec-refresh');
    views(h).at(-1).resolve(changed);
    await h.settle();
    assert.equal(h.root.dataset.hasSelection, 'true');
    assert.match(
      h.element('#ec-selection-support').textContent,
      /2 entities · 9 assets · 6 findings/,
    );
    const moved = envelope();
    moved.intelligence.atlas.nodes[1].latitude = 34;
    moved.intelligence.atlas.nodes[1].longitude = -81;
    h.click('#ec-refresh');
    views(h).at(-1).resolve(moved);
    await h.settle();
    assert.equal(
      h.root.dataset.hasSelection,
      'false',
      'A moved member must not retain a stale geographic cluster',
    );
  } finally {
    h.destroy();
  }

  const zeroFindings = envelope();
  zeroFindings.records = { items: [], total: 0, limit: 20, offset: 0 };
  zeroFindings.snapshot.counts.findings = 0;
  h = await open(zeroFindings);
  try {
    assert.equal(
      h.element('#ec-map-empty').hidden,
      true,
      'Mapped entities remain visible with no recognized finding',
    );
  } finally {
    h.destroy();
  }
  const unplacedOnly = envelope();
  unplacedOnly.intelligence.atlas.nodes = [];
  unplacedOnly.intelligence.atlas.mapped_entities = 0;
  h = await open(unplacedOnly);
  try {
    assert.equal(h.element('#ec-map-empty').hidden, false);
    assert.match(h.element('#ec-map-empty').innerHTML, /Entities need a usable city area/);
    h.click('[data-ec-action="unplaced-entities"]');
    assert.match(h.element('#ec-inspector-content').innerHTML, /Entity 3/);
  } finally {
    h.destroy();
  }

  h = await open(envelope(), { defaultView: 'field' });
  try {
    geo(h).reject(new Error('Geography unavailable'));
    await h.settle();
    h.click('[data-ec-view="atlas"]');
    assert.match(h.element('#ec-map-caption').textContent, /Local geography could not load/);
    h.click('[data-ec-view="atlas"]');
    assert.match(h.element('#ec-map-caption').textContent, /Local geography could not load/);
    assert.equal(h.element('#ec-time').getAttribute('aria-valuetext'), 'All dates');
    assert.match(h.element('#ec-canvas').getAttribute('aria-label'), /Brackets select/);
  } finally {
    h.destroy();
  }
  h = await open(envelope(), { defaultView: 'atlas', cutoff: '2026-11-01' });
  try {
    assert.equal(h.element('#ec-time').getAttribute('aria-valuetext'), 'Through 2026-11-01');
    assert.match(h.element('#ec-map-caption').textContent, /saved profiles are current/);
  } finally {
    h.destroy();
  }

  const fallback = envelope();
  Object.assign(fallback.intelligence.atlas.nodes[0], {
    location_basis: 'reported_asset_city_area',
    location_temporal_basis: 'latest_selected_report',
    basis: 'Latest associated reported city area because no complete entity location is saved.',
    location_hostname: 'latest.example',
    location_ip: '8.8.8.8',
    location_observed_at: '2026-11-01T10:00:00Z',
    location_observation_id: 'fallback-source',
    location_source_locator: {
      id: 'fallback-source',
      observation_id: 'fallback-source',
      hostname: 'latest.example',
      ip: '8.8.8.8',
      observed_at: '2026-11-01T10:00:00Z',
      detail_url: '/api/eclipse/observations/fallback-source?source_key=exact',
      source: { workbook: 'latest.csv', sheet: 'CSV', row: 7 },
    },
  });
  h = await open(fallback, { defaultView: 'atlas', cutoff: '2026-11-01' });
  try {
    const node = model(h).nodes[0];
    assert.equal(
      node.id,
      'entity-location:e1',
      'A fallback is still the same entity, not an asset marker',
    );
    h.hooks.hover(node, 20, 20);
    assert.match(h.element('#ec-tooltip').innerHTML, /Latest associated reported city area/);
    h.click('[data-ec-map-entity="entity-location:e1"]');
    const panel = h.element('#ec-inspector-content').innerHTML;
    assert.match(panel, /Reported city fallback/);
    assert.match(panel, /latest.example/);
    assert.match(panel, /2026-11-01T10:00:00Z/);
    assert.match(panel, /latest.csv · CSV · row 7/);
    assert.match(panel, /#entity\/e1\?tab=details/);
    assert.match(panel, /reported fallback cities follow the selected evidence/);
    h.click('[data-ec-location-source="entity-location:e1"]');
    assert.equal(
      h.requests.at(-1).url,
      '/api/eclipse/observations/fallback-source?source_key=exact',
      'The fallback opens its exact source locator, even outside the global sample',
    );
  } finally {
    h.destroy();
  }

  const legacy = envelope();
  legacy.intelligence.atlas = legacy.snapshot.observations;
  h = await open(legacy);
  try {
    assert.equal(
      model(h).nodes.length,
      0,
      'Legacy raw observations cannot masquerade as entity locations',
    );
  } finally {
    h.destroy();
  }
  console.log(
    'Entity map controller: entity units, directory, workflow, source separation, drill/back, refresh, empty states, geography failure and keyboard/date semantics passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
