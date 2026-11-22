/** Independent routes, guarded record edits, and explicit intake-to-notification actions. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { loadApplication } = require('../../../tests/frontend_harness.cjs');
(async () => {
  const nodes = new Map(),
    calls = [],
    location = { hash: '#entities' };
  let allowLeave = false,
    prompts = 0;
  const node = (selector) => {
    if (!nodes.has(selector))
      nodes.set(selector, {
        innerHTML: '',
        textContent: '',
        hidden: false,
        open: false,
        dataset: {},
        setAttribute() {},
        removeAttribute() {},
        classList: { toggle() {}, add() {}, remove() {} },
        focus() {},
        contains() {
          return false;
        },
      });
    return nodes.get(selector);
  };
  const context = vm.createContext({
    console,
    URLSearchParams,
    structuredClone,
    location,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
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
      pushState(_s, _t, url) {
        location.hash = url;
      },
    },
    localStorage: {
      getItem() {
        return null;
      },
      setItem() {},
    },
    confirm() {
      prompts++;
      return allowLeave;
    },
  });
  const { application: app } = await loadApplication(context, { attach: false });
  const entity = {
    id: 'e1',
    company: 'Example <script>',
    domain: 'example.com',
    entity_revision: 4,
    draft_revision: 4,
    entity_profile: {
      contact_email: 'saved@example.com',
      address: 'Old address',
      notes: 'Keep notes',
    },
    hostnames: [],
    entries: [],
    cases: [],
    history: [],
    entity_review: { required: true, fields: [] },
  };
  const lead = {
    id: 'l1',
    revision: 7,
    domain: 'example.com',
    entity_id: 'e1',
    entity_name: 'Example',
    association_state: 'known',
    association_basis: 'Stored domain',
    status: 'pending',
    hostnames: ['mail.example.com'],
    ips: ['8.8.8.8'],
    findings: ['eol-php'],
    entries: [],
    observations: 1,
    attribution_status: 'qualified',
    can_start: true,
    active_cases: [],
  };
  app.actions.api = async (url, options) => {
    calls.push([url, options]);
    if (url === '/api/navigation-counts')
      return { entities_review: 2, leads: 1, attribution_review: 0 };
    if (url.startsWith('/api/contact-discovery/overviews?')) return {};
    if (url === '/api/contact-discovery/directory-status') return {};
    if (url.startsWith('/api/entities?')) return [{ ...entity, review_required: true }];
    if (url === '/api/entities/e1') return structuredClone(entity);
    if (url.startsWith('/api/pending-leads?')) return [lead];
    if (url === '/api/pending-leads/l1') return structuredClone(lead);
    if (url === '/api/pending-leads/l1/start') return { entity_id: 'e1', case_id: 'c1' };
    if (url === '/api/entities/e1/profile') return structuredClone(entity);
    if (url === '/api/cases/c1')
      return { id: 'e1', case_id: 'c1', case: { stage: 'in_progress' }, draft: { notes: 'Saved' } };
    throw Error('Unexpected API ' + url);
  };
  app.actions.leadMarkup = () => '<div>Notification</div>';
  app.actions.dashboard = async () => '<h1>Workspace</h1>';
  app.actions.toast = () => {};
  app.actions.contactDiscoveryMarkup = () => '<div id="contact-discovery-panel"></div>';
  app.actions.loadContactDiscovery = async () => {};
  await app.actions.route();
  assert.match(node('#main').innerHTML, /href="#entity\/e1"/);
  assert.match(node('#main').innerHTML, /Example &lt;script&gt;/);
  await app.actions.refreshNavigationCounts();
  assert.equal(node('#nav-count').textContent, '2');
  location.hash = '#entity/e1';
  await app.actions.route();
  assert.equal(app.state.editor.currentLead, null);
  assert.equal(app.state.entities.tab, 'overview');
  assert(!node('#main').innerHTML.includes('id="entity-details-form"'));
  assert.match(node('#main').innerHTML, /href="#entity\/e1\?tab=details"/);
  assert(!calls.some(([url]) => url.startsWith('/api/cases/')));
  location.hash = '#entity/e1?tab=details';
  await app.actions.route();
  assert.match(node('#main').innerHTML, /id="entity-details-form"/);
  app.state.entities.dirty = true;
  location.hash = '#leads';
  await app.actions.route();
  assert.equal(prompts, 1);
  assert.equal(location.hash, '#entity/e1?tab=details');
  assert.equal(app.state.entities.dirty, true);
  await app.actions.route(true);
  assert.equal(app.state.entities.dirty, true, 'Background refresh cannot discard entity edits');
  allowLeave = true;
  location.hash = '#leads';
  await app.actions.route();
  assert.equal(app.state.entities.current, null);
  assert.match(node('#main').innerHTML, /href="#leads\/l1"/);
  location.hash = '#leads/l1';
  await app.actions.route();
  assert.match(node('#main').innerHTML, /Start notification/);
  assert.match(node('#main').innerHTML, /Source observations/);
  assert(!calls.some(([, options]) => options?.method === 'POST'));
  const eventModule = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../../leads/static/entity_leads_events.js'), 'utf8'),
    { context },
  );
  await eventModule.link(() => {
    throw Error('Unexpected dependency');
  });
  await eventModule.evaluate();
  const handlers = eventModule.namespace.createHandlers(app);
  const entityEventModule = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../../entities/static/entities_events.js'), 'utf8'),
    { context },
  );
  await entityEventModule.link(() => {
    throw Error('Unexpected entity event dependency');
  });
  await entityEventModule.evaluate();
  const entityHandlers = entityEventModule.namespace.createHandlers(app);
  await handlers.actions['start-lead']();
  assert.equal(location.hash, 'workspace/notifications/c1');
  assert.equal(calls.find(([url]) => url.endsWith('/start'))[1].body.expected_revision, 7);
  location.hash = '#case/c1?tab=activity';
  await app.actions.route();
  assert.equal(location.hash, '#workspace/notifications/c1?tab=activity');
  assert.equal(app.state.editor.tab, 'activity');
  app.state.editor.dirty = true;
  app.state.editor.draft.notes = 'Unsaved note';
  location.hash = '#workspace/notifications/c1?tab=contact';
  await app.actions.route();
  assert.equal(app.state.editor.dirty, true);
  assert.equal(app.state.editor.draft.notes, 'Unsaved note');
  assert.equal(
    calls.filter(([url]) => url === '/api/cases/c1').length,
    1,
    'Internal tab history does not reload an edited case',
  );
  app.state.editor.dirty = false;
  location.hash = '#entity/e1?tab=contacts';
  await app.actions.route();
  app.state.entities.dirty = true;
  await entityHandlers.forms['entity-contact-form'](
    { dataset: { entity: 'e1' } },
    {
      contact_name: 'IT',
      contact_email: 'new@example.com',
      contact_title: '',
      contact_phone: '7045550100',
    },
  );
  const saved = calls.findLast(([url]) => url.endsWith('/profile'))[1].body;
  assert.equal(saved.address, 'Old address');
  assert.equal(saved.notes, 'Keep notes');
  assert.equal(saved.contact_email, 'new@example.com');
  assert.equal(app.state.entities.dirty, false);
  assert.equal(calls.filter(([url]) => url === '/api/cases/c1').length, 1);
  assert.equal(app.actions.canonicalRoute('reports'), 'workspace/completed');
  assert.equal(app.actions.canonicalRoute('imports?tab=api'), 'data?tab=api');
  assert.equal(app.actions.canonicalRoute('lead/e1'), 'entity/e1');
  // The API applies text/status filters; lenses and pagination apply to that full response.
  const queueRows = Array.from({ length: 125 }, (_, index) => ({
    ...lead,
    id: `queue-${String(index).padStart(3, '0')}`,
    domain: `asset-${String(index).padStart(3, '0')}.example.com`,
    observations: index + 1,
    observed_to: '2026-11-11',
    association_state: index < 85 ? 'known' : 'new',
    can_start: true,
  }));
  const deferredRows = queueRows.slice(0, 3).map((row) => ({ ...row, status: 'deferred' }));
  let customRows = null;
  const priorApi = app.actions.api;
  app.actions.api = async (url, options) => {
    if (url.startsWith('/api/pending-leads?')) {
      calls.push([url, options]);
      const params = new URLSearchParams(url.split('?')[1]);
      if (params.get('q') === 'no matching rows') return [];
      return structuredClone(
        customRows ||
          (params.get('status') === 'deferred'
            ? deferredRows
            : params.get('status') === 'dismissed'
              ? []
              : queueRows),
      );
    }
    if (url === '/api/pending-leads/l1/disposition') {
      calls.push([url, options]);
      return { ...lead, status: options.body.status };
    }
    return priorApi(url, options);
  };
  const decodeAttribute = (value) => value.replaceAll('&amp;', '&').replaceAll('&quot;', '"');
  const routeParams = (href) => new URLSearchParams(decodeAttribute(href).split('?')[1]);
  const renderedRows = (html) =>
    [...html.matchAll(/class="text-link" href="#leads\/([^"?]+)"/g)].map((match) =>
      decodeURIComponent(match[1]),
    );
  const lensLinks = (html) =>
    [...html.matchAll(/<a[^>]*href="([^"]+)"[^>]*>([^<]+)<strong>([\d,]+)<\/strong><\/a>/g)].map(
      (match) => ({ href: match[1], label: match[2], count: Number(match[3].replaceAll(',', '')) }),
    );
  const q = 'mail & <needle>';
  const params = new URLSearchParams({
    q,
    status: 'pending',
    lens: 'known',
    sort: 'observations',
    page: '2',
  });
  const middlePage = await app.actions.pendingLeadsPage(params);
  const sent = new URLSearchParams(calls.at(-1)[0].split('?')[1]);
  assert.equal(sent.get('q'), q);
  assert.equal(sent.get('status'), 'pending');
  assert.equal(sent.has('page'), false, 'The full filtered response supplies lens counts');
  assert.match(middlePage, /41–80 of 85/);
  assert.match(middlePage, /Page 2 of 3/);
  assert.equal(renderedRows(middlePage).length, 40);
  assert.equal(renderedRows(middlePage)[0], 'queue-044');
  assert.equal(renderedRows(middlePage).at(-1), 'queue-005');
  assert.match(middlePage, /value="mail &amp; &lt;needle&gt;"/);
  assert.deepEqual(
    lensLinks(middlePage).map(({ label, count }) => [label, count]),
    [
      ['All', 125],
      ['Known entity', 85],
      ['New entity', 40],
    ],
  );
  for (const [text, targetPage] of [
    ['Previous', '1'],
    ['Next', '3'],
  ]) {
    const href = middlePage.match(new RegExp(`href="([^"]+)"[^>]*>${text}</a>`))[1];
    const target = routeParams(href);
    assert.equal(target.get('page'), targetPage);
    for (const key of ['q', 'status', 'lens', 'sort'])
      assert.equal(target.get(key), params.get(key));
  }
  const newLens = routeParams(
    lensLinks(middlePage).find((item) => item.label === 'New entity').href,
  );
  assert.equal(newLens.get('lens'), 'new');
  assert.equal(newLens.get('page'), '1', 'Changing a lens resets pagination');
  for (const key of ['q', 'status', 'sort']) assert.equal(newLens.get(key), params.get(key));
  const lastPage = await app.actions.pendingLeadsPage(
    new URLSearchParams({ ...Object.fromEntries(params), page: '999' }),
  );
  assert.match(lastPage, /81–85 of 85/);
  assert.match(lastPage, /Page 3 of 3/);
  assert.equal(renderedRows(lastPage).length, 5);
  assert.match(lastPage, /<button[^>]*disabled>Next<\/button>/);
  const fallbackPage = await app.actions.pendingLeadsPage(
    new URLSearchParams('lens=invalid&sort=invalid&page=not-a-page'),
  );
  assert.match(fallbackPage, /Page 1 of 4/);
  assert.equal(renderedRows(fallbackPage).length, 40);
  assert.match(fallbackPage, /<option value="priority" selected>/);
  assert.equal(routeParams(lensLinks(fallbackPage)[0].href).get('lens'), 'all');
  const reviewPage = await app.actions.pendingLeadsPage(new URLSearchParams('lens=review'));
  assert.equal(renderedRows(reviewPage).length, 40);
  assert(!reviewPage.includes('Resolve match'));
  assert(!reviewPage.includes('<small>Ready to start</small>'));
  const deferredPage = await app.actions.pendingLeadsPage(
    new URLSearchParams('status=deferred&lens=known&sort=oldest'),
  );
  assert.equal(renderedRows(deferredPage).length, 3);
  assert.match(deferredPage, /<option value="deferred" selected>/);
  assert.match(deferredPage, /<option value="oldest" selected>/);
  const emptyPage = await app.actions.pendingLeadsPage(
    new URLSearchParams('q=no+matching+rows&status=deferred&lens=ready&page=99'),
  );
  assert.match(emptyPage, /No leads in this view/);
  assert.match(emptyPage, /href="#leads">[\s\S]*?Clear filters<\/a>/);
  assert.match(emptyPage, /0 leads.*Page 1 of 1/);
  assert.match(emptyPage, /disabled>Previous<\/button>/);
  assert.match(emptyPage, /disabled>Next<\/button>/);
  assert.equal(renderedRows(emptyPage).length, 0);
  location.hash = '#leads';
  await app.actions.route();
  assert.match(node('#main').innerHTML, /125 leads/);
  assert.equal(
    renderedRows(node('#main').innerHTML).length,
    40,
    'Clear filters recovers the full queue',
  );

  // Details/dispositions preserve the precise queue return URL, including its page.
  const returnRoute = 'leads?' + params;
  location.hash = '#' + returnRoute;
  await app.actions.route();
  location.hash = '#leads/l1';
  await app.actions.route();
  const backHref = node('#main').innerHTML.match(/class="page-back" href="([^"]+)"/)[1];
  assert.equal(decodeAttribute(backHref), '#' + returnRoute);
  await handlers.actions['defer-lead']();
  assert.equal(location.hash, returnRoute);
  const deferred = calls.findLast(([url]) => url.endsWith('/disposition'))[1].body;
  assert.equal(deferred.expected_revision, 7);
  assert.equal(deferred.status, 'deferred');
  await handlers.forms['pending-lead-search'](
    {},
    {
      q: 'changed & query',
      status: 'deferred',
      lens: 'known',
      sort: 'oldest',
    },
  );
  const searched = new URLSearchParams(location.hash.split('?')[1]);
  assert.equal(searched.get('q'), 'changed & query');
  assert.equal(searched.get('status'), 'deferred');
  assert.equal(searched.get('lens'), 'known');
  assert.equal(searched.get('sort'), 'oldest');
  assert.equal(searched.has('page'), false, 'A new search starts on the first page');

  // Source content is data; route identifiers and import provenance survive escaping.
  const unsafe = {
    ...lead,
    id: 'lead /?<id>&"',
    domain: '<img src=x onerror="alert(1)">',
    entity_id: 'entity /?<id>&"',
    entity_name: 'Entity <script>alert(1)</script>',
    association_basis: 'Saved <b>basis</b>',
    findings: ['<script>finding</script>', 'Second', 'Third', 'Fourth'],
    ips: ['8.8.8.8', '"><svg onload="alert(2)">'],
    import_id: 'import"><unsafe',
    import_name: '<script>source.csv</script>',
    entries: [
      {
        ip: '8.8.8.8',
        source: {
          sheet: '<sheet>',
          row: 73,
          fields: {
            hostname: '<host>',
            tag: '<finding>',
            version: '<version>',
            timestamp: '<time>',
          },
        },
      },
    ],
  };
  customRows = [unsafe];
  const escapedPage = await app.actions.pendingLeadsPage(new URLSearchParams());
  assert.equal(renderedRows(escapedPage)[0], unsafe.id);
  assert(escapedPage.includes(`href="#entity/${encodeURIComponent(unsafe.entity_id)}"`));
  assert.match(escapedPage, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
  assert.match(escapedPage, /&lt;script&gt;finding&lt;\/script&gt;/);
  assert.match(escapedPage, /Saved &lt;b&gt;basis&lt;\/b&gt;/);
  assert.match(escapedPage, /\+1 more/);
  assert(
    !escapedPage.includes('<script>') &&
      !escapedPage.includes('<img ') &&
      !escapedPage.includes('<svg onload='),
  );
  const queueApi = app.actions.api;
  app.actions.api = async (url, options) => {
    if (url === '/api/pending-leads/' + encodeURIComponent(unsafe.id)) {
      calls.push([url, options]);
      return structuredClone(unsafe);
    }
    return queueApi(url, options);
  };
  const unsafeDetail = await app.actions.pendingLeadPage(unsafe.id);
  assert.match(unsafeDetail, /data-import="import&quot;&gt;&lt;unsafe"/);
  assert.match(unsafeDetail, /&lt;script&gt;source.csv&lt;\/script&gt;/);
  assert.match(unsafeDetail, /&lt;sheet&gt; 73/);
  for (const field of ['host', 'finding', 'version', 'time'])
    assert(unsafeDetail.includes(`&lt;${field}&gt;`));
  assert(!unsafeDetail.includes('<script>') && !unsafeDetail.includes('<img '));
  context.localStorage.getItem = (key) => (key === 'companion-landing' ? 'eclipse' : null);
  context.localStorage.setItem = () =>
    assert.fail('Navigation must not persist a landing override');
  location.hash = '';
  await app.actions.route();
  assert.equal(
    location.hash,
    '#workspace',
    'A fresh launch opens Workspace despite the old preference',
  );
  assert.match(node('#main').innerHTML, /<h1>Workspace<\/h1>/);
  context.window.Eclipse.loading = () => 'Opening Observatory';
  context.window.Eclipse.render = () => 'Observatory deep link';
  context.window.Eclipse.mount = () => {};
  location.hash = '#eclipse?product=example-product';
  await app.actions.route();
  assert.equal(location.hash, '#eclipse?product=example-product');
  assert.equal(node('#main').innerHTML, 'Observatory deep link');
  console.log(
    'Independent routes, guarded edits, explicit notification actions, Chaos lead lenses, counts, sorting, bounded pagination, query/status recovery, source escaping and preserved return navigation passed.',
  );
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
