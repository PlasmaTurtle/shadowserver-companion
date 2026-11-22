/** Local-catalog rendering, source safety, lifecycle races and edit isolation. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { loadApplication } = require('../../../tests/frontend_harness.cjs');

(async () => {
  const nodes = new Map();
  const timers = new Map();
  let timerId = 0;
  const context = vm.createContext({
    console,
    URLSearchParams,
    window: {},
    setTimeout: (fn) => {
      const id = ++timerId;
      timers.set(id, fn);
      return id;
    },
    clearTimeout: (id) => timers.delete(id),
    document: {
      documentElement: { dataset: {} },
      querySelector: (s) => nodes.get(s) || null,
      querySelectorAll: () => [],
    },
  });
  const { application: ctx } = await loadApplication(context, { attach: false });
  ctx.state.navigation.boot = { settings: {} };
  ctx.actions.stamp = (s) => ctx.actions.esc(s);
  const initial = {
    total: 0,
    bootstrap_complete: false,
    enabled: false,
    years_complete: [],
    required_years: [2002, 2003],
    job: { status: 'idle' },
  };
  let status = initial;
  const calls = [];
  ctx.actions.api = async (url, request) => {
    calls.push([url, request]);
    if (url === '/api/library/views') return [];
    if (url === '/api/cve-catalog/status') return status;
    if (url.startsWith('/api/cve-catalog/search?'))
      return { items: [], total: 0, limit: 25, offset: 0 };
    throw Error('Unexpected endpoint ' + url);
  };
  let html = await ctx.actions.catalogSection(new URLSearchParams('view=cves'));
  assert.match(html, /Download catalog/);
  assert.match(html, /Complete compressed annual feeds/);
  assert.match(html, /allow 10 GiB free/);
  assert.match(html, /id="catalog-enabled"[^>]*disabled/);
  assert.match(html, /not endorsed or certified by the NVD/);
  assert.equal(calls.length, 3);
  assert(
    calls.every(([url]) => url.startsWith('/api/cve-catalog/') || url === '/api/library/views'),
  );
  assert.equal(timers.size, 1);

  const record = {
    cve: {
      id: 'CVE-2026-12345',
      vulnStatus: 'Rejected',
      descriptions: [
        { lang: 'en', value: '<script>unsafe()</script> Fake vulnerability & description' },
      ],
      published: '2026-01-01T00:00:00Z',
      lastModified: '2026-11-11T00:00:00Z',
      references: [
        { url: 'javascript:unsafe()' },
        { url: 'data:text/html,unsafe' },
        { url: 'https://example.test/advisory?a=1&b=2', tags: ['<unsafe>'] },
      ],
      metrics: {
        cvssMetricV31: [
          {
            source: 'nvd@nist.gov',
            type: 'Primary',
            cvssData: {
              version: '3.1',
              baseScore: 9.8,
              baseSeverity: 'CRITICAL',
              vectorString: 'CVSS:3.1/AV:N',
            },
          },
        ],
      },
    },
    source: {
      url: 'https://nvd.nist.gov/feeds/json/cve/2.0/nvdcve-2.0-2026.json.gz',
      retrieved_at: '2026-11-11T01:00:00Z',
      record_sha256: 'a'.repeat(64),
    },
  };
  html = ctx.actions.catalogDetailMarkup(record);
  assert.match(html, /Rejected/);
  assert.match(html, /9\.8/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
  assert.doesNotMatch(html, /href="(?:javascript|data):/);
  assert.match(html, /https:\/\/example.test\/advisory\?a=1&amp;b=2/);
  assert.match(html, /rel="noopener noreferrer"/);
  assert.match(html, /<details class="catalog-sources"><summary>Source record/);
  assert.match(html, /This record is rejected/);
  assert.match(html, /CVSS 3.1 · nvd@nist.gov · Primary/);
  assert.match(html, /KEV: unavailable · EPSS: unavailable/);

  status = {
    ...initial,
    total: 99,
    enabled: true,
    running: true,
    years_complete: [2002],
    download_method: 'feeds',
    job: { status: 'running', message: 'Downloading 2003 <source>' },
  };
  html = ctx.actions.catalogStatusMarkup(status);
  assert.match(html, /Pause download/);
  assert.match(html, /id="catalog-enabled"[^>]*disabled/);
  assert.match(html, /Downloading 2003 &lt;source&gt;/);
  assert.match(html, /1 of 2 yearly feeds saved/);
  assert.match(html, /enabled closed-app schedule; catches up when reopened/);

  const cached = {
    ...initial,
    total: 123,
    bootstrap_complete: true,
    enabled: true,
    last_success_at: '2026-11-19T10:00:00Z',
    last_attempt_at: '2026-11-20T10:00:00Z',
    last_error: 'NVD TLS verification failed.',
    next_check_at: '2026-11-20T11:00:00Z',
  };
  const failedSync = ctx.actions.catalogStatusMarkup(cached);
  assert.match(failedSync, /Last update failed/);
  assert.match(failedSync, /123<\/strong><span>CVEs stored locally/);
  assert.match(failedSync, /Last successful sync 2026-11-19/);
  assert.match(failedSync, /Last attempt 2026-11-20.*NVD TLS verification failed/);
  assert.match(failedSync, /Next check 2026-11-20T11/);
  assert.match(ctx.actions.catalogStatusMarkup({ ...cached, running: true }), />Updating</);
  assert.match(ctx.actions.catalogStatusMarkup({ ...cached, last_error: null }), />Ready</);

  const pausedBeforeFirstYear = ctx.actions.catalogStatusMarkup({ ...initial, enabled: true });
  assert.doesNotMatch(
    pausedBeforeFirstYear.match(/<input id="catalog-enabled"[^>]*>/)[0],
    /disabled/,
  );

  const makeRegion = () => ({
    innerHTML: '',
    attributes: {},
    setAttribute(k, v) {
      this.attributes[k] = v;
    },
    removeAttribute(k) {
      delete this.attributes[k];
    },
  });
  const resultRegion = makeRegion(),
    detailRegion = makeRegion(),
    statusRegion = makeRegion();
  nodes.set('#cve-catalog', {});
  nodes.set('#cve-catalog-results', resultRegion);
  nodes.set('#cve-catalog-detail', detailRegion);
  nodes.set('#cve-catalog-status', statusRegion);
  const explainer = { dataset: { dirty: 'true' }, innerHTML: 'Unrelated unsaved explanation' };
  nodes.set('#resource-form', explainer);

  let firstResolve, secondResolve;
  ctx.actions.api = (url) =>
    new Promise((resolve) => {
      if (url.includes('q=old')) firstResolve = resolve;
      else if (url.includes('q=new')) secondResolve = resolve;
      else throw Error(url);
    });
  const first = ctx.actions.searchCatalog('old', '', 0);
  const second = ctx.actions.searchCatalog('new', 'HIGH', 25);
  secondResolve({
    items: [
      {
        id: 'CVE-2026-22222',
        description: '<img onerror="bad">',
        severity: 'HIGH',
        status: 'Analyzed',
      },
    ],
    total: 70,
    limit: 25,
    offset: 25,
  });
  await second;
  firstResolve({
    items: [{ id: 'CVE-2026-11111', description: 'Obsolete response' }],
    total: 1,
    limit: 25,
    offset: 0,
  });
  await first;
  assert.match(resultRegion.innerHTML, /CVE-2026-22222/);
  assert.doesNotMatch(resultRegion.innerHTML, /CVE-2026-11111/);
  assert.match(resultRegion.innerHTML, /&lt;img/);
  assert.match(resultRegion.innerHTML, /data-offset="50"/);
  assert.equal(ctx.state.resources.catalog.query, 'new');

  ctx.actions.api = async (url) => {
    assert.match(url, /^\/api\/cve-catalog\/records\//);
    return record;
  };
  await ctx.actions.selectCatalogRecord('CVE-2026-12345');
  assert.match(detailRegion.innerHTML, /CVE-2026-12345/);
  assert.equal(explainer.dataset.dirty, 'true');
  assert.equal(explainer.innerHTML, 'Unrelated unsaved explanation');

  let resolveLate;
  ctx.actions.api = () =>
    new Promise((resolve) => {
      resolveLate = resolve;
    });
  const pending = ctx.actions.selectCatalogRecord('CVE-2026-33333');
  const replacement = makeRegion();
  nodes.set('#cve-catalog-detail', replacement);
  resolveLate(record);
  await pending;
  assert.equal(replacement.innerHTML, '', 'A departed view cannot receive a late detail');

  const requests = [];
  ctx.actions.api = async (url, request) => {
    requests.push([url, request]);
    if (url === '/api/cve-catalog/settings') return { ...initial, enabled: false };
    return { ...initial, enabled: false };
  };
  await ctx.actions.catalogCommand('settings', false);
  assert.equal(requests[0][1].body.enabled, false);
  assert.equal(requests[0][1].method, 'POST');
  assert.equal(explainer.dataset.dirty, 'true');
  ctx.actions.stopCatalogPolling();
  assert.equal(timers.size, 0);

  const events = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../static/library_events.js'), 'utf8'),
    { context },
  );
  await events.link(() => {
    throw Error('Unexpected import');
  });
  await events.evaluate();
  const handlers = events.namespace.createHandlers(ctx);
  let query;
  ctx.actions.searchCatalog = (...args) => {
    query = args;
  };
  await handlers.forms['catalog-search-form']({}, { query: 'Apache', severity: 'CRITICAL' });
  assert.deepEqual(query, ['Apache', 'CRITICAL', 0]);
  console.log(
    'CVE catalog UI: local-only search, source escaping, provenance disclosure, daily controls, stale-response rejection and explainer edit isolation passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
