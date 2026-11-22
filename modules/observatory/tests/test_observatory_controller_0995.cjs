/** Production controller acceptance: scopes, revisions, reversible descent and cancellation. */
const assert = require('node:assert/strict');
const { createHarness } = require('./eclipse_controller_harness.cjs');

const rows = [1, 2].map((n) => ({
  id: 'f' + n,
  finding_id: 'f' + n,
  observation_id: 'o' + n,
  detail_url: `/api/eclipse/observations/o${n}?finding_id=f${n}&source_key=source${n}`,
  finding_ids: ['f' + n],
  asset_id: 'a' + n,
  hostname: `mail.org${n}.example`,
  domain: `org${n}.example`,
  ip: n === 1 ? '8.8.8.8' : '1.1.1.1',
  entity_id: 'e' + n,
  entity_name: 'Organization ' + n,
  tag: 'CVE-2026-1000' + n,
  observed_day: '2026-11-0' + n,
  observed_at: '2026-11-0' + n + 'T01:00:00Z',
  admitted: true,
  dark_matter: false,
  status: 'qualified',
  workflow: 'unworked',
  observation_count: 1,
  source: { workbook: 'synthetic.csv', sheet: 'CSV', row: n + 1 },
}));
function envelope({ revision = 'r1', selected = rows, total = selected.length, offset = 0 } = {}) {
  const counts = {
    findings: total,
    observations: total,
    assets: total,
    entities: total,
    dark_matter: 0,
    unplaced: total,
  };
  const timeline = {
    bins: selected.map((row) => ({ day: row.observed_day, count: 1 })),
    undated: 0,
  };
  return {
    revision,
    filters: {},
    snapshot: {
      revision,
      observations: selected.map((row) => ({ ...row, id: row.observation_id })),
      findings: selected,
      entities: selected.map((row) => ({
        id: row.entity_id,
        name: row.entity_name,
        domain: row.domain,
      })),
      networks: [],
      counts,
      timeline,
    },
    intelligence: {
      revision,
      counts,
      coverage: { complete: true },
      graph: { nodes: [], edges: [], limits: { total_nodes: 0 } },
      patterns: [],
      timeline,
      atlas: [],
      pulse: [],
    },
    records: { items: selected, total, offset, limit: 20 },
  };
}
const requests = (h) =>
  h.requests.filter((request) => request.url.startsWith('/api/eclipse/view?'));
const params = (request) => new URL(request.url, 'http://127.0.0.1').searchParams;
async function open(options = {}, response = envelope()) {
  const h = await createHarness(options);
  assert.equal(requests(h).length, 1);
  requests(h)[0].resolve(response);
  for (const request of h.requests.filter((r) => r.url.startsWith('/modules/observatory/static/')))
    request.resolve({ type: 'FeatureCollection', features: [] });
  await h.settle();
  assert.equal(h.root.dataset.ready, 'true');
  return h;
}

