/** Cinematic navigation is local, bounded, accessible, and quiescent at rest. */
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');

(async () => {
  class Target {
    constructor() {
      this.listeners = {};
    }
    addEventListener(name, fn, { signal } = {}) {
      (this.listeners[name] ||= []).push(fn);
      signal?.addEventListener(
        'abort',
        () => {
          this.listeners[name] = this.listeners[name].filter((item) => item !== fn);
        },
        { once: true },
      );
    }
    emit(name, event = {}) {
      for (const fn of this.listeners[name] || []) fn(event);
    }
  }
  let clock = 0,
    next = 0,
    resize;
  const frames = new Map(),
    root = { dataset: { inspectorOpen: 'true' } },
    media = new Target(),
    document = new Target(),
    text = [],
    marks = [];
  media.matches = false;
  document.hidden = false;
  const gradient = (kind, args) => ({
    kind,
    args,
    stops: [],
    addColorStop(at, color) {
      this.stops.push([at, color]);
    },
  });
  const context = new Proxy(
    {
      path: [],
      dash: [],
      measureText: (value) => ({ width: String(value).length * 7 }),
      createRadialGradient: (...args) => gradient('radial', args),
      createLinearGradient: (...args) => gradient('linear', args),
      beginPath() {
        this.path = [];
      },
      arc(...args) {
        this.path.push({ kind: 'arc', args });
      },
      ellipse(...args) {
        this.path.push({ kind: 'ellipse', args });
      },
      roundRect(...args) {
        this.path.push({ kind: 'roundRect', args });
      },
      moveTo(...args) {
        this.path.push({ kind: 'moveTo', args });
      },
      lineTo(...args) {
        this.path.push({ kind: 'lineTo', args });
      },
      quadraticCurveTo(...args) {
        this.path.push({ kind: 'quadraticCurveTo', args });
      },
      setLineDash(value) {
        this.dash = value;
      },
      fill() {
        marks.push({ kind: 'fill', style: this.fillStyle, path: [...this.path] });
      },
      stroke() {
        marks.push({
          kind: 'stroke',
          style: this.strokeStyle,
          width: this.lineWidth,
          dash: [...this.dash],
          path: [...this.path],
        });
      },
      fillText(value, x, y) {
        text.push({ value, x, y, alpha: this.globalAlpha });
      },
    },
    { get: (target, key) => (key in target ? target[key] : () => {}) },
  );
  class Canvas extends Target {
    constructor() {
      super();
      this.style = {};
      this.attrs = {};
      this.rect = { width: 1200, height: 760, left: 0, top: 0 };
    }
    getContext() {
      return context;
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
  const canvas = new Canvas();
  document.createElement = () => new Canvas();
  Object.assign(global, {
    document,
    devicePixelRatio: 1,
    performance: { now: () => clock },
    getComputedStyle: () => ({ getPropertyValue: () => '340px' }),
    matchMedia: (query) =>
      query.includes('max-width') ? { matches: canvas.rect.width <= 1050 } : media,
    ResizeObserver: class {
      constructor(fn) {
        resize = fn;
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
  function frame(at = clock) {
    clock = at;
    const work = [...frames.values()];
    frames.clear();
    for (const fn of work) fn(clock);
  }
  function model(far = false) {
    const nodes = [
      {
        id: 'hub',
        label: 'Organization',
        type: 'entity',
        x: 5000,
        y: 4000,
        depth: 1,
        revealRank: 0,
      },
      {
        id: 'asset-a',
        label: 'mail.example',
        type: 'asset',
        x: 4800,
        y: 3870,
        depth: 0.5,
        revealRank: 1,
      },
      {
        id: 'asset-b',
        label: 'vpn.example',
        type: 'asset',
        x: 5200,
        y: 4130,
        depth: 0,
        revealRank: 2,
      },
    ];
    if (far)
      nodes.push({
        id: 'distant',
        label: 'Distant',
        type: 'entity',
        x: 12000,
        y: 10000,
        revealRank: 3,
      });
    const edges = [1, 2].map((index) => ({
      source: 'hub',
      target: nodes[index].id,
      from: nodes[0],
      to: nodes[index],
    }));
    return {
      nodes,
      edges,
      neighbors: new Map([
        ['hub', [nodes[1], nodes[2]]],
        ['asset-a', [nodes[0]]],
        ['asset-b', [nodes[0]]],
      ]),
      bounds: far
        ? { minX: 0, maxX: 12100, minY: 0, maxY: 10100 }
        : { minX: 4700, maxX: 5300, minY: 3750, maxY: 4250 },
    };
  }
  const { createScene } = await import(
    pathToFileURL(path.resolve(__dirname, '../static/eclipse_scene.js'))
  );
  const { graphLayout } = await import(
    pathToFileURL(path.resolve(__dirname, '../static/eclipse_model.js'))
  );
  const choices = [],
    settlements = [];
  let scene = createScene(canvas, {
    select(node) {
      choices.push(node.id);
      scene.focus(node.id, 1.5, { onSettled: (value) => settlements.push(value) });
    },
  });
  const data = model(true);
  scene.set(data, 'field', 'organization', { reset: true });
  frame();
  const overview = scene.captureView();
  scene.motion(false);
  scene.select('hub');
  scene.focus('hub', 1.5);
  frame();
  let focused = scene.captureView();
  assert(
    focused.camera.k > overview.fitScale * 5,
    'A large global field cannot keep its local selection microscopic',
  );
  assert(focused.camera.k >= 1, 'Local observations have readable inspection spacing');
  for (const node of data.nodes.slice(0, 3)) {
    const p = scene.position(node.id),
      x = ((p.x + 1) / 2) * 1200,
      y = ((p.y + 1) / 2) * 760;
    assert(
      x > 40 && x < 810 && y > 120 && y < 670,
      'Entire constellation fits beside the open inspector and HUD',
    );
  }
  assert.equal(scene.position('missing'), null);
  assert.deepEqual(
    scene.position('distant'),
    { x: 1, y: 1 },
    'Background navigation receives bounded normalized screen coordinates',
  );
  canvas.rect = { ...canvas.rect, width: 700, height: 600 };
  resize();
  frame();
  for (const node of data.nodes.slice(0, 3)) {
    const p = scene.position(node.id);
    assert(
      p.x > -0.95 && p.x < 0.95 && p.y > -0.8 && p.y < 0.8,
      'Resize reframes the selected constellation',
    );
  }
  canvas.rect = { ...canvas.rect, width: 1200, height: 760 };
  resize();
  frame();
  scene.motion(true);
  const p = scene.position('hub'),
    x = ((p.x + 1) / 2) * 1200,
    y = ((p.y + 1) / 2) * 760;
  canvas.emit('pointerdown', { button: 0, pointerId: 1, clientX: x, clientY: y });
  canvas.emit('pointerup', { pointerId: 1, clientX: x, clientY: y });
  frame(clock + 800);
  assert.deepEqual(choices, ['hub']);
  assert.deepEqual(
    settlements,
    [{ completed: true, reason: 'arrived' }],
    'pick must not supersede the controller focus',
  );

  root.dataset.inspectorOpen = 'false';
  scene.select(null);
  scene.set(model(), 'field', 'organization', { reset: true, reveal: true });
  const start = clock;
  frame(start);
  assert.equal(scene.snapshot().revealing, true);
  assert(
    Number(root.dataset.renderedCount) >= 3,
    'All nodes have hit targets at the start of reveal',
  );
  assert(frames.size > 0);
  canvas.emit('keydown', { key: ']', preventDefault() {} });
  assert.equal(choices.length, 2, 'Keyboard selection remains available during reveal');
  frame(start + 800);
  assert.equal(scene.snapshot().revealing, true);
  frame(start + 1400);
  assert.equal(scene.snapshot().revealing, false);
  assert.equal(frames.size, 0, 'No decorative canvas loop remains after arrival');
  const settled = scene.captureView().camera;
  frame(start + 9000);
  assert.deepEqual(
    scene.captureView().camera,
    settled,
    'Readable labels and observations do not drift at rest',
  );
  media.matches = true;
  media.emit('change');
  scene.set(model(), 'field', 'organization', { reset: true, reveal: true });
  frame(clock);
  assert.equal(scene.snapshot().revealing, false, 'Reduced motion reveals all data immediately');
  assert.equal(frames.size, 0);
  media.matches = false;
  scene.motion(true);
  scene.set(model(), 'field', 'organization', { reveal: true });
  frame(clock);
  document.hidden = true;
  document.emit('visibilitychange');
  assert.equal(scene.snapshot().revealing, false);
  assert.equal(frames.size, 0, 'Hidden views stop the sweep immediately');
  document.hidden = false;
  document.emit('visibilitychange');
  frame(clock);
  assert.equal(frames.size, 0, 'Visibility restoration does not restart a stale reveal');
  scene.set(model(), 'field', 'organization', { reveal: true });
  scene.destroy();
  assert.equal(frames.size, 0, 'Teardown cancels pending reveal frames');

  // Visual order, interaction and labels share discovery depth, never urgency.
  const selected = [];
  scene = createScene(canvas, {
    select(node) {
      selected.push(node.id);
    },
  });
  scene.motion(false);
  const near = {
      id: 'near',
      label: 'Near discovery',
      type: 'entity',
      x: 500,
      y: 350,
      depth: 1,
      temperature: 'cool',
      asset_count: 20,
    },
    far = {
      id: 'far',
      label: 'Old dense mass',
      type: 'entity',
      x: 500,
      y: 350,
      depth: 0,
      temperature: 'blazing',
      asset_count: 1,
    },
    field = (nodes) => ({ nodes, edges: [], bounds: { minX: 0, maxX: 1000, minY: 0, maxY: 700 } });
  const render = (nodes) => {
    scene.select(null);
    scene.set(field(nodes), 'field', 'organization', { reset: true });
    marks.length = 0;
    text.length = 0;
    frame(clock);
  };
  const click = (id) => {
    const point = scene.position(id),
      clientX = ((point.x + 1) / 2) * canvas.rect.width,
      clientY = ((point.y + 1) / 2) * canvas.rect.height;
    canvas.emit('pointerdown', { button: 0, pointerId: 2, clientX, clientY });
    canvas.emit('pointerup', { pointerId: 2, clientX, clientY });
  };
  render([near, far]);
  let cores = marks.filter((mark) => mark.kind === 'fill' && mark.style === '#091521');
  assert.equal(cores.length, 2);
  assert(
    cores[0].path[0].args[2] < cores[1].path[0].args[2],
    'Far core paints first; nearest discovery remains on top',
  );
  assert(text.some((mark) => mark.value === near.label));
  assert(
    text.findIndex((mark) => mark.value === far.label) === -1 ||
      text.findIndex((mark) => mark.value === near.label) <
        text.findIndex((mark) => mark.value === far.label),
    'Near discovery receives label placement before a hotter distant object',
  );
  click('near');
  assert.equal(selected.at(-1), 'near', 'Reverse hit order follows the visibly topmost core');
  scene.select('far');
  marks.length = 0;
  frame(clock);
  cores = marks.filter((mark) => mark.kind === 'fill' && mark.style === '#091521');
  assert(
    cores[0].path[0].args[2] > cores[1].path[0].args[2],
    'An explicitly selected far object moves to the foreground',
  );
  click('far');
  assert.equal(selected.at(-1), 'far');

  const unresolved = {
    id: 'unresolved',
    label: 'unresolved.example',
    type: 'asset',
    field_object: true,
    x: 500,
    y: 350,
    depth: 0.5,
    finding_count: 1,
  };
  render([unresolved]);
  cores = marks.filter((mark) => mark.kind === 'fill' && mark.style === '#091521');
  assert.equal(
    cores[0].path[0].kind,
    'arc',
    'An unresolved field object is a full body, not a tiny satellite',
  );
  assert(cores[0].path[0].args[2] >= 13);
  assert(
    text.some((mark) => mark.value === '0 observations'),
    'Single unresolved endpoints do not invent finding or asset totals',
  );
  click('unresolved');
  assert.equal(selected.at(-1), 'unresolved');
  canvas.emit('keydown', { key: ']', preventDefault() {} });
  assert.equal(selected.at(-1), 'unresolved', 'Unresolved field bodies remain keyboard selectable');

  const shadows = () =>
    marks.filter(
      (mark) =>
        mark.kind === 'fill' &&
        mark.style?.stops?.some((stop) => ['#02060de0', '#01040af2'].includes(stop[1])),
    );
  render([{ ...unresolved, admitted_density: 12, dark_matter_density: 0 }]);
  assert.equal(shadows().length, 0, 'No unadmitted observations means no dark-matter envelope');
  render([{ ...unresolved, admitted_density: 12, dark_matter_density: 120 }]);
  assert.equal(shadows().length, 1);
  assert.equal(
    shadows()[0].path.filter((part) => part.kind === 'quadraticCurveTo').length,
    24,
    'One bounded irregular cloud is drawn per real dark-bearing body',
  );
  assert(
    marks.some((mark) => mark.kind === 'fill' && mark.style === '#d3ffff'),
    'Mixed approved and unadmitted evidence retains a bright approved core',
  );
  const mixedShape = shadows()[0].path;
  render([{ ...unresolved, admitted_density: 12, dark_matter_density: 120 }]);
  assert.deepEqual(
    shadows()[0].path,
    mixedShape,
    'Cloud contours are deterministic across redraws',
  );
  render([{ ...unresolved, admitted_density: 0, dark_matter_density: 1000000000 }]);
  assert.equal(shadows().length, 1);
  assert(shadows()[0].style.args[5] <= 75, 'Even extreme dark density has a bounded cloud radius');
  assert(
    !marks.some((mark) => mark.kind === 'fill' && mark.style === '#d3ffff'),
    'Entirely unadmitted data must not borrow an approved bright core',
  );
  assert(
    marks.some((mark) => mark.kind === 'stroke' && mark.dash.length > 0),
    'Dark-only body keeps a dashed core',
  );
  click('unresolved');
  assert.equal(
    selected.at(-1),
    'unresolved',
    'A dark-only unresolved body remains directly selectable',
  );
  frame(clock);
  assert.equal(frames.size, 0, 'Density coronas and dark envelopes never start idle animation');

  // A new focused payload refits local bounds; that must not erase arrival.
  const body = {
      id: 'constellation',
      label: 'Focused organization',
      type: 'entity',
      field_object: true,
      asset_count: 48,
      total_assets: 48,
      density_count: 1270,
    },
    assets = Array.from({ length: 48 }, (_, index) => ({
      id: 'endpoint-' + index,
      label: 'host-' + index + '.example',
      type: 'asset',
      rows: [{ id: 'evidence-' + index, observed_day: '2026-11-13' }],
    })),
    graph = {
      nodes: [body, ...assets],
      edges: assets.map((node) => ({ source: body.id, target: node.id })),
    };
  scene.select(null);
  scene.set(graphLayout(graph, 'organization'), 'field', 'organization', { reset: true });
  marks.length = 0;
  frame(clock);
  const overviewRadius = marks.find(
    (mark) => mark.kind === 'fill' && mark.style === '#091521' && mark.path[0].kind === 'arc',
  ).path[0].args[2];
  root.dataset.inspectorOpen = 'true';
  scene.set(graphLayout(graph, 'organization', { focused: true }), 'field', 'organization', {
    reset: true,
  });
  scene.select(body.id);
  scene.focus(body.id);
  marks.length = 0;
  text.length = 0;
  frame(clock);
  const localView = scene.captureView();
  assert(
    localView.camera.k / localView.fitScale < 1.35,
    'Fixture reproduces the local-fit semantic reset',
  );
  assert.equal(
    scene.snapshot().level,
    'endpoints',
    'Fetched constellation arrives in inspection even below its new fitScale',
  );
  assert.equal(root.dataset.semanticLevel, 'endpoints');
  const arrivedRadius = marks.find(
    (mark) => mark.kind === 'fill' && mark.style === '#091521' && mark.path[0].kind === 'arc',
  ).path[0].args[2];
  assert(
    arrivedRadius > overviewRadius * 1.3,
    'Arrival keeps the primary core visibly larger than its overview appearance',
  );
  const endpoints = marks.filter(
    (mark) => mark.kind === 'fill' && mark.style === '#091521' && mark.path[0].kind === 'roundRect',
  );
  assert.equal(endpoints.length, 48, 'Every real endpoint remains rendered');
  assert(
    endpoints.every((mark) => mark.path[0].args[2] >= 10),
    'Endpoint marks remain readable at local arrival',
  );
  assert(
    text.filter((mark) => mark.value.startsWith('host-')).length >= 5,
    'Endpoint identities are visible without another zoom gesture',
  );
  assert(
    text.some((mark) => mark.value === body.label),
    'The selected organization retains its identity when nearby endpoint marks block its first label position',
  );
  assert(
    text.some((mark) => mark.value === '48 assets · 1,270 observations'),
    'Body subtitle shows actual breadth and density rather than redundant type or findings',
  );
  click('endpoint-0');
  assert.equal(selected.at(-1), 'endpoint-0', 'Focused endpoints retain direct pointer access');
  scene.level('sources');
  frame(clock);
  assert.equal(
    scene.snapshot().level,
    'sources',
    'Explicit evidence zoom still reaches source detail',
  );
  assert(Number(root.dataset.sourceCards) > 0);
  scene.select(null);
  scene.set(graphLayout(graph, 'organization'), 'field', 'organization', { reset: true });
  frame(clock);
  assert.equal(
    scene.snapshot().level,
    'overview',
    'Returning to the field clears the inspection semantic minimum',
  );
  assert.equal(frames.size, 0);

  const denseAssets = Array.from({ length: 120 }, (_, index) => ({
      id: 'dense-' + index,
      label: 'dense-' + index + '.example',
      type: 'asset',
    })),
    denseGraph = {
      nodes: [{ ...body, total_assets: 120, asset_count: 120 }, ...denseAssets],
      edges: denseAssets.map((node) => ({ source: body.id, target: node.id })),
    };
  scene.set(graphLayout(denseGraph, 'organization', { focused: true }), 'field', 'organization', {
    reset: true,
  });
  scene.select(body.id);
  scene.focus(body.id);
  marks.length = 0;
  text.length = 0;
  frame(clock);
  assert.equal(
    marks.filter(
      (mark) =>
        mark.kind === 'fill' && mark.style === '#091521' && mark.path[0].kind === 'roundRect',
    ).length,
    120,
  );
  assert(
    text.filter((mark) => mark.value.startsWith('dense-')).length >= 5,
    'Label budget counts successful placements so uncrowded outer endpoints are attempted',
  );
  assert(
    text.some((mark) => mark.value === body.label),
    'Maximum-page constellation retains selected identity',
  );
  assert.equal(frames.size, 0);
  scene.destroy();
  console.log(
    'Observatory0998 framing, reveal, depth paint/hit order, primary unresolved bodies, bounded dark envelopes and RAF cleanup passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
