const assert = require('node:assert/strict');
const vm = require('node:vm');

(async () => {
  const nodes = new Map();
  const node = (selector) => {
    if (!nodes.has(selector))
      nodes.set(selector, {
        innerHTML: '',
        outerHTML: '',
        classList: { add() {}, remove() {}, toggle() {} },
      });
    return nodes.get(selector);
  };
  const context = vm.createContext({
    document: { querySelector: node, querySelectorAll: () => [] },
    window: {},
    console,
    URLSearchParams,
    FormData,
    Date,
    Number,
    String,
    structuredClone,
    setTimeout,
    clearTimeout,
    location: { hash: '' },
  });
  const { application: app } = await require('./frontend_harness.cjs').loadApplication(context, {
    attach: false,
  });
  const rows = Array.from({ length: 121 }, (_, index) => ({
    entry_id: `row-${index}`,
    hostname: index === 0 ? '<script>bad</script>' : `host${index}.example.com`,
    ip: index === 0 ? '10.1.2.3' : '8.8.8.8',
    service: 'tcp 443',
    finding: 'eol-php',
    included: true,
    requires_review: index === 0,
    issue: index === 0 ? 'Nonpublic address' : '',
    source: { workbook: 'test.csv', sheet: 'CSV', row: index + 2 },
    observed_at: '2026-11-13',
  }));
  app.state.editor.currentLead = {
    id: 'entity',
    case_id: 'case',
    case: { version: 4, stage: 'in_progress' },
    draft_revision: 3,
    draft: {},
    observation_scope: {
      total: 121,
      included: 121,
      finding_observations: 120,
      excluded: 0,
      unresolved: 1,
      rows,
      editable: true,
    },
    section_reviews: [{ key: 'introduction', status: 'validated' }],
  };
  app.state.editor.draft = {};
  let modal = '',
    body,
    applied = 0,
    saved = 0,
    closed = 0;
  Object.assign(app.actions, {
    modal: (title, html) => {
      modal = html;
    },
    closeModal: () => {
      closed++;
    },
    toast() {},
    saveDraft: async () => {
      saved++;
      app.state.editor.dirty = false;
    },
    api: async (url, options) => {
      assert.equal(url, '/api/cases/case/observation-scope');
      body = options.body;
      return { draft: {}, scope_reopened_sections: ['introduction'] };
    },
    applyNotificationMutation: () => {
      applied++;
    },
  });
  let html = app.actions.observationScopeMarkup();
  assert.equal((html.match(/data-action="scope-review-row"/g) || []).length, 50);
  assert(
    html.includes('1–50 of 121') &&
      html.includes(
        '121 included source observations · 120 with findings · 0 excluded · 1 need review',
      ),
  );
  assert(html.includes('&lt;script&gt;bad&lt;/script&gt;') && !html.includes('<script>bad'));
  assert(html.includes('original evidence stays in the internal record'));
  app.actions.scopePage(1);
  assert(node('#observation-scope-panel').outerHTML.includes('51–100 of 121'));
  app.actions.scopeSearch('host120');
  assert(node('#observation-scope-panel').outerHTML.includes('1–1 of 1'));
  app.state.editor.dirty = true;
  await app.actions.openScopeAnomalies();
  assert.equal(saved, 1);
  assert(modal.includes('reopen_affected') && modal.includes('required'));
  assert(modal.includes('&lt;script&gt;bad&lt;/script&gt;'));
  await app.actions.submitObservationScope(
    { dataset: { case: 'case' }, isConnected: true },
    { reason: 'Bad source address', reopen_affected: 'true' },
  );
  assert.deepEqual(JSON.parse(JSON.stringify(body)), {
    expected_version: 4,
    expected_revision: 3,
    entry_ids: ['row-0'],
    decision: 'exclude',
    reason: 'Bad source address',
    reopen_affected: true,
  });
  assert.equal(applied, 1);
  assert.equal(closed, 1);
  await app.actions.openScopeRow({ dataset: { entryId: 'row-1' } });
  app.state.editor.currentLead.case_id = 'other-case';
  await assert.rejects(
    () =>
      app.actions.submitObservationScope({ dataset: { case: 'case' } }, { reason: 'Stale action' }),
    /notification changed/,
  );
  assert.equal(applied, 1);
  app.state.editor.currentLead.case_id = 'case';
  // A response may arrive after another dialog was opened for this same case.
  let finish;
  app.actions.api = async (url, options) => {
    body = options.body;
    return await new Promise((resolve) => {
      finish = resolve;
    });
  };
  await app.actions.openScopeRow({ dataset: { entryId: 'row-1' } });
  const firstForm = { dataset: { case: 'case' }, isConnected: true };
  const firstSave = app.actions.submitObservationScope(firstForm, { reason: 'First decision' });
  await app.actions.openScopeRow({ dataset: { entryId: 'row-2' } });
  firstForm.isConnected = false;
  finish({ draft: {}, scope_reopened_sections: [] });
  await firstSave;
  assert.equal(closed, 1, 'Late response must not close the replacement scope dialog');
  app.actions.api = async (url, options) => {
    body = options.body;
    return { draft: {} };
  };
  await app.actions.submitObservationScope(
    { dataset: { case: 'case' }, isConnected: true },
    { reason: 'Second decision' },
  );
  assert.equal(body.entry_ids[0], 'row-2', 'New pending scope survives the first response');
  assert.equal(closed, 2);
  await app.actions.openScopeRow({ dataset: { entryId: 'row-3' } });
  const replacedForm = { dataset: { case: 'case' }, isConnected: true };
  app.actions.api = async () =>
    await new Promise((resolve) => {
      finish = resolve;
    });
  const replacedSave = app.actions.submitObservationScope(replacedForm, {
    reason: 'Third decision',
  });
  replacedForm.isConnected = false;
  app.actions.modal('Different dialog', 'User is now editing another form');
  finish({ draft: {} });
  await replacedSave;
  assert.equal(closed, 2, 'Late response must not close an unrelated same-case dialog');
  app.state.editor.currentLead.observation_scope.editable = false;
  html = app.actions.observationScopeMarkup();
  assert(!html.includes('scope-review-row') && !html.includes('scope-exclude-anomalies'));
  console.log(
    'Observation scope UI: pagination, escaping, explicit reasons, versioning and navigation guards passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
