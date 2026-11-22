/** Entity dossiers present saved relationships; opening one never starts report work. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('../../../tests/frontend_harness.cjs');

(async () => {
  const elements = new Map(),
    calls = [],
    location = { hash: '#entity/entity-one' };
  const element = (selector) => {
    if (!elements.has(selector))
      elements.set(selector, {
        innerHTML: '',
        textContent: '',
        hidden: false,
        open: false,
        dataset: {},
        classList: { toggle() {}, add() {}, remove() {} },
        setAttribute() {},
        removeAttribute() {},
        focus() {},
        contains() {
          return false;
        },
      });
    return elements.get(selector);
  };
  const context = vm.createContext({
    console,
    URL,
    URLSearchParams,
    structuredClone,
    location,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    document: {
      querySelector: element,
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
      replaceState(_s, _t, value) {
        location.hash = value;
      },
      pushState(_s, _t, value) {
        location.hash = value;
      },
    },
    localStorage: {
      getItem() {
        return null;
      },
      setItem() {},
    },
    confirm() {
      throw Error('Opening saved dossier views must not request permission.');
    },
  });
  const { application: app } = await loadApplication(context, { attach: false });
  const entry = (id, hostname, ip, day = '2026-11-01', tag = 'CVE-2026-10001') => ({
    id,
    ip,
    source: {
      workbook: 'observations.csv',
      sheet: 'Reported',
      row: Number(id.replace(/\D/g, '')) + 1,
      fields: {
        hostname,
        ip,
        protocol: 'tcp',
        port: '443',
        tag,
        version: '7.1',
        timestamp: `${day}T12:00:00Z`,
      },
    },
  });
  const entity = {
    id: 'entity-one',
    company: 'Example <Business>',
    domain: 'example.com',
    entity_revision: 5,
    draft_revision: 5,
    entity_profile: {
      contact_name: 'Security team',
      contact_email: 'security@example.com',
      contact_phone: '704-555-0100',
      address: '42 Main Street',
      city: 'Charlotte',
      state: 'NC',
      notes: 'Retained profile note',
    },
    hostnames: [
      { name: 'a.example.com', root_domain: 'example.com' },
      { name: 'b.example.com', root_domain: 'example.com' },
      { name: 'known-only.example.com', root_domain: 'example.com' },
    ],
    entries: [
      entry('row-1', 'A.Example.com.', '8.8.8.8'),
      entry('row-2', 'a.example.com', '8.8.8.8', '2026-11-03'),
      entry('row-3', 'b.example.com', '1.1.1.1', '2026-11-02', 'eol-example'),
      entry('row-4', '', '9.9.9.9'),
      entry('row-5', 'host-only.example.com', ''),
      entry('row-6', '', ''),
    ],
    cases: [
      {
        id: 'case-active',
        title: 'Working notification',
        company: 'Pinned report name',
        stage: 'in_progress',
        assets: 1,
        observations: 2,
      },
      {
        id: 'case-history',
        title: 'Earlier notification',
        company: 'Prior recipient',
        stage: 'closed',
        assets: 1,
        observations: 1,
      },
    ],
    history: [
      {
        id: 1,
        lead_id: 'entity-one',
        case_id: 'case-history',
        action: 'case_closed',
        detail: 'Recorded <closure> retained',
        created_at: '2026-11-02T12:00:00Z',
      },
    ],
    entity_review: { required: false, fields: [] },
    attribution_summaries: [],
    ip_associations: [{ ip: '4.4.4.4', recorded_at: '2026-11-02T12:00:00Z' }],
  };
  app.actions.api = async (url, options) => {
    calls.push([url, options]);
    if (url === '/api/entities/entity-one') return structuredClone(entity);
    if (url === '/api/navigation-counts')
      return { entities_review: 0, leads: 0, attribution_review: 0 };
    throw Error('Unexpected dossier API ' + url);
  };
  app.actions.contactDiscoveryMarkup = () =>
    '<section id="saved-contact-results">Saved contact results</section>';
  let contactReads = 0;
  app.actions.loadContactDiscovery = async () => {
    contactReads++;
  };
  await app.actions.route();
  const overview = element('#main').innerHTML;
  assert.equal(app.state.entities.tab, 'overview');
  assert.equal(app.state.editor.currentLead, null);
  assert.equal(app.state.entities.dirty, false);
  assert(!overview.includes('id="entity-details-form"'));
  assert(!overview.includes('id="entity-contact-form"'));
  assert.match(overview, /Example &lt;Business&gt;/);
  assert(overview.includes('security@example.com'));
  assert(overview.includes('CVE-2026-10001'));
  assert(overview.includes('href="#entity/entity-one?tab=details"'));
  assert(overview.includes('href="#entity/entity-one?tab=contacts"'));
  assert(overview.includes('href="#entity/entity-one?tab=history"'));
  assert(overview.includes('href="#workspace/notifications/case-active"'));
  assert(overview.includes('href="#workspace/notifications/case-history"'));
  assert.equal(contactReads, 0, 'The dossier summary does not launch contact research.');
  assert(calls.every(([url, options]) => !url.startsWith('/api/cases/') && !options?.method));

  location.hash = '#entity/entity-one?tab=details';
  await app.actions.route();
  assert.equal(app.state.entities.tab, 'details');
  assert.match(element('#main').innerHTML, /id="entity-details-form"/);
  assert(element('#main').innerHTML.includes('Retained profile note'));
  location.hash = '#entity/entity-one?tab=contacts';
  await app.actions.route();
  assert.equal(app.state.entities.tab, 'contacts');
  assert.match(element('#main').innerHTML, /id="entity-contact-form"/);
  assert.equal(contactReads, 1);
  location.hash = '#entity/entity-one?tab=history';
  await app.actions.route();
  assert.equal(app.state.entities.tab, 'history');
  assert(element('#main').innerHTML.includes('Recorded &lt;closure&gt; retained'));
  assert(
    entity.cases[0].company === 'Pinned report name',
    'Entity presentation cannot rewrite a notification snapshot.',
  );

  const plain = (value) => JSON.parse(JSON.stringify(value));
  const before = structuredClone(entity);
  const model = plain(app.actions.entityDossierModel(entity));
  assert.equal(model.entryCount, 6);
  assert.equal(model.hostCount, 4);
  assert.equal(model.ipCount, 4);
  assert.equal(model.connectionCount, 2);
  assert.equal(model.observedFrom, '2026-11-01');
  assert.equal(model.observedTo, '2026-11-03');
  assert.deepEqual(
    model.edges.map(({ host, ip, count }) => ({ host, ip, count })),
    [
      { host: 'a.example.com', ip: '8.8.8.8', count: 2 },
      { host: 'b.example.com', ip: '1.1.1.1', count: 1 },
    ],
  );
  assert.deepEqual(model.edges[0].entry_ids, ['row-1', 'row-2']);
  assert.equal(model.hosts.find((item) => item.value === 'known-only.example.com').count, 0);
  assert.equal(model.hosts.find((item) => item.value === 'host-only.example.com').count, 1);
  assert.equal(model.ips.find((item) => item.value === '4.4.4.4').count, 0);
  assert.equal(model.ips.find((item) => item.value === '9.9.9.9').count, 1);
  assert.deepEqual(
    entity,
    before,
    'Dossier projections cannot mutate profile, observations or case snapshots.',
  );
  assert.deepEqual(
    plain(
      app.actions.entityDossierModel({
        ...entity,
        entries: [...entity.entries].reverse(),
        hostnames: [...entity.hostnames].reverse(),
      }),
    ),
    model,
    'The same source rows produce stable graph ordering and support IDs.',
  );
  assert.match(
    overview,
    /<svg[^>]*data-dossier-graph[^>]*role="img"|<svg[^>]*role="img"[^>]*data-dossier-graph/,
  );
  const renderedEdges = [...overview.matchAll(/<path\b[^>]*data-dossier-edge[^>]*>/g)].map(
    ([tag]) => ({
      host: tag.match(/data-host="([^"]*)"/)[1],
      ip: tag.match(/data-ip="([^"]*)"/)[1],
      count: Number(tag.match(/data-count="([^"]*)"/)[1]),
    }),
  );
  assert.deepEqual(
    renderedEdges,
    model.graph.edges.map(({ host, ip, count }) => ({ host, ip, count })),
  );
  assert.equal(
    renderedEdges.length,
    2,
    'The SVG renders observed pairs, never the host/IP cross product.',
  );
  assert(!renderedEdges.some((edge) => edge.host === 'a.example.com' && edge.ip === '1.1.1.1'));
  assert(!renderedEdges.some((edge) => edge.host === 'b.example.com' && edge.ip === '8.8.8.8'));
  assert(
    !renderedEdges.some((edge) => edge.host === 'known-only.example.com' || edge.ip === '4.4.4.4'),
  );

  const manyEntries = Array.from({ length: 40 }, (_, index) =>
    entry(
      `source-${index + 10}`,
      `h${String(index).padStart(2, '0')}.example.com`,
      `203.0.113.${index + 1}`,
    ),
  );
  manyEntries.push(
    ...Array.from({ length: 5 }, (_, index) =>
      entry(`repeat-${100 + index}`, 'h00.example.com', '203.0.113.1'),
    ),
  );
  const crowded = { ...entity, entries: manyEntries, hostnames: [], ip_associations: [] };
  const bounded = plain(app.actions.entityDossierModel(crowded));
  assert.equal(bounded.entryCount, 45);
  assert.equal(bounded.hostCount, 40);
  assert.equal(bounded.ipCount, 40);
  assert.equal(bounded.connectionCount, 40);
  assert.equal(bounded.edges[0].count, 6);
  assert.equal(bounded.edges[0].entry_ids.length, 3);
  assert(bounded.graph.hosts.length <= 6 && bounded.graph.ips.length <= 6);
  const hostValues = new Set(bounded.graph.hosts.map((item) => item.value));
  const ipValues = new Set(bounded.graph.ips.map((item) => item.value));
  assert(bounded.graph.edges.every((edge) => hostValues.has(edge.host) && ipValues.has(edge.ip)));
  assert(
    bounded.graph.edges.every((edge) =>
      bounded.edges.some((saved) => saved.host === edge.host && saved.ip === edge.ip),
    ),
  );
  assert.deepEqual(
    plain(app.actions.entityDossierModel({ ...crowded, entries: [...manyEntries].reverse() })),
    bounded,
  );
  const unknown = plain(
    app.actions.entityDossierModel({
      id: 'unknown',
      hostnames: [],
      ip_associations: [],
      entries: [{ id: 'source-unknown', source: { fields: {} } }],
    }),
  );
  assert.equal(unknown.entryCount, 1);
  assert.equal(unknown.hostCount, 0);
  assert.equal(unknown.ipCount, 0);
  assert.equal(unknown.connectionCount, 0);
  assert.deepEqual(unknown.graph.edges, []);
  assert.deepEqual(unknown.findings, []);
  assert.equal(unknown.observedFrom, '');
  assert.equal(unknown.observedTo, '');
  const dated = plain(
    app.actions.entityDossierModel({
      entries: [
        entry('date-1', 'example.com', '8.8.8.8', '2026-11-01'),
        entry('date-2', 'example.com', '8.8.8.8', '2026-02-30'),
        entry('date-3', 'example.com', '8.8.8.8', '2026-99-99'),
      ],
    }),
  );
  assert.equal(dated.observedFrom, '2026-11-01');
  assert.equal(
    dated.observedTo,
    '2026-11-01',
    'Malformed calendar values do not become observed history.',
  );
  const boundedMarkup = app.actions.entityConstellationMarkup(crowded, bounded);
  assert(boundedMarkup.includes('graph is a selection'));
  assert(boundedMarkup.includes(`${bounded.graph.edges.length} of 40 recorded pairs shown`));
  for (const edge of bounded.edges) {
    assert(boundedMarkup.includes(`<td>${edge.host}</td><td>${edge.ip}</td>`));
    for (const id of edge.entry_ids)
      assert(boundedMarkup.includes(`href="/api/eclipse/observations/${encodeURIComponent(id)}"`));
  }
  const emptyMarkup = app.actions.entityConstellationMarkup({ id: 'unknown', entries: [] });
  assert(emptyMarkup.includes('No hostname or IP recorded.'));
  assert(!emptyMarkup.includes('data-dossier-edge'));
  assert(!emptyMarkup.includes('<svg class="dossier-constellation"'));
  const untrusted = {
    id: 'entity"><script>',
    company: '<script>entity</script>',
    entries: [entry('source /?"', '<img src=x onerror="alert(1)">', '<svg onload="alert(2)">')],
  };
  const escapedGraph = app.actions.entityConstellationMarkup(untrusted);
  assert(escapedGraph.includes('&lt;script&gt;entity&lt;/script&gt;'));
  assert(!escapedGraph.includes('<script>') && !escapedGraph.includes('<img '));
  assert(!escapedGraph.includes('<svg onload='));
  assert(escapedGraph.includes('/api/eclipse/observations/source%20%2F%3F%22'));
  console.log(
    'Entity dossier overview, deliberate edits, saved summaries, independent case history and factual bounded source-pair graphs passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
