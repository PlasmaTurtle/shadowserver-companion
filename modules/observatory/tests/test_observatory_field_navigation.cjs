/** Production-controller field paging, focused asset pages and revision recovery. */
const assert = require('node:assert/strict');
const { createHarness } = require('./eclipse_controller_harness.cjs');
function envelope({
  offset = 0,
  total = 90,
  revision = 'r1',
  focus = false,
  assetOffset = 0,
} = {}) {
  const nodes = [
    {
      id: 'entity:e1',
      type: 'entity',
      label: 'Example organization',
      fresh_at: '2026-11-12',
      last_seen: '2026-11-13',
      finding_count: 2,
      observation_count: 11,
    },
    { id: 'asset:a1', type: 'asset', label: 'mail.example.org', observation_count: 11 },
  ];
  const counts = { findings: 90, observations: 450, assets: 100, entities: 90 };
  return {
    revision,
    snapshot: { findings: [], observations: [], entities: [], counts, timeline: { bins: [] } },
    records: { items: [], total: 90 },
    intelligence: {
      counts,
      graph: { nodes, edges: [{ source: nodes[0].id, target: nodes[1].id }], limits: {} },
      field: {
        offset,
        limit: 24,
        total_objects: total,
        next_offset: offset + 24 < total ? offset + 24 : null,
        has_more: offset + 24 < total,
        revision,
        asset_page: focus
          ? {
              offset: assetOffset,
              limit: 120,
              total_assets: 150,
              has_more: !assetOffset,
              next_offset: !assetOffset ? 120 : null,
            }
          : null,
      },
    },
  };
}
const requests = (h) => h.requests.filter((r) => r.url.startsWith('/api/eclipse/view?'));
const params = (request) => new URL(request.url, 'http://127.0.0.1').searchParams;
function traditionalEnvelope() {
  const result = envelope();
  delete result.intelligence.field;
  result.intelligence.atlas = { nodes: [], unplaced: 0 };
  result.intelligence.pulse = { lanes: [], undated: 0 };
  return result;
}
(async () => {
  let h = await createHarness();
  try {
    assert.equal(params(requests(h)[0]).get('field_only'), 'true');
    assert.equal(params(requests(h)[0]).get('field_limit'), '24');
    requests(h)[0].resolve(envelope());
    await h.settle();
    assert.equal(h.element('#ec-field-range').textContent, '1–24 of 90 objects');
    assert(h.element('#ec-field-prev').disabled);
    for (const offset of [24, 48, 72]) {
      h.click('#ec-field-next');
      const pending = requests(h).at(-1);
      assert.equal(params(pending).get('field_offset'), String(offset));
      assert.equal(params(pending).get('field_revision'), 'r1');
      assert(h.element('#ec-field-next').disabled);
      pending.resolve(envelope({ offset }));
      await h.settle();
    }
    assert.equal(h.element('#ec-field-range').textContent, '73–90 of 90 objects');
    assert(h.element('#ec-field-next').disabled);
    h.click('#ec-field-prev');
    requests(h)
      .at(-1)
      .resolve({ detail: { code: 'field_revision_changed' } }, 409);
    await h.settle();
    const fresh = requests(h).at(-1);
    assert.equal(params(fresh).get('field_offset'), '0');
    assert.equal(params(fresh).get('field_revision'), null);
    fresh.resolve(envelope({ revision: 'r2' }));
    await h.settle();
    assert.equal(h.root.dataset.ready, 'true');
    assert.equal(h.element('#ec-field-range').textContent, '1–24 of 90 objects');
    assert(!h.element('#ec-scene-title').textContent.includes('relationships'));
  } finally {
    h.destroy();
  }
  h = await createHarness({ envelope: envelope({ offset: 48 }) });
  try {
    h.click('[data-ec-node="entity:e1"]');
    await h.settle();
    const focused = requests(h).at(-1);
    assert.equal(params(focused).get('focus'), 'entity:e1');
    assert.equal(params(focused).get('field_asset_offset'), '0');
    focused.resolve(envelope({ focus: true }));
    await h.settle();
    assert.equal(h.element('#ec-field-range').textContent, '1–120 of 150 assets');
    assert.equal(h.element('#ec-scene-title').textContent, 'Example organization');
    h.click('#ec-field-next');
    assert.equal(params(requests(h).at(-1)).get('field_asset_offset'), '120');
    requests(h)
      .at(-1)
      .resolve(envelope({ focus: true, assetOffset: 120 }));
    await h.settle();
    assert.equal(h.element('#ec-field-range').textContent, '121–150 of 150 assets');
    const count = requests(h).length;
    h.click('#ec-back-field');
    await h.settle();
    assert.equal(requests(h).length, count, 'Back reuses the exact overview snapshot');
    assert.equal(h.element('#ec-field-range').textContent, '49–72 of 90 objects');
    assert(h.sceneCalls.some((c) => c.name === 'restoreView'));
  } finally {
    h.destroy();
  }
  // Legacy inspector focus must not reuse the overview's later page offset.
  h = await createHarness({ envelope: envelope({ offset: 48 }) });
  try {
    h.hooks.select(envelope().intelligence.graph.nodes[1]);
    h.click('[data-ec-action="focus"]');
    const pending = requests(h).at(-1);
    assert.equal(params(pending).get('focus'), 'asset:a1');
    assert.equal(params(pending).get('field_offset'), '0');
    assert.equal(params(pending).get('field_asset_offset'), '0');
    const focusedAsset = envelope({ total: 1 });
    focusedAsset.intelligence.graph.nodes = [focusedAsset.intelligence.graph.nodes[1]];
    focusedAsset.intelligence.graph.edges = [];
    pending.resolve(focusedAsset);
    await h.settle();
    assert.equal(h.root.dataset.nodeCount, '1');
    assert(h.element('#ec-field-navigation').hidden, 'A standalone endpoint has no asset pager');
    h.click('#ec-back-field');
    await h.settle();
    assert.equal(h.element('#ec-field-range').textContent, '49–72 of 90 objects');
  } finally {
    h.destroy();
  }
  // Both directions of a rapid view reversal supersede the incompatible fetch.
  for (const from of ['field', 'atlas']) {
    const to = from === 'field' ? 'atlas' : 'field';
    h = await createHarness({
      envelope: from === 'field' ? envelope() : traditionalEnvelope(),
      hash: '#eclipse?view=' + from,
    });
    try {
      h.click(`[data-ec-view="${to}"]`);
      const obsolete = requests(h).at(-1);
      h.click(`[data-ec-view="${from}"]`);
      const replacement = requests(h).at(-1);
      assert.notEqual(replacement, obsolete, 'The return view starts a compatible request');
      assert(obsolete.options.signal.aborted);
      assert.equal(params(replacement).get('field_only'), from === 'field' ? 'true' : null);
      obsolete.resolve(to === 'field' ? envelope() : traditionalEnvelope());
      await h.settle();
      assert.equal(h.root.dataset.ready, 'loading', 'A late obsolete response cannot commit');
      assert.equal(h.root.dataset.view, from);
      replacement.resolve(from === 'field' ? envelope() : traditionalEnvelope());
      await h.settle();
      assert.equal(h.root.dataset.ready, 'true');
      assert.equal(h.element('#ec-field-navigation').hidden, from !== 'field');
    } finally {
      h.destroy();
    }
  }
  h = await createHarness({ envelope: envelope() });
  try {
    h.click('[data-ec-view="atlas"]');
    const pending = requests(h).at(-1);
    assert.equal(
      params(pending).get('field_only'),
      null,
      'Traditional views request their own aggregates',
    );
    h.destroyController();
    assert(pending.options.signal.aborted);
  } finally {
    h.destroy();
  }
  const dark = envelope({ total: 1 });
  dark.records.total = 0;
  dark.snapshot.counts = { findings: 0, observations: 12, assets: 1, entities: 0, dark_matter: 12 };
  dark.intelligence.graph.nodes = [
    {
      id: 'asset:dark',
      asset_id: 'dark',
      type: 'asset',
      field_object: true,
      label: 'Unresolved endpoint',
      observation_count: 12,
      dark_matter_density: 12,
      admitted_density: 0,
      dark_matter_reasons: [{ reason: 'Outside jurisdiction', count: 12 }],
      first_dark_observed_at: '2026-11-01',
      last_dark_observed_at: '2026-11-13',
    },
  ];
  dark.intelligence.graph.edges = [];
  h = await createHarness({ envelope: dark });
  try {
    assert(
      h.element('#ec-map-empty').hidden,
      'Dark-only objects remain visible without admitted findings',
    );
    assert.equal(
      h.element('#ec-dark-matter').textContent,
      '12',
      'The census counts dark source observations rather than distinct findings',
    );
    h.click('[data-ec-node="asset:dark"]');
    assert.match(h.element('#ec-inspector-content').innerHTML, /Dark matter evidence/);
    assert.match(h.element('#ec-inspector-content').innerHTML, /Outside jurisdiction/);
    assert.match(h.element('#ec-inspector-content').innerHTML, /2026-11-01/);
    h.click('[data-ec-action="dark-records"]');
    await h.settle();
    const request = requests(h).at(-1);
    assert.equal(params(request).get('intake'), 'dark_matter');
    assert.equal(params(request).get('asset_id'), 'dark');
    const listed = structuredClone(dark);
    delete listed.intelligence.field;
    listed.records = {
      kind: 'observations',
      total: 1,
      offset: 0,
      items: [
        {
          id: 'dark-source',
          record_kind: 'observation',
          observation_id: 'dark-source',
          hostname: 'dark.example.org',
          observed_day: '2026-11-01',
          dark_matter: true,
          disposition_reason: 'Outside jurisdiction',
        },
      ],
    };
    request.resolve(listed);
    await h.settle();
    assert.equal(h.element('#ec-record-title').textContent, 'Dark matter observations');
    assert.equal(
      h.element('#ec-rows').textContent,
      '0',
      'An observation is not promoted into a finding count',
    );
  } finally {
    h.destroy();
  }
  console.log(
    'Field pages beyond60, focus asset pages, exact return, revision recovery and navigation cancellation passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
