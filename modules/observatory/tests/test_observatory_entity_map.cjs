/** Entity geography is independent of supporting asset/finding volume. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const fs = require('node:fs');

(async () => {
  const model = await import(pathToFileURL(path.resolve(__dirname, '../static/eclipse_model.js')));
  const space = await import(pathToFileURL(path.resolve(__dirname, '../static/eclipse_space.js')));
  const { createScene } = await import(
    pathToFileURL(path.resolve(__dirname, '../static/eclipse_scene.js'))
  );
  const entity = (id, latitude = 35.227, longitude = -80.843, extra = {}) => ({
    id: 'entity-location:' + id,
    type: 'entity-location',
    entity_id: id,
    entity_ids: [id],
    entity_count: 1,
    label: 'Entity ' + id,
    scope: { entity_id: id },
    city: 'Charlotte',
    region: 'NC',
    latitude,
    longitude,
    location_basis: 'entity_city_area',
    approximate: true,
    basis: 'Current saved entity city area; not an exact or historical business address.',
    asset_count: 1,
    finding_count: 1,
    observation_count: 1,
    density_count: 1,
    admitted_density: 1,
    dark_matter_density: 0,
    rows: [],
    ...extra,
  });
  const layout = (nodes) =>
    model.atlasSummaryLayout({
      unit: 'entities',
      nodes,
      total_entities: nodes.length,
      mapped_entities: nodes.length,
      unplaced_entities: 0,
      unresolved_asset_count: 0,
    });
  const camera = { k: 1, x: 0, y: 0 };
  const manySupport = entity('alpha', 35.227, -80.843, {
    asset_count: 41,
    finding_count: 140,
    observation_count: 120000,
    density_count: 120000,
    admitted_density: 110000,
    dark_matter_density: 10000,
  });
  const single = layout([manySupport]);
  assert.equal(single.unit, 'entities');
  assert.equal(single.nodes.length, 1, 'Many assets and observations still yield one entity point');
  assert.equal(single.nodes[0].type, 'entity-location');
  assert.equal(
    single.nodes[0].basis,
    manySupport.basis,
    'Keep the explicit entity-city provenance',
  );
  assert.equal(single.nodes[0].approximate, true);
  const singleCluster = space.clusterLocations(single.nodes, camera, 56);
  assert.equal(singleCluster.length, 1);
  assert.equal(singleCluster[0].entity_count, 1);
  assert.equal(singleCluster[0].label, manySupport.label);
  assert.equal(singleCluster[0].asset_count, 41, 'Asset totals remain secondary context');
  assert.equal(singleCluster[0].finding_count, 140, 'Finding totals remain secondary context');
  assert.equal(singleCluster[0].observation_count, 120000);

  const colocated = layout([manySupport, entity('beta')]);
  const colocatedBefore = JSON.stringify(colocated.nodes);
  const together = space.clusterLocations(colocated.nodes, camera, 56);
  assert.equal(together.length, 1);
  assert.equal(together[0].entity_count, 2);
  assert.equal(together[0].label, '2 entities');
  assert.deepEqual([...together[0].entity_ids].sort(), ['alpha', 'beta']);
  assert.deepEqual(
    together[0].members.map((node) => node.scope.entity_id).sort(),
    ['alpha', 'beta'],
    'Every co-located entity remains individually selectable through its scope',
  );
  assert.equal(
    JSON.stringify(colocated.nodes),
    colocatedBefore,
    'No geographic scatter mutates entities',
  );
  assert.equal(together[0].x, colocated.nodes[0].x);
  assert.equal(together[0].y, colocated.nodes[0].y);

  const savedCityEntity = entity('saved-city', 35.227, -80.843, {
      location_temporal_basis: 'current_saved_profile',
    }),
    reportedCityEntity = entity('reported-city', 35.227, -80.843, {
      location_basis: 'reported_asset_city_area',
      location_temporal_basis: 'latest_selected_report',
      location_hostname: 'edge.example.test',
      location_ip: '203.0.113.9',
      location_observed_at: '2026-11-12T09:00:00Z',
      location_observed_day: '2026-11-12',
      location_observation_id: 'report-latest',
      basis:
        'Approximate city area from the latest selected IP/hostname report; not a verified business address.',
    });
  const mixed = layout([savedCityEntity, reportedCityEntity]),
    mixedBefore = JSON.stringify(mixed.nodes),
    mixedClusters = space.clusterLocations(mixed.nodes, camera, 56);
  assert.equal(mixedClusters.length, 1);
  assert.equal(mixedClusters[0].entity_count, 2);
  assert.deepEqual(mixedClusters[0].entity_ids, ['reported-city', 'saved-city']);
  for (const expected of [savedCityEntity, reportedCityEntity]) {
    const member = mixedClusters[0].members.find((node) => node.id === expected.id);
    assert(member, 'Both entity identities survive a mixed-provenance cluster');
    assert.equal(member.entity_id, expected.entity_id);
    assert.deepEqual(member.entity_ids, expected.entity_ids);
    assert.equal(member.location_basis, expected.location_basis);
    assert.equal(member.location_temporal_basis, expected.location_temporal_basis);
    assert.equal(member.basis, expected.basis);
    assert.equal(member.approximate, true);
  }
  const reportedMember = mixedClusters[0].members.find((node) => node.id === reportedCityEntity.id);
  assert.equal(reportedMember.location_observation_id, reportedCityEntity.location_observation_id);
  assert.equal(reportedMember.location_hostname, reportedCityEntity.location_hostname);
  assert.equal(reportedMember.location_observed_at, reportedCityEntity.location_observed_at);
  assert.equal(
    JSON.stringify(mixed.nodes),
    mixedBefore,
    'Mixed-basis grouping preserves entity records',
  );

  // The old anchor-grouping/centroid-painting mismatch produced two 27px circles
  // just 3.14px apart. Every entity must remain represented without ambiguous centers.
  const converging = layout([
    entity('anchor-a', 35, -80),
    entity('anchor-b', 35, -78.9),
    ...Array.from({ length: 50 }, (_, i) => entity('near-a-' + i, 35, -79.45)),
    ...Array.from({ length: 50 }, (_, i) => entity('near-b-' + i, 35, -79.44)),
  ]).nodes;
  const stable = (nodes) =>
    space
      .clusterLocations(nodes, camera, 56)
      .map((cluster) => ({
        id: cluster.id,
        x: cluster.x,
        y: cluster.y,
        entity_count: cluster.entity_count,
        members: cluster.members.map((node) => node.id).sort(),
      }))
      .sort((a, b) => a.id.localeCompare(b.id));
  const clustered = stable(converging);
  assert.deepEqual(
    stable([...converging].reverse()),
    clustered,
    'Input order cannot change map groups',
  );
  assert.deepEqual(
    stable([...converging.slice(37), ...converging.slice(0, 37)]),
    clustered,
    'A second permutation preserves cluster identity and representative coordinates',
  );
  assert.equal(
    clustered.reduce((sum, cluster) => sum + cluster.entity_count, 0),
    102,
  );
  assert.equal(new Set(clustered.flatMap((cluster) => cluster.members)).size, 102);
  for (let i = 0; i < clustered.length; i++) {
    for (let j = i + 1; j < clustered.length; j++) {
      assert(
        Math.hypot(clustered[i].x - clustered[j].x, clustered[i].y - clustered[j].y) >= 56,
        'Distinct marker centers preserve the requested screen-space separation',
      );
    }
  }

  class Target {
    constructor() {
      this.listeners = {};
    }
    addEventListener(name, callback, { signal } = {}) {
      (this.listeners[name] ||= []).push(callback);
      signal?.addEventListener(
        'abort',
        () => {
          this.listeners[name] = this.listeners[name].filter((fn) => fn !== callback);
        },
        { once: true },
      );
    }
    emit(name, event = {}) {
      for (const callback of this.listeners[name] || []) callback(event);
    }
  }
  const marks = [],
    texts = [];
  function context(capture) {
    const gradient = () => ({ addColorStop() {} });
    return new Proxy(
      {
        path: [],
        measureText: (value) => ({ width: String(value).length * 7 }),
        createRadialGradient: gradient,
        createLinearGradient: gradient,
        beginPath() {
          this.path = [];
        },
        arc(...args) {
          this.path.push({ kind: 'arc', args });
        },
        ellipse(...args) {
          this.path.push({ kind: 'ellipse', args });
        },
        stroke() {
          if (capture)
            marks.push({
              kind: 'stroke',
              style: this.strokeStyle,
              width: this.lineWidth,
              path: [...this.path],
            });
        },
        fill() {
          if (capture) marks.push({ kind: 'fill', path: [...this.path] });
        },
        fillText(value, x, y) {
          if (capture) texts.push({ value: String(value), x, y });
        },
      },
      { get: (target, key) => (key in target ? target[key] : () => {}) },
    );
  }
  const root = { dataset: { inspectorOpen: 'false' } };
  class Canvas extends Target {
    constructor(capture = false) {
      super();
      this.context = context(capture);
      this.style = {};
      this.attrs = {};
      this.rect = { width: 1200, height: 760, left: 0, top: 0 };
    }
    getContext() {
      return this.context;
    }
    closest() {
      return root;
    }
    getBoundingClientRect() {
      return this.rect;
    }
    setAttribute(key, value) {
      this.attrs[key] = value;
    }
    focus() {}
    setPointerCapture() {}
    hasPointerCapture() {
      return false;
    }
  }
  const canvas = new Canvas(true),
    document = new Target(),
    media = new Target(),
    frames = new Map();
  let nextFrame = 0,
    resize;
  media.matches = true;
  document.hidden = false;
  document.createElement = () => new Canvas();
  Object.assign(global, {
    document,
    devicePixelRatio: 1,
    matchMedia: (query) =>
      query.includes('max-width') ? { matches: canvas.rect.width <= 1050 } : media,
    getComputedStyle: () => ({ getPropertyValue: () => '340px' }),
    ResizeObserver: class {
      constructor(callback) {
        resize = callback;
      }
      observe() {}
      disconnect() {}
    },
    requestAnimationFrame: (callback) => {
      frames.set(++nextFrame, callback);
      return nextFrame;
    },
    cancelAnimationFrame: (id) => frames.delete(id),
  });
  function frame() {
    marks.length = 0;
    texts.length = 0;
    const pending = [...frames.values()];
    frames.clear();
    for (const callback of pending) callback(performance.now());
  }
  const selected = [],
    scene = createScene(canvas, { select: (node) => selected.push(node.id) });
  scene.set(single, 'atlas', 'organization', { reset: true });
  frame();
  assert(
    texts.some((text) => text.value === '1'),
    'A single entity marker displays one',
  );
  assert(!texts.some((text) => ['41', '140', '120000'].includes(text.value)));
  const highVolumeGeometry = marks.filter((mark) => mark.path.length);
  scene.set(layout([entity('alpha')]), 'atlas', 'organization', { reset: true });
  frame();
  assert.deepEqual(
    marks.filter((mark) => mark.path.length),
    highVolumeGeometry,
    'Asset, finding and observation growth cannot enlarge the entity marker or halo',
  );
  scene.set(colocated, 'atlas', 'organization', { reset: true });
  frame();
  assert(
    texts.some((text) => text.value === '2'),
    'Co-located entity markers show entity count',
  );
  assert.equal(root.dataset.renderedCount, '1');
  canvas.emit('keydown', { key: ']', preventDefault() {} });
  frame();
  assert.equal(selected[0], manySupport.id);
  assert(
    marks.some(
      (mark) =>
        mark.kind === 'stroke' &&
        mark.style === '#fff' &&
        mark.width === 2.5 &&
        mark.path.some((part) => part.kind === 'arc'),
    ),
    'Selecting an entity by keyboard visibly highlights its containing marker',
  );

  scene.select(null);
  scene.set(
    { ...layout([]), nodes: converging, bounds: model.bounds(converging) },
    'atlas',
    'organization',
    { reset: true },
  );
  const targetView = {
    ...scene.captureView(),
    camera: { k: 1, x: 500, y: 350 },
    fitScale: 1,
  };
  for (const cluster of clustered) {
    scene.restoreView(targetView);
    frame();
    assert.equal(Number(root.dataset.renderedCount), clustered.length);
    const clientX = cluster.x + targetView.camera.x,
      clientY = cluster.y + targetView.camera.y;
    canvas.emit('pointerdown', { button: 0, pointerId: 1, clientX, clientY });
    canvas.emit('pointerup', { pointerId: 1, clientX, clientY });
    frame();
    assert.equal(
      selected.at(-1),
      cluster.id,
      'Every formerly overlapping cluster center selects its own visible marker',
    );
  }

  scene.select(null);
  const cities = layout([
    entity('asheville', 35.595, -82.551),
    entity('greensboro', 36.073, -79.792),
    entity('wilmington', 34.226, -77.945),
    entity('charleston', 32.783, -79.932),
  ]);
  root.dataset.inspectorOpen = 'true';
  scene.set(cities, 'atlas', 'organization', { reset: true });
  frame();
  function assertMarkerBodiesFit({ top, bottom }) {
    const bodies = marks
      .filter((mark) => mark.kind === 'stroke' && mark.style === '#7cffff' && mark.width === 1.3)
      .flatMap((mark) => mark.path.filter((part) => part.kind === 'arc'));
    assert(bodies.length > 0, 'The fitted map draws entity marker bodies');
    for (const {
      args: [x, y, radius],
    } of bodies) {
      assert(x - radius > 0, 'Fitted marker bodies remain inside the left canvas boundary');
      assert(x + radius <= 812, 'Fitted marker bodies clear the desktop inspector and its margin');
      assert(y - radius >= top, 'Fitted marker bodies clear the header');
      assert(y + radius <= bottom, 'Fitted marker bodies clear the footer');
    }
  }
  assertMarkerBodiesFit({ top: 124, bottom: 672 });
  canvas.rect.height = 400;
  resize();
  frame();
  assertMarkerBodiesFit({ top: 76, bottom: 344 });
  const resized = scene.captureView();
  for (const node of cities.nodes) {
    const x = node.x * resized.camera.k + resized.camera.x,
      y = node.y * resized.camera.k + resized.camera.y;
    assert(x > 0 && x < 1200 && y > 0 && y < 400, 'Height-only resize preserves a fitted overview');
  }
  assert.equal(frames.size, 0, 'Entity map remains idle when camera and selection settle');
  const nationalGeometry = JSON.parse(
    fs.readFileSync(path.resolve(__dirname, '../static/geo/states.json'), 'utf8'),
  );
  const states = model.geographicStates(nationalGeometry);
  assert.equal(states.length, 56, 'Offline context includes all Census state equivalents');
  const texas = model.jurisdictionBounds(states, ['TX']);
  const alaska = model.jurisdictionBounds(states, ['AK']);
  assert(
    texas.minX < model.mercatorPoint(-97.74, 30.27).x &&
      texas.maxX > model.mercatorPoint(-97.74, 30.27).x,
  );
  assert(
    alaska.maxX - alaska.minX < 6000,
    'Alaska does not span both sides of the world at the date line',
  );
  assert.equal(model.jurisdictionBounds(states, ['unknown']), null);
  scene.geometry(nationalGeometry);
  scene.jurisdiction({ states: ['TX'] });
  scene.set(cities, 'atlas', 'organization', { reset: true });
  frame();
  const texasCamera = scene.captureView();
  assert.equal(texasCamera.fitMode, 'region', 'A fresh map fits the configured jurisdiction');
  scene.jurisdiction({ states: ['AK'] });
  frame();
  assert.notDeepEqual(
    scene.captureView().camera,
    texasCamera.camera,
    'Changing settings refreshes geographic context and its camera',
  );
  scene.fit(false);
  assert.equal(
    scene.captureView().fitMode,
    'data',
    'Fit entities still includes all mapped entities',
  );
  scene.jurisdiction({ states: [] });
  assert.equal(
    scene.captureView().fitMode,
    'data',
    'Missing jurisdiction never assumes the Carolinas',
  );
  scene.destroy();
  console.log(
    'Entity map primary counts, provenance, co-location, permutation stability, separated targets, keyboard highlight, support-independent geometry and height resize passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
