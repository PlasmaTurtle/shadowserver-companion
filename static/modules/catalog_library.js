import { createLibraryRender } from './catalog_library_render.js';

/** Shared selections for product research, CVEs, fields and material changes. */
export function installLibrary(ctx) {
  const state = (ctx.state.resources.catalog.library = {
    view: 'products',
    query: '',
    scope: 'critical',
    productId: '',
    version: '',
    field: 'weakness',
    products: null,
    product: null,
    observed: null,
    fields: null,
    changes: null,
    darkMatter: null,
    darkMatterQuery: '',
    darkMatterRequest: 0,
    error: '',
    request: 0,
    productRequest: 0,
    fieldRequest: 0,
    changeRequest: 0,
    fieldSelection: null,
    saved: [],
  });
  const render = createLibraryRender(ctx, state),
    esc = (value) => ctx.actions.esc(value ?? ''),
    allowedScopes = new Set(['critical', 'critical_kev', 'kev', 'all']),
    allowedViews = new Set(['products', 'cves', 'fields', 'changes', 'dark-matter']);
  const api = (path, params) =>
    ctx.actions.api('/api/cve-catalog/' + path + (params ? '?' + new URLSearchParams(params) : ''));
  const optional = (promise) => promise.catch(() => null);

  function catalogSelectionURL(selection = state) {
    if (selection.view === 'dark-matter') {
      const params = new URLSearchParams({ view: 'dark-matter' });
      if (selection.darkMatterQuery) params.set('dark_query', selection.darkMatterQuery);
      return '#library?' + params;
    }
    const params = new URLSearchParams({ view: selection.view, scope: selection.scope });
    if (selection.view === 'dark-matter' && selection.darkMatterQuery)
      params.set('dark_query', selection.darkMatterQuery);
    if (selection.query) params.set('product_query', selection.query);
    if (selection.productId) params.set('product', selection.productId);
    if (selection.version) params.set('version', selection.version);
    if (selection.field) params.set('field', selection.field);
    if (selection.fieldSelection?.value) params.set('field_value', selection.fieldSelection.value);
    if (selection.view === 'cves') {
      const catalog = ctx.state.resources.catalog;
      if (catalog.query) params.set('q', catalog.query);
      if (catalog.severity) params.set('severity', catalog.severity);
    }
    if (selection.view === 'cves' && ctx.state.resources.catalog.selected)
      params.set('cve', ctx.state.resources.catalog.selected);
    return '#library?' + params;
  }

  function rememberSelection() {
    if (typeof window !== 'undefined' && window.history?.replaceState) {
      window.history.replaceState(null, '', catalogSelectionURL());
      if (ctx.state.navigation.currentRoute?.startsWith('library'))
        ctx.state.navigation.currentRoute = catalogSelectionURL().slice(1);
    }
  }

  function savedMarkup() {
    return `<div class="catalog-saved-views"><label for="catalog-saved-view">Saved views</label><select id="catalog-saved-view"><option value="">Choose a saved view</option>${state.saved.map((item, index) => `<option value="${index}">${esc(item.label)}</option>`).join('')}</select><button class="button" data-action="catalog-save-view">Save this view</button>${state.saved.length ? '<button class="button" data-action="catalog-remove-view">Remove selected</button>' : ''}</div>`;
  }

  function catalogLibraryMarkup(cveMarkup) {
    return `<div id="catalog-library"><div class="catalog-library-nav"><nav class="catalog-tabs" aria-label="Library catalog views">${[
      ['products', 'Products'],
      ['cves', 'CVEs'],
      ['fields', 'Fields'],
      ['changes', 'Changes'],
      ['dark-matter', 'Dark Matter'],
    ]
      .map(
        ([view, name]) =>
          `<button type="button" data-catalog-view="${view}" aria-controls="catalog-${view}-panel" aria-pressed="${state.view === view}">${name}</button>`,
      )
      .join(
        '',
      )}</nav><a id="catalog-view-link" class="text-link" href="${esc(catalogSelectionURL())}">Link to this view</a></div><div id="catalog-saved-views">${savedMarkup()}</div><section id="catalog-products-panel" ${state.view === 'products' ? '' : 'hidden'}>${render.productsPanel()}</section><section id="catalog-cves-panel" ${state.view === 'cves' ? '' : 'hidden'}><div id="catalog-cve-context">${cveContext()}</div>${cveMarkup}</section><section id="catalog-fields-panel" ${state.view === 'fields' ? '' : 'hidden'}>${render.fieldsPanel()}</section><section id="catalog-changes-panel" ${state.view === 'changes' ? '' : 'hidden'}>${render.changesPanel()}</section><section id="catalog-dark-matter-panel" ${state.view === 'dark-matter' ? '' : 'hidden'}>${render.darkMatterPanel()}</section></div>`;
  }

  function cveContext() {
    if (!state.fieldSelection) return '';
    return `<div class="catalog-selection-note"><span>${esc(state.fieldSelection.field)}: <strong>${esc(state.fieldSelection.value)}</strong> · ${esc(state.scope.replaceAll('_', ' + '))}</span><button class="button" data-action="catalog-clear-field">Clear field selection</button></div>`;
  }

  function updateSelectionControls() {
    ctx.actions.$$('[data-catalog-view]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.catalogView === state.view));
    });
    for (const view of allowedViews) {
      const panel = ctx.actions.$('#catalog-' + view + '-panel');
      if (panel) panel.hidden = view !== state.view;
    }
    const link = ctx.actions.$('#catalog-view-link');
    if (link) link.href = catalogSelectionURL();
    const context = ctx.actions.$('#catalog-cve-context');
    if (context) context.innerHTML = cveContext();
    rememberSelection();
  }

  function restoreSelection(params) {
    const view = params.get('view'),
      scope = params.get('scope');
    if (allowedViews.has(view)) state.view = view;
    if (params.get('cve')) state.view = 'cves';
    if (allowedScopes.has(scope)) state.scope = scope;
    if (view === 'dark-matter' && !params.has('dark_query')) state.darkMatterQuery = '';
    if (params.has('dark_query')) state.darkMatterQuery = params.get('dark_query').slice(0, 200);
    if (params.has('product_query')) state.query = params.get('product_query').slice(0, 200);
    if (params.has('product')) state.productId = params.get('product').slice(0, 160);
    if (params.has('version')) state.version = params.get('version').slice(0, 160);
    if (params.has('field')) state.field = params.get('field').slice(0, 80);
    state.fieldSelection = params.has('field_value')
      ? { field: state.field, value: params.get('field_value').slice(0, 300) }
      : null;
    try {
      const saved = JSON.parse(localStorage.getItem('companion-library-views') || '[]');
      state.saved = Array.isArray(saved)
        ? saved
            .filter(
              (v) =>
                v &&
                typeof v.label === 'string' &&
                allowedViews.has(v.view) &&
                allowedScopes.has(v.scope),
            )
            .slice(0, 20)
        : [];
    } catch {
      state.saved = [];
    }
  }

  async function loadCatalogLibrary(params) {
    const generation = ctx.state.resources.catalog.generation;
    restoreSelection(params);
    state.error = '';
    if (state.view === 'dark-matter') {
      try {
        state.darkMatter = await ctx.actions.api(
          '/api/dark-matter?' +
            new URLSearchParams({ q: state.darkMatterQuery, limit: 25, offset: 0 }),
        );
      } catch (error) {
        if (error.name === 'AbortError' || generation !== ctx.state.resources.catalog.generation)
          throw error;
        state.error = error.message || 'Dark Matter is unavailable.';
      }
      return;
    }
    if (!ctx.state.resources.catalog.status?.total) return;
    try {
      state.products = await api('products', {
        q: state.query,
        scope: state.scope,
        limit: 25,
        offset: 0,
      });
      if (state.productId) {
        [state.product, state.observed] = await Promise.all([
          api('products/' + encodeURIComponent(state.productId), {
            scope: state.scope,
            version: state.version,
            limit: 25,
            offset: 0,
          }),
          optional(
            api('products/' + encodeURIComponent(state.productId) + '/observations', {
              scope: state.scope,
              limit: 25,
              offset: 0,
            }),
          ),
        ]);
      }
      if (state.view === 'fields') state.fields = await fieldData();
      if (state.view === 'changes') state.changes = await api('changes', { limit: 25, offset: 0 });
      if (state.view === 'cves' && state.fieldSelection)
        ctx.state.resources.catalog.result = await api('fields/records', {
          field: state.field,
          value: state.fieldSelection.value,
          scope: state.scope,
          product_id: state.productId,
          limit: 25,
          offset: 0,
        });
    } catch (error) {
      if (error.name === 'AbortError' || generation !== ctx.state.resources.catalog.generation)
        throw error;
      state.error = error.message || 'The product index is unavailable.';
    }
  }

  async function showCatalogView(view) {
    if (!allowedViews.has(view)) return;
    state.view = view;
    updateSelectionControls();
    if (view === 'products' && !state.products && ctx.state.resources.catalog.status?.total)
      await searchCatalogProducts(state.query, state.scope);
    if (view === 'fields') await loadCatalogFields();
    if (view === 'changes') await loadCatalogChanges();
    if (view === 'dark-matter') await loadDarkMatter();
  }

  async function loadDarkMatter(query = state.darkMatterQuery, offset = 0) {
    const region = ctx.actions.$('#catalog-dark-matter-panel');
    if (!region) return;
    const request = ++state.darkMatterRequest;
    state.darkMatterQuery = String(query).trim().slice(0, 200);
    state.darkMatter = null;
    state.error = '';
    region.setAttribute('aria-busy', 'true');
    try {
      const result = await ctx.actions.api(
        '/api/dark-matter?' + new URLSearchParams({ q: state.darkMatterQuery, limit: 25, offset }),
      );
      if (
        request !== state.darkMatterRequest ||
        ctx.actions.$('#catalog-dark-matter-panel') !== region
      )
        return;
      state.darkMatter = result;
    } catch (error) {
      if (
        request !== state.darkMatterRequest ||
        ctx.actions.$('#catalog-dark-matter-panel') !== region
      )
        return;
      state.error = error.message || 'Dark Matter is unavailable.';
    } finally {
      if (
        request === state.darkMatterRequest &&
        ctx.actions.$('#catalog-dark-matter-panel') === region
      ) {
        region.innerHTML = render.darkMatterPanel();
        region.removeAttribute('aria-busy');
        updateSelectionControls();
      }
    }
  }

  async function searchCatalogProducts(query = state.query, scope = state.scope, offset = 0) {
    const region = ctx.actions.$('#catalog-products-panel');
    if (!region) return;
    const request = ++state.request;
    state.query = String(query).trim().slice(0, 200);
    state.scope = allowedScopes.has(scope) ? scope : 'critical';
    state.error = '';
    region.setAttribute('aria-busy', 'true');
    try {
      const products = await api('products', {
        q: state.query,
        scope: state.scope,
        limit: 25,
        offset,
      });
      if (request !== state.request || ctx.actions.$('#catalog-products-panel') !== region) return;
      state.products = products;
      region.innerHTML = render.productsPanel();
      if (state.productId) await selectCatalogProduct(state.productId);
      updateSelectionControls();
    } catch (error) {
      if (request === state.request && ctx.actions.$('#catalog-products-panel') === region) {
        state.error = error.message;
        region.innerHTML = render.productsPanel();
      }
    } finally {
      if (request === state.request) region.removeAttribute('aria-busy');
    }
  }

  async function selectCatalogProduct(id, offset = 0) {
    const region = ctx.actions.$('#catalog-product-detail');
    if (!region) return;
    const request = ++state.productRequest;
    if (state.productId !== id) state.version = '';
    state.productId = id;
    region.setAttribute('aria-busy', 'true');
    ctx.actions.$$('[data-catalog-product]').forEach((button) => {
      const selected = button.dataset.catalogProduct === id;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
    try {
      const [detail, observed] = await Promise.all([
        api('products/' + encodeURIComponent(id), {
          scope: state.scope,
          version: state.version,
          limit: 25,
          offset,
        }),
        optional(
          api('products/' + encodeURIComponent(id) + '/observations', {
            scope: state.scope,
            limit: 25,
            offset: 0,
          }),
        ),
      ]);
      if (request !== state.productRequest || ctx.actions.$('#catalog-product-detail') !== region)
        return;
      state.product = detail;
      state.observed = observed;
      region.innerHTML = render.productDetail();
      updateSelectionControls();
    } catch (error) {
      if (request === state.productRequest && ctx.actions.$('#catalog-product-detail') === region)
        region.innerHTML = `<p class="catalog-error" role="status">${esc(error.message)}</p>`;
    } finally {
      if (request === state.productRequest) region.removeAttribute('aria-busy');
    }
  }

  async function compareCatalogVersion(version) {
    state.version = String(version || '')
      .trim()
      .slice(0, 160);
    if (state.productId) await selectCatalogProduct(state.productId);
  }

  function fieldData() {
    return api('fields', {
      field: state.field,
      scope: state.scope,
      product_id: state.productId,
      limit: 30,
    });
  }

  async function loadCatalogFields(field = state.field) {
    const region = ctx.actions.$('#catalog-fields-panel');
    if (!region) return;
    const request = ++state.fieldRequest;
    state.field = field;
    region.setAttribute('aria-busy', 'true');
    try {
      const result = await fieldData();
      if (request !== state.fieldRequest || ctx.actions.$('#catalog-fields-panel') !== region)
        return;
      state.fields = result;
      state.error = '';
      region.innerHTML = render.fieldsPanel();
      updateSelectionControls();
    } catch (error) {
      if (request === state.fieldRequest && ctx.actions.$('#catalog-fields-panel') === region) {
        state.error = error.message;
        region.innerHTML = render.fieldsPanel();
      }
    } finally {
      if (request === state.fieldRequest) region.removeAttribute('aria-busy');
    }
  }

  async function selectCatalogFieldValue(value, offset = 0) {
    state.fieldSelection = { field: state.field, value };
    await showCatalogView('cves');
    const region = ctx.actions.$('#cve-catalog-results');
    if (!region) return;
    const catalog = ctx.state.resources.catalog,
      request = ++catalog.searchRequest;
    region.setAttribute('aria-busy', 'true');
    region.innerHTML = '<p class="catalog-empty" role="status">Loading matching CVEs…</p>';
    try {
      const result = await api('fields/records', {
        field: state.field,
        value,
        scope: state.scope,
        product_id: state.productId,
        limit: 25,
        offset,
      });
      if (request !== catalog.searchRequest || ctx.actions.$('#cve-catalog-results') !== region)
        return;
      catalog.result = result;
      region.innerHTML = ctx.actions.catalogResultsMarkup();
      updateSelectionControls();
    } catch (error) {
      if (request === catalog.searchRequest && ctx.actions.$('#cve-catalog-results') === region)
        region.innerHTML = `<p class="catalog-error" role="status">${esc(error.message)}</p>`;
    } finally {
      if (request === catalog.searchRequest) region.removeAttribute('aria-busy');
    }
  }

  async function loadCatalogChanges(offset = 0) {
    const region = ctx.actions.$('#catalog-changes-panel');
    if (!region) return;
    const request = ++state.changeRequest;
    region.setAttribute('aria-busy', 'true');
    try {
      const result = await api('changes', { limit: 25, offset });
      if (request !== state.changeRequest || ctx.actions.$('#catalog-changes-panel') !== region)
        return;
      state.changes = result;
      state.error = '';
      region.innerHTML = render.changesPanel();
    } catch (error) {
      if (request === state.changeRequest && ctx.actions.$('#catalog-changes-panel') === region) {
        state.error = error.message;
        region.innerHTML = render.changesPanel();
      }
    } finally {
      if (request === state.changeRequest) region.removeAttribute('aria-busy');
    }
  }

  function saveCatalogView() {
    const label =
      state.view === 'dark-matter'
        ? ['Dark Matter', state.darkMatterQuery].filter(Boolean).join(' · ')
        : [
            state.product?.product?.product || state.query || 'All products',
            state.scope.replaceAll('_', ' + '),
            state.view,
            state.version,
          ]
            .filter(Boolean)
            .join(' · ');
    const item = Object.fromEntries(
      ['view', 'query', 'scope', 'productId', 'version', 'field', 'darkMatterQuery'].map((key) => [
        key,
        state[key],
      ]),
    );
    item.fieldSelection = state.fieldSelection ? { ...state.fieldSelection } : null;
    item.cveQuery = ctx.state.resources.catalog.query;
    item.cveSeverity = ctx.state.resources.catalog.severity;
    state.saved = [{ ...item, label }, ...state.saved.filter((v) => v.label !== label)].slice(
      0,
      20,
    );
    persistViews();
  }

  function persistViews() {
    try {
      localStorage.setItem('companion-library-views', JSON.stringify(state.saved));
      const region = ctx.actions.$('#catalog-saved-views');
      if (region) region.innerHTML = savedMarkup();
      ctx.actions.toast?.('Library views saved in this browser.');
    } catch {
      ctx.actions.toast?.('This browser could not save the view.', true);
    }
  }

  async function applyCatalogView(index) {
    const item = state.saved[Number(index)];
    if (!item) return;
    for (const key of [
      'view',
      'query',
      'scope',
      'productId',
      'version',
      'field',
      'darkMatterQuery',
    ])
      state[key] = typeof item[key] === 'string' ? item[key] : '';
    state.fieldSelection =
      item.fieldSelection && typeof item.fieldSelection.value === 'string'
        ? { field: state.field, value: item.fieldSelection.value.slice(0, 300) }
        : null;
    ctx.state.resources.catalog.query =
      typeof item.cveQuery === 'string' ? item.cveQuery.slice(0, 200) : '';
    ctx.state.resources.catalog.severity =
      typeof item.cveSeverity === 'string' ? item.cveSeverity : 'CRITICAL';
    state.product = null;
    state.observed = null;
    if (state.view === 'dark-matter') {
      await showCatalogView(state.view);
      return;
    }
    await searchCatalogProducts(state.query, state.scope);
    await showCatalogView(state.view);
    if (state.view === 'cves') {
      if (state.fieldSelection) await selectCatalogFieldValue(state.fieldSelection.value);
      else
        await ctx.actions.searchCatalog(
          ctx.state.resources.catalog.query,
          ctx.state.resources.catalog.severity,
        );
    }
  }

  function removeCatalogView(index) {
    if (!/^(?:0|[1-9]\d*)$/.test(String(index))) return;
    state.saved.splice(Number(index), 1);
    persistViews();
  }

  async function clearCatalogProduct() {
    state.productId = '';
    state.product = null;
    state.observed = null;
    state.version = '';
    const region = ctx.actions.$('#catalog-product-detail');
    if (region) region.innerHTML = render.productDetail();
    ctx.actions.$$('[data-catalog-product]').forEach((button) => {
      button.classList.remove('active');
      button.setAttribute('aria-pressed', 'false');
    });
    updateSelectionControls();
    if (state.view === 'fields') await loadCatalogFields();
  }

  Object.assign(ctx.actions, {
    catalogLibraryMarkup,
    loadCatalogLibrary,
    showCatalogView,
    searchCatalogProducts,
    selectCatalogProduct,
    compareCatalogVersion,
    loadCatalogFields,
    selectCatalogFieldValue,
    loadCatalogChanges,
    loadDarkMatter,
    saveCatalogView,
    applyCatalogView,
    removeCatalogView,
    clearCatalogProduct,
    catalogSelectionURL,
    refreshCatalogSelection: updateSelectionControls,
    catalogObservedMarkup: render.observedMarkup,
    clearCatalogField: async () => {
      state.fieldSelection = null;
      updateSelectionControls();
      await ctx.actions.searchCatalog(
        ctx.state.resources.catalog.query,
        ctx.state.resources.catalog.severity,
        0,
      );
    },
  });
}
