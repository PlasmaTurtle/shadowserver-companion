import { downloadBlob } from '../../ui/static/download.js';

/** Settings and workspace-maintenance controls; no Library editor ownership. */
export function createHandlers(ctx) {
  return {
    input: (event) => {
      const form = event.target.closest?.('#settings-form');
      if (form) ctx.actions.settingsChanged(form);
      const keyForm = event.target.closest?.('#nvd-key-form');
      if (keyForm) ctx.actions.nvdKeyChanged(keyForm);
    },
    change: [
      {
        matches: (el, e) => el.id === 'outreach-mode',
        run: (el) => ctx.actions.settingsOutreachChanged(el),
      },
      {
        matches: (el) => el.id === 'settings-agency-preset',
        run: (el) => ctx.actions.applySettingsAgency(el),
      },
      {
        matches: (el) =>
          el.id !== 'settings-agency-preset' && Boolean(el.closest?.('#settings-form')),
        run: (el) => ctx.actions.settingsChanged(el.closest('#settings-form')),
      },
      {
        matches: (el) => Boolean(el.closest?.('#nvd-key-form')),
        run: (el) => ctx.actions.nvdKeyChanged(el.closest('#nvd-key-form')),
      },
    ],
    click: [],
    actions: {
      'settings-remove-unsupported-regions': (el) =>
        ctx.actions.removeSettingsUnsupportedRegions(el),
      'settings-section': (el) => ctx.actions.scrollSettingsSection(el.dataset.section),
      'remove-nvd-key': () => ctx.actions.removeNvdKey(),
      'clear-nvd-key': () => ctx.actions.clearNvdKey(),
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
        downloadBlob(
          new Blob([JSON.stringify(summary, null, 2)], { type: 'application/json' }),
          'companion-diagnostics.json',
        );
        ctx.actions.toast(
          'Diagnostic summary exported without logs, report contents, credentials or contact values.',
        );
      },
      backup: async (el) => {
        const blob = await ctx.actions.api('/api/backup', { method: 'POST', blob: true });
        downloadBlob(blob, 'shadowserver-companion-backup.zip');
        ctx.actions.toast('Data exported and restore verified.');
        await ctx.actions.refreshSettingsData();
      },
    },
    forms: {
      'workspace-cleanup-form': async (form, values) => ctx.actions.applyWorkspaceCleanup(values),
      'workspace-index-form': async (form, values) => ctx.actions.rebuildWorkspaceIndex(values),
      'nvd-key-form': (form, values) => ctx.actions.saveNvdKey(form, values),
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
      'settings-form': async (form, obj, data, reviewDecision) => {
        if (!ctx.actions.validateSettingsForm(form)) return;
        const editRevision = form.dataset?.editRevision || '0';
        form.setAttribute?.('aria-busy', 'true');
        ctx.actions.settingsSaveStatus('Saving settings…', 'saving', form);
        const value = {
          ...obj,
          regions: data.getAll('regions'),
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
          const settings = await ctx.actions.persistSettings(value);
          ctx.actions.$('#office-label').textContent = settings.office;
          ctx.actions.applyPresentation(settings);
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
