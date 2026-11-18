/** Dark Matter is a bounded reference field, distinct from workflow and priority. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');

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
  ctx.actions.api = async (url) => {
    calls.push(url);
    assert.match(url, /^\/api\/dark-matter\?/);
    return {
      total: 30,
      limit: 25,
      offset: 0,
      counts: { dark_matter: 30, lead: 4 },
      reasons: [{ label: 'Outside scope', total: 30 }],
      items: [
        {
          hostname: 'mail.example.com',
          ip: '8.8.8.8',
          tag: '<script>bad()</script>',
          version: 'PHP/7',
          reason_label: 'Below threshold',
          region: 'NC',
          city: 'City',
          import_id: 'first',
          import_name: '<img onerror="bad()">',
          sheet: 'CSV',
          row: 2,
          observed_at: '2026-11-12',
          entity_id: 'known',
          entity_name: 'Example',
          clipped_fields: [],
        },
      ],
    };
  };
  await ctx.actions.loadCatalogLibrary(new URLSearchParams('view=dark-matter&dark_query=example'));
  const html = ctx.actions.catalogLibraryMarkup('<p>CVEs</p>');
  assert.equal(calls.length, 1, 'Dark Matter works without a downloaded CVE catalog');
  assert.match(calls[0], /q=example/);
  assert.match(html, /Dark Matter/);
  assert.match(html, /intake=dark_matter/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>|<img /);
  assert.match(html, /Recorded business association/);
  assert.match(html, /catalog-dark-matter-page/);
  assert.match(html, /Each physical observation counts once/);
  const panel = { innerHTML: '', setAttribute() {}, removeAttribute() {} };
  nodes.set('#catalog-dark-matter-panel', panel);
  await ctx.actions.loadDarkMatter('city', 25);
  assert.match(calls[1], /offset=25/);
  assert.match(panel.innerHTML, /Dark Matter/);
  assert.match(panel.innerHTML, /catalog-dark-matter-clear/);
  await ctx.actions.loadCatalogLibrary(new URLSearchParams('view=dark-matter'));
  assert.equal(
    ctx.state.resources.catalog.library.darkMatterQuery,
    '',
    'An explicit unfiltered view clears a previous query.',
  );
  ctx.actions.api = async () => {
    throw Error('Source <unavailable>');
  };
  await ctx.actions.loadDarkMatter('unmatched', 0);
  assert.match(panel.innerHTML, /Source &lt;unavailable&gt;/);
  assert.doesNotMatch(
    panel.innerHTML,
    /mail.example.com/,
    'Failed searches do not relabel previous results.',
  );
  assert.match(panel.innerHTML, /No observations match this search/);
  ctx.actions.api = async () => ({ total: 0, items: [], counts: { dark_matter: 0, lead: 0 } });
  await ctx.actions.loadDarkMatter('', 0);
  assert.doesNotMatch(panel.innerHTML, /catalog-dark-matter-clear/);
  assert.match(panel.innerHTML, /No observations match this view/);
  ctx.actions.api = async () => ({
    total: 1,
    items: [
      {
        hostname: 'legacy.example.com',
        import_id: 'old',
        disposition: 'qualification_unknown',
        known_aggregate_admitted: true,
        reason_label: 'Qualification provenance unavailable',
      },
    ],
    counts: {
      dark_matter: 0,
      lead: 1,
      qualification_unknown: 1,
      known_aggregate_qualified_observations: 2,
    },
  });
  await ctx.actions.loadDarkMatter('', 0);
  assert.match(panel.innerHTML, /<strong>1<\/strong> qualification unavailable/);
  assert.match(panel.innerHTML, /catalog-match">Qualification unavailable/);
  assert.doesNotMatch(panel.innerHTML, /catalog-match">Dark Matter/);
  assert.match(
    panel.innerHTML,
    /Earlier qualification is recorded; exact condition approval is unavailable/,
  );
  const { filterRows } = await import('../static/eclipse_model.js');
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
