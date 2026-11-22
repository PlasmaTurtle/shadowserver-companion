/** Dark Matter is a bounded reference field, distinct from workflow and priority. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('../../../tests/frontend_harness.cjs');

(async () => {
  const nodes = new Map();
  const context = vm.createContext({
    console,
    URLSearchParams,
    window: {},
    localStorage: { getItem: () => null },
    document: {
      documentElement: { dataset: {} },
      querySelector: (s) => nodes.get(s) || null,
      querySelectorAll: () => [],
    },
  });
  const { application: ctx } = await loadApplication(context, { attach: false });
  ctx.state.navigation.boot = { settings: {} };
  ctx.state.resources.catalog.status = { total: 0 };
  ctx.actions.stamp = ctx.actions.esc;
  const calls = [];
  const records = {
    total: 30,
    limit: 25,
    offset: 0,
    counts: { rejected: 30 },
    items: [
      {
        record_id: 'source-row',
        import_id: 'first',
        report_type: 'scan_http_vulnerable',
        hostname: '',
        ip: null,
        stage: 'filter',
        outcome: 'rejected',
        reason: 'invalid_ip',
        source: { name: '<img onerror="bad()">', sheet: 'CSV', row: 2 },
        raw_fields: {
          ip: 'bad-ip',
          tag: '<script>bad()</script>',
          future_column: 'complete value',
          http_code: '503',
        },
        normalized_fields: {
          ip: null,
          tag: '<script>bad()</script>',
          future_column: 'complete value',
          http_code: 503,
        },
        errors: { ip: 'Invalid IP' },
      },
    ],
  };
  ctx.actions.api = async (url) => {
    calls.push(url);
    if (url === '/api/dark-matter/fields')
      return {
        fields: [
          { name: 'http_code', type: 'integer' },
          { name: 'future_column', type: 'text' },
          { name: 'port', type: 'port' },
        ],
      };
    assert.match(url, /^\/api\/dark-matter\?/);
    return records;
  };
  await ctx.actions.loadCatalogLibrary(new URLSearchParams('view=dark-matter&dark_query=example'));
  const html = ctx.actions.catalogLibraryMarkup('<p>CVEs</p>');
  assert.equal(calls.length, 2, 'The archive browser needs only its own field and record APIs.');
  assert.match(calls[1], /q=example/);
  assert.match(html, /Dark Matter/);
  assert.match(html, /intake=dark_matter/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>|<img /);
  assert.match(html, /Hostname missing/);
  assert.match(html, /future_column/);
  assert.match(html, /complete value/);
  assert.match(html, /All 4 source fields/);
  assert.match(html, /catalog-dark-matter-page/);
  const panel = { innerHTML: '', setAttribute() {}, removeAttribute() {} };
  nodes.set('#catalog-dark-matter-panel', panel);
  await ctx.actions.loadDarkMatter(
    { field: 'http_code', operator: 'gte', value: '500', query: '' },
    25,
  );
  const parameters = new URL(calls.at(-1), 'https://local.test').searchParams;
  assert.equal(parameters.get('offset'), '25');
  assert.deepEqual(JSON.parse(parameters.get('filters')), [
    { field: 'http_code', op: 'gte', source: 'normalized', value: 500 },
  ]);
  assert.match(ctx.actions.catalogSelectionURL(), /dark_field=http_code/);
  await ctx.actions.loadDarkMatter({ field: 'port', operator: 'eq', value: '443' });
  assert.equal(
    JSON.parse(new URL(calls.at(-1), 'https://local.test').searchParams.get('filters'))[0].value,
    443,
  );
  await ctx.actions.loadDarkMatter({ field: 'ip', operator: 'invalid' });
  assert.deepEqual(
    JSON.parse(new URL(calls.at(-1), 'https://local.test').searchParams.get('filters')),
    [{ field: 'ip', op: 'invalid', source: 'normalized' }],
  );
  await ctx.actions.loadCatalogLibrary(new URLSearchParams('view=dark-matter'));
  assert.equal(ctx.state.resources.catalog.library.darkMatterSelection.field, '');
  assert.equal(ctx.state.resources.catalog.library.darkMatterSelection.query, '');
  ctx.actions.api = async () => {
    throw Error('Source <unavailable>');
  };
  await ctx.actions.loadDarkMatter({ query: 'unmatched' });
  assert.match(panel.innerHTML, /Source &lt;unavailable&gt;/);
  assert.doesNotMatch(
    panel.innerHTML,
    /complete value/,
    'Failed queries never relabel previous records.',
  );
  ctx.actions.api = async () => ({ total: 0, items: [] });
  await ctx.actions.clearDarkMatter();
  assert.doesNotMatch(panel.innerHTML, /catalog-dark-matter-clear/);
  assert.match(panel.innerHTML, /No observations match this view/);
  const { filterRows } = await import('../../observatory/static/eclipse_model.js');
  const rows = [
    { id: 'residue', intake_disposition: 'dark_matter', dark_matter: true },
    { id: 'admitted', intake_disposition: 'lead' },
    { id: 'legacy' },
  ];
  assert.deepEqual(
    filterRows(rows, { intake: 'dark_matter' }).map((r) => r.id),
    ['residue'],
  );
  assert.deepEqual(
    filterRows(rows, { intake: 'unclassified' }).map((r) => r.id),
    ['legacy'],
  );
  assert.deepEqual(
    filterRows(rows, { intake: 'lead' }).map((r) => r.id),
    ['admitted'],
  );
  console.log(
    'Dark Matter reference view, catalog independence, safe rendering, paging and explicit observation filtering passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
