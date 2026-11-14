/** Settings interactions. No browser listeners or startup side effects. */
export function createHandlers(ctx) {
  return {
    input: (event) => {
      const form = event.target.closest?.('#settings-form');
      if (form) ctx.actions.settingsChanged(form);
      const resource = event.target.closest?.('#resource-form');
      if (resource) {
        resource.dataset.dirty = 'true';
        resource.dataset.editRevision = String(Number(resource.dataset.editRevision || 0) + 1);
      }
    },
    change: [
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
        matches: (el, e) => el.id === 'outreach-mode',
        run: async (el, e) => {
          const reason = ctx.actions.$('#f-targeted_reason');
          if (reason) reason.required = el.value === 'targeted';
          ctx.actions.settingsChanged(el.closest?.('#settings-form'));
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
      {
        matches: (el) => Boolean(el.closest?.('#settings-form')),
        run: (el) => ctx.actions.settingsChanged(el.closest('#settings-form')),
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
        run: (el) => ctx.actions.selectCatalogFieldValue(el.dataset.catalogFieldValue),
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
      'settings-section': (el) => ctx.actions.scrollSettingsSection(el.dataset.section),
      'remove-nvd-key': () => ctx.actions.removeNvdKey(),
      'catalog-dark-matter-clear': () => ctx.actions.loadDarkMatter('', 0),
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
      'catalog-save-view': () => ctx.actions.saveCatalogView(),
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
      'import-data': async () => {
        ctx.actions.modal(
          'Import data',
          `<form id="import-data-form" class="form-grid"><p class="full">Replace this workspace’s records, evidence, reports, and settings with a saved backup. Your current workspace is kept as a verified restore point first.</p><div class="field full"><label for="data-backup">Companion backup ZIP</label><input id="data-backup" type="file" name="file" accept=".zip,application/zip" required></div><div class="field full"><label for="data-confirmation">Type IMPORT to confirm replacement</label><input id="data-confirmation" name="confirmation" pattern="IMPORT" autocomplete="off" spellcheck="false" required></div><details class="full settings-help"><summary>Recovery option for damaged current data</summary><label class="checkbox"><input type="checkbox" name="skip_restore_point" value="true"><span>Replace without saving a current restore point<small>Use only if damaged files prevent the current workspace from being backed up. Current records will be removed after restart.</small></span></label></details><p class="full help">The selected backup is checked before it is ready to apply. Close and reopen the app to apply. You can cancel before restarting.</p><button type="submit" class="button primary">Verify and stage import</button></form>`,
        );
      },
      'delete-data': async () => {
        ctx.actions.modal(
          'Delete all data',
          `<form id="delete-data-form" class="form-grid"><p class="full">This deletes all workspace records, original reports, evidence, completed reports, inbox files, settings, and managed restore points. Export first if you need to keep them. Exported copies outside this workspace are not deleted.</p><div class="field full"><label for="data-confirmation">Type DELETE to confirm</label><input id="data-confirmation" name="confirmation" pattern="DELETE" autocomplete="off" spellcheck="false" required></div><p class="full help">Deletion takes effect when you close and reopen the app. You can cancel before restarting.</p><button type="submit" class="button danger">Stage deletion</button></form>`,
        );
      },
      'cancel-data-change': async () => {
        await ctx.actions.api('/api/data/cancel', { method: 'POST' });
        ctx.actions.toast('Staged change cancelled. Your current records are retained.');
        await ctx.actions.refreshSettingsData();
      },
      'check-workspace': () => ctx.actions.checkWorkspaceHealth(),
      'cancel-workspace-health': () => ctx.actions.cancelWorkspaceHealth(),
      'review-workspace-cleanup': () => ctx.actions.reviewWorkspaceCleanup(),
      'rebuild-workspace-index': () => ctx.actions.reviewIndexRebuild(),
      'export-diagnostics': async () => {
        const summary = await ctx.actions.api('/api/data/diagnostics');
        const a = document.createElement('a');
        a.href = URL.createObjectURL(
          new Blob([JSON.stringify(summary, null, 2)], { type: 'application/json' }),
        );
        a.download = 'companion-diagnostics.json';
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
        ctx.actions.toast(
          'Diagnostic summary exported without logs, report contents, credentials or contact values.',
        );
      },
      backup: async (el) => {
        const blob = await ctx.actions.api('/api/backup', { method: 'POST', blob: true });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'shadowserver-companion-backup.zip';
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
        ctx.actions.toast('Data exported and restore verified.');
        await ctx.actions.refreshSettingsData();
      },
    },
    forms: {
      'workspace-cleanup-form': async (form, values) => ctx.actions.applyWorkspaceCleanup(values),
      'workspace-index-form': async (form, values) => ctx.actions.rebuildWorkspaceIndex(values),
      'nvd-key-form': (form, values) => ctx.actions.saveNvdKey(form, values),
      'catalog-dark-matter-form': (form, values) => ctx.actions.loadDarkMatter(values.query, 0),
      'catalog-product-form': (form, values) =>
        ctx.actions.searchCatalogProducts(values.query, values.scope),
      'catalog-version-form': (form, values) => ctx.actions.compareCatalogVersion(values.version),
      'catalog-field-form': (form, values) => ctx.actions.loadCatalogFields(values.field),
      'catalog-search-form': (form, values) => {
        ctx.state.resources.catalog.library.fieldSelection = null;
        void ctx.actions.showCatalogView('cves');
        return ctx.actions.searchCatalog(values.query, values.severity, 0);
      },
      'import-data-form': async (form, obj, data) => {
        await ctx.actions.api('/api/data/import', { method: 'POST', body: data });
        ctx.actions.closeModal();
        ctx.actions.toast('Import staged. Close and reopen the app to apply.');
        await ctx.actions.refreshSettingsData();
      },
      'delete-data-form': async (form, obj) => {
        await ctx.actions.api('/api/data/delete', {
          method: 'POST',
          body: { confirmation: obj.confirmation },
        });
        ctx.actions.closeModal();
        ctx.actions.toast('Deletion staged. Close and reopen the app to apply.');
        await ctx.actions.refreshSettingsData();
      },
      'resource-form': async (form, obj, data, reviewDecision) => {
        const editRevision = form.dataset?.editRevision || '0';
        obj.source_metadata = ctx.actions.readResourceCitations(form);
        const saved = await ctx.actions.api(
          '/api/explainers' +
            (ctx.state.resources.resourceId ? '/' + ctx.state.resources.resourceId : ''),
          { method: ctx.state.resources.resourceId ? 'PUT' : 'POST', body: obj },
        );
        ctx.actions.toast('Explainer saved.');
        if (ctx.actions.$('#resource-form') !== form) return;
        if (saved?.id) ctx.state.resources.resourceId = saved.id;
        if ((form.dataset?.editRevision || '0') !== editRevision) {
          ctx.actions.toast('New edits remain unsaved.');
          return;
        }
        if (form.dataset) form.dataset.dirty = 'false';
        await ctx.actions.route(true);
        return;
      },
      'settings-form': async (form, obj, data, reviewDecision) => {
        const editRevision = form.dataset?.editRevision || '0';
        form.setAttribute?.('aria-busy', 'true');
        ctx.actions.settingsSaveStatus('Saving settings…', 'saving', form);
        const value = {
          ...obj,
          regions: obj.regions
            .split('\n')
            .map((x) => x.trim())
            .filter(Boolean),
          timeout: Number(obj.timeout),
          retries: Number(obj.retries),
          interval: Number(obj.interval),
          watch_inbox: data.has('watch_inbox'),
          accretion_priority_cities: String(obj.accretion_priority_cities || '')
            .split(/[\n,]/)
            .map((value) => value.trim())
            .filter(Boolean),
          accretion_priority_products: String(obj.accretion_priority_products || '')
            .split(/[\n,]/)
            .map((value) => value.trim())
            .filter(Boolean),
          critical_only: obj.outreach_mode !== 'targeted',
        };
        try {
          ctx.state.navigation.boot.settings = await ctx.actions.api('/api/settings', {
            method: 'PUT',
            body: value,
          });
          ctx.actions.$('#office-label').textContent = ctx.state.navigation.boot.settings.office;
          ctx.actions.applyPresentation(ctx.state.navigation.boot.settings);
          const changedDuringSave = (form.dataset?.editRevision || '0') !== editRevision;
          if (form.dataset) form.dataset.dirty = changedDuringSave ? 'true' : 'false';
          ctx.actions.settingsSaveStatus(
            changedDuringSave ? 'Settings saved. New edits remain unsaved.' : 'Settings saved.',
            changedDuringSave ? 'unsaved' : 'saved',
            form,
          );
          ctx.actions.toast('Settings saved.');
          await ctx.actions.afterSettingsProfileSave?.();
        } catch (error) {
          if (form.dataset) form.dataset.dirty = 'true';
          ctx.actions.settingsSaveStatus(
            'Could not save: ' + error.message + ' Your edits remain here.',
            'error',
            form,
          );
          throw error;
        } finally {
          form.removeAttribute?.('aria-busy');
        }
        return;
      },
    },
  };
}
