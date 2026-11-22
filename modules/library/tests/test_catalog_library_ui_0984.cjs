/** Product selection, safe public text, risk assessments and field drilldown. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('../../../tests/frontend_harness.cjs');

(async () => {
  const nodes = new Map(),
    storage = new Map();
  const context = vm.createContext({
    console,
    URLSearchParams,
    window: {},
    setTimeout: () => 1,
    clearTimeout() {},
    localStorage: { getItem: (k) => storage.get(k), setItem: (k, v) => storage.set(k, v) },
    document: {
      documentElement: { dataset: {} },
      querySelector: (s) => nodes.get(s) || null,
      querySelectorAll: () => [],
    },
  });
  const { application: ctx } = await loadApplication(context, { attach: false });
  ctx.state.navigation.boot = { settings: {} };
  ctx.actions.stamp = (s) => ctx.actions.esc(s);
  ctx.actions.toast = () => {};
  const status = { total: 4, enabled: true, bootstrap_complete: true, job: { status: 'idle' } };
  const product = {
    id: 'p1',
    vendor: 'Example <vendor>',
    product: 'Mail Server',
    sources: ['CPE', 'CNA'],
    cve_count: 2,
    critical_count: 2,
    kev_count: 1,
  };
  const detail = {
    product,
    items: [
      {
        id: 'CVE-2026-12345',
        description: '<img onerror="evil()">',
        severity: 'CRITICAL',
        score: 9.8,
        kev: true,
        versions: [
          {
            source: 'CNA',
            range: '>= 1.0, < 2.0',
            status: 'affected',
            match: { state: 'candidate', reason: 'Version fits; configuration remains unresolved' },
            conditions: 'Platform must also match',
          },
        ],
      },
    ],
    total: 1,
    limit: 25,
    offset: 0,
  };
  const observed = {
    counts: { observations: 3, endpoints: 1, entities: 1, pending_entities: 1 },
    versions: [{ version: '1.1', count: 3 }],
    items: [
      {
        entity_name: '<script>unsafe()</script>',
        entity_url: 'javascript:unsafe()',
        hostname: 'mail.example.test',
        version: '1.1',
        basis: 'Reported CVE',
        case_url: '#investigations/case-a',
        case_stage: 'Documentation',
        matched_cves: ['CVE-2026-12345'],
      },
    ],
    total: 3,
  };
  const calls = [];
  ctx.actions.api = async (url, request) => {
    calls.push(url);
    if (url === '/api/library/views')
      return request?.method === 'POST'
        ? { id: 'saved-1', name: request.body.name, selection: request.body.selection, revision: 1 }
        : [];
    if (url.endsWith('/status')) return status;
    if (url.includes('/search?')) return { items: [], total: 0 };
    if (url.includes('/products?')) return { items: [product], total: 1, index: { ready: true } };
    if (url.includes('/observations')) return observed;
    if (url.includes('/products/p1?')) return detail;
    if (url.includes('/fields/records?'))
      return {
        items: [{ id: 'CVE-2026-12345', severity: 'CRITICAL', description: 'Selected weakness' }],
        total: 1,
      };
    if (url.includes('/fields?'))
      return {
        field: 'weakness',
        population: 2,
        covered: 1,
        missing: 1,
        available_fields: [{ id: 'weakness', label: 'Weakness' }],
        items: [{ value: 'CWE-79', count: 1 }],
      };
    if (url.includes('/changes?'))
      return {
        items: [
          {
            cve_id: 'CVE-2026-12345',
            changed_at: '2026-11-11',
            fields: [{ field: 'severity', before: 'HIGH', after: 'CRITICAL' }],
          },
        ],
        total: 1,
      };
    throw Error('Unexpected endpoint ' + url);
  };
  let html = await ctx.actions.catalogSection();
  assert.match(html, /data-catalog-view="products"[^>]*aria-pressed="true"/);
  assert.match(html, /value="critical" selected/);
  assert.match(html, /Example &lt;vendor&gt;/);
  assert(calls.some((url) => url.includes('/products?') && url.includes('scope=critical')));
  assert(!calls.some((url) => url.includes('/search?')), 'Inactive CVE search is lazy');

  const region = () => ({ innerHTML: '', hidden: false, setAttribute() {}, removeAttribute() {} });
  for (const id of [
    'catalog-library',
    'catalog-products-panel',
    'catalog-product-detail',
    'catalog-cves-panel',
    'catalog-fields-panel',
    'catalog-changes-panel',
    'cve-catalog-results',
    'cve-catalog-detail',
    'catalog-cve-context',
    'catalog-saved-views',
  ])
    nodes.set('#' + id, region());
  const explainer = { dataset: { dirty: 'true' }, innerHTML: 'Unsaved source explanation' };
  nodes.set('#resource-form', explainer);
  await ctx.actions.selectCatalogProduct('p1');
  html = nodes.get('#catalog-product-detail').innerHTML;
  assert.match(html, /Observed here/);
  assert.match(html, />candidate</);
  assert.match(html, /&gt;= 1.0, &lt; 2.0/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /href="javascript:/);
  assert.match(html, /href="#investigations\/case-a"/);
  assert.match(html, /#eclipse\?product=p1&amp;scope=critical/);
  await ctx.actions.compareCatalogVersion('1.1');
  assert(calls.some((url) => url.includes('version=1.1')));
  await ctx.actions.showCatalogView('fields');
  assert.match(nodes.get('#catalog-fields-panel').innerHTML, /1<\/strong> missing or unclassified/);
  await ctx.actions.selectCatalogFieldValue('CWE-79');
  assert(
    calls.some(
      (url) =>
        url.includes('/fields/records?') &&
        url.includes('value=CWE-79') &&
        url.includes('product_id=p1'),
    ),
  );
  assert.match(nodes.get('#cve-catalog-results').innerHTML, /Selected weakness/);
  assert.equal(nodes.get('#catalog-cves-panel').hidden, false);
  await ctx.actions.showCatalogView('changes');
  assert.match(nodes.get('#catalog-changes-panel').innerHTML, /HIGH/);
  assert.match(nodes.get('#catalog-changes-panel').innerHTML, /CRITICAL/);
  await ctx.actions.saveCatalogView('Changed critical products');
  assert.equal(ctx.state.resources.catalog.library.saved.length, 1);
  assert.equal(ctx.state.resources.catalog.library.saved[0].name, 'Changed critical products');
  assert.equal(explainer.dataset.dirty, 'true');
  assert.equal(explainer.innerHTML, 'Unsaved source explanation');

  html = ctx.actions.catalogDetailMarkup({
    cve: {
      id: 'CVE-2026-12345',
      metrics: {
        cvssMetricV40: [
          {
            type: 'Secondary',
            source: 'CNA',
            cvssData: { version: '4.0', baseScore: 8.7, baseSeverity: 'HIGH' },
          },
        ],
        cvssMetricV31: [
          {
            type: 'Primary',
            source: 'NVD',
            cvssData: { version: '3.1', baseScore: 9.8, baseSeverity: 'CRITICAL' },
          },
        ],
      },
    },
    risk: {
      epss: {
        score: 0.25,
        percentile: 0.98,
        score_date: '2026-11-11',
        model_version: 'model-test',
      },
      kev: {
        listed: true,
        entry: {
          dateAdded: '2026-11-10',
          requiredAction: '<b>Official action</b>',
          knownRansomwareCampaignUse: 'Unknown',
        },
      },
    },
    observations: observed,
  });
  assert.match(html, /catalog-score[^>]*><strong>8.7/);
  assert.match(html, /25.00% probability/);
  assert.match(html, /98.0th percentile/);
  assert.match(html, /CVSS assessments · 2/);
  assert.match(html, /&lt;b&gt;Official action&lt;\/b&gt;/);
  assert.match(html, /Ransomware use: Unknown/);

  // A slow response for a previous selection cannot overwrite the next product.
  const deferred = new Map();
  ctx.actions.api = (url) =>
    url.includes('/observations')
      ? Promise.resolve(observed)
      : new Promise((resolve) => deferred.set(url.includes('/p-old?') ? 'old' : 'new', resolve));
  const old = ctx.actions.selectCatalogProduct('p-old');
  const newer = ctx.actions.selectCatalogProduct('p-new');
  deferred.get('new')({ ...detail, product: { ...product, product: 'Current product' } });
  await newer;
  deferred.get('old')({ ...detail, product: { ...product, product: 'Obsolete product' } });
  await old;
  assert.match(nodes.get('#catalog-product-detail').innerHTML, /Current product/);
  assert.doesNotMatch(nodes.get('#catalog-product-detail').innerHTML, /Obsolete product/);
  ctx.actions.stopCatalogPolling();
  console.log(
    'Library products, version candidates, local risk, source comparisons, field drilldown, saved views and stale response isolation passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
