/** Outcome-aware contacts, deliberate batch selection, and copy-only outreach. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');
(async () => {
  const nodes = new Map(),
    calls = [],
    clipboard = [];
  const node = (id) => {
    if (!nodes.has(id)) nodes.set(id, { innerHTML: '', outerHTML: '', value: '', checked: false });
    return nodes.get(id);
  };
  const context = vm.createContext({
    console,
    URL,
    URLSearchParams,
    structuredClone,
    setTimeout: () => 1,
    clearTimeout() {},
    clearInterval() {},
    document: { querySelector: node, querySelectorAll: () => [] },
    window: { Eclipse: { destroy() {} } },
    navigator: { clipboard: { writeText: async (text) => clipboard.push(text) } },
  });
  const { application: app } = await loadApplication(context, { attach: false });
  const { state: s, actions: a } = app;
  a.toast = () => {};
  let modal = '';
  a.modal = (_title, html) => {
    modal = html;
  };
  a.closeModal = () => {};
  const candidate = {
    id: 'candidate',
    revision: 4,
    kind: 'email',
    value: 'security@example.com',
    purpose: 'security',
    decision: 'confirmed',
    unusable: true,
    usable: false,
    usability_reason: 'bounced',
    sources: [],
  };
  s.editor.currentLead = {
    id: 'entity',
    case_id: 'case',
    case: { version: 1, stage: 'pending_notification' },
  };
  s.editor.tab = 'contact';
  s.contacts.entities.set('entity', { roots: [], candidates: [candidate] });
  let html = a.contactDiscoveryMarkup();
  assert.match(html, /Unavailable · bounced/);
  assert.doesNotMatch(html, /data-contact-use=/);
  assert.match(html, /data-route-action="restore"/);
  assert.doesNotMatch(html, /Prepare outreach/);
  assert.doesNotMatch(html, /Saved contact summary/);
  assert.match(html, /data-contact-detail="details"><summary>Sources &/);
  candidate.preferred = true;
  assert.match(a.contactDiscoveryMarkup(), /Preferred/);
  a.openContactRouteDecision('candidate', 'restore');
  assert.match(modal, /Reason/);
  a.api = async (url, opts = {}) => {
    calls.push([url, opts]);
    return { candidates: [{ ...candidate, usable: true, unusable: false }] };
  };
  await a.saveContactRouteDecision({ reason: 'Recipient verified mailbox restored' });
  assert.equal(calls.at(-1)[1].body.expected_revision, 4);
  assert.equal(calls.at(-1)[1].body.action, 'restore');
  // Nothing is selected implicitly, and a filter change cannot broaden a batch.
  s.navigation.currentRoute = 'leads';
  s.contacts.batchEntityIds = Array.from({ length: 30 }, (_, n) => `business-${n}`);
  const baseline = calls.length;
  await a.startContactBatch();
  assert.equal(calls.length, baseline);
  s.contacts.selectedEntityIds = new Set(s.contacts.batchEntityIds);
  await assert.rejects(a.startContactBatch(), /up to 25/);
  s.contacts.selectedEntityIds = new Set(['business-14', 'business-23', 'no-longer-visible']);
  assert.match(a.contactBatchMarkup(), /1 selected outside this view will not be included/);
  a.api = async (url, opts = {}) => {
    calls.push([url, opts]);
    return { id: 'batch', state: 'completed', total: 2, completed: 2 };
  };
  await a.startContactBatch();
  assert.deepEqual(Array.from(calls.at(-1)[1].body.entity_ids), ['business-14', 'business-23']);
  a.clearContactSelection();
  assert.equal(s.contacts.selectedEntityIds.size, 0);
  assert.match(a.contactBatchMarkup(), /No businesses selected in this view/);
  // Handoff is a read; all report/source/editor text is escaped and nothing is sent.
  const handoff = {
    case_id: 'case',
    ready: false,
    blockers: ['Outreach is do not contact'],
    warnings: [],
    contact: { value: 'security@example.com' },
    source_explanation: '<img src=x onerror=alert(1)>',
    report: { url: '/api/reports/r1/pdf', revision: 2 },
    subject: 'Notification',
    message: '</textarea><script>bad()</script>',
    call_outline: 'Confirm recipient',
    verification_route: '',
  };
  a.api = async (url, opts = {}) => {
    calls.push([url, opts]);
    return handoff;
  };
  await a.showOutreachHandoff();
  assert.equal(calls.at(-1)[0], '/api/cases/case/outreach-handoff');
  assert.equal(calls.at(-1)[1].method, undefined);
  assert.match(modal, /Outreach is do not contact/);
  assert.doesNotMatch(modal, /<script>|<img/);
  assert.match(modal, /&lt;script&gt;/);
  node('#outreach-message').value = 'Operator-edited message';
  node('#outreach-subject').value = 'Operator-edited subject';
  const beforeCopy = calls.length;
  await assert.rejects(a.copyOutreachMessage(), /Save your outreach preparation/);
  assert.equal(calls.length, beforeCopy);
  assert.equal(clipboard.length, 0, 'Unsaved and held preparation cannot be copied');
  s.workflow.changedCaseForms.add('case-plan');
  await assert.rejects(a.showOutreachHandoff(), /Save your contact plan/);
  // Publication routing, checked coverage and unresolved pages remain distinct.
  const route = {
    ...candidate,
    id: 'form-route',
    kind: 'form',
    value: 'https://forms.example/report',
    purpose: 'security',
    decision: 'pending',
    unusable: false,
    usable: false,
    preferred: false,
    review_required: true,
    route_type: 'published_link',
    external_destination: true,
    routing_label: 'Inquiry Type: Webmaster',
    routing_options: [{ label: '<script>unsafe</script>', purpose: 'it' }],
  };
  const coverageState = {
    roots: [{ root_domain: 'example.com', eligible: true }],
    candidates: [route],
    best_route_id: route.id,
    latest_run: {
      status: 'partial',
      outcome: 'reporting_route_found',
      next_step: 'Review the published route; blocked pages remain unresolved.',
      coverage: [
        {
          url: 'https://example.com/contact',
          state: 'checked_empty',
          checked_at: '2026-11-10T12:00:00Z',
          status_code: 200,
        },
        {
          url: 'https://www.example.com/',
          state: 'blocked',
          checked_at: '2026-11-10T12:00:01Z',
          status_code: 403,
          next_step: '</td><script>unsafe</script>',
        },
        { url: 'javascript:alert(1)', state: 'unvisited', next_step: 'Review manually' },
      ],
    },
  };
  s.contacts.entities.set('entity', coverageState);
  const beforeCoverage = calls.length;
  html = a.contactDiscoveryMarkup();
  assert.equal(calls.length, beforeCoverage);
  assert.match(html, /Contact found/);
  assert.match(html, /No contact on this page/);
  assert.match(html, /Blocked.*HTTP 403/);
  assert.match(html, /Not checked/);
  assert.doesNotMatch(html, /Next step/);
  assert.match(html, /Inquiry Type: Webmaster/);
  assert.match(html, /Security contact/);
  assert.doesNotMatch(html, /Best starting point to review/);
  assert.doesNotMatch(html, /<script>|href="javascript:/);
  node('#contact-root').value = 'example.com';
  node('#contact-source-url').value = 'https://security.example.com/report';
  await assert.rejects(a.inspectContactSource(), /selected hostname or its www counterpart/);
  assert.equal(calls.length, beforeCoverage);
  node('#contact-source-url').value = 'https://www.example.com/contact';
  a.api = async (url, opts = {}) => {
    calls.push([url, opts]);
    return url.endsWith('/discover')
      ? { id: 'focused', state: 'completed', total: 1, completed: 1 }
      : coverageState;
  };
  await a.inspectContactSource();
  const focusedCall = calls.filter(([url]) => url.endsWith('/discover')).at(-1);
  assert.equal(focusedCall[1].body.source_url, 'https://www.example.com/contact');
  assert.equal(focusedCall[1].body.include_www, true);
  assert.equal(focusedCall[1].body.refresh, true);
  assert.equal(s.contacts.sourceUrls.get('entity'), 'https://www.example.com/contact');
  app.destroy();
  console.log(
    '0.9.5 contact usability, explicit batch selection, escaped handoff and copy-only outreach passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
