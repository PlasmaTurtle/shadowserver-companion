/** Document-workbench boundaries, contextual actions and preserved form contracts. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');

(async () => {
  const nodes = new Map(),
    listeners = {};
  const document = {
    querySelector: (selector) => nodes.get(selector) || null,
    querySelectorAll: () => [],
    addEventListener: (type, fn) => {
      listeners[type] = fn;
    },
  };
  function node() {
    return {
      innerHTML: '',
      textContent: '',
      classList: { remove() {}, add() {} },
      focus() {
        document.activeElement = this;
      },
      scrollIntoView() {},
    };
  }
  for (const key of [
    '#sidebar',
    '#main',
    '#editor-content',
    '#save-state',
    '#contact-activity-compose',
    '#attempt-outcome',
    '#editor-tab-contact',
    '#editor-tab-notification',
  ])
    nodes.set(key, node());
  let allowLeave = false;
  const context = vm.createContext({
    document,
    window: { addEventListener() {} },
    console,
    structuredClone,
    URLSearchParams,
    FormData,
    setTimeout,
    clearTimeout,
    location: { hash: '' },
    confirm: () => allowLeave,
  });
  const { application: app } = await loadApplication(context, { attach: false });
  app.actions.setSidebarOpen = () => {};
  app.attach();
  const { editor, navigation, workflow } = app.state;
  navigation.boot = {
    settings: { agency: 'Synthetic agency', analyst_name: 'Reviewer' },
    explainers: [],
  };
  editor.currentLead = {
    id: 'entity1',
    case_id: 'case1',
    domain: 'example.com',
    company: 'Example <unsafe>',
    case: { stage: 'in_progress', version: 1, contact_email: 'team@example.com' },
    entries: [],
    evidence: [],
    reports: [],
    history: [],
    hostnames: [],
    domain_groups: [],
    narrative_groups: [],
    attempts: [],
    readiness: [{ key: 'source', ok: true }],
    section_history: [],
    approved_copy: {},
    draft_revision: 3,
    section_reviews: [
      'Introduction',
      'Vulnerabilities',
      'Attribution',
      'Information',
      'Closing',
    ].map((label) => ({
      key: label.toLowerCase(),
      label,
      status: 'draft',
      can_validate: true,
      issues: [],
    })),
  };
  editor.draft = {
    company: 'Example',
    report_date: '2026-11-11',
    intro: 'Unsaved introduction',
    selected_explainers: [],
    cve_records: [],
    cve_dispositions: {},
    include_appendix: true,
  };
  editor.currentLead.draft = structuredClone(editor.draft);
  let html = app.actions.leadMarkup();
  assert.match(html, /class="document-paper section-content/);
  assert.equal((html.match(/data-report-section=/g) || []).length, 5);
  assert.match(html, /<details class="investigation-context"><summary>/);
  assert.match(html, /class="report-certification"/);
  assert.doesNotMatch(html, /class="editor-sidebar/);
  assert.match(html, /Example &lt;unsafe&gt;/);
  assert.match(html, /href="#entity\/entity1\?tab=details">Edit entity/);

  editor.currentLead.section_reviews[0] = {
    key: 'introduction',
    label: 'Introduction',
    status: 'validated',
    validated_by: 'Reviewer',
    revision: 1,
    frozen_fields: {
      intro: 'Preserved introduction',
      report_date: '2026-11-10',
      include_appendix: false,
    },
  };
  html = app.actions.reportBuilderMarkup();
  assert.match(html, /Preserved introduction/);
  assert.doesNotMatch(html, /Unsaved introduction/);
  assert.equal(editor.draft.intro, 'Unsaved introduction');
  assert.match(
    html,
    /name="include_appendix" checked/,
    'Legacy frozen output flags must not replace the current delivery choice',
  );
  html = app.actions.appendixOverview();
  assert.match(html, /name="include_appendix"[^>]*>/);
  assert.doesNotMatch(html.match(/<input[^>]*name="include_appendix"[^>]*>/)[0], /disabled/);
  editor.currentLead.case.stage = 'pending_notification';
  assert.match(
    app.actions.appendixOverview().match(/<input[^>]*name="include_appendix"[^>]*>/)[0],
    /disabled/,
  );
  editor.currentLead.case.stage = 'in_progress';

  // Each workflow view owns its actions; report certification never follows the user into outreach.
  for (const tab of ['contact', 'closing', 'assets']) {
    editor.tab = tab;
    if (tab === 'assets') app.actions.assetsMarkup = () => '<section>Assets fixture</section>';
    html = app.actions.leadMarkup();
    assert.doesNotMatch(html, /data-action="(?:save|preview|finalize)"/);
    assert.doesNotMatch(html, /class="report-certification/);
  }
  editor.tab = 'contact';
  html = app.actions.leadMarkup();
  assert.match(html, /<details class="saved-plan-editor"><summary>Edit contact plan/);
  assert.match(html, /<details id="contact-activity-compose" class="contact-activity-compose">/);
  for (const name of [
    'contact_name',
    'contact_email',
    'contact_phone',
    'occurred_at',
    'report_id',
    'information_source',
    'recorded_by',
  ])
    assert.match(html, new RegExp(`name="${name}"`));
  assert(html.indexOf('Recent activity') < html.indexOf('id="case-attempt"'));
  app.actions.busy = async (_button, fn) => fn();
  const activity = { dataset: { action: 'open-contact-activity' } };
  await listeners.click({
    target: { closest: (selector) => (selector === 'button,[data-open-lead]' ? activity : null) },
  });
  assert.equal(nodes.get('#contact-activity-compose').open, true);
  assert.equal(document.activeElement, nodes.get('#attempt-outcome'));

  editor.tab = 'closing';
  html = app.actions.leadMarkup();
  assert.match(html, /id="case-close"/);
  assert.match(html, /name="intent" value="preview"/);
  assert.match(html, /name="intent" value="close"/);
  assert.match(html, /type="checkbox" name="reviewed"/);
  assert.match(html, /<details class="closing-history">/);

  // Tab switching guards contact work and preserves the report draft in memory.
  app.actions.loadContactDiscovery = async () => {};
  app.actions.stopContactDiscoveryPolling = () => {};
  const switchTo = async (tab) => {
    const button = { dataset: { tab } };
    await listeners.click({
      target: { closest: (selector) => (selector === 'button,[data-open-lead]' ? button : null) },
    });
  };
  workflow.workflowDirty = true;
  await switchTo('contact');
  assert.equal(editor.tab, 'closing');
  allowLeave = true;
  editor.dirty = true;
  await switchTo('contact');
  assert.equal(editor.tab, 'contact');
  assert.equal(editor.dirty, true);
  assert.equal(editor.draft.intro, 'Unsaved introduction');
  assert.match(nodes.get('#main').innerHTML, /data-action="open-contact-activity"/);
  await switchTo('notification');
  assert.doesNotMatch(nodes.get('#main').innerHTML, /data-action="open-contact-activity"/);

  // Saving and evidence refresh no longer require the removed permanent sidebar.
  app.actions.api = async () => structuredClone(editor.currentLead);
  editor.currentLead.draft = structuredClone(editor.draft);
  await app.actions.saveDraft();
  assert.equal(editor.dirty, false);
  assert.equal(nodes.get('#save-state').textContent, 'Saved locally');
  assert.match(nodes.get('#editor-content').innerHTML, /report-certification/);
  editor.currentLead.section_reviews.forEach((section) => {
    section.status = 'validated';
  });
  assert.match(app.actions.caseSidebar(), /data-action="finalize" >/);
  editor.currentLead.readiness[0].ok = false;
  assert.match(app.actions.caseSidebar(), /data-action="finalize" disabled/);
  console.log(
    'Investigation canvas, contextual actions, independent output choices, saved snapshots, form disclosures and dirty-state guards passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
