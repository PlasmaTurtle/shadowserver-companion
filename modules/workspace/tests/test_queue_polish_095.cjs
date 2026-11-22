/** Queue recovery, hierarchy, filter pagination and immediate form constraints. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('../../../tests/frontend_harness.cjs');
(async () => {
  const nodes = new Map(),
    listeners = new Map();
  const node = (selector) => {
    if (!nodes.has(selector))
      nodes.set(selector, {
        textContent: '',
        innerHTML: '',
        classList: { add() {}, remove() {}, toggle() {} },
        focus() {},
      });
    return nodes.get(selector);
  };
  const context = vm.createContext({
    document: {
      querySelector: node,
      querySelectorAll: () => [],
      addEventListener: (name, handler) => listeners.set(name, handler),
      removeEventListener() {},
      body: { classList: { toggle() {} } },
    },
    window: { addEventListener() {}, removeEventListener() {} },
    console,
    URLSearchParams,
    Date,
    Number,
    String,
    structuredClone,
    setTimeout,
    clearTimeout,
    FormData,
    location: { hash: '#workspace' },
    confirm: () => true,
  });
  const { application: app } = await loadApplication(context);
  let html = app.actions.leadTable([], true);
  assert.match(html, /No businesses match these filters/);
  assert.match(html, /href="#entities"/);
  assert.doesNotMatch(html, /Import a report/);
  assert.match(app.actions.leadTable([]), /No business entities yet/);
  assert.match(app.actions.caseTable([], true), /Clear filters/);
  const row = {
    id: 'case1',
    company: '<Company>',
    domain: 'example.com',
    title: 'A case',
    stage: 'in_progress',
    action_tab: 'notification',
    priority_reasons: ['Critical <reported>'],
    suggested_action: 'Review report',
    outreach_policy: { state: 'active' },
  };
  const dashboardRequests = [];
  app.actions.api = async (url) => {
    dashboardRequests.push(url);
    if (url.startsWith('/api/workspace/queue?as_of='))
      return { items: [row], total: 1, held: 0, basis: 'Explicit order' };
    if (url.startsWith('/api/workspace/brief?as_of='))
      return {
        counts: { review: 0, leads: 7 },
        workflow: { in_progress: 1, due: 2, closed: 3 },
        leads: [{ id: 'ready-1', entity_name: 'Next <Company>', domain: 'next.example.com' }],
        imports: [],
        events: [],
      };
    throw Error('Unexpected Workspace request: ' + url);
  };
  let dayReads = 0;
  app.actions.localDay = () => (++dayReads === 1 ? '2026-11-21' : '2026-11-22');
  html = await app.actions.dashboard();
  assert.equal(dayReads, 1, 'A midnight boundary must not mix dates within one dashboard');
  assert.equal(dashboardRequests.length, 2);
  assert.equal(dashboardRequests[0].split('as_of=')[1], dashboardRequests[1].split('as_of=')[1]);
  assert.equal(dashboardRequests[0].split('as_of=')[1], '2026-11-21');
  assert.match(html, /due_before=2026-11-21/);
  assert(html.includes(app.actions.esc(app.actions.date('2026-11-21'))));
  assert(html.indexOf('dm-work-index') < html.indexOf('dm-board-aside'));
  assert.equal((html.match(/class="dm-priority-row"/g) || []).length, 1);
  assert.match(html, /class="dm-rank">01<\/span>/);
  assert.match(html, /href="#workspace\/notifications\/case1\?tab=notification"/);
  assert.match(html, /Priority work/);
  assert.match(html, /How this list is ordered/);
  assert.match(html, /Explicit order/);
  assert.match(html, /1 actionable/);
  assert.match(html, /0 held/);
  assert.match(html, /<strong>7<\/strong><span>Leads<\/span>/);
  assert.match(html, /<strong>2<\/strong><span>Follow-ups due<\/span>/);
  assert.match(html, /<strong>3<\/strong><span>Completed<\/span>/);
  assert.match(html, /href="#leads\/ready-1"/);
  assert.match(html, /Next &lt;Company&gt;/);
  assert.match(html, /&lt;Company&gt;/);
  assert.match(html, /&lt;reported&gt;/);
  assert.doesNotMatch(html, /Source observations|Recent imports|undefined observations/);
  assert.doesNotMatch(
    html,
    /workspace-focus|Continue notification|Next in line|data-action="search-records"/,
  );
  assert.doesNotMatch(html, /<Company>|<reported>/);
  app.actions.api = async () => ({ items: [], total: 0, next_before: null });
  html = await app.actions.activityPage(new URLSearchParams());
  assert.match(html, /No activity recorded yet/);
  assert.doesNotMatch(html, /activity-pagination/);
  assert.doesNotMatch(html, /activity-advanced" open/);
  html = await app.actions.activityPage(new URLSearchParams({ q: 'unmatched', actor: 'Reviewer' }));
  assert.match(html, /No matching events/);
  assert.match(html, /activity-advanced" open/);
  assert.match(html, /Clear filters/);
  app.actions.api = async () => ({
    items: [
      {
        case_id: 'case1',
        created_at: '2026-11-08T00:00:00Z',
        actor: '<Reviewer>',
        action: 'outreach_policy_changed',
        detail: '<Saved>',
        metadata: {},
      },
    ],
    total: 60,
    next_before: 10,
  });
  html = await app.actions.activityPage(
    new URLSearchParams({ q: 'a&b', actor: 'Reviewer', before: '30' }),
  );
  assert.match(html, /Showing 1 of 60 matching recorded events/);
  assert.match(html, /&lt;Reviewer&gt;/);
  const older = html.match(/href="([^"]+)"[^>]*>Older events/)[1].replaceAll('&amp;', '&');
  const pagination = new URLSearchParams(older.split('?')[1]);
  assert.equal(pagination.get('q'), 'a&b');
  assert.equal(pagination.get('actor'), 'Reviewer');
  assert.equal(pagination.get('before'), '10');
  const date = { required: false },
    hint = { textContent: '' };
  const form = { querySelector: (selector) => (selector === '[name="review_on"]' ? date : hint) };
  const select = { id: 'outreach-state', value: 'deferred', closest: () => form };
  await listeners.get('change')({ target: select });
  assert.equal(date.required, true);
  assert.match(hint.textContent, /Required/);
  select.value = 'active';
  await listeners.get('change')({ target: select });
  assert.equal(date.required, false);
  assert.match(hint.textContent, /Optional/);
  // The sidebar uses the actual tab handler so declining its dirty-form guard
  // preserves the current form; accepting opens contact and focuses the decision.
  let focused = 0,
    scrolled = 0,
    contactLoads = 0;
  const decisionForm = {
    scrollIntoView() {
      scrolled++;
    },
    querySelector: () => ({
      focus() {
        focused++;
      },
    }),
  };
  const eventFor = (button) => ({
    target: { closest: (selector) => (selector === 'button,[data-open-lead]' ? button : null) },
  });
  const contactTab = {
    id: 'editor-tab-contact',
    dataset: { tab: 'contact' },
    focus() {},
    click() {
      void listeners.get('click')(eventFor(this));
    },
  };
  nodes.set('#editor-tab-contact', contactTab);
  nodes.set('#case-outreach-policy', null);
  app.actions.busy = (_button, run) => run();
  app.actions.stopContactDiscoveryPolling = () => {};
  app.actions.loadContactDiscovery = () => {
    contactLoads++;
  };
  app.actions.leadMarkup = () => {
    nodes.set('#case-outreach-policy', decisionForm);
    return 'Contact';
  };
  const reviewButton = { dataset: { action: 'review-outreach-decision' } };
  app.state.editor.tab = 'entity';
  app.state.workflow.workflowDirty = true;
  context.confirm = () => false;
  await listeners.get('click')(eventFor(reviewButton));
  assert.equal(app.state.editor.tab, 'entity');
  assert.equal(app.state.workflow.workflowDirty, true);
  assert.equal(focused, 0);
  assert.equal(scrolled, 0);
  context.confirm = () => true;
  await listeners.get('click')(eventFor(reviewButton));
  assert.equal(app.state.editor.tab, 'contact');
  assert.equal(app.state.workflow.workflowDirty, false);
  assert.equal(focused, 1);
  assert.equal(scrolled, 1);
  assert.equal(contactLoads, 1);
  await listeners.get('click')(eventFor(reviewButton));
  assert.equal(focused, 2);
  assert.equal(contactLoads, 1);
  console.log(
    'Dashboard hierarchy/escaping and one-day snapshot, Activity filters, deferred date and guarded outreach decision focus passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
