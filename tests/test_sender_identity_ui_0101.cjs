/** Sender changes are explicit in the editor and never offered on certified records. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');

(async () => {
  const context = vm.createContext({
    console,
    structuredClone,
    URLSearchParams,
    FormData,
    setTimeout,
    clearTimeout,
    document: { querySelector: () => null, querySelectorAll: () => [] },
    window: {},
  });
  const { application: app } = await loadApplication(context, { attach: false });
  Object.assign(app.actions, {
    entityUpdateMarkup: () => '',
    field: () => '',
    templateMarkup: () => '',
    sectionLocked: () => false,
    historicalReportNotice: () => '',
  });
  const draft = {
    sender_name: 'Saved Analyst',
    sender_title: '',
    sender_profile: { agency: 'Saved Office', office: '<Regional Office>' },
    subject: 'Notification',
    intro: 'Saved report introduction',
  };
  app.state.editor.reportSection = 'Introduction';
  app.state.editor.draft = draft;
  app.state.editor.currentLead = {
    id: 'entity-1',
    case_id: 'case-1',
    case: { stage: 'in_progress' },
    sender_profile_update_available: true,
    draft,
  };
  let markup = app.actions.reportSectionContent();
  assert.match(markup, /Saved Analyst\nSaved Office\n&lt;Regional Office&gt;/);
  assert.match(markup, /Sender settings have changed/);
  assert.match(markup, /Review sender update/);
  assert.match(markup, /Settings changes do not rewrite existing reports/);
  app.state.editor.currentLead.sender_profile_update_available = false;
  markup = app.actions.reportSectionContent();
  assert.doesNotMatch(markup, /Review sender update/);
  app.state.editor.currentLead.case.stage = 'pending_notification';
  app.state.editor.currentLead.sender_profile_update_available = true;
  markup = app.actions.reportSectionContent();
  assert.match(markup, /retains the wording, sender and source records used at certification/);
  assert.doesNotMatch(markup, /Review sender update|Adopt current report format/);
  console.log('Sender identity editor safeguards passed');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
