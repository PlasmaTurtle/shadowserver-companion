/** Execute the production Observatory controller intact; mock only DOM and canvas IO. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function datasetName(name) {
  return name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
}
class Element {
  constructor(tag = 'div', attributes = {}, parent = null) {
    this.tagName = tag.toUpperCase();
    this.attributes = { ...attributes };
    this.id = attributes.id || '';
    this.parentElement = parent;
    this.dataset = {};
    for (const [name, value] of Object.entries(attributes))
      if (name.startsWith('data-')) this.dataset[datasetName(name)] = value;
    this.children = [];
    this.listeners = new Map();
    this.style = { setProperty() {}, removeProperty() {} };
    this.hidden = Object.hasOwn(attributes, 'hidden');
    this.disabled = false;
    this.value = '';
    this.textContent = '';
    this._html = '';
    this.isConnected = true;
    this.clientWidth = 1400;
    this.clientHeight = 800;
    const classes = new Set((attributes.class || '').split(/\s+/).filter(Boolean));
    this.classList = {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
      toggle(name, force) {
        const value = force === undefined ? !classes.has(name) : force;
        if (value) classes.add(name);
        else classes.delete(name);
        return value;
      },
    };
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name.startsWith('data-')) this.dataset[datasetName(name)] = String(value);
  }
  getAttribute(name) {
    return this.attributes[name] ?? null;
  }
  removeAttribute(name) {
    delete this.attributes[name];
  }
  matches(selector) {
    return selector.split(',').some((part) => {
      part = part.trim();
      if (part.startsWith('#')) return this.id === part.slice(1);
      if (part.startsWith('.')) return this.classList.contains(part.slice(1));
      const match = part.match(/^(\w+)?\[([^=\]]+)(?:=["']?([^"'\]]*)["']?)?\]$/);
      if (match) {
        const [, tag, attribute, value] = match;
        return (
          (!tag || this.tagName === tag.toUpperCase()) &&
          this.getAttribute(attribute) !== null &&
          (value === undefined || this.getAttribute(attribute) === value)
        );
      }
      return this.tagName === part.toUpperCase();
    });
  }
  descendants() {
    return this.children.flatMap((child) => [child, ...child.descendants()]);
  }
  querySelectorAll(selector) {
    return this.descendants().filter((child) => child.matches(selector));
  }
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
  closest(selector) {
    for (let node = this; node; node = node.parentElement) if (node.matches(selector)) return node;
    return null;
  }
  contains(node) {
    return node === this || this.descendants().includes(node);
  }
  set innerHTML(html) {
    this._html = String(html);
    this.children = parse(this._html, this);
  }
  get innerHTML() {
    return this._html;
  }
  insertAdjacentHTML(_where, html) {
    this._html += String(html);
    this.children.push(...parse(String(html), this));
  }
  addEventListener(type, fn, options = {}) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(fn);
    options.signal?.addEventListener('abort', () => this.listeners.get(type)?.delete(fn), {
      once: true,
    });
  }
  removeEventListener(type, fn) {
    this.listeners.get(type)?.delete(fn);
  }
  emit(type, event = {}) {
    for (const fn of this.listeners.get(type) || [])
      fn({ target: this, preventDefault() {}, stopPropagation() {}, ...event });
  }
  focus() {
    this.focused = true;
  }
  scrollIntoView() {}
  getBoundingClientRect() {
    return { x: 0, y: 0, width: this.clientWidth, height: this.clientHeight };
  }
}
function parse(html, parent) {
  const tree = new Element('fragment');
  const stack = [tree];
  for (const token of String(html).matchAll(/<\/?([a-z][a-z0-9-]*)([^>]*)>/gi)) {
    const [text, tag, attributes] = token;
    if (text.startsWith('</')) {
      for (let i = stack.length - 1; i > 0; i--)
        if (stack[i].tagName === tag.toUpperCase()) {
          stack.length = i;
          break;
        }
      continue;
    }
    const attrs = {};
    for (const match of attributes.matchAll(
      /([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g,
    ))
      attrs[match[1]] = match[2] ?? match[3] ?? match[4] ?? '';
    const node = new Element(tag, attrs, stack.at(-1));
    stack.at(-1).children.push(node);
    if (!['input', 'br', 'hr', 'img', 'meta', 'link'].includes(tag.toLowerCase())) stack.push(node);
  }
  for (const node of tree.children) node.parentElement = parent;
  return tree.children;
}

async function createHarness({ envelope, saved = {}, hash = '#eclipse', mobile = false } = {}) {
  assert(vm.SourceTextModule, 'Use node --experimental-vm-modules.');
  const staticRoot = path.resolve(__dirname, '../static');
  const requests = [],
    sceneCalls = [],
    storage = new Map();
  storage.set('companion.eclipse.view.0982', JSON.stringify(saved));
  storage.set('companion.eclipse.view.0995', JSON.stringify(saved));
  const scene = {
    captureView: () => ({ camera: { x: 127, y: -38, k: 2.25 }, selected: 'organization:e1' }),
  };
  let hooks, root;
  const timers = new Set();
  const timeouts = new Map();
  const location = { hash };
  const document = new Element('document');
  const window = new Element('window');
  window.matchMedia = () => ({ matches: mobile, addEventListener() {}, removeEventListener() {} });
  window.scrollTo = () => {};
  const context = vm.createContext({
    console,
    URLSearchParams,
    URL,
    AbortController,
    structuredClone,
    location,
    document,
    window,
    performance: { now: () => 1 },
    CustomEvent: class {
      constructor(type) {
        this.type = type;
      }
    },
    localStorage: {
      getItem: (key) => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key),
    },
    history: {
      replaceState: (_state, _title, hash) => {
        location.hash = hash;
      },
    },
    setTimeout: (fn, delay) => {
      const timer = setTimeout(() => {
        timers.delete(timer);
        timeouts.delete(timer);
        fn();
      }, delay);
      timers.add(timer);
      timeouts.set(timer, { fn, delay });
      return timer;
    },
    clearTimeout: (timer) => {
      clearTimeout(timer);
      timers.delete(timer);
      timeouts.delete(timer);
    },
    setInterval: (fn, delay) => {
      const timer = setInterval(fn, delay);
      timers.add(timer);
      return timer;
    },
    clearInterval: (timer) => {
      clearInterval(timer);
      timers.delete(timer);
    },
    requestAnimationFrame: (fn) => setTimeout(fn, 0),
    cancelAnimationFrame: clearTimeout,
    fetch: (url, options = {}) =>
      new Promise((resolve, reject) => {
        requests.push({
          url,
          options,
          resolve: (body, status = 200) =>
            resolve({ ok: status >= 200 && status < 300, status, json: async () => body }),
          reject,
        });
      }),
  });
  document.dispatchEvent = () => {};
  window.dispatchEvent = () => {};
  vm.runInContext(fs.readFileSync(path.join(staticRoot, 'eclipse.js'), 'utf8'), context);
  const container = new Element('main');
  const { escapeHTML } = await import('../../ui/static/format.js');
  container.innerHTML = window.Eclipse.render(envelope?.snapshot || {}, escapeHTML);
  root = container.querySelector('#eclipse');
  assert(root, 'Production render creates Observatory root');
  document.children = [container];
  const sceneModule = new vm.SyntheticModule(
    ['createScene'],
    function () {
      this.setExport('createScene', (_canvas, callbacks) => {
        hooks = callbacks;
        return new Proxy(scene, {
          get(target, name) {
            if (name in target) return target[name];
            return (...args) => {
              sceneCalls.push({ name, args });
              return undefined;
            };
          },
        });
      });
    },
    { context },
  );
  const modules = new Map();
  function load(file) {
    if (file === path.join(staticRoot, 'eclipse_scene.js')) return sceneModule;
    if (modules.has(file)) return modules.get(file);
    const mod = new vm.SourceTextModule(fs.readFileSync(file, 'utf8'), {
      context,
      identifier: file,
    });
    modules.set(file, mod);
    return mod;
  }
  const controllerModule = load(path.join(staticRoot, 'eclipse_controller.js'));
  await controllerModule.link((specifier, referring) =>
    load(path.resolve(path.dirname(referring.identifier), specifier)),
  );
  await controllerModule.evaluate();
  const controller = controllerModule.namespace.mount(root, envelope || {});
  const element = (selector) => {
    const result = root.querySelector(selector);
    assert(result, 'Production markup contains ' + selector);
    return result;
  };
  const click = (selector) => {
    const target = element(selector);
    target.emit('click');
    root.emit('click', { target });
  };
  const change = (selector, value, type = 'change') => {
    const target = element(selector);
    target.value = value;
    target.emit(type);
    root.emit(type, { target });
  };
  return {
    root,
    element,
    click,
    change,
    requests,
    sceneCalls,
    scene,
    storage,
    location,
    get hooks() {
      return hooks;
    },
    pendingTimeouts() {
      return [...timeouts.values()].map((timer) => timer.delay).sort((a, b) => a - b);
    },
    fireTimeout(delay) {
      const entry = [...timeouts.entries()].find(([, timer]) => timer.delay === delay);
      assert(entry, 'A pending timeout exists for ' + delay);
      const [timer, value] = entry;
      clearTimeout(timer);
      timers.delete(timer);
      timeouts.delete(timer);
      value.fn();
    },
    destroyController() {
      controller.destroy();
    },
    async settle() {
      for (let i = 0; i < 4; i++) await new Promise(setImmediate);
    },
    async waitForRequest(count, timeout = 2000) {
      const start = Date.now();
      while (requests.length < count && Date.now() - start < timeout)
        await new Promise((resolve) => setTimeout(resolve, 5));
      assert(requests.length >= count, 'Controller emitted request ' + count);
      return requests[count - 1];
    },
    destroy() {
      controller.destroy();
      for (const timer of timers) {
        clearTimeout(timer);
        clearInterval(timer);
      }
      timers.clear();
      timeouts.clear();
    },
  };
}
module.exports = { createHarness, Element };
