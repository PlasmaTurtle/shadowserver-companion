/** Catalog and reference editor events owned by Library. */
export function createHandlers(ctx) {
  return {
    input: (event) => {
      const resource = event.target.closest?.('#resource-form');
      if (resource) {
        resource.dataset.dirty = 'true';
        resource.dataset.editRevision = String(Number(resource.dataset.editRevision || 0) + 1);
      }
    },
    change: [
      {
        matches: (el) => el.id === 'catalog-impact-completed',
        run: (el) => ctx.actions.loadCatalogImpact(undefined, 0, el.checked),
      },
      {
        matches: (el) => el.id === 'catalog-saved-view',
        run: (el) => (el.value === '' ? undefined : ctx.actions.applyCatalogView(el.value)),
      },
      {
        matches: (el) => el.id === 'catalog-enabled',
        run: async (el) => {
          el.disabled = true;
          try {
            await ctx.actions.catalogCommand('settings', el.checked);
          } catch (error) {
            el.checked = Boolean(ctx.state.resources.catalog.status?.enabled);
            throw error;
          } finally {
            el.disabled = false;
          }
        },
      },
      {
        matches: (el, e) => el.id === 'f-sources' && el.closest('#resource-form'),
        run: async (el, e) => {
          const form = el.closest('#resource-form');
          ctx.actions.$('#resource-citations').innerHTML = ctx.actions.resourceCitationFields(
            el.value,
            ctx.actions.readResourceCitations(form),
          );
        },
      },
    ],
    click: [
      {
        matches: (el) => Boolean(el.dataset.catalogView),
        run: (el) => ctx.actions.showCatalogView(el.dataset.catalogView),
      },
      {
        matches: (el) => Boolean(el.dataset.catalogProduct),
        run: (el) => ctx.actions.selectCatalogProduct(el.dataset.catalogProduct),
      },
      {
        matches: (el) => el.dataset.catalogObservedVersion !== undefined,
        run: (el) => ctx.actions.compareCatalogVersion(el.dataset.catalogObservedVersion),
      },
      {
        matches: (el) => el.dataset.catalogFieldValue !== undefined,
        run: (el) =>
          ctx.actions.selectCatalogFieldValue(
            el.dataset.catalogFieldValue,
            0,
            el.dataset.catalogField,
          ),
      },
      {
        matches: (el) => Boolean(el.dataset.catalogCve),
        run: (el) => ctx.actions.selectCatalogRecord(el.dataset.catalogCve),
      },
      {
        matches: (el, e) => el.dataset.resource,
        run: async (el, e) => {
          if (ctx.actions.hasUnsavedLibrary?.() && !confirm('Leave without saving your changes?'))
            return;
          ctx.state.resources.resourceId = el.dataset.resource;
          ctx.actions.$('#resource-editor').innerHTML = ctx.actions.resourceForm();
          ctx.actions
            .$$('[data-resource]')
            .forEach((x) =>
              x.classList.toggle('active', x.dataset.resource === ctx.state.resources.resourceId),
            );
          return;
        },
      },
    ],
    actions: {
      'library-open-kev-page': (el) => ctx.actions.loadOpenKev(Number(el.dataset.offset) || 0),
      'library-vendor-page': (el) =>
        ctx.actions.loadVendorGuidance(false, Number(el.dataset.offset) || 0),
      'library-vendor-refresh': () => ctx.actions.loadVendorGuidance(true),
      'library-reported-page': (el) =>
        ctx.actions.loadReported(
          Number(el.dataset.cveOffset) || 0,
          Number(el.dataset.productOffset) || 0,
        ),
      'catalog-review-impact': (el) => ctx.actions.loadCatalogImpact(el.dataset.cveId),
      'catalog-impact-page': (el) =>
        ctx.actions.loadCatalogImpact(undefined, Number(el.dataset.offset) || 0),
      'catalog-dark-matter-clear': () => ctx.actions.clearDarkMatter(),
      'catalog-dark-matter-page': (el) =>
        ctx.actions.loadDarkMatter(undefined, Number(el.dataset.offset) || 0),
      'catalog-products-page': (el) =>
        ctx.actions.searchCatalogProducts(undefined, undefined, Number(el.dataset.offset) || 0),
      'catalog-product-cves-page': (el) =>
        ctx.actions.selectCatalogProduct(
          ctx.state.resources.catalog.library.productId,
          Number(el.dataset.offset) || 0,
        ),
      'catalog-changes-page': (el) =>
        ctx.actions.loadCatalogChanges(Number(el.dataset.offset) || 0),
      'catalog-refresh-changes': () => ctx.actions.loadCatalogChanges(),
      'catalog-clear-product': () => ctx.actions.clearCatalogProduct(),
      'catalog-version-clear': () => ctx.actions.compareCatalogVersion(''),
      'catalog-clear-field': () => ctx.actions.clearCatalogField(),
      'catalog-update-view': () => ctx.actions.updateCatalogView(),
      'catalog-retry-views': () => ctx.actions.loadCatalogViews(),
      'library-retry-explainers': () => ctx.actions.loadLibraryExplainers(),
      'library-retry-guides': () => ctx.actions.loadReviewedGuides(),
      'catalog-remove-view': () =>
        ctx.actions.removeCatalogView(ctx.actions.$('#catalog-saved-view')?.value),
      'catalog-index': () => ctx.actions.catalogCommand('index'),
      'catalog-risk-sync': () => ctx.actions.catalogCommand('risk/sync'),
      'catalog-risk-cancel': () => ctx.actions.catalogCommand('risk/cancel'),
      'catalog-sync': async (el) => {
        el.disabled = true;
        try {
          await ctx.actions.catalogCommand('sync');
        } finally {
          el.disabled = false;
        }
      },
      'catalog-cancel': (el) => ctx.actions.catalogCommand('cancel'),
      'catalog-refresh': () => ctx.actions.refreshCatalogStatus(),
      'catalog-page': (el) =>
        ctx.state.resources.catalog.library.fieldSelection
          ? ctx.actions.selectCatalogFieldValue(
              ctx.state.resources.catalog.library.fieldSelection.value,
              Number(el.dataset.offset) || 0,
              ctx.state.resources.catalog.library.fieldSelection.field,
            )
          : ctx.actions.searchCatalog(
              ctx.state.resources.catalog.query,
              ctx.state.resources.catalog.severity,
              Number(el.dataset.offset) || 0,
            ),
      'new-block': async (el) => {
        if (ctx.actions.hasUnsavedLibrary?.() && !confirm('Leave without saving your changes?'))
          return;
        ctx.state.resources.resourceId = null;
        ctx.actions.$$('[data-resource]').forEach((x) => x.classList.remove('active'));
        ctx.actions.$('#resource-editor').innerHTML = ctx.actions.resourceForm();
        ctx.actions.$('#f-title').focus();
      },
      'resource-history': (el) => ctx.actions.resourceHistory(el?.dataset.before),
      'resource-compare': (el) => ctx.actions.compareResource(el.dataset.revision),
      'resource-restore': (el) => ctx.actions.resourceLifecycle('restore', el.dataset.revision),
      'resource-archive': (el) =>
        ctx.actions.resourceLifecycle(el.dataset.archived === 'true' ? 'archive' : 'unarchive'),
      'resource-usage': (el) => ctx.actions.resourceUsage(Number(el?.dataset.offset) || 0),
      'resource-rebase': () => ctx.actions.rebaseResourceDraft(),
      'resource-reload': async () => {
        if (ctx.actions.hasUnsavedLibrary?.() && !confirm('Reload and discard your unsaved draft?'))
          return;
        await ctx.actions.loadLibraryExplainers();
      },
    },
    forms: {
      'library-search-form': (form, values) => ctx.actions.searchLibrary(values.query),
      'catalog-view-form': (form, values) => ctx.actions.saveCatalogView(values.name),
      'catalog-dark-matter-form': (form, values) => ctx.actions.loadDarkMatter(values, 0),
      'catalog-product-form': (form, values) =>
        ctx.actions.searchCatalogProducts(values.query, values.scope),
      'catalog-version-form': (form, values) => ctx.actions.compareCatalogVersion(values.version),
      'catalog-field-form': (form, values) => ctx.actions.loadCatalogFields(values.field),
      'catalog-search-form': (form, values) => {
        ctx.state.resources.catalog.library.fieldSelection = null;
        void ctx.actions.showCatalogView('cves', { load: false });
        return ctx.actions.searchCatalog(values.query, values.severity, 0);
      },
      'resource-form': async (form, obj, data, reviewDecision) => {
        if (form.dataset.saving === 'true') return;
        form.dataset.saving = 'true';
        const submit = form.querySelector?.('[type="submit"]');
        if (submit) submit.disabled = true;
        const editRevision = form.dataset?.editRevision || '0';
        const blockId = form.dataset.blockId || '';
        obj.source_metadata = ctx.actions.readResourceCitations(form);
        if (blockId) obj.expected_revision = Number(form.dataset.expectedRevision);
        try {
          const saved = await ctx.actions.api(
            '/api/explainers' + (blockId ? '/' + encodeURIComponent(blockId) : ''),
            { method: blockId ? 'PUT' : 'POST', body: obj },
          );
          ctx.actions.rememberResource(saved);
          ctx.actions.toast('Explainer saved.');
          if (ctx.actions.$('#resource-form') !== form) return;
          ctx.state.resources.resourceId = saved.id;
          form.dataset.blockId = saved.id;
          form.dataset.expectedRevision = String(saved.revision);
          if ((form.dataset?.editRevision || '0') !== editRevision) {
            ctx.actions.toast('New edits remain unsaved.');
            return;
          }
          form.dataset.dirty = 'false';
          ctx.actions.renderResourceList();
        } catch (error) {
          if (!ctx.actions.showResourceConflict(form, error)) throw error;
        } finally {
          form.dataset.saving = 'false';
          if (submit) submit.disabled = false;
        }
      },
    },
  };
}
