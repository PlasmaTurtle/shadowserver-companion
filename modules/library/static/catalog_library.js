import { createDarkMatterBrowser } from '../../observatory/static/dark_matter_browser.js';
import { createLibraryRender } from './catalog_library_render.js';
import { createCatalogSearch } from './catalog_search.js';
import { createReportedView } from './reported_references.js';

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
    impact: null,
    impactId: '',
    impactError: '',
    impactRequest: 0,
    error: '',
    request: 0,
    productRequest: 0,
    fieldRequest: 0,
    changeRequest: 0,
    loadRequest: 0,
    fieldSelection: null,
    saved: [],
    savedId: '',
    savedError: '',
  });
  const darkMatter = createDarkMatterBrowser(ctx, { onChange: updateSelectionControls });
  const research = createCatalogSearch(ctx);
  const reported = createReportedView(ctx);
  state.darkMatterSelection = darkMatter.selection;
  const render = createLibraryRender(ctx, state, darkMatter),
    esc = (value) => ctx.actions.esc(value ?? ''),
    allowedScopes = new Set(['critical', 'critical_kev', 'kev', 'all']),
    allowedViews = new Set(['products', 'cves', 'fields', 'changes', 'dark-matter', 'reported']);
  const api = (path, params) =>
    ctx.actions.api('/api/cve-catalog/' + path + (params ? '?' + new URLSearchParams(params) : ''));
  const optional = (promise) => promise.catch(() => null);

  function currentSelection() {
    const catalog = ctx.state.resources.catalog;
    return {
      schema_version: 1,
      ...Object.fromEntries(
        ['view', 'query', 'scope', 'productId', 'version', 'field'].map((key) => [key, state[key]]),
      ),
      fieldSelection: state.fieldSelection ? { ...state.fieldSelection } : null,
      cveQuery: catalog.query,
      cveSeverity: catalog.severity,
      selectedCve: catalog.selected || '',
      darkMatterSelection: { ...darkMatter.selection },
    };
  }

  function catalogSelectionURL(selection = state) {
    if (selection.view === 'reported') return '#library?view=reported';
    if (selection.view === 'dark-matter') {
      const params = new URLSearchParams({ view: 'dark-matter' });
      for (const [key, value] of Object.entries(selection.darkMatterSelection || {})) {
        if (value) params.set('dark_' + key, value);
      }
      return '#library?' + params;
    }
    const params = new URLSearchParams({ view: selection.view, scope: selection.scope });
    if (selection.query) params.set('product_query', selection.query);
    if (selection.productId) params.set('product', selection.productId);
    if (selection.version) params.set('version', selection.version);
    if (selection.field) params.set('field', selection.field);
    if (selection.fieldSelection) {
      params.set('field_value', selection.fieldSelection.value);
      if (selection.fieldSelection.field !== selection.field)
        params.set('filter_field', selection.fieldSelection.field);
    }
    if (selection.view === 'cves') {
      const catalog = ctx.state.resources.catalog;
      params.set('q', catalog.query);
      params.set('severity', catalog.severity);
    }
    if (selection.view === 'cves' && ctx.state.resources.catalog.selected)
      params.set('cve', ctx.state.resources.catalog.selected);
    return '#library?' + params;
  }

  function rememberSelection() {
    if (ctx.state.navigation.currentRoute?.split('?')[0] !== 'library') return;
    if (typeof window !== 'undefined' && window.history?.replaceState) {
      let url = catalogSelectionURL();
      const params = new URLSearchParams((window.location?.hash || '').split('?')[1] || '');
      for (const key of ['item', 'guide']) {
        if (params.get(key)) url += '&' + key + '=' + encodeURIComponent(params.get(key));
      }
      window.history.replaceState(null, '', url);
      if (ctx.state.navigation.currentRoute?.startsWith('library'))
        ctx.state.navigation.currentRoute = url.slice(1);
    }
  }

  function savedMarkup() {
    const selected = state.saved.find((item) => item.id === state.savedId);
    return `<div class="catalog-saved-views"><label for="catalog-saved-view">Workspace views</label><select id="catalog-saved-view"><option value="">Choose a saved view</option>${state.saved.map((item) => `<option value="${esc(item.id)}" ${item.id === state.savedId ? 'selected' : ''}>${esc(item.name)}</option>`).join('')}</select><form id="catalog-view-form"><label for="catalog-view-name">View name</label><input id="catalog-view-name" name="name" maxlength="120" required value="${esc(selected?.name || selectionLabel())}"><button class="button" type="submit" data-action="catalog-save-view">Save new view</button><button class="button" type="button" data-action="catalog-update-view" ${selected ? '' : 'disabled'}>Update selected</button><button class="button" type="button" data-action="catalog-remove-view" ${selected ? '' : 'disabled'}>Remove selected</button></form>${state.savedError ? `<p class="catalog-error" role="status">${esc(state.savedError)} <button class="button" data-action="catalog-retry-views">Retry saved views</button></p>` : ''}</div>`;
  }

  function catalogLibraryMarkup(cveMarkup) {
    return `${research.markup()}<div id="catalog-library"><div class="catalog-library-nav"><nav class="catalog-tabs" aria-label="Library catalog views">${[
      ['products', 'Products'],
      ['cves', 'CVEs'],
      ['reported', 'By entity count'],
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
      )}</nav><a id="catalog-view-link" class="text-link" href="${esc(catalogSelectionURL())}">Link to this view</a></div><div id="catalog-saved-views">${savedMarkup()}</div><section id="catalog-products-panel" ${state.view === 'products' ? '' : 'hidden'}>${render.productsPanel()}</section><section id="catalog-cves-panel" ${state.view === 'cves' ? '' : 'hidden'}><div id="catalog-cve-context">${cveContext()}</div>${cveMarkup}</section><section id="catalog-fields-panel" ${state.view === 'fields' ? '' : 'hidden'}>${render.fieldsPanel()}</section><section id="catalog-changes-panel" ${state.view === 'changes' ? '' : 'hidden'}>${render.changesPanel()}</section><section id="catalog-reported-panel" ${state.view === 'reported' ? '' : 'hidden'}><h3>Ranked by entity count</h3></section><section id="catalog-dark-matter-panel" ${state.view === 'dark-matter' ? '' : 'hidden'}>${render.darkMatterPanel()}</section></div>`;
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
    state.view = allowedViews.has(view) ? view : 'products';
    if (params.get('cve')) state.view = 'cves';
    state.scope = allowedScopes.has(scope) ? scope : 'critical';
    darkMatter.select({
      query: params.get('dark_query') || '',
      field: params.get('dark_field') || '',
      operator: params.get('dark_operator') || 'eq',
      value: params.get('dark_value') || '',
      source: params.get('dark_source') || 'normalized',
    });
    state.query = (params.get('product_query') || '').slice(0, 200);
    state.productId = (params.get('product') || '').slice(0, 160);
    state.version = (params.get('version') || '').slice(0, 160);
    state.field = (params.get('field') || 'weakness').slice(0, 80);
    state.fieldSelection = params.has('field_value')
      ? { field: params.get('filter_field') ?? state.field, value: params.get('field_value') }
      : null;
    const catalog = ctx.state.resources.catalog;
    catalog.query = (params.get('q') || '').slice(0, 200);
    const severity = params.get('severity');
    catalog.severity = ['', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NONE', 'UNKNOWN'].includes(
      severity,
    )
      ? severity
      : 'CRITICAL';
    catalog.selected = /^CVE-\d{4}-\d{4,}$/i.test(params.get('cve') || '')
      ? params.get('cve').toUpperCase()
      : null;
    state.product = state.products = state.observed = state.fields = state.changes = null;
    state.impact = null;
    state.impactId = '';
    state.impactRequest++;
    catalog.detail = null;
    catalog.result = { items: [], total: 0, limit: 25, offset: 0 };
    state.loadRequest++;
    state.productRequest++;
    state.fieldRequest++;
    state.changeRequest++;
    catalog.searchRequest++;
    catalog.detailRequest++;
  }

  async function loadCatalogLibrary(params) {
    if (params) restoreSelection(params);
    const catalog = ctx.state.resources.catalog,
      generation = catalog.generation,
      request = ++state.loadRequest,
      view = state.view,
      initialField = view === 'fields' ? ctx.actions.$('#catalog-field')?.value : null,
      region = ctx.actions.$('#catalog-' + view + '-panel'),
      current = () =>
        generation === catalog.generation &&
        request === state.loadRequest &&
        (!region || ctx.actions.$('#catalog-' + view + '-panel') === region);
    if (view === 'products') {
      state.request++;
      state.productRequest++;
    }
    if (view === 'cves') {
      catalog.searchRequest++;
      catalog.detailRequest++;
    }
    if (view === 'fields') state.fieldRequest++;
    if (view === 'changes') state.changeRequest++;
    state.error = '';
    if (view === 'reported') {
      await reported.load();
      return;
    }
    if (view === 'dark-matter') {
      await darkMatter.load();
      return;
    }
    region?.setAttribute('aria-busy', 'true');
    try {
      if (view === 'products') {
        const [products, detail, observations] = await Promise.all([
          api('products', { q: state.query, scope: state.scope, limit: 25, offset: 0 }),
          state.productId
            ? api('products/' + encodeURIComponent(state.productId), {
                scope: state.scope,
                version: state.version,
                limit: 25,
                offset: 0,
              })
            : null,
          state.productId
            ? optional(
                api('products/' + encodeURIComponent(state.productId) + '/observations', {
                  scope: state.scope,
                  limit: 25,
                  offset: 0,
                }),
              )
            : null,
        ]);
        if (!current()) return;
        state.products = products;
        state.product = detail;
        state.observed = observations;
      } else if (view === 'cves') {
        const selection = state.fieldSelection,
          search = selection
            ? api('fields/records', {
                field: selection.field,
                value: selection.value,
                scope: state.scope,
                product_id: state.productId,
                limit: 25,
                offset: 0,
              })
            : api('search', { q: catalog.query, severity: catalog.severity, limit: 25, offset: 0 }),
          record = catalog.selected
            ? '/api/cve-catalog/records/' + encodeURIComponent(catalog.selected)
            : null;
        const [result, detail, observations] = await Promise.all([
          search,
          record ? optional(ctx.actions.api(record)) : null,
          record ? optional(ctx.actions.api(record + '/observations')) : null,
        ]);
        if (!current()) return;
        catalog.result = result;
        catalog.detail = detail
          ? { ...detail, observations: observations || detail.observations }
          : null;
      } else if (view === 'fields') {
        const fields = await fieldData();
        if (!current()) return;
        state.fields = fields;
      } else if (view === 'changes') {
        const changes = await api('changes', { limit: 25, offset: 0 });
        if (!current()) return;
        state.changes = changes;
      }
    } catch (error) {
      if (!current() || error.name === 'AbortError') return;
      state.error = error.message || 'This catalog view is unavailable.';
    } finally {
      if (current() && region) {
        if (view === 'products') renderProductData();
        else if (view === 'cves') renderCveData();
        else if (view === 'fields') renderFields(region, initialField);
        else region.innerHTML = render.changesPanel();
        region.removeAttribute('aria-busy');
        updateSelectionControls();
      }
    }
  }

  function renderProductData() {
    const results = ctx.actions.$('#catalog-products-results'),
      detail = ctx.actions.$('#catalog-product-detail'),
      error = ctx.actions.$('#catalog-products-error');
    if (results) results.innerHTML = render.productRows();
    if (detail) detail.innerHTML = render.productDetail();
    if (error)
      error.innerHTML = state.error
        ? `<p class="catalog-error" role="status">${esc(state.error)}</p>`
        : '';
  }

  function renderCveData() {
    const results = ctx.actions.$('#cve-catalog-results'),
      detail = ctx.actions.$('#cve-catalog-detail');
    if (results)
      results.innerHTML = state.error
        ? `<p class="catalog-error" role="status">${esc(state.error)}</p>`
        : ctx.actions.catalogResultsMarkup();
    if (detail) {
      detail.innerHTML = ctx.actions.catalogDetailMarkup();
      void ctx.actions.loadVendorGuidance?.();
    }
  }

  function syncSelectionInputs() {
    const catalog = ctx.state.resources.catalog;
    for (const [selector, value] of [
      ['#catalog-product-query', state.query],
      ['#catalog-product-scope', state.scope],
      ['#catalog-query', catalog.query],
      ['#catalog-severity', catalog.severity],
    ]) {
      const input = ctx.actions.$(selector);
      if (input) input.value = value;
    }
  }

  async function showCatalogView(view, { load = true } = {}) {
    if (!allowedViews.has(view)) return;
    state.loadRequest++;
    for (const name of allowedViews)
      ctx.actions.$('#catalog-' + name + '-panel')?.removeAttribute('aria-busy');
    state.view = view;
    updateSelectionControls();
    if (load) await loadCatalogLibrary();
  }

  async function loadDarkMatter(values, offset = 0) {
    return darkMatter.load(typeof values === 'string' ? { query: values } : values, offset);
  }

  async function searchCatalogProducts(query = state.query, scope = state.scope, offset = 0) {
    const region = ctx.actions.$('#catalog-products-panel');
    if (!region) return;
    const request = ++state.request;
    state.loadRequest++;
    state.productRequest++;
    state.fieldRequest++;
    ctx.state.resources.catalog.searchRequest++;
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
      renderProductData();
      if (state.productId) await selectCatalogProduct(state.productId);
      updateSelectionControls();
    } catch (error) {
      if (request === state.request && ctx.actions.$('#catalog-products-panel') === region) {
        state.error = error.message;
        renderProductData();
      }
    } finally {
      if (request === state.request) region.removeAttribute('aria-busy');
    }
  }

  async function selectCatalogProduct(id, offset = 0) {
    const region = ctx.actions.$('#catalog-product-detail');
    if (!region) return;
    const request = ++state.productRequest;
    state.loadRequest++;
    ctx.actions.$('#catalog-products-panel')?.removeAttribute('aria-busy');
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

  function renderFields(region, initialChoice) {
    // An incoming result may replace the form between choosing a field and pressing Explore.
    const choice = ctx.actions.$('#catalog-field')?.value;
    region.innerHTML = render.fieldsPanel();
    const select = ctx.actions.$('#catalog-field');
    if (
      choice &&
      choice !== initialChoice &&
      select &&
      [...select.options].some((option) => option.value === choice)
    )
      select.value = choice;
  }

  async function loadCatalogFields(field = state.field) {
    const region = ctx.actions.$('#catalog-fields-panel');
    if (!region) return;
    const request = ++state.fieldRequest;
    const initialChoice = ctx.actions.$('#catalog-field')?.value;
    state.loadRequest++;
    state.field = field;
    region.setAttribute('aria-busy', 'true');
    try {
      const result = await fieldData();
      if (request !== state.fieldRequest || ctx.actions.$('#catalog-fields-panel') !== region)
        return;
      state.fields = result;
      state.error = '';
      renderFields(region, initialChoice);
      updateSelectionControls();
    } catch (error) {
      if (request === state.fieldRequest && ctx.actions.$('#catalog-fields-panel') === region) {
        state.error = error.message;
        renderFields(region, initialChoice);
      }
    } finally {
      if (request === state.fieldRequest) region.removeAttribute('aria-busy');
    }
  }

  async function selectCatalogFieldValue(value, offset = 0, field = state.field) {
    state.fieldSelection = { field, value };
    await showCatalogView('cves', { load: false });
    const region = ctx.actions.$('#cve-catalog-results');
    if (!region) return;
    const catalog = ctx.state.resources.catalog,
      request = ++catalog.searchRequest;
    region.setAttribute('aria-busy', 'true');
    region.innerHTML = '<p class="catalog-empty" role="status">Loading matching CVEs…</p>';
    try {
      const result = await api('fields/records', {
        field,
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
    state.loadRequest++;
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

  async function loadCatalogImpact(
    cveId = state.impactId,
    offset = 0,
    includeCompleted = state.impact?.cases?.include_completed || false,
  ) {
    const region = ctx.actions.$('#catalog-change-impact');
    if (!region || !/^CVE-\d{4}-\d{4,}$/.test(cveId)) return;
    const request = ++state.impactRequest;
    state.impactId = cveId;
    state.impact = null;
    state.impactError = '';
    region.innerHTML = render.impactMarkup();
    region.setAttribute('aria-busy', 'true');
    try {
      const result = await ctx.actions.api(
        '/api/library/changes/' +
          encodeURIComponent(cveId) +
          '/impact?' +
          new URLSearchParams({ limit: 25, offset, include_completed: includeCompleted }),
      );
      if (request !== state.impactRequest || ctx.actions.$('#catalog-change-impact') !== region)
        return;
      state.impact = result;
    } catch (error) {
      if (
        error.name === 'AbortError' ||
        request !== state.impactRequest ||
        ctx.actions.$('#catalog-change-impact') !== region
      )
        return;
      state.impactError = error.message;
    } finally {
      if (request === state.impactRequest && ctx.actions.$('#catalog-change-impact') === region) {
        region.innerHTML = render.impactMarkup();
        region.removeAttribute('aria-busy');
      }
    }
  }

  function selectionLabel() {
    if (state.view === 'reported') return 'Ranked by entity count';
    const catalog = ctx.state.resources.catalog;
    return (
      state.view === 'dark-matter'
        ? [
            'Dark Matter',
            darkMatter.selection.query,
            darkMatter.selection.field,
            darkMatter.selection.operator,
            darkMatter.selection.value,
            darkMatter.selection.source,
          ]
            .filter(Boolean)
            .join(' · ')
        : [
            state.product?.product?.product || state.query || 'All products',
            state.scope.replaceAll('_', ' + '),
            state.view,
            state.version,
            state.view === 'cves' ? catalog.query : '',
            state.view === 'cves' ? catalog.severity || 'All severities' : '',
            state.fieldSelection?.value,
          ]
            .filter(Boolean)
            .join(' · ')
    ).slice(0, 120);
  }

  function renderSavedViews() {
    const region = ctx.actions.$('#catalog-saved-views');
    if (region) region.innerHTML = savedMarkup();
  }

  function normalizedSavedSelection(item) {
    const text = (key, fallback = '', length = 200) =>
      typeof item[key] === 'string' ? item[key].slice(0, length) : fallback;
    const field = text('field', 'weakness', 80);
    // Legacy browser values can exceed workspace limits, which count Unicode code points.
    const bounded = (value, length) => Array.from(value).slice(0, length).join('');
    return {
      schema_version: 1,
      view: allowedViews.has(item.view) ? item.view : 'products',
      query: text('query'),
      scope: allowedScopes.has(item.scope) ? item.scope : 'critical',
      productId: text('productId', '', 160),
      version: text('version', '', 160),
      field,
      fieldSelection:
        typeof item.fieldSelection?.value === 'string'
          ? {
              field:
                typeof item.fieldSelection.field === 'string'
                  ? bounded(item.fieldSelection.field, 200)
                  : field,
              value: bounded(item.fieldSelection.value, 2000),
            }
          : null,
      cveQuery: text('cveQuery'),
      cveSeverity: ['', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NONE', 'UNKNOWN'].includes(
        item.cveSeverity,
      )
        ? item.cveSeverity
        : 'CRITICAL',
      selectedCve: /^CVE-\d{4}-\d{4,}$/.test(item.selectedCve || '') ? item.selectedCve : '',
      darkMatterSelection: Object.fromEntries(
        Object.entries({
          query: '',
          field: '',
          operator: 'eq',
          value: '',
          source: 'normalized',
        }).map(([key, fallback]) => [
          key,
          typeof item.darkMatterSelection?.[key] === 'string'
            ? item.darkMatterSelection[key].slice(0, key === 'value' ? 2000 : 200)
            : fallback,
        ]),
      ),
    };
  }

  async function loadCatalogViews() {
    const generation = ctx.state.resources.catalog.generation;
    try {
      let saved = await ctx.actions.api('/api/library/views');
      let legacy = [];
      try {
        const raw = JSON.parse(localStorage.getItem('companion-library-views') || '[]');
        if (Array.isArray(raw))
          legacy = raw
            .filter((item) => item && typeof item.label === 'string' && allowedViews.has(item.view))
            .slice(0, 20);
      } catch {
        /* Browser storage is optional; workspace views remain available. */
      }
      if (legacy.length) {
        saved = await ctx.actions.api('/api/library/views/import', {
          method: 'POST',
          body: {
            views: legacy.map((item) => ({
              name: item.label.slice(0, 120) || 'Imported view',
              selection: normalizedSavedSelection(item),
            })),
          },
        });
        try {
          localStorage.removeItem('companion-library-views');
        } catch {
          /* Import is idempotent. */
        }
      }
      if (generation !== ctx.state.resources.catalog.generation) return;
      state.saved = saved;
      state.savedError = '';
    } catch (error) {
      if (generation !== ctx.state.resources.catalog.generation || error.name === 'AbortError')
        return;
      state.savedError = error.message || 'Workspace views are unavailable.';
    }
    if (generation === ctx.state.resources.catalog.generation) renderSavedViews();
  }

  async function saveCatalogView(
    name = ctx.actions.$('#catalog-view-name')?.value || selectionLabel(),
    update = false,
  ) {
    const selected = state.saved.find((item) => item.id === state.savedId);
    if (update && !selected) return;
    const item = await ctx.actions.api(
      '/api/library/views' + (update ? '/' + encodeURIComponent(selected.id) : ''),
      {
        method: update ? 'PUT' : 'POST',
        body: {
          name: String(name).trim(),
          selection: currentSelection(),
          ...(update ? { expected_revision: selected.revision } : {}),
        },
      },
    );
    state.saved = [item, ...state.saved.filter((view) => view.id !== item.id)];
    state.savedId = item.id;
    state.savedError = '';
    renderSavedViews();
    ctx.actions.toast?.('Library view saved in this workspace.');
  }

  async function applyCatalogView(id) {
    const saved = state.saved.find((item) => item.id === id);
    if (!saved) return;
    const item = normalizedSavedSelection(saved.selection);
    state.savedId = saved.id;
    state.loadRequest++;
    state.productRequest++;
    state.fieldRequest++;
    state.changeRequest++;
    ctx.state.resources.catalog.searchRequest++;
    ctx.state.resources.catalog.detailRequest++;
    for (const key of ['view', 'query', 'scope', 'productId', 'version', 'field'])
      state[key] = typeof item[key] === 'string' ? item[key] : '';
    darkMatter.select(
      item.darkMatterSelection || {
        query: '',
        field: '',
        operator: 'eq',
        value: '',
        source: 'normalized',
      },
    );
    state.fieldSelection = item.fieldSelection;
    ctx.state.resources.catalog.query =
      typeof item.cveQuery === 'string' ? item.cveQuery.slice(0, 200) : '';
    ctx.state.resources.catalog.severity =
      typeof item.cveSeverity === 'string' ? item.cveSeverity : 'CRITICAL';
    ctx.state.resources.catalog.selected = item.selectedCve || null;
    ctx.state.resources.catalog.detail = null;
    state.product = null;
    state.observed = null;
    renderSavedViews();
    syncSelectionInputs();
    await showCatalogView(state.view);
  }

  async function removeCatalogView(id = state.savedId) {
    const selected = state.saved.find((item) => item.id === id);
    if (!selected) return;
    await ctx.actions.api(
      '/api/library/views/' + encodeURIComponent(id) + '?expected_revision=' + selected.revision,
      { method: 'DELETE' },
    );
    state.saved = state.saved.filter((item) => item.id !== id);
    state.savedId = '';
    renderSavedViews();
  }

  async function clearCatalogProduct() {
    state.loadRequest++;
    state.productRequest++;
    state.fieldRequest++;
    ctx.state.resources.catalog.searchRequest++;
    state.productId = '';
    state.product = null;
    state.observed = null;
    state.version = '';
    const region = ctx.actions.$('#catalog-product-detail');
    if (region) {
      region.innerHTML = render.productDetail();
      region.removeAttribute('aria-busy');
    }
    ctx.actions.$('#catalog-products-panel')?.removeAttribute('aria-busy');
    ctx.actions.$$('[data-catalog-product]').forEach((button) => {
      button.classList.remove('active');
      button.setAttribute('aria-pressed', 'false');
    });
    updateSelectionControls();
    if (state.view === 'fields') await loadCatalogFields();
  }

  Object.assign(ctx.actions, {
    catalogLibraryMarkup,
    loadReported: reported.load,
    showReportedEntities: reported.showEntities,
    recordMembership: reported.recordMembership,
    searchLibrary: research.search,
    loadCatalogLibrary,
    restoreCatalogSelection: restoreSelection,
    currentCatalogSelection: currentSelection,
    showCatalogView,
    searchCatalogProducts,
    selectCatalogProduct,
    compareCatalogVersion,
    loadCatalogFields,
    selectCatalogFieldValue,
    loadCatalogChanges,
    loadCatalogImpact,
    loadDarkMatter,
    clearDarkMatter: darkMatter.clear,
    saveCatalogView,
    updateCatalogView: () => saveCatalogView(undefined, true),
    loadCatalogViews,
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
