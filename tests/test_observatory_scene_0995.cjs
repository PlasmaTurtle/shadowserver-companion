/** Field meaning and navigation stay stable while aggregate history grows. */
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
(async () => {
  const m = await import(pathToFileURL(path.resolve(__dirname, '../static/eclipse_model.js')));
  const space = await import(pathToFileURL(path.resolve(__dirname, '../static/eclipse_space.js')));
  assert(
    m.fieldBodyScale(2.75) > m.fieldBodyScale(1) * 1.7,
    'Approaching a Field body visibly enlarges it',
  );
  assert(m.fieldBodyScale(200) <= 2.6, 'Close inspection keeps body growth restrained');
  assert.equal(m.fieldBodyScale(NaN), 1, 'Malformed scale cannot poison drawing');
  const old = {
    id: 'o-old',
    observation_id: 'o-old',
    asset_id: 'a',
    finding_ids: ['f'],
    hostname: 'mail.example',
    ip: '8.8.8.8',
    observed_at: '2026-11-01T00:00:00Z',
    observed_day: '2026-11-01',
    admitted: true,
    status: 'qualified',
  };
  const representative = {
    ...old,
    id: 'f',
    finding_id: 'f',
    observed_at: '2026-11-10T00:00:00Z',
    observed_day: '2026-11-10',
    ip: '1.1.1.1',
    status: 'delivered',
    case_id: 'notification',
    tag: 'CVE-2026-12345',
  };
  const replay = m.findingRows([old], [representative]);
  assert.equal(replay[0].observed_day, '2026-11-01');
  assert.equal(replay[0].ip, '8.8.8.8');
  assert.equal(
    replay[0].status,
    'delivered',
    'Current workflow is distinct from historical observation time',
  );
  assert.equal(
    m.filterRows(replay, { cutoff: '2026-11-05' }).length,
    1,
    'Historical finding remains visible',
  );
  const mixed = {
    id: 'mixed',
    tag: 'CVE-2026-11111;CVE-2026-22222',
    kev: true,
    catalog_findings: [
      { id: 'CVE-2026-11111', severity: 'HIGH', kev: false },
      { id: 'CVE-2026-22222', severity: 'CRITICAL', kev: true },
    ],
  };
  assert.equal(
    m.filterRows([mixed], { search: 'CVE-2026-11111', intelligence: 'critical_kev' }).length,
    0,
  );
  assert.equal(m.filterRows([mixed], { search: 'CVE-2026-11111', intelligence: 'kev' }).length, 0);
  assert.equal(
    m.filterRows([mixed], { search: 'CVE-2026-22222', intelligence: 'critical_kev' }).length,
    1,
  );
  assert.deepEqual(
    m.observationKeys({ protocol: 'tcp', port: 443, version: '1.0' }, 'version'),
    [],
    'Bare version cannot identify shared software',
  );
  const graph = {
    nodes: [
      {
        id: 'entity:a',
        type: 'entity',
        label: 'Alpha',
        asset_count: 2,
        observation_count: 9,
        temperature: 'hot',
      },
      { id: 'asset:a', type: 'asset', asset_id: 'a', label: 'mail.alpha.example', asset_count: 1 },
      { id: 'entity:b', type: 'entity', label: 'Beta', asset_count: 1, observation_count: 8 },
      { id: 'asset:b', type: 'asset', asset_id: 'b', label: 'mail.beta.example' },
    ],
    edges: [
      { source: 'entity:a', target: 'asset:a' },
      { source: 'entity:b', target: 'asset:b' },
    ],
  };
  const before = m.graphLayout(graph, 'organization');
  assert.deepEqual(
    space
      .membershipForObservation(
        { ...before, selectedRow: { id: 'older-detail', asset_id: 'a' } },
        'older-detail',
      )
      .map((n) => n.id),
    ['asset:a'],
    'An older loaded observation resolves to its canonical asset beyond bounded examples',
  );
  const after = m.graphLayout(
    { ...graph, nodes: graph.nodes.map((n) => ({ ...n, observation_count: 9000 })) },
    'organization',
  );
  assert.deepEqual(
    before.nodes.map((n) => [n.id, n.x, n.y]),
    after.nodes.map((n) => [n.id, n.x, n.y]),
    'Repeat density does not rearrange the universe',
  );
  const atlas = m.atlasLayout({
    nodes: [
      {
        id: 'a',
        asset_id: 'a',
        entity_id: 'e',
        label: 'Alpha',
        latitude: 35,
        longitude: -80,
        observation_count: 1000,
        density_count: 1000,
        admitted_density: 900,
        dark_matter_density: 100,
        finding_count: 2,
        observed_days: ['2026-11-01', '2026-11-02'],
        rows: [old],
        summary: true,
      },
      {
        id: 'b',
        asset_id: 'b',
        entity_id: 'e',
        label: 'Beta',
        latitude: 35,
        longitude: -80,
        observation_count: 500,
        density_count: 500,
        admitted_density: 400,
        dark_matter_density: 100,
        finding_count: 3,
        observed_days: ['2026-11-02'],
        rows: [],
        summary: true,
      },
    ],
    unplaced_count: 7,
    omitted_nodes: 3,
  });
  const clustering = space.createLocationClusterer(atlas.nodes),
    c = clustering({ x: 0, y: 0, k: 1 });
  assert.equal(c.length, 1);
  assert.equal(c[0].observation_count, 1500);
  assert.equal(c[0].finding_count, 5);
  assert.equal(c[0].entity_count, 1);
  assert.equal(c[0].day_count, 2);
  assert.equal(c[0].rows.length, 1, 'Bounded examples never substitute for aggregate counts');
  const rowsIdentity = c[0].rows;
  const panned = clustering({ x: 100, y: 50, k: 1 });
  assert.strictEqual(panned, c, 'Pan and hover reuse cluster summaries');
  assert.strictEqual(panned[0].rows, rowsIdentity, 'History is not recopied during pan');
  assert.equal(atlas.unplaced, 7);
  assert.equal(atlas.omittedLocations, 3);
  const pulse = m.pulseLayout(
    {
      lanes: [
        {
          id: 'a',
          label: 'Alpha',
          scope: { asset_id: 'a' },
          observation_count: 900,
          day_count: 2,
          bins: [
            { day: '2026-11-01', observation_count: 400 },
            { day: '2026-11-05', observation_count: 500 },
          ],
        },
      ],
      undated: 3,
      omitted_lanes: 2,
    },
    'organization',
  );
  assert.equal(pulse.nodes[1].observation_count, 500);
  assert.equal(pulse.nodes[1].scope.asset_id, 'a');
  assert.equal(pulse.nodes[1].scope.date_to, '2026-11-05');
  assert(pulse.nodes[1].x > pulse.nodes[0].x);
  assert.equal(pulse.undated, 3);

  class Target {
    constructor() {
      this.listeners = {};
    }
    addEventListener(k, fn) {
      (this.listeners[k] ??= []).push(fn);
    }
    emit(k, v = {}) {
      for (const f of this.listeners[k] || []) f(v);
    }
  }
  const context = new Proxy(
    {
      measureText: (t) => ({ width: String(t).length * 7 }),
      createRadialGradient: () => ({ addColorStop() {} }),
      createLinearGradient: () => ({ addColorStop() {} }),
    },
    { get: (o, k) => (k in o ? o[k] : () => {}) },
  );
  const root = { dataset: { inspectorOpen: 'false' } };
  class Canvas extends Target {
    constructor() {
      super();
      this.style = {};
      this.attrs = {};
    }
    getContext() {
      return context;
    }
    closest() {
      return root;
    }
    getBoundingClientRect() {
      return this.rect || { width: 1100, height: 650, left: 0, top: 0 };
    }
    focus() {}
    setAttribute(k, v) {
      this.attrs[k] = v;
    }
    setPointerCapture() {}
    hasPointerCapture() {
      return false;
    }
  }
  const document = new Target();
  document.hidden = false;
  document.createElement = () => new Canvas();
  const media = new Target();
  media.matches = false;
  let next = 0,
    resizeCallback;
  const frames = new Map();
  Object.assign(global, {
    document,
    devicePixelRatio: 1,
    matchMedia: () => media,
    ResizeObserver: class {
      constructor(fn) {
        resizeCallback = fn;
      }
      observe() {}
      disconnect() {}
    },
    requestAnimationFrame: (fn) => {
      frames.set(++next, fn);
      return next;
    },
    cancelAnimationFrame: (id) => frames.delete(id),
  });
  const runFrame = () => {
    const pending = [...frames.values()];
    frames.clear();
    for (const fn of pending) fn(performance.now() + 1000);
  };
  const { createScene } = await import(
    pathToFileURL(path.resolve(__dirname, '../static/eclipse_scene.js'))
  );
  const canvas = new Canvas(),
    selected = [];
  const scene = createScene(canvas, { select: (n) => selected.push(n.id) });
  scene.set(before, 'field', 'organization', { reset: true });
  runFrame();
  const home = scene.captureView();
  canvas.rect = { width: 0, height: 0, left: 0, top: 0 };
  resizeCallback();
  assert.deepEqual(
    scene.captureView(),
    home,
    'Hiding the canvas in Records preserves the field camera and dimensions',
  );
  canvas.rect = null;
  resizeCallback();
  let completions = 0;
  const cancelledApproach = scene.approach('entity:a', { onComplete: () => completions++ });
  scene.cancelApproach();
  assert.deepEqual(await cancelledApproach, { completed: false, reason: 'cancelled' });
  runFrame();
  assert.equal(completions, 0, 'Cancellation cannot open an obsolete destination');
  const completedApproach = scene.approach('entity:a', { onComplete: () => completions++ });
  runFrame();
  assert.deepEqual(await completedApproach, { completed: true, reason: 'arrived' });
  assert.equal(completions, 1);
  scene.set(atlas, 'atlas', 'organization');
  runFrame();
  assert.equal(
    scene.restoreView(home),
    false,
    'Do not apply field camera to a geographic projection',
  );
  scene.set(before, 'field', 'organization');
  assert.equal(scene.restoreView(home), true);
  runFrame();
  assert.deepEqual(scene.captureView().camera, home.camera);
  canvas.emit('keydown', { key: ']', preventDefault() {} });
  runFrame();
  assert.equal(selected.length, 1, 'Canvas objects have a keyboard selection route');
  assert(
    canvas.attrs['aria-label'].includes('Alpha') || canvas.attrs['aria-label'].includes('Beta'),
  );
  media.matches = true;
  media.emit('change');
  scene.approach('entity:a', { onComplete: () => completions++ });
  assert.equal(completions, 2, 'Reduced motion resolves immediately');
  media.matches = false;
  scene.motion(true);
  const hiddenApproach = scene.approach('entity:a');
  document.hidden = true;
  document.emit('visibilitychange');
  assert.equal(
    (await hiddenApproach).completed,
    true,
    'Background visibility settles navigation without a stalled RAF',
  );
  document.hidden = false;
  document.emit('visibilitychange');
  const replacedApproach = scene.approach('entity:a');
  scene.set(atlas, 'atlas', 'organization');
  assert.equal((await replacedApproach).reason, 'view-changed');
  scene.set(before, 'field', 'organization');
  const destroyedApproach = scene.approach('entity:a');
  scene.destroy();
  assert.equal((await destroyedApproach).reason, 'destroyed');
  assert.equal(frames.size, 0, 'No animation frame survives teardown');
  console.log(
    'Observatory0995 historical fields, CVE-specific risk, spatial identity, exact aggregate counts, cached panning, camera return, cancellation, keyboard and reduced motion passed.',
  );
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
