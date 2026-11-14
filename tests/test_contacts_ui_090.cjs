/** Discovery boundaries, evidence escaping, bounded polling and plan preservation. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');
(async () => {
  const timers = new Map(),
    nodes = new Map(),
    calls = [],
    toasts = [];
  let nextTimer = 0,
    now = 1000;
  const timer = (fn) => {
    const id = ++nextTimer;
    timers.set(id, fn);
    return id;
  };
  const node = (key) => {
    if (!nodes.has(key))
      nodes.set(key, { innerHTML: '', outerHTML: '', value: '', checked: false });
    return nodes.get(key);
  };
  const context = vm.createContext({
    console,
    URL,
    URLSearchParams,
    structuredClone,
    Date: class extends Date {
      static now() {
        return now;
      }
    },
    setTimeout: timer,
    clearTimeout: (id) => timers.delete(id),
    clearInterval() {},
    document: { querySelector: node, querySelectorAll: () => [] },
    window: { Eclipse: { destroy() {} } },
    navigator: { clipboard: { writeText: async (value) => calls.push(['copy', value]) } },
  });
  const { application: app } = await loadApplication(context, { attach: false });
  const { actions: a, state: s } = app;
  a.toast = (message) => toasts.push(message);
  s.editor.currentLead = {
    id: 'e1',
    case_id: 'c1',
    case: { version: 3, stage: 'in_progress' },
    entity_profile: {},
  };
  s.editor.tab = 'contact';
  s.navigation.currentRoute = 'case/c1';
  const candidate = {
    id: 'candidate1',
    kind: 'email',
    value: 'security@company.test',
    name: '',
    role: '',
    purpose: 'security',
    decision: 'pending',
    revision: 2,
    last_seen: '2026-11-09T10:00:00Z',
    provenance_text: 'Published on https://company.test/contact; accepted attribution group g1.',
    sources: [
      {
        url: 'https://company.test/contact',
        excerpt: 'Security issues: security@company.test',
        retrieved_at: '2026-11-09T10:00:00Z',
      },
    ],
  };
  const saved = () => ({
    entity_id: 'e1',
    roots: [{ root_domain: 'company.test', eligible: true, attribution_ref: 'g1' }],
    candidates: [structuredClone(candidate)],
    latest_run: { status: 'relevant_found', finished_at: '2026-11-09T10:00:00Z' },
    active_job: null,
  });
  const activeJob = { id: 'j1', state: 'running', total: 1, completed: 0, entity_ids: ['e1'] };
  a.api = async (url, opts = {}) => {
    calls.push([url, opts]);
    return saved();
  };
  // Pure rendering never starts discovery or performs even a saved-state request.
  a.contactDiscoveryMarkup();
  assert.equal(calls.length, 0);
  await a.loadContactDiscovery();
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], '/api/entities/e1/contacts');
  assert.equal(calls[0][1].timeoutMs, 15000);
  let html = a.contactDiscoveryMarkup();
  assert.doesNotMatch(html, /Review required/);
  assert.doesNotMatch(html, /data-decision="confirm"/);
  assert.match(html, /data-contact-use=/);
  assert.doesNotMatch(html, /id="contact-include-www"/);
  assert.match(html, /data-contact-detail="details"><summary>Sources &/);
  assert.match(html, /evidence\.zip/);
  // Display prioritizes relevant active channels without changing saved order or decisions.
  const unsorted = saved();
  unsorted.candidates = [
    { ...candidate, id: 'general', purpose: 'general', value: 'support@company.test' },
    { ...candidate, id: 'ignored', decision: 'ignored', value: 'ignored@company.test' },
    { ...candidate, id: 'other', purpose: 'other', value: 'other@company.test' },
    { ...candidate, id: 'missing', missing_from_latest: true, value: 'missing@company.test' },
    { ...candidate, id: 'management', purpose: 'management', value: 'manager@company.test' },
    { ...candidate, id: 'security', value: 'security@company.test' },
    { ...candidate, id: 'it', purpose: 'it', value: 'it@company.test' },
  ];
  const beforeSort = JSON.stringify(unsorted.candidates);
  s.contacts.entities.set('e1', unsorted);
  html = a.contactDiscoveryMarkup();
  const displayOrder = [...html.matchAll(/<h3>([^<]+)<\/h3>/g)].map((match) => match[1]);
  assert.deepEqual(displayOrder, [
    'security@company.test',
    'it@company.test',
    'manager@company.test',
    'support@company.test',
    'other@company.test',
    'ignored@company.test',
    'missing@company.test',
  ]);
  assert.equal(JSON.stringify(unsorted.candidates), beforeSort);
  // Every candidate string and source excerpt is escaped; unsafe URL is never clickable.
  const unsafe = saved();
  Object.assign(unsafe.candidates[0], {
    name: '<img src=x onerror=alert(1)>',
    role: '<script>bad()</script>',
    value: '<svg onload=evil()>',
    provenance_text: '</textarea><script>bad()</script>',
  });
  unsafe.candidates[0].sources = [
    { url: 'javascript:alert(1)', excerpt: '</blockquote><img src=x onerror=evil()>' },
  ];
  s.contacts.entities.set('e1', unsafe);
  html = a.contactDiscoveryMarkup();
  assert.doesNotMatch(html, /<(script|img|svg onload)/);
  assert.doesNotMatch(html, /href="javascript:/);
  assert.match(html, /&lt;img/);
  s.contacts.entities.set('e1', saved());
  node('#contact-root').value = 'attacker.test';
  const before = calls.length;
  await assert.rejects(a.startContactDiscovery(), /entity website/);
  assert.equal(calls.length, before);
  node('#contact-root').value = 'company.test';
  node('#contact-include-www').checked = false;
  a.api = async (url, opts) => {
    calls.push([url, opts]);
    return structuredClone(activeJob);
  };
  await a.startContactDiscovery();
  assert.equal(calls.at(-1)[1].body.root_domain, 'company.test');
  assert.equal(calls.at(-1)[1].body.include_www, true);
  assert.equal(calls.at(-1)[1].body.refresh, false);
  assert.equal(timers.size, 1);
  // A repeated click does not queue another lookup; terminal completion settles timers.
  const count = calls.length;
  await a.startContactDiscovery();
  assert.equal(calls.length, count);
  a.api = async (url, opts) => {
    calls.push([url, opts]);
    return url.includes('/jobs/') ? { ...activeJob, state: 'completed', completed: 1 } : saved();
  };
  const tick = async () => {
    const [id, fn] = timers.entries().next().value;
    timers.delete(id);
    await fn();
  };
  await tick();
  assert.equal(timers.size, 0);
  assert.equal(s.contacts.watch, null);
  assert.equal(calls.filter(([url]) => String(url).endsWith('/discover')).length, 1);
  // A failed job without a persisted run must remain visible after the saved-state read.
  a.api = async (url) =>
    url.endsWith('/discover')
      ? { ...activeJob, state: 'failed', error: 'Attribution changed during discovery' }
      : saved();
  await a.startContactDiscovery(true);
  assert.match(a.contactDiscoveryMarkup(), /Attribution changed during discovery/);
  assert.equal(timers.size, 0);
  // Confirm retains optimistic concurrency and changes only the isolated panel.
  const sentinel = 'analyst text already typed';
  node('#case-plan').innerHTML = sentinel;
  a.api = async (url, opts) => {
    calls.push([url, opts]);
    const result = saved();
    result.candidates[0].decision = 'confirmed';
    result.candidates[0].revision++;
    return result;
  };
  await a.reviewContactCandidate('candidate1', 'confirm');
  assert.equal(calls.at(-1)[1].body.expected_revision, 2);
  assert.equal(node('#case-plan').innerHTML, sentinel);
  assert.match(a.contactDiscoveryMarkup(), /data-contact-use="candidate1"/);
  // Changed source context is informational and does not gate autocomplete.
  const changed = s.contacts.entities.get('e1');
  changed.candidates[0].source_changed = true;
  changed.candidates[0].review_required = true;
  html = a.contactDiscoveryMarkup();
  assert.match(html, /source context changed/);
  assert.doesNotMatch(html, /Review required/);
  assert.match(html, /data-contact-use=/);
  changed.candidates[0].source_changed = false;
  changed.candidates[0].review_required = false;
  // Autocomplete fills blanks without a request and preserves dirty manual edits.
  s.workflow.changedCaseForms.add('case-plan');
  const fields = new Map(
    ['contact_name', 'contact_role', 'contact_email', 'contact_phone'].map((name) => [
      name,
      { value: '' },
    ]),
  );
  fields.get('contact_name').value = 'Existing manual name';
  node('#case-plan').id = 'case-plan';
  node('#case-plan').elements = { namedItem: (name) => fields.get(name) };
  const fillCalls = calls.length;
  await a.useContactCandidate('candidate1');
  assert.equal(fields.get('contact_email').value, candidate.value);
  assert.equal(fields.get('contact_name').value, 'Existing manual name');
  assert.equal(calls.length, fillCalls);
  assert.equal(s.editor.currentLead.case.version, 3);
  fields.get('contact_email').value = 'analyst@chosen.test';
  await a.useContactCandidate('candidate1');
  assert.equal(fields.get('contact_email').value, 'analyst@chosen.test');
  assert.ok(s.workflow.changedCaseForms.has('case-plan'));
  s.workflow.changedCaseForms.clear();
  // Explicit clipboard copy contains preserved references, not a fabricated summary.
  await a.copyContactProvenance('candidate1');
  assert.equal(calls.at(-1)[1], candidate.provenance_text);
  // A stuck job has a finite absolute deadline, with an actionable stopped state.
  s.contacts.entities.set('e1', saved());
  a.api = async (url) => (url.endsWith('/discover') ? structuredClone(activeJob) : saved());
  await a.startContactDiscovery();
  now += 100000;
  await tick();
  assert.equal(timers.size, 0);
  assert.equal(s.contacts.watch, null);
  assert.match(s.contacts.entities.get('e1').error, /time limit/);
  assert.doesNotMatch(a.contactDiscoveryMarkup(), /class="spinner"/);
  // Cancellation failure is explicit, stops the poller, and does not claim cancellation.
  a.api = async () => ({ ...saved(), active_job: structuredClone(activeJob) });
  await a.loadContactDiscovery();
  a.api = async () => {
    throw Error('Connection lost');
  };
  await a.cancelContactDiscovery();
  assert.equal(timers.size, 0);
  assert.match(s.contacts.entities.get('e1').error, /Could not confirm cancellation/);
  assert.equal(s.contacts.entities.get('e1').active_job.state, 'running');
  // Navigation/destroy invalidates an in-flight response and cancels its next tick.
  let resolveRead;
  a.api = () =>
    new Promise((resolve) => {
      resolveRead = resolve;
    });
  const read = a.loadContactDiscovery();
  a.stopContactDiscoveryPolling();
  const old = s.contacts.entities.get('e1');
  resolveRead({ ...saved(), active_job: activeJob });
  await read;
  assert.equal(s.contacts.entities.get('e1'), old);
  assert.equal(timers.size, 0);
  // Batch click uses explicit selection, has a hard cap, and never broadens www scope.
  s.editor.currentLead = null;
  s.navigation.currentRoute = 'leads?q=test';
  s.contacts.batchEntityIds = Array.from({ length: 40 }, (_, index) => `e${index}`);
  s.contacts.selectedEntityIds = new Set(s.contacts.batchEntityIds.slice(5, 30));
  a.api = async (url, opts) => {
    calls.push([url, opts]);
    return { ...activeJob, total: 25 };
  };
  await a.startContactBatch();
  assert.equal(calls.at(-1)[0], '/api/contact-discovery/batch');
  assert.equal(calls.at(-1)[1].body.entity_ids.length, 25);
  assert.equal(calls.at(-1)[1].body.include_www, true);
  // Entity-only contacts render and fill independently of any report editor.
  s.editor.currentLead = null;
  s.editor.tab = null;
  s.navigation.currentRoute = 'entity/independent?tab=contacts';
  s.entities ||= {};
  s.entities.current = { id: 'independent', domain: 'example.com' };
  s.contacts.entities.set('independent', {
    roots: [{ root_domain: 'example.com', eligible: true }],
    contacts: [
      {
        ...candidate,
        id: 'known-contact',
        known: true,
        decision: 'pending',
        name: 'Known Person',
        role: 'IT',
        value: 'known@example.com',
      },
    ],
    latest_run: {
      status: 'partial',
      outcome: 'reporting_route_found',
      issues: [{ code: 'page_truncated', message: 'One optional source reached its size limit.' }],
    },
  });
  const entityFields = new Map(
    ['contact_name', 'contact_title', 'contact_email', 'contact_phone'].map((name) => [
      name,
      { value: '' },
    ]),
  );
  entityFields.get('contact_name').value = 'Already entered';
  node('#entity-contact-form').elements = { namedItem: (name) => entityFields.get(name) };
  const entityCalls = calls.length;
  html = a.contactDiscoveryMarkup(s.entities.current);
  assert.match(html, /Contact found/);
  assert.match(html, /known@example.com/);
  assert.match(html, /Known contact/);
  assert.doesNotMatch(html, /Review required|Confirm relevance|Next step|data-decision="confirm"/);
  assert.ok(html.indexOf('known@example.com') < html.indexOf('data-contact-detail="details"'));
  assert.ok(html.indexOf('One optional source') > html.indexOf('data-contact-detail="details"'));
  await a.useContactCandidate('known-contact');
  assert.equal(entityFields.get('contact_name').value, 'Already entered');
  assert.equal(entityFields.get('contact_email').value, 'known@example.com');
  assert.equal(entityFields.get('contact_title').value, 'IT');
  assert.equal(s.entities.dirty, true);
  assert.equal(calls.length, entityCalls);
  app.destroy();
  assert.equal(timers.size, 0);
  console.log(
    'Contact discovery escaping, explicit scopes, review, form preservation, deadlines, cancellation, stale responses and batch limits passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
