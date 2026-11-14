/** Focus/required-field contracts and stale case responses without a browser. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');
(async () => {
  const timers = [];
  const nodes = new Map();
  const document = {
    body: {},
    activeElement: null,
    querySelector: (key) => nodes.get(key) || null,
    querySelectorAll: () => [],
  };
  function node(id) {
    const attrs = {};
    return {
      id,
      attrs,
      innerHTML: '',
      textContent: '',
      isConnected: true,
      disabled: false,
      classList: { add() {}, remove() {}, toggle() {} },
      setAttribute(key, value) {
        attrs[key] = value;
      },
      removeAttribute(key) {
        delete attrs[key];
      },
      getAttribute(key) {
        return attrs[key] ?? null;
      },
      focus() {
        document.activeElement = this;
      },
      showModal() {
        this.open = true;
      },
      close() {
        this.open = false;
      },
    };
  }
  for (const key of ['#modal', '#modal-body', '#modal-title', '#main'])
    nodes.set(key, node(key.slice(1)));
  const context = vm.createContext({
    document,
    window: {},
    console,
    structuredClone,
    URLSearchParams,
    FormData,
    setTimeout: (fn) => {
      timers.push(fn);
      return fn;
    },
    clearTimeout() {},
  });
  const { application: app } = await loadApplication(context, { attach: false });
  for (const choices of [undefined, ['one', 'two']]) {
    const html = app.actions.field('Required value', 'value', '', {
      required: true,
      area: !choices,
      choices,
    });
    assert.match(html, choices ? /<select[^>]+required/ : /<textarea[^>]+required/);
  }
  nodes.get('#modal').contains = (element) => element === nodes.get('#modal-title');
  const opener = node('open');
  opener.innerHTML = 'Open dialog';
  opener.focus();
  await app.actions.busy(opener, async () => {
    assert.equal(opener.getAttribute('aria-busy'), 'true');
    app.actions.modal('Progress', '<p>Working</p>');
    assert.equal(nodes.get('#modal').getAttribute('aria-labelledby'), 'modal-title');
    assert.equal(document.activeElement.id, 'modal-title');
    app.actions.modal('Finished', '<p>Done</p>');
    assert.equal(document.activeElement.id, 'modal-title');
    app.actions.closeModal();
    app.actions.modal('Immediately reopened', '<p>Another result</p>');
    app.actions.closeModal();
  });
  timers.splice(0).forEach((fn) => fn());
  assert.equal(opener.disabled, false);
  assert.equal(opener.getAttribute('aria-busy'), null);
  assert.equal(document.activeElement, opener);
  app.actions.modal('Removed opener', '');
  opener.isConnected = false;
  app.actions.closeModal();
  timers.splice(0).forEach((fn) => fn());
  assert.equal(document.activeElement.id, 'main');
  const responses = {};
  app.actions.api = (url) =>
    new Promise((resolve) => {
      responses[url] = resolve;
    });
  app.actions.leadMarkup = () => app.state.editor.currentLead.case_id;
  const first = app.actions.leadPage('first', true);
  const second = app.actions.leadPage('second', true);
  const value = (id) => ({ case_id: id, case: { stage: 'in_progress' }, draft: { notes: id } });
  responses['/api/cases/second'](value('second'));
  assert.equal(await second, 'second');
  app.state.editor.dirty = true;
  responses['/api/cases/first'](value('first'));
  assert.equal(await first, '');
  assert.equal(app.state.editor.currentLead.case_id, 'second');
  assert.equal(app.state.editor.dirty, true, 'Late responses cannot discard newer unsaved state');
  const detached = app.actions.leadPage('detached', true);
  app.state.navigation.renderId++;
  responses['/api/cases/detached'](value('detached'));
  assert.equal(await detached, '');
  assert.equal(app.state.editor.currentLead.case_id, 'second');
  const region = node('toasts');
  region.children = [];
  region.append = (value) => {
    value.parent = region;
    region.children.push(value);
  };
  region.querySelectorAll = () =>
    region.children.filter((value) => !value.className.includes('error'));
  nodes.set('#toasts', region);
  document.createElement = (tag) => {
    const value = node(tag);
    value.children = [];
    value.listeners = {};
    value.append = (...children) => value.children.push(...children);
    value.addEventListener = (name, handler) => {
      value.listeners[name] = handler;
    };
    value.remove = () => {
      if (value.parent)
        value.parent.children = value.parent.children.filter((item) => item !== value);
    };
    return value;
  };
  app.actions.toast('Keep this error', true);
  for (let i = 1; i <= 5; i++) app.actions.toast('Saved ' + i);
  assert.equal(region.children.length, 4);
  assert.equal(region.children[0].children[0].textContent, 'Keep this error');
  assert.deepEqual(
    region.children.slice(1).map((notice) => notice.children[0].textContent),
    ['Saved 3', 'Saved 4', 'Saved 5'],
  );
  const close = region.children[0].children[1];
  assert.equal(close.getAttribute('aria-label'), 'Dismiss notification');
  close.listeners.click();
  assert.equal(region.children.length, 3, 'Dismiss is explicit and works for an error');
  console.log(
    'Modal focus, busy state, required controls, stale responses and bounded dismissible success notices passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
