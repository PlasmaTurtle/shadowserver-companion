/** Guided identity adoption and next-action links through production modules. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');

(async () => {
  const nodes = new Map();
  const node = (selector) => {
    if (!nodes.has(selector))
      nodes.set(selector, {
        innerHTML: '',
        textContent: '',
        dataset: {},
        setAttribute() {},
        removeAttribute() {},
        classList: { add() {}, remove() {}, toggle() {} },
        focus() {},
        showModal() {
          this.open = true;
        },
      });
    return nodes.get(selector);
  };
  const location = { hash: '#workspace/notifications/one?tab=notification' };
  const context = vm.createContext({
    console,
    structuredClone,
    URLSearchParams,
    FormData,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    location,
    document: {
      querySelector: node,
      querySelectorAll: () => [],
      body: { dataset: {}, classList: { toggle() {} } },
    },
    window: {
      scrollY: 0,
      scrollTo() {},
      Eclipse: { destroy() {} },
      matchMedia: () => ({ matches: false }),
    },
    history: {
      replaceState(_s, _t, url) {
        location.hash = url;
      },
    },
    confirm: () => true,
  });
  const { application: app } = await loadApplication(context, { attach: false });
  const module = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../static/modules/entity_leads_events.js'), 'utf8'),
    { context },
  );
  await module.link(() => {
    throw Error('Unexpected dependency');
  });
  await module.evaluate();
  const handlers = module.namespace.createHandlers(app);
  const make = (id, version = 5) => ({
    id: 'entity-' + id,
    case_id: id,
    draft_revision: version,
    case: { stage: 'in_progress', version },
    company: 'Old business',
    domain: 'example.com',
    entity_profile: {},
    current_entity: { company: '<New business>', domain: 'example.com', entity_profile: {} },
    draft: { notes: 'Saved', company: 'Old business' },
    section_reviews: [],
  });
  function open(id) {
    app.state.editor.currentLead = make(id);
    app.state.editor.draft = structuredClone(app.state.editor.currentLead.draft);
    app.state.editor.dirty = false;
    app.state.navigation.renderId++;
  }
  let modalHTML = '',
    modalCount = 0,
    closes = 0;
  const renderModal = app.actions.modal;
  app.actions.modal = (_title, html) => {
    renderModal(_title, html);
    modalHTML = html;
    modalCount++;
  };
  app.actions.closeModal = () => {
    closes++;
  };
  app.actions.toast = () => {};
  app.actions.editorContent = () => 'Editor';
  const plan = {
    case_id: 'one',
    expected_version: 5,
    expected_entity_revision: 7,
    changed: true,
    changes: [
      { key: 'company', label: 'Business name', before: 'Old business', after: '<New business>' },
    ],
    affected_sections: ['introduction', 'vulnerabilities', 'attribution'],
    reopen_sections: ['introduction', 'vulnerabilities', 'attribution'],
  };
  const requests = [];
  let finish;
  app.actions.api = async (url, options) => {
    requests.push({ url, options });
    if (!options) return structuredClone(plan);
    return new Promise((resolve) => {
      finish = resolve;
    });
  };
  open('one');
  assert.match(app.actions.entityUpdateMarkup(), /reviewed business details/);
  await handlers.actions['use-entity-details']();
  assert.equal(requests.length, 1, 'Opening the plan does not mutate or reopen anything');
  assert.match(modalHTML, /&lt;New business&gt;/);
  assert.match(modalHTML, /Introduction, Vulnerabilities, Attribution/);
  assert.match(modalHTML, /Other validated sections stay frozen/);
  assert.match(modalHTML, /required/);
  let pending = handlers.forms['adopt-entity-details-form'](
    { dataset: { case: 'one' }, isConnected: true },
    { reason: 'Confirmed official identity' },
  );
  assert.equal(requests[1].options.body.expected_entity_revision, 7);
  assert.equal(requests[1].options.body.expected_version, 5);
  assert.equal(requests[1].options.body.reopen_affected, true);
  assert.equal(requests[1].options.body.reason, 'Confirmed official identity');
  app.state.editor.dirty = true;
  app.state.editor.draft.notes = 'New note while adoption is saving';
  finish({
    ...make('one', 6),
    company: '<New business>',
    draft: { notes: 'Saved', company: '<New business>' },
  });
  await pending;
  assert.equal(app.state.editor.draft.company, '<New business>');
  assert.equal(app.state.editor.draft.notes, 'New note while adoption is saving');
  assert.equal(closes, 1);

  // A stale request cannot close another notification's dialog or replace it.
  open('one');
  await handlers.actions['use-entity-details']();
  pending = handlers.forms['adopt-entity-details-form'](
    { dataset: { case: 'one' } },
    { reason: 'Reviewed' },
  );
  open('two');
  finish(make('one', 6));
  await pending;
  assert.equal(app.state.editor.currentLead.case_id, 'two');
  assert.equal(closes, 1);
  await assert.rejects(
    handlers.forms['adopt-entity-details-form'](
      { dataset: { case: 'one' } },
      { reason: 'Late click' },
    ),
    /notification changed/,
  );

  // Saving this case must not dismiss a replacement dialog on the same case.
  open('one');
  await handlers.actions['use-entity-details']();
  const detachedForm = { dataset: { case: 'one' }, isConnected: true };
  pending = handlers.forms['adopt-entity-details-form'](detachedForm, { reason: 'Reviewed' });
  detachedForm.isConnected = false;
  app.actions.modal('Different review', '<textarea>New unsaved reason</textarea>');
  finish(make('one', 6));
  await pending;
  assert.equal(closes, 1, 'A completed adoption cannot close a different dialog');
  assert.match(modalHTML, /New unsaved reason/);

  // A late plan response must not open a dialog on another case.
  open('one');
  app.actions.api = () =>
    new Promise((resolve) => {
      finish = resolve;
    });
  const priorCount = modalCount;
  pending = handlers.actions['use-entity-details']();
  open('two');
  finish(structuredClone(plan));
  await pending;
  assert.equal(modalCount, priorCount);

  // A later dialog on the same case also supersedes a pending plan request.
  open('one');
  pending = handlers.actions['use-entity-details']();
  app.actions.modal('Scope decision', '<textarea>Another unsaved reason</textarea>');
  const replacementCount = modalCount;
  finish(structuredClone(plan));
  await pending;
  assert.equal(modalCount, replacementCount, 'Late plan cannot replace a newer dialog');
  assert.match(modalHTML, /Another unsaved reason/);

  assert.equal(
    app.actions.workspaceActionURL({
      id: 'case/one',
      action_tab: 'notification',
      action_section: 'Vulnerabilities',
    }),
    '#workspace/notifications/case%2Fone?tab=notification&section=Vulnerabilities',
  );
  assert(
    !app.actions
      .workspaceActionURL({ id: 'one', action_tab: 'notification', action_section: '<script>' })
      .includes('section='),
  );
  open('one');
  app.actions.leadMarkup = () => 'Editor';
  app.state.navigation.currentRoute = 'workspace/notifications/one?tab=notification';
  location.hash = '#workspace/notifications/one?tab=notification&section=Vulnerabilities';
  await app.actions.route();
  assert.equal(app.state.editor.reportSection, 'Vulnerabilities');
  location.hash = '#workspace/notifications/one?tab=notification&section=Untrusted';
  await app.actions.route();
  assert.equal(app.state.editor.reportSection, 'Vulnerabilities');
  console.log(
    'Workday guidance UI: plans, atomic payload, edit preservation, stale views and direct section navigation passed',
  );
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