(async () => {
  // A supplied atomic response is usable immediately, without a duplicate query.
  let h = await createHarness({ envelope: envelope() });
  try {
    assert.equal(h.root.dataset.ready, 'true');
    assert.equal(h.element('#ec-loading').hidden, true);
    assert.equal(requests(h).length, 0);
    assert.equal(h.element('#ec-rows').textContent, '2');
  } finally {
    h.destroy();
  }

  // Cold views get a truthful slow message and a bounded two-minute timeout.
  h = await createHarness();
  try {
    assert.deepEqual(h.pendingTimeouts(), [10000, 120000]);
    const cold = requests(h)[0];
    h.fireTimeout(10000);
    assert.match(
      h.element('#ec-data-status').textContent,
      /Still preparing.*continue using the app/,
    );
    assert.equal(cold.options.signal.aborted, false);
    h.change('#ec-entity', 'e2');
    assert(cold.options.signal.aborted);
    assert.deepEqual(
      h.pendingTimeouts(),
      [10000, 120000],
      'Supersession keeps exactly one slow/timeout pair',
    );
    const current = requests(h).at(-1);
    h.fireTimeout(120000);
    assert(current.options.signal.aborted);
    current.reject(Object.assign(new Error('Timed out'), { name: 'AbortError' }));
    await h.settle();
    assert.equal(h.root.dataset.ready, 'error');
    assert.match(h.element('#ec-data-status').textContent, /unavailable/);
    assert.deepEqual(h.pendingTimeouts(), []);
  } finally {
    h.destroy();
  }
  // Explicit routes start clean; ordinary returns retain intentional saved intake.
  h = await open(
    {
      hash: '#eclipse?entity=e1',
      saved: {
        search: 'CVE-2026-99999',
        network: '64512',
        status: 'delivered',
        intake: 'dark_matter',
      },
    },
    envelope({ selected: [rows[0]] }),
  );
  try {
    const query = params(requests(h)[0]);
    assert.equal(query.get('entity_id'), 'e1');
    for (const key of ['q', 'cve', 'network', 'status', 'intake'])
      assert.equal(query.get(key), null, key);
    assert.equal(h.element('#ec-rows').textContent, '1');
    assert.equal(h.root.dataset.view, 'field');
  } finally {
    h.destroy();
  }

  // The named directory gives keyboard users the same contextual path as canvas selection.
  const directory = envelope();
  directory.intelligence.graph.nodes = [
    {
      id: 'entity:e1',
      type: 'entity',
      entity_id: 'e1',
      label: 'Organization 1',
      scope: { entity_id: 'e1' },
      observation_ids: ['o1'],
      finding_count: 1,
      asset_count: 1,
      entity_count: 1,
      observation_count: 1,
    },
  ];
  h = await open({}, directory);
  try {
    h.click('[data-ec-node="entity:e1"]');
    assert.equal(h.element('#ec-selection-name').textContent, 'Organization 1');
    h.click('[data-ec-drill="products"]');
    assert.equal(h.root.dataset.view, 'field', 'The origin remains visible until arrival');
    assert.equal(params(requests(h).at(-1)).get('entity_id'), 'e1');
    const products = envelope({ selected: [rows[0]] });
    products.intelligence.products = [
      {
        id: 'product-mail',
        label: 'Example Mail',
        scope: { product_name: 'Example Mail' },
        entity_count: 1,
        asset_count: 1,
        finding_count: 1,
        observation_count: 1,
      },
    ];
    requests(h).at(-1).resolve(products);
    await h.settle();
    assert.equal(h.root.dataset.view, 'records');
    assert.match(h.element('#ec-record-list').innerHTML, /Example Mail/);
    h.click('[data-ec-product="product-mail"]');
    h.click('[data-ec-drill="assets"]');
    const scope = params(requests(h).at(-1));
    assert.equal(
      scope.get('entity_id'),
      'e1',
      'Product refinement retains its originating organization',
    );
    assert.equal(scope.get('product_name'), 'Example Mail');
    h.click('#ec-back-field');
    const obsolete = requests(h).at(-1);
    assert(obsolete.options.signal.aborted);
    obsolete.resolve(envelope({ selected: [], revision: 'obsolete-product-response' }));
    await h.settle();
    assert.equal(h.root.dataset.view, 'field');
    assert.equal(h.root.dataset.revision, 'r1');
    assert.equal(h.element('#ec-rows').textContent, '2');
  } finally {
    h.destroy();
  }
  h = await open({ saved: { intake: 'dark_matter', defaultView: 'atlas' } });
  try {
    assert.equal(params(requests(h)[0]).get('intake'), 'dark_matter');
    assert.equal(h.element('#ec-intake').value, 'dark_matter');
    assert.equal(h.root.dataset.view, 'atlas');
  } finally {
    h.destroy();
  }

  // EOL findings have the same exact contextual journey as reported CVEs.
  const eolRow = { ...rows[0], tag: 'eol-php:7.3', finding_kind: 'eol' };
  const eolEnvelope = envelope({ selected: [eolRow, rows[1]] });
  eolEnvelope.intelligence.graph.nodes = [
    {
      id: 'finding:eol-php',
      type: 'finding',
      label: 'PHP 7.3 end of life',
      scope: { condition: 'eol-php:7.3' },
      observation_ids: ['o1'],
      finding_count: 1,
      observation_count: 1,
      asset_count: 1,
      entity_count: 1,
    },
  ];
  h = await open({}, eolEnvelope);
  try {
    h.click('[data-ec-node="finding:eol-php"]');
    h.click('[data-ec-drill="locations"]');
    assert.equal(params(requests(h).at(-1)).get('condition'), 'eol-php:7.3');
    assert.equal(
      params(requests(h).at(-1)).get('q'),
      null,
      'EOL uses exact condition membership, not broad search',
    );
    requests(h)
      .at(-1)
      .resolve(envelope({ revision: 'eol-focused', selected: [eolRow] }));
    await h.settle();
    assert.equal(h.root.dataset.view, 'atlas');
    assert.match(h.element('#ec-scope-chips').innerHTML, /End of life/);
    assert.equal(h.element('#ec-rows').textContent, '1');
    h.click('#ec-back-field');
    assert.equal(h.root.dataset.view, 'field');
    assert.equal(h.root.dataset.revision, 'r1');
    assert.equal(h.element('#ec-rows').textContent, '2');
    assert.equal(h.element('#ec-selection-name').textContent, 'PHP 7.3 end of life');
    assert.equal(new URLSearchParams(h.location.hash.split('?')[1] || '').get('condition'), null);
  } finally {
    h.destroy();
  }

  // Leaving Observatory invalidates a late response even if the transport ignores abort.
  h = await open();
  h.change('#ec-entity', 'e2');
  const abandoned = requests(h).at(-1);
  h.destroy();
  assert(abandoned.options.signal.aborted);
  abandoned.resolve(envelope({ revision: 'after-destroy', selected: [rows[1]] }));
  await h.settle();
  assert.equal(h.root.dataset.ready, 'destroyed');
  assert.notEqual(h.root.dataset.revision, 'after-destroy');

  // Reset replaces the complete response; it cannot retain a product's initial subset.
  h = await open({ hash: '#eclipse?product=product-one' }, envelope({ selected: [rows[0]] }));
  try {
    assert.equal(params(requests(h)[0]).get('product_id'), 'product-one');
    h.click('#ec-reset');
    assert.equal(params(requests(h).at(-1)).get('product_id'), null);
    requests(h)
      .at(-1)
      .resolve(envelope({ revision: 'r2' }));
    await h.settle();
    assert.equal(h.root.dataset.revision, 'r2');
    assert.equal(h.element('#ec-rows').textContent, '2');
    assert.equal(h.element('#ec-observations').textContent, '2');
    assert.equal(h.location.hash, '#eclipse');
    assert.match(h.element('#ec-histogram').innerHTML, /2026-11-02/);
    h.click('[data-ec-view="records"]');
    assert.match(h.element('#ec-record-list').innerHTML, /mail\.org2\.example/);
  } finally {
    h.destroy();
  }

  // Navigate into an identified mass and return to its original scope/camera/revision.
  h = await open();
  try {
    const selected = {
      id: 'entity:e1',
      type: 'entity',
      entity_id: 'e1',
      label: 'Organization 1',
      scope: { entity_id: 'e1' },
      observation_count: 1,
      entity_count: 1,
      asset_count: 1,
      finding_count: 1,
      observation_ids: ['o1'],
      rows: [rows[0]],
    };
    h.hooks.select(selected);
    assert.equal(h.element('#ec-selection-name').textContent, 'Organization 1');
    h.click('[data-ec-drill="locations"]');
    assert.equal(h.root.dataset.view, 'field', 'Do not switch views before approach completes');
    assert.equal(params(requests(h).at(-1)).get('entity_id'), 'e1');
    assert(h.sceneCalls.some((call) => call.name === 'approach' && call.args[0] === 'entity:e1'));
    requests(h)
      .at(-1)
      .resolve(envelope({ revision: 'r2', selected: [rows[0]] }));
    await h.settle();
    assert.equal(h.root.dataset.view, 'atlas');
    assert.equal(h.element('#ec-rows').textContent, '1');
    assert.equal(h.element('#ec-back-field').hidden, false);
    const before = requests(h).length;
    h.click('#ec-back-field');
    assert.equal(h.root.dataset.view, 'field');
    assert.equal(h.root.dataset.revision, 'r1');
    assert.equal(h.element('#ec-rows').textContent, '2');
    assert.equal(h.element('#ec-selection-name').textContent, 'Organization 1');
    assert.equal(
      requests(h).length,
      before,
      'Returning does not rebuild the field or lose its revision',
    );
    const restored = h.sceneCalls.filter((call) => call.name === 'restoreView').at(-1);
    assert.deepEqual(restored.args[0].camera, { x: 127, y: -38, k: 2.25 });
    assert.equal(h.element('#ec-back-field').hidden, true);
    assert.deepEqual(
      h.pendingTimeouts(),
      [],
      'Returning clears both slow-status and timeout callbacks',
    );
  } finally {
    h.destroy();
  }

  // Leaving during a slow records page clears timers in production teardown itself.
  h = await open({}, envelope({ total: 42 }));
  try {
    h.click('[data-ec-view="records"]');
    h.click('#ec-next');
    assert.deepEqual(h.pendingTimeouts(), [10000, 120000]);
    h.fireTimeout(10000);
    assert.match(h.element('#ec-record-list').innerHTML, /Still preparing.*continue using the app/);
    const pending = requests(h).at(-1);
    h.destroyController();
    assert(pending.options.signal.aborted);
    assert.deepEqual(
      h.pendingTimeouts(),
      [],
      'Controller teardown clears timers without harness cleanup',
    );
  } finally {
    h.destroy();
  }

  // A fast data response waits for the actual approach; the origin remains readable.
  h = await open({}, directory);
  try {
    let arrive;
    h.scene.approach = () =>
      new Promise((resolve) => {
        arrive = resolve;
      });
    h.scene.cancelApproach = () => arrive?.({ completed: false });
    h.click('[data-ec-node="entity:e1"]');
    h.click('[data-ec-drill="locations"]');
    requests(h)
      .at(-1)
      .resolve(envelope({ revision: 'arrival', selected: [rows[0]] }));
    await h.settle();
    assert.equal(h.root.dataset.view, 'field');
    assert.equal(h.root.dataset.revision, 'r1');
    assert.equal(h.root.dataset.journey, 'approaching');
    assert.equal(h.element('#ec-rows').textContent, '2');
    assert.equal(h.element('#ec-loading').hidden, true);
    arrive({ completed: true });
    await h.settle();
    assert.equal(h.root.dataset.view, 'atlas');
    assert.equal(h.root.dataset.revision, 'arrival');
    assert.equal(h.root.dataset.journey, 'resolved');
    assert.equal(h.element('#ec-rows').textContent, '1');
  } finally {
    h.destroy();
  }

  // A user choosing another view interrupts travel and rejects its delayed result.
  h = await open({}, directory);
  try {
    let arrive;
    h.scene.approach = () =>
      new Promise((resolve) => {
        arrive = resolve;
      });
    h.scene.cancelApproach = () => arrive?.({ completed: false });
    h.click('[data-ec-node="entity:e1"]');
    h.click('[data-ec-drill="locations"]');
    const obsolete = requests(h).at(-1);
    h.click('[data-ec-view="pulse"]');
    assert(obsolete.options.signal.aborted);
    obsolete.resolve(envelope({ revision: 'unwanted-arrival', selected: [rows[0]] }));
    arrive({ completed: true });
    await h.settle();
    assert.equal(h.root.dataset.view, 'pulse');
    assert.equal(h.root.dataset.revision, 'r1');
    assert.equal(h.root.dataset.ready, 'true');
    assert.equal(h.element('#ec-rows').textContent, '2');
    assert.equal(h.element('#ec-back-field').hidden, true);
  } finally {
    h.destroy();
  }

  // Obsolete source work cannot replace a new selection with a false timeout.
  h = await open();
  try {
    h.click('[data-ec-view="records"]');
    h.click('[data-ec-row="f1"]');
    const detail = h.requests.find((request) => request.url.includes('/observations/'));
    assert(detail);
    assert.equal(
      detail.url,
      '/api/eclipse/observations/o1?finding_id=f1&source_key=source1',
      'Use the exact source locator supplied for this scoped finding',
    );
    h.change('#ec-entity', 'e2');
    assert.equal(detail.options.signal.aborted, true);
    detail.reject(Object.assign(new Error('Aborted'), { name: 'AbortError' }));
    requests(h)
      .at(-1)
      .resolve(envelope({ selected: [rows[1]], revision: 'r3' }));
    await h.settle();
    assert.equal(h.root.dataset.revision, 'r3');
    assert.doesNotMatch(
      h.element('#ec-inspector-content').innerHTML,
      /timed out|Could not open this source/,
    );
  } finally {
    h.destroy();
  }

  // Even a transport that ignores abort cannot install an earlier scope/revision.
  h = await open();
  try {
    h.change('#ec-entity', 'e1');
    const earlier = requests(h).at(-1);
    h.change('#ec-entity', 'e2');
    const later = requests(h).at(-1);
    assert(earlier.options.signal.aborted);
    later.resolve(envelope({ selected: [rows[1]], revision: 'latest' }));
    await h.settle();
    earlier.resolve(envelope({ selected: [rows[0]], revision: 'stale' }));
    await h.settle();
    assert.equal(h.root.dataset.revision, 'latest');
    assert.equal(h.element('#ec-entity').value, 'e2');
    assert.doesNotMatch(h.element('#ec-histogram').innerHTML, /2026-11-01/);
    assert.match(h.element('#ec-histogram').innerHTML, /2026-11-02/);
  } finally {
    h.destroy();
  }

  // Counts are server totals, never the size of a sample or one records page.
  h = await open({}, envelope({ total: 42 }));
  try {
    assert.equal(h.element('#ec-rows').textContent, '42');
    h.click('[data-ec-view="records"]');
    const histogram = h.element('#ec-histogram').innerHTML;
    const scenePaints = h.sceneCalls.filter((call) => call.name === 'set').length;
    h.click('#ec-next');
    assert.equal(params(requests(h).at(-1)).get('offset'), '20');
    assert.equal(params(requests(h).at(-1)).get('records_only'), 'true');
    const nextPage = envelope({ total: 42, offset: 20, selected: [rows[1]] });
    requests(h).at(-1).resolve({ revision: nextPage.revision, records: nextPage.records });
    await h.settle();
    assert.equal(h.element('#ec-rows').textContent, '42');
    assert.match(h.element('#ec-record-list').innerHTML, /mail\.org2\.example/);
    assert.equal(h.element('#ec-histogram').innerHTML, histogram);
    assert.equal(h.sceneCalls.filter((call) => call.name === 'set').length, scenePaints);

    h.click('#ec-next');
    const changed = envelope({
      revision: 'intake-commit',
      total: 43,
      offset: 40,
      selected: [rows[1]],
    });
    requests(h).at(-1).resolve({ revision: changed.revision, records: changed.records });
    await h.settle();
    assert.equal(
      params(requests(h).at(-1)).get('records_only'),
      null,
      'New revision requires a complete scoped response',
    );
    assert.notEqual(
      h.root.dataset.revision,
      'intake-commit',
      'Do not mix a new records page with old graph/history',
    );
    requests(h).at(-1).resolve(changed);
    await h.settle();
    assert.equal(h.root.dataset.revision, 'intake-commit');
    assert.equal(h.element('#ec-rows').textContent, '43');
    assert.doesNotMatch(h.element('#ec-histogram').innerHTML, /2026-11-01/);
  } finally {
    h.destroy();
  }

  console.log(
    'Observatory actual-controller scopes, reversible descent, revisions, pagination and abort acceptance passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
