const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');

(async () => {
  const nodes = new Map();
  for (const id of ['#main', '#editor-content', '#modal', '#modal-title', '#modal-body'])
    nodes.set(id, { innerHTML: '', textContent: '', open: true });
  const context = vm.createContext({
    console,
    structuredClone,
    URLSearchParams,
    setTimeout,
    clearTimeout,
    document: { querySelector: (id) => nodes.get(id) || null, querySelectorAll: () => [] },
    window: {},
  });
  const { application: app } = await loadApplication(context, { attach: false });
  const { editor, navigation } = app.state;
  app.actions.leadMarkup = () => 'rendered';
  app.actions.toast = () => {};
  app.actions.closeModal = () => {};
  app.actions.editorContent = () => 'content';
  app.actions.scheduleNarrative = () => {};
  app.actions.saveDraft = () => {
    throw new Error('Reopening must not force a save');
  };
  const value = (id, draft = {}) => ({
    id: 'entity',
    case_id: id,
    draft,
    draft_revision: 4,
    case: { stage: 'in_progress', version: 4 },
    entries: [],
    section_reviews: [],
  });
  editor.currentLead = value('previous');
  editor.reportSection = 'Closing';
  app.actions.api = async () => value('next');
  await app.actions.leadPage('next', true);
  assert.equal(editor.reportSection, 'Introduction');
  editor.reportSection = 'Attribution';
  await app.actions.leadPage('next', true);
  assert.equal(editor.reportSection, 'Attribution', 'Same case retains the working section');

  const original = {
    notes: 'Saved',
    narrative_values: { one: { software: 'Saved' } },
    resources: 'Unchanged',
  };
  editor.currentLead = value('next', structuredClone(original));
  editor.draft = { ...structuredClone(original), notes: 'Unsaved before request' };
  editor.dirty = true;
  let resolve;
  let submitted;
  app.actions.api = (url, options) => {
    submitted = { url, options };
    return new Promise((done) => {
      resolve = done;
    });
  };
  const reopening = app.actions.submitReopen(
    { id: 'section-reopen-form', dataset: { case: 'next', section: 'attribution' } },
    { reason: 'Add website evidence' },
  );
  editor.draft.notes = 'Edited while reopening';
  editor.draft.narrative_values.one.software = 'Also unsaved';
  resolve({ ...value('next', structuredClone(original)), draft_revision: 5 });
  await reopening;
  assert.equal(submitted.options.body.expected_revision, 4);
  assert.equal(editor.currentLead.draft_revision, 5);
  assert.equal(editor.draft.notes, 'Edited while reopening');
  assert.equal(editor.draft.narrative_values.one.software, 'Also unsaved');
  assert.equal(editor.dirty, true);
  assert.equal(editor.reportSection, 'Attribution');

  const late = app.actions.submitReopen(
    { id: 'section-reopen-form', dataset: { case: 'next', section: 'closing' } },
    { reason: 'Correction' },
  );
  editor.currentLead = value('different', { notes: 'Other notification' });
  editor.draft = { notes: 'Newer edits elsewhere' };
  navigation.renderId++;
  resolve(value('next', original));
  await late;
  assert.equal(editor.currentLead.case_id, 'different');
  assert.equal(editor.draft.notes, 'Newer edits elsewhere');

  editor.currentLead = value('cve');
  editor.currentLead.entries = [
    {
      source: { fields: { tag: 'CVE-2025-1234 CVE-2025-5678' } },
      normalized: { case_condition_scope: true, active_conditions: ['CVE-2025-5678'] },
    },
  ];
  editor.draft = { cve_records: [] };
  app.actions.sectionLocked = () => false;
  app.actions.modal = (title) => {
    nodes.get('#modal-title').textContent = title;
  };
  app.actions.markDirty = () => {
    editor.dirty = true;
  };
  const record = { id: 'CVE-2025-5678', verification_status: 'published', local_only: true };
  app.actions.api = async (url, options) => {
    assert.equal(url, '/api/source-jobs');
    assert.equal(options.body.local_only, true);
    assert.deepEqual([...options.body.cve_ids], ['CVE-2025-5678']);
    return { id: 'job', status: 'completed', results: [record], errors: [] };
  };
  await app.actions.retrieveCveSources();
  assert.equal(editor.draft.cve_records[0].id, record.id);
  assert.equal(editor.pendingCveRefresh, null, 'Available local records do not require acceptance');
  console.log(
    'Local CVE adoption, report scope, section reset, and unsaved reopen regressions passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
