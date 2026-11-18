/** Notification mutations retain newer edits and never cross notification boundaries. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');

(async () => {
  const nodes = new Map();
  for (const id of ['#main', '#editor-content', '#save-state'])
    nodes.set(id, { innerHTML: '', textContent: '', classList: { add() {}, remove() {} } });
  const context = vm.createContext({
    console,
    structuredClone,
    URLSearchParams,
    FormData,
    setTimeout,
    clearTimeout,
    document: { querySelector: (id) => nodes.get(id) || null, querySelectorAll: () => [] },
    window: {},
  });
  const { application: app } = await loadApplication(context, { attach: false });
  const events = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../static/modules/editor_events.js'), 'utf8'),
    { context },
  );
  await events.link(() => {
    throw Error('Unexpected import');
  });
  await events.evaluate();
  const handlers = events.namespace.createHandlers(app);
  const { editor, navigation } = app.state;
  const record = (id, revision = 1, draft = { notes: 'Saved', reviewed: true }) => ({
    id: 'entity-' + id,
    case_id: id,
    draft_revision: revision,
    draft,
    case: { stage: 'in_progress' },
    section_reviews: [],
    evidence: [
      {
        id: 'evidence-' + id,
        included: false,
        caption: 'A website',
        source_url: 'https://example.com',
        captured_at: '2026-11-13T00:00:00Z',
      },
    ],
  });
  function open(id) {
    editor.currentLead = record(id);
    editor.draft = structuredClone(editor.currentLead.draft);
    editor.dirty = false;
    navigation.renderId++;
  }
  let repaints = 0;
  app.actions.editorContent = () => {
    repaints++;
    return 'Report editor';
  };
  app.actions.toast = () => {};
  const screenshot = () => new FormData();
  const captured = { captured_at: '2026-11-13T00:00' };
  let complete;
  app.actions.api = () =>
    new Promise((resolve) => {
      complete = resolve;
    });
  open('one');
  let pending = handlers.forms['evidence-form']({}, captured, screenshot());
  editor.draft.notes = 'Typed while the screenshot was attaching';
  editor.dirty = true;
  complete(record('one', 2, { notes: 'Saved', reviewed: false }));
  await pending;
  assert.equal(editor.currentLead.draft_revision, 2);
  assert.equal(editor.draft.notes, 'Typed while the screenshot was attaching');
  assert.equal(editor.draft.reviewed, false, 'Server invalidation is retained beside newer edits');
  assert.equal(editor.dirty, true);
  assert.equal(repaints, 1);

  open('one');
  pending = handlers.forms['evidence-form']({}, captured, screenshot());
  open('two');
  const previousRepaints = repaints;
  complete(record('one', 3));
  await pending;
  assert.equal(editor.currentLead.case_id, 'two');
  assert.equal(repaints, previousRepaints, 'A late attachment does not replace another view');

  // Leaving and returning to the same notification still invalidates an old view response.
  open('one');
  pending = handlers.forms['evidence-form']({}, captured, screenshot());
  navigation.renderId++;
  editor.draft.notes = 'Reopened notification';
  complete(record('one', 4));
  await pending;
  assert.equal(editor.draft.notes, 'Reopened notification');

  // Do not submit an upload to a different case when navigation happens during autosave.
  open('one');
  editor.dirty = true;
  let finishSave;
  const saveDraft = app.actions.saveDraft;
  app.actions.saveDraft = () =>
    new Promise((resolve) => {
      finishSave = resolve;
    });
  let calls = 0;
  app.actions.api = async () => {
    calls++;
    return record('two');
  };
  pending = handlers.forms['evidence-form']({}, captured, screenshot());
  open('two');
  finishSave();
  await pending;
  assert.equal(calls, 0);
  app.actions.saveDraft = saveDraft;

  // Toggling an existing attachment cannot refresh the record currently on screen.
  open('one');
  const toggle = handlers.change.find((handler) =>
    handler.matches({ dataset: { evidence: 'evidence-one' } }),
  );
  const checkbox = { dataset: { evidence: 'evidence-one' }, checked: true, disabled: false };
  const requests = [];
  app.actions.api = (url) => {
    requests.push(url);
    return new Promise((resolve) => {
      complete = resolve;
    });
  };
  pending = toggle.run(checkbox);
  assert.equal(checkbox.disabled, true);
  open('two');
  complete({ included: true });
  await pending;
  assert.deepEqual(requests, ['/api/evidence/evidence-one']);
  assert.equal(editor.currentLead.case_id, 'two');

  // A Library read begun on one report cannot replace another report's selections.
  open('one');
  editor.draft.selected_explainers = ['general'];
  navigation.boot = { explainers: [] };
  pending = handlers.actions['adopt-blocks']();
  open('two');
  editor.draft.explainer_snapshots = [{ id: 'other', body: 'Keep this' }];
  complete([{ id: 'general', body: 'New library text' }]);
  await pending;
  assert.equal(editor.draft.explainer_snapshots[0].body, 'Keep this');

  // A background attachment must not erase an in-progress Contact & delivery form.
  open('one');
  const mutation = app.actions.notificationContext();
  app.state.workflow.workflowDirty = true;
  nodes.get('#editor-content').innerHTML = 'Unsaved contact form';
  app.actions.applyNotificationMutation(record('one', 2), mutation);
  assert.equal(nodes.get('#editor-content').innerHTML, 'Unsaved contact form');
  app.state.workflow.workflowDirty = false;

  const entityEvents = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../static/modules/entity_leads_events.js'), 'utf8'),
    { context },
  );
  await entityEvents.link(() => {
    throw Error('Unexpected import');
  });
  await entityEvents.evaluate();
  open('one');
  app.actions.modal = () => {};
  app.actions.closeModal = () => {};
  app.actions.api = () =>
    new Promise((resolve) => {
      complete = resolve;
    });
  const entityHandlers = entityEvents.namespace.createHandlers(app);
  pending = entityHandlers.actions['use-entity-details']();
  complete({
    case_id: 'one',
    changed: true,
    expected_version: 1,
    expected_entity_revision: 2,
    changes: [{ label: 'Business name', before: 'Old name', after: 'New business name' }],
    reopen_sections: [],
  });
  await pending;
  pending = entityHandlers.forms['adopt-entity-details-form'](
    { dataset: { case: 'one' } },
    { reason: 'Reviewed business identity' },
  );
  editor.draft.notes = 'Edited during entity adoption';
  editor.dirty = true;
  complete(record('one', 2, { notes: 'Saved', company: 'New business name', reviewed: false }));
  await pending;
  assert.equal(editor.draft.company, 'New business name');
  assert.equal(editor.draft.notes, 'Edited during entity adoption');
  assert.equal(editor.dirty, true);

  // Closing shows exactly the grouped resources and sender retained in its report model.
  open('one');
  editor.reportSection = 'Closing';
  editor.currentLead.report_model = {
    exhibits: [
      {
        type: 'closing',
        responsibility: 'Recipient statement.',
        closing: 'Thank you.',
        resource_groups: [
          {
            title: 'Reporting and assistance',
            items: [
              { label: 'Verified assistance', url: 'https://example.com/help', active: true },
            ],
          },
        ],
        sender_lines: ['Recorded sender', 'Recorded office'],
        appendix_note: 'Appendix note.',
      },
    ],
  };
  navigation.boot.settings = { agency: 'Changed agency', office: 'Changed office' };
  app.actions.appendixOverview = () => '';
  const html = app.actions.reportSectionContent();
  assert.match(html, /Verified assistance/);
  assert.match(html, /Recorded office/);
  assert(!html.includes('Changed office'));
  assert(!html.includes('<h3>Responsibility</h3>'));
  assert.match(html, /excluded from recipient reports/);
  editor.reportSection = 'Introduction';
  editor.currentLead.report_model.sections = [
    {
      kind: 'introduction',
      model: {
        severity_from_source: true,
        severity: 'High, Critical',
      },
    },
  ];
  app.actions.entityUpdateMarkup = () => '';
  app.actions.templateMarkup = () => '';
  app.actions.documentPresentation = () => '';
  const introduction = app.actions.reportSectionContent();
  assert.match(introduction, /value="High, Critical" readonly/);
  assert(
    !introduction.includes('name="severity"'),
    'Source severity must not offer edits that saving discards',
  );
  editor.currentLead.section_reviews = [
    {
      key: 'introduction',
      status: 'validated',
      frozen_fields: {
        severity: 'Not specified',
        narrative_revision: 'report-start-2026-11-12-v5',
      },
      frozen_context: { report_model: { exhibits: [] } },
      snapshot: {
        nodes: [
          {
            kind: 'introduction',
            model: { severity_from_source: true, severity: 'High, Critical' },
          },
        ],
      },
    },
  ];
  const frozen = app.actions.reportBuilderMarkup();
  assert.match(
    frozen,
    /value="High, Critical" readonly/,
    'Frozen section uses its retained model, including mixed severity',
  );
  console.log(
    'Notification evidence races, unsaved edits, view isolation, Library adoption and closing-model fidelity passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
