/** Real production controller with an offline DOM model; no browser/GPU claim. */
const fs = require('fs'),
  vm = require('vm'),
  assert = require('assert'),
  path = require('path');
(async () => {
  const elements = new Map(),
    listeners = new Map(),
    callbacks = new Map(),
    prefs = new Map();
  let raf = 0,
    observer;
  class Element {
    constructor() {
      this.attrs = {};
      this.style = {};
      this.children = [];
      this.dataset = {};
      this.events = new Map();
      this.classes = new Set();
      this.classList = { contains: (n) => this.classes.has(n) };
    }
    setAttribute(n, v) {
      this.attrs[n] = String(v);
    }
    getAttribute(n) {
      return this.attrs[n];
    }
    append(v) {
      this.children.push(v);
    }
    prepend(v) {
      this.children.unshift(v);
    }
    querySelector(s) {
      return elements.get(s.slice(1));
    }
    set innerHTML(s) {
      for (const m of s.matchAll(/id="([^"]+)"/g)) elements.set(m[1], new Element());
      this.firstElementChild = elements.get('dm-viewport');
      this.firstElementChild.attrs['aria-hidden'] = 'true';
    }
    getTotalLength() {
      return 1200;
    }
    getPointAtLength(n) {
      return { x: n * 0.6, y: n * 0.7 };
    }
    addEventListener(n, f) {
      this.events.set(n, f);
    }
    removeEventListener(n) {
      this.events.delete(n);
    }
    remove() {
      this.removed = true;
    }
  }
  elements.set('background-motion', new Element());
  const body = new Element(),
    media = new Element();
  media.matches = false;
  const document = {
    body,
    hidden: false,
    documentElement: { dataset: { theme: 'dark' } },
    createElement: () => new Element(),
    createElementNS: () => new Element(),
    getElementById: (id) => elements.get(id),
    addEventListener: (n, f) => listeners.set(n, f),
    removeEventListener: (n) => listeners.delete(n),
  };
  const window = new Element();
  const context = vm.createContext({
    document,
    window,
    matchMedia: () => media,
    localStorage: { getItem: (k) => prefs.get(k), setItem: (k, v) => prefs.set(k, v) },
    MutationObserver: class {
      constructor(f) {
        observer = f;
      }
      observe() {}
      disconnect() {
        observer = null;
      }
    },
    requestAnimationFrame: (f) => {
      callbacks.set(++raf, f);
      return raf;
    },
    cancelAnimationFrame: (id) => callbacks.delete(id),
    console,
  });
  const mod = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../static/cosmic_background.js'), 'utf8'),
    { context },
  );
  await mod.link(() => {
    throw Error('Unexpected dependency');
  });
  await mod.evaluate();
  const scene = mod.namespace.mountCosmicBackground();
  assert.equal(callbacks.size, 1);
  assert.equal(elements.get('dm-viewport').attrs['aria-hidden'], 'true');
  function tick(now) {
    const [id, fn] = callbacks.entries().next().value;
    callbacks.delete(id);
    fn(now);
  }
  const before = elements.get('dm-camera').style.transform;
  for (let n = 0; n < 480; n++) tick(1 + (n * 1000) / 30);
  assert.notEqual(elements.get('dm-camera').style.transform, before);
  assert(scene.getState().frames > 200);
  const pause = elements.get('background-motion');
  pause.events.get('click')();
  assert.equal(callbacks.size, 0);
  assert.equal(prefs.get('companion-background-motion'), 'paused');
  media.matches = true;
  media.events.get('change')();
  pause.events.get('click')();
  assert.equal(callbacks.size, 0, 'Reduced motion cannot be accidentally overridden');
  media.matches = false;
  media.events.get('change')();
  assert.equal(callbacks.size, 1);
  document.hidden = true;
  listeners.get('visibilitychange')();
  assert.equal(callbacks.size, 0);
  document.hidden = false;
  listeners.get('visibilitychange')();
  assert.equal(callbacks.size, 1);
  body.classes.add('eclipse-view');
  observer();
  assert.equal(callbacks.size, 1, 'Ambient drift continues in the loaded Observatory');
  body.classes.add('observatory-loading');
  observer();
  assert.equal(callbacks.size, 1, 'Opening Observatory reuses ambient drift');
  body.classes.delete('observatory-loading');
  observer();
  assert.equal(callbacks.size, 1, 'Completing Observatory loading must not stop drift');
  assert.equal(window.CosmicBackground, scene);
  assert.equal(scene.motionEnabled(), true);
  document.documentElement.dataset.theme = 'light';
  window.events.get('companion:presentation')();
  assert.equal(callbacks.size, 1, 'The dark Observatory remains animated inside a light shell');
  document.documentElement.dataset.theme = 'dark';
  const approach = elements.get('dm-approach');
  const ambientBeforeApproach = elements.get('dm-camera').style.transform;
  const timeBeforeApproach = scene.getState().time;
  scene.approach({ depth: 1, x: 1, y: -1 });
  assert.equal(approach.style.transform, 'translate3d(-2.000000%,2.000000%,0) scale(1.120000)');
  assert.equal(approach.style.transitionDuration, '650ms');
  assert.equal(
    scene.getState().time,
    timeBeforeApproach,
    'Approach does not restart ambient phase',
  );
  assert.equal(elements.get('dm-camera').style.transform, ambientBeforeApproach);
  tick(20000);
  tick(20050);
  assert.notEqual(elements.get('dm-camera').style.transform, ambientBeforeApproach);
  assert.equal(approach.style.transform, 'translate3d(-2.000000%,2.000000%,0) scale(1.120000)');
  assert.equal(callbacks.size, 1, 'Approach does not create a second animation loop');
  scene.approach({ depth: 100, x: -100, y: Infinity });
  assert.equal(approach.style.transform, 'translate3d(2.000000%,0.000000%,0) scale(1.120000)');
  scene.approach({ depth: NaN, x: 1, y: 1 });
  assert.equal(approach.style.transform, 'translate3d(0.000000%,0.000000%,0) scale(1.000000)');
  scene.setMotion(false);
  assert.equal(callbacks.size, 0);
  assert.equal(scene.motionEnabled(), false);
  scene.approach({ depth: 0.5, x: 0.5 });
  assert.equal(approach.style.transitionDuration, '0ms', 'Paused motion keeps selection immediate');
  assert.equal(approach.style.transform, 'translate3d(-0.500000%,0.000000%,0) scale(1.060000)');
  scene.setMotion(true);
  media.matches = true;
  media.events.get('change')();
  assert.equal(scene.motionEnabled(), false);
  scene.approach({ depth: 1, y: 1 });
  assert.equal(
    approach.style.transitionDuration,
    '0ms',
    'Reduced motion keeps selection immediate',
  );
  assert.equal(callbacks.size, 0);
  media.matches = false;
  media.events.get('change')();
  assert.equal(scene.motionEnabled(), true);
  scene.resetApproach();
  assert.equal(scene.getState().approach.depth, 0);
  assert.equal(approach.style.transitionDuration, '650ms');
  scene.approach({ depth: 1, immediate: true });
  assert.equal(approach.style.transitionDuration, '0ms');
  body.classes.clear();
  observer();
  assert.equal(callbacks.size, 1);
  assert.equal(
    scene.getState().approach.depth,
    0,
    'Leaving Observatory restores the app background',
  );
  assert.equal(approach.style.transitionDuration, '0ms');
  document.documentElement.dataset.theme = 'light';
  window.events.get('companion:presentation')();
  assert.equal(callbacks.size, 0);
  scene.destroy();
  assert.equal(callbacks.size, 0);
  assert.equal(listeners.size, 0);
  assert.equal(media.events.size, 0);
  assert.equal(window.events.size, 0);
  assert.equal(pause.events.size, 0);
  assert.equal(observer, null);
  assert(elements.get('dm-viewport').removed);
  assert.equal(window.CosmicBackground, undefined);
  scene.approach({ depth: 1 });
  assert.equal(callbacks.size, 0, 'Destroyed backgrounds cannot restart motion');
  console.log(
    'Production background: persistent Observatory drift, bounded independent approach, pause/reduced/hidden/light preferences and complete teardown passed. Browser GPU profiling remains separate.',
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
