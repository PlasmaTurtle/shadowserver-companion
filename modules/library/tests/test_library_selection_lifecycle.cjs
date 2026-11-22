/** Selection correctness and independent loading through the actual application modules. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('../../../tests/frontend_harness.cjs');

async function fixture() {
  const historyWrites = [];
  const nodes = new Map(),
    storage = new Map(),
    calls = [];
  const region = () => ({ innerHTML: '', hidden: false, setAttribute() {}, removeAttribute() {} });
  const context = vm.createContext({
    console,
    URLSearchParams,
    window: {
      history: {
        replaceState(_state, _title, url) {
          historyWrites.push(url);
        },
      },
    },
    setTimeout: () => 1,
    clearTimeout() {},
    localStorage: {
      getItem: (k) => storage.get(k),
      setItem: (k, v) => storage.set(k, v),
      removeItem: (k) => storage.delete(k),
    },
    document: {
      documentElement: { dataset: {} },
      querySelector: (s) => nodes.get(s) || null,
      querySelectorAll: () => [],
    },
  });
  const { application: app } = await loadApplication(context, { attach: false });
  app.state.navigation.boot = { settings: {} };
  app.actions.toast = () => {};
  for (const id of [
    'catalog-library',
    'catalog-products-panel',
    'catalog-product-detail',
    'catalog-cves-panel',
    'catalog-fields-panel',
    'catalog-changes-panel',
    'catalog-dark-matter-panel',
    'cve-catalog-results',
    'cve-catalog-detail',
    'catalog-cve-context',
    'catalog-saved-views',
    'cve-catalog',
    'cve-catalog-status',
    'library-explainers',
    'library-search-results',
  ])
    nodes.set('#' + id, region());
  const empty = { items: [], total: 0, limit: 25, offset: 0 };
  const status = { total: 1, bootstrap_complete: true, running: false, job: { status: 'idle' } };
  app.actions.api = async (url) => {
    calls.push(url);
    return url === '/api/library/views' ? [] : url.endsWith('/status') ? status : empty;
  };
  return { app, nodes, storage, calls, empty, status, historyWrites };
}

(async () => {
  {
    const { app, historyWrites } = await fixture();
    app.state.navigation.currentRoute = 'workspace';
    await app.actions.loadDarkMatter();
    assert.deepEqual(
      historyWrites,
      [],
      'A late source-browser completion cannot navigate back to Library',
    );
  }
  {
    const { app } = await fixture();
    app.state.resources.catalog.library.view = 'cves';
    app.state.resources.catalog.severity = '';
    app.state.resources.catalog.query = 'mail';
    const link = app.actions.catalogSelectionURL();
    assert.equal(new URLSearchParams(link.split('?')[1]).get('severity'), '');
    const fresh = await fixture();
    await fresh.app.actions.catalogSection(new URLSearchParams(link.split('?')[1]));
    assert.equal(fresh.app.state.resources.catalog.severity, '');
    assert.equal(fresh.app.state.resources.catalog.query, 'mail');
    await fresh.app.actions.catalogSection(new URLSearchParams('view=cves&severity=HIGH'));
    assert.equal(
      fresh.app.state.resources.catalog.query,
      '',
      'An unrelated previous query is not retained',
    );
    assert.equal(fresh.app.state.resources.catalog.severity, 'HIGH');
  }
  {
    const { app, nodes, empty } = await fixture();
    const { createHandlers } = await import('../static/library_events.js');
    const events = createHandlers(app);
    const requests = [];
    let finishExplore;
    app.actions.api = async (url, options) => {
      const params = new URLSearchParams(url.split('?')[1]);
      if (url.includes('/fields/records?')) {
        requests.push([params.get('field'), params.get('value'), params.get('offset')]);
        return empty;
      }
      if (url.includes('/fields?')) {
        const field = params.get('field');
        if (field === 'attack_vector')
          return new Promise((resolve) => (finishExplore = () => resolve({ field, ...empty })));
        return { field, items: [{ value: 'CWE-79', count: 1 }], population: 1 };
      }
      if (options?.method === 'POST') return { id: 'saved', revision: 1, ...options.body };
      return empty;
    };
    await app.actions.showCatalogView('fields');
    const pending = app.actions.loadCatalogFields('attack_vector');
    // Click the still-visible weakness row while the next field's groups are loading.
    const markup = nodes.get('#catalog-fields-panel').innerHTML;
    const row = markup.match(/<button [^>]*data-catalog-field-value="CWE-79"[^>]*>/)[0];
    const button = {
      dataset: {
        catalogField: row.match(/data-catalog-field="([^"]+)"/)?.[1],
        catalogFieldValue: 'CWE-79',
      },
    };
    await events.click.find((handler) => handler.matches(button)).run(button);
    finishExplore();
    await pending;
    const library = app.state.resources.catalog.library;
    assert.equal(library.field, 'attack_vector');
    assert.equal(library.fieldSelection.field, 'weakness');
    const params = new URLSearchParams(app.actions.catalogSelectionURL().split('?')[1]);
    await app.actions.saveCatalogView('Selected weakness');
    await events.actions['catalog-page']({ dataset: { offset: '25' } });
    await app.actions.applyCatalogView('saved');
    await app.actions.loadCatalogLibrary(params);
    assert.deepEqual(requests, [
      ['weakness', 'CWE-79', '0'],
      ['weakness', 'CWE-79', '25'],
      ['weakness', 'CWE-79', '0'],
      ['weakness', 'CWE-79', '0'],
    ]);
    assert.equal(library.field, 'attack_vector');
    const legacyLink = new URLSearchParams({
      view: 'cves',
      field: 'reference_type',
      field_value: '🌍'.repeat(300),
    });
    await app.actions.loadCatalogLibrary(legacyLink);
    assert.deepEqual(requests.at(-1), ['reference_type', legacyLink.get('field_value'), '0']);
  }
  {
    const { app, nodes } = await fixture();
    let resolve;
    app.actions.api = (url) =>
      url.includes('/observations') ? Promise.resolve(null) : new Promise((r) => (resolve = r));
    const pending = app.actions.selectCatalogProduct('synthetic-product');
    await app.actions.clearCatalogProduct();
    resolve({
      product: { id: 'synthetic-product', product: 'Obsolete product' },
      items: [],
      total: 0,
    });
    await pending;
    assert.equal(app.state.resources.catalog.library.productId, '');
    assert.equal(app.state.resources.catalog.library.product, null);
    assert.match(nodes.get('#catalog-product-detail').innerHTML, /Explore affected products/);
    assert.doesNotMatch(nodes.get('#catalog-product-detail').innerHTML, /Obsolete product/);
  }
  {
    const { app, nodes, calls, empty, status } = await fixture();
    const state = app.state.resources.catalog;
    state.status = { ...status, running: true, job: { status: 'running' } };
    state.library.view = 'cves';
    state.library.fieldSelection = { field: 'weakness', value: 'CWE-79' };
    app.actions.api = async (url) => {
      calls.push(url);
      return url.endsWith('/status')
        ? status
        : {
            ...empty,
            items: [
              {
                id: url.includes('/fields/records?') ? 'CVE-2026-10001' : 'CVE-2026-99999',
                description: 'Scoped membership',
              },
            ],
            total: 1,
          };
    };
    await app.actions.refreshCatalogStatus();
    assert.match(nodes.get('#catalog-cve-context').innerHTML, /CWE-79/);
    assert.match(nodes.get('#cve-catalog-results').innerHTML, /CVE-2026-10001/);
    assert.equal(state.result.items[0].id, 'CVE-2026-10001');
    assert(calls.some((url) => url.includes('/fields/records?') && url.includes('value=CWE-79')));
    assert(!calls.some((url) => url.includes('/search?')));
  }
  {
    const { app, calls, empty } = await fixture();
    app.actions.api = async (url) => {
      calls.push(url);
      if (url === '/api/library/views') return [];
      if (url.startsWith('/api/dark-matter')) return { ...empty, fields: [] };
      throw Error('Optional catalog unavailable');
    };
    await app.actions.catalogSection(new URLSearchParams('view=dark-matter'));
    assert.equal(app.state.resources.catalog.library.view, 'dark-matter');
    assert(calls.some((url) => url.startsWith('/api/dark-matter?')));
    assert(!calls.some((url) => url.includes('/api/cve-catalog/search')));
  }
  {
    const { app, calls } = await fixture();
    await app.actions.catalogSection(new URLSearchParams('view=changes'));
    assert(calls.some((url) => url.includes('/changes?')));
    assert(!calls.some((url) => url.includes('/search?') || url.includes('/products?')));
  }
  {
    const { app, nodes, calls, empty, status } = await fixture();
    let resolveStatus;
    app.actions.api = async (url) => {
      calls.push(url);
      if (url === '/api/library/views') return [];
      if (url.endsWith('/status')) return new Promise((r) => (resolveStatus = r));
      if (url.startsWith('/api/explainers')) throw Error('Synthetic explainer read failure');
      return empty;
    };
    const shell = await app.actions.resourcesPage();
    assert.deepEqual(
      calls,
      [],
      'The skeleton is immediately renderable without waiting for storage',
    );
    assert.match(shell, /library-explainers/);
    const mounted = app.actions.mountLibraryPage();
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(nodes.get('#library-explainers').innerHTML, /Synthetic explainer read failure/);
    assert(
      calls.some((url) => url.includes('/products?')),
      'Catalog loads despite explainer failure and pending status',
    );
    resolveStatus(status);
    await mounted;
  }
  {
    const { app, nodes, storage } = await fixture();
    const saved = [];
    storage.set(
      'companion-library-views',
      JSON.stringify([
        {
          label: 'Old shared label',
          view: 'cves',
          scope: 'critical',
          cveQuery: 'Apache',
          cveSeverity: 'HIGH',
          field: 'attack_vector',
          fieldSelection: { field: 'weakness', value: 'CWE-79' },
        },
        {
          label: 'Old shared label',
          view: 'cves',
          scope: 'critical',
          cveQuery: 'Exchange',
          cveSeverity: '',
          field: 'reference_type',
          fieldSelection: { value: '🌍'.repeat(2001) },
        },
      ]),
    );
    app.actions.api = async (url, options = {}) => {
      if (url === '/api/library/views/import') {
        for (const view of options.body.views)
          saved.push({ id: 'v' + saved.length, revision: 1, ...view });
        return [...saved];
      }
      if (url === '/api/library/views' && options.method === 'POST') {
        const view = { id: 'v' + saved.length, revision: 1, ...options.body };
        saved.push(view);
        return view;
      }
      if (url === '/api/library/views') return [...saved];
      if (options.method === 'PUT') {
        assert.equal(options.body.expected_revision, 1);
        return { id: 'v2', revision: 2, ...options.body };
      }
      if (options.method === 'DELETE') {
        assert.match(url, /expected_revision=2/);
        return { ok: true };
      }
      return { items: [], total: 0 };
    };
    await app.actions.loadCatalogViews();
    assert.equal(storage.has('companion-library-views'), false);
    assert.equal(
      app.state.resources.catalog.library.saved.length,
      2,
      'Different legacy selections survive identical display names',
    );
    await app.actions.applyCatalogView('v0');
    assert.equal(app.state.resources.catalog.query, 'Apache');
    assert.equal(app.state.resources.catalog.library.fieldSelection.field, 'weakness');
    await app.actions.applyCatalogView('v1');
    assert.equal(app.state.resources.catalog.query, 'Exchange');
    assert.equal(app.state.resources.catalog.library.fieldSelection.field, 'reference_type');
    assert.equal(app.state.resources.catalog.library.fieldSelection.value, '🌍'.repeat(2000));
    assert.equal(app.state.resources.catalog.severity, '');
    await app.actions.saveCatalogView('Named research');
    assert.equal(app.state.resources.catalog.library.saved.length, 3);
    nodes.set('#catalog-view-name', { value: 'Renamed research' });
    await app.actions.updateCatalogView();
    assert.equal(app.state.resources.catalog.library.saved[0].name, 'Renamed research');
    await app.actions.removeCatalogView();
    assert.equal(app.state.resources.catalog.library.saved.length, 2);
  }
  {
    const { app, nodes, empty, status } = await fixture();
    const pending = [];
    app.actions.api = async (url) => {
      if (url === '/api/library/views') return [];
      if (url.startsWith('/api/explainers'))
        return [
          {
            id: 'ready',
            title: 'Available immediately',
            body: 'Preserved wording',
            sources: '',
            revision: 1,
          },
        ];
      return new Promise((resolve) =>
        pending.push(() => resolve(url.endsWith('/status') ? status : empty)),
      );
    };
    await app.actions.resourcesPage();
    const mounted = app.actions.mountLibraryPage();
    await new Promise((resolve) => setImmediate(resolve));
    assert.match(
      nodes.get('#library-explainers').innerHTML,
      /Available immediately/,
      'A slow catalog cannot delay an available editor',
    );
    assert.equal(pending.length, 2);
    pending.forEach((resolve) => resolve());
    await mounted;
  }
  {
    const { app, storage } = await fixture();
    const legacy = JSON.stringify([{ label: 'Keep me', view: 'cves', scope: 'critical' }]);
    storage.set('companion-library-views', legacy);
    app.actions.api = async (url) => {
      if (url === '/api/library/views') return [];
      throw Error('Storage write unavailable');
    };
    await app.actions.loadCatalogViews();
    assert.equal(
      storage.get('companion-library-views'),
      legacy,
      'Failed migration retains the only original copy',
    );
    assert.match(app.state.resources.catalog.library.savedError, /Storage write unavailable/);
  }
  {
    const { app, nodes } = await fixture();
    app.actions.api = async () => ({
      groups: {
        cves: { items: [], total: 0, error: 'Catalog unavailable' },
        products: {
          items: [{ id: 'product:example', vendor: 'Example', product: 'Mail' }],
          total: 1,
          notice: 'Product search covers 1 of 2 local CVE records.',
        },
        explainers: { items: [{ id: 'one', title: 'Safe <script> text', revision: 3 }], total: 1 },
      },
    });
    await app.actions.searchLibrary('mail');
    const html = nodes.get('#library-search-results').innerHTML;
    assert.match(html, /Catalog unavailable/);
    assert.match(html, /Product search covers 1 of 2 local CVE records/);
    assert.match(html, /Example · Mail/);
    assert.match(html, /Safe &lt;script&gt; text/);
    assert.match(html, /item=one/);
    assert.match(html, /scope=all/);
  }
  {
    const { app, nodes } = await fixture();
    const attributes = new Map();
    const region = nodes.get('#library-search-results');
    region.setAttribute = (name, value) => attributes.set(name, value);
    region.removeAttribute = (name) => attributes.delete(name);
    let finish;
    app.actions.api = () => new Promise((resolve) => (finish = resolve));
    const pending = app.actions.searchLibrary('mail');
    assert.equal(attributes.get('aria-busy'), 'true');
    await app.actions.searchLibrary('   ');
    assert.equal(attributes.has('aria-busy'), false);
    finish({ groups: {} });
    await pending;
    assert.equal(region.innerHTML, '');
    assert.equal(attributes.has('aria-busy'), false);
  }
  {
    const { app, nodes, calls } = await fixture();
    const region = { innerHTML: '', setAttribute() {}, removeAttribute() {} };
    nodes.set('#catalog-change-impact', region);
    app.actions.api = async (url) => {
      calls.push(url);
      return {
        cve_id: 'CVE-2026-10001',
        current: { available: true, status: 'Analyzed', severity: 'CRITICAL', catalog_stale: true },
        cases: {
          items: [
            {
              id: 'case-one',
              title: 'Synthetic <case>',
              stage: 'completed',
              url: '#workspace/notifications/case-one',
              certified: true,
              changed: true,
              changes: [{ field: 'description', label: 'Description' }],
              reason: 'Current reference differs',
              pinned_revision_id: 'immutable-reference',
            },
          ],
          total: 26,
          limit: 25,
          offset: 25,
          include_completed: true,
          unreadable_cases: 1,
          basis: 'Preserved case selections compared with current local reference.',
        },
      };
    };
    await app.actions.loadCatalogImpact('CVE-2026-10001', 25, true);
    assert.match(calls[0], /offset=25/);
    assert.match(calls[0], /include_completed=true/);
    assert.match(region.innerHTML, /Certified copy retained/);
    assert.match(region.innerHTML, /Reference changed/);
    assert.match(region.innerHTML, /Coverage is incomplete/);
    assert.match(region.innerHTML, /Catalog update due/);
    assert.match(region.innerHTML, /Synthetic &lt;case&gt;/);
    assert.match(region.innerHTML, /#workspace\/notifications\/case-one/);
    assert.match(region.innerHTML, /changes no draft/);
    assert.doesNotMatch(region.innerHTML, /data-action="adopt/);
  }
  console.log(
    'Library selections: complete links, cleared requests, exact refresh membership, isolated active panels, workspace view migration/CRUD, and typed search passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
