/** One owner for delegated browser listeners; feature handlers own behavior. */
import { createHandlers as entityHandlers } from '../../entities/static/entities_events.js';
import { createHandlers as intakeHandlers } from '../../accretion/static/intake_events.js';
import { createHandlers as libraryHandlers } from '../../library/static/library_events.js';
import { createHandlers as assetHandlers } from '../../attribution/static/assets_events.js';
import { createHandlers as activityHandlers } from '../../activity/static/activity_events.js';
import { createHandlers as contactHandlers } from '../../entities/static/contacts_events.js';
import { createHandlers as editorHandlers } from '../../investigations/static/editor_events.js';
import { createHandlers as observationScopeHandlers } from '../../investigations/static/observation_scope.js';
import { createHandlers as workflowHandlers } from '../../investigations/static/workflow_events.js';
import { createHandlers as attributionHandlers } from '../../attribution/static/attribution.js';
import { createHandlers as settingsHandlers } from '../../settings/static/settings_events.js';
import { createHandlers as onboardingHandlers } from '../../settings/static/onboarding.js';
import { createHandlers as softwareHandlers } from '../../settings/static/software_updates.js';
import { createHandlers as entityReviewHandlers } from '../../entities/static/entity_review.js';
import { createHandlers as entityLeadHandlers } from '../../leads/static/entity_leads_events.js';
import { createHandlers as apiDataHandlers } from '../../accretion/static/shadowserver_data.js';
import { createHandlers as commandHandlers } from './command_palette.js';

function uniqueHandlers(features, key) {
  const result = new Map();
  for (const feature of features)
    for (const [name, handler] of Object.entries(feature[key])) {
      if (result.has(name)) throw Error(`Duplicate ${key} handler: ${name}`);
      result.set(name, handler);
    }
  return result;
}

export function bindEvents(ctx) {
  const features = [
    workflowHandlers(ctx),
    editorHandlers(ctx),
    observationScopeHandlers(ctx),
    assetHandlers(ctx),
    activityHandlers(ctx),
    contactHandlers(ctx),
    attributionHandlers(ctx),
    intakeHandlers(ctx),
    settingsHandlers(ctx),
    libraryHandlers(ctx),
    onboardingHandlers(ctx),
    softwareHandlers(ctx),
    entityReviewHandlers(ctx),
    entityHandlers(ctx),
    entityLeadHandlers(ctx),
    apiDataHandlers(ctx),
    commandHandlers(ctx),
  ];
  const actions = uniqueHandlers(features, 'actions');
  actions.set('reload', () => ctx.actions.route(true));
  const forms = uniqueHandlers(features, 'forms');
  forms.set('global-search-form', async (_form, values) => {
    ctx.actions.closeModal();
    location.hash = 'entities?q=' + encodeURIComponent(values.q);
  });
  const cleanups = [];
  const listen = (target, type, listener) => {
    target.addEventListener(type, listener);
    cleanups.push(() => target.removeEventListener(type, listener));
  };
  listen(document, 'input', (event) => {
    for (const feature of features) feature.input?.(event);
  });
  listen(document, 'change', async (event) => {
    for (const feature of features)
      for (const handler of feature.change) {
        if (handler.matches(event.target, event)) return handler.run(event.target, event);
      }
    if (event.target.hasAttribute?.('data-submit-filter'))
      event.target.closest('form')?.requestSubmit();
  });
  const shell = {
    'close-modal': () => ctx.actions.closeModal(),
    'global-search': () => ctx.actions.globalSearch(),
    'theme-toggle': () => ctx.actions.toggleTheme(),
    'menu-toggle': () =>
      ctx.actions.setSidebarOpen(!ctx.actions.$('#sidebar').classList.contains('open')),
    'close-navigation': () => ctx.actions.setSidebarOpen(false, { returnFocus: true }),
    'sidebar-backdrop': () => ctx.actions.setSidebarOpen(false, { returnFocus: true }),
  };
  listen(document, 'click', async (event) => {
    if (event.target.closest('[data-skip-content]')) {
      event.preventDefault();
      ctx.actions.$('#main').focus();
      return;
    }
    if (event.target.closest('[data-close-modal]')) return ctx.actions.closeModal();
    const el = event.target.closest('button,[data-open-lead]');
    if (!el) return;
    if (Object.hasOwn(shell, el.id)) return shell[el.id]();
    for (const feature of features)
      for (const handler of feature.click) {
        if (handler.matches(el, event)) return handler.run(el, event);
      }
    const handler = actions.get(el.dataset.action);
    if (handler) return ctx.actions.busy(el, () => handler(el));
  });
  listen(document, 'submit', async (event) => {
    const form = event.target,
      handler = forms.get(form.id);
    if (!handler) return;
    event.preventDefault();
    const data = new FormData(form),
      obj = Object.fromEntries(data);
    const button = event.submitter || ctx.actions.$('button[type=submit]', form);
    return ctx.actions.busy(button, () => handler(form, obj, data, event.submitter?.value));
  });
  listen(window, 'hashchange', () => ctx.actions.route());
  listen(window, 'companion:presentation', ctx.actions.updateThemeLabel);
  listen(window, 'eclipse:refresh', () => {
    if (ctx.state.navigation.currentRoute === 'eclipse') ctx.actions.route(true);
  });
  listen(window, 'beforeunload', (e) => {
    if (
      ctx.state.editor.dirty ||
      ctx.state.workflow.workflowDirty ||
      ctx.state.entities.dirty ||
      ctx.actions.hasUnsavedSetup?.() ||
      ctx.actions.hasUnsavedOutreach?.() ||
      ctx.actions.hasUnsavedSettings?.() ||
      ctx.actions.hasUnsavedLibrary?.()
    ) {
      e.preventDefault();
      e.returnValue = '';
    }
  });
  listen(document, 'keydown', (e) => {
    if (ctx.actions.commandPaletteKeydown?.(e)) return;
    if (ctx.actions.trapModalFocus(e)) return;
    if (ctx.actions.navigationKeydown(e)) return;
    const tab = e.target?.closest?.('.editor-tabs [role="tab"]');
    if (tab && ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) {
      const tabs = ctx.actions.$$('.editor-tabs [role="tab"]');
      const index = tabs.indexOf(tab);
      const next =
        e.key === 'Home'
          ? 0
          : e.key === 'End'
            ? tabs.length - 1
            : (index + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      e.preventDefault();
      tabs.forEach((node, position) => {
        node.tabIndex = position === next ? 0 : -1;
      });
      tabs[next]?.focus();
      // Manual activation preserves a form until Enter/Space confirms a switch.
      return;
    }
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      if (!ctx.actions.$('#modal').open) {
        ctx.actions.setSidebarOpen(false, { focus: false });
        ctx.actions.globalSearch();
      }
    }
    if (
      (e.ctrlKey || e.metaKey) &&
      !e.shiftKey &&
      e.key.toLowerCase() === 's' &&
      (ctx.state.editor.currentLead ||
        ctx.state.entities.current ||
        ['settings', 'library'].includes(ctx.state.navigation.currentRoute?.split('?')[0]))
    ) {
      e.preventDefault();
      if (ctx.actions.$('#modal').open) return;
      if (ctx.state.navigation.currentRoute?.split('?')[0] === 'library') {
        const form = ctx.actions.$('#resource-form');
        const save = form && ctx.actions.$('button[type="submit"]', form);
        if (save && !save.disabled) form.requestSubmit?.(save);
        return;
      }
      if (ctx.state.navigation.currentRoute?.startsWith('entity/')) {
        const form = ctx.actions.$(
          document.activeElement?.closest?.('form')
            ? '#' + document.activeElement.closest('form').id
            : ctx.state.entities.tab === 'contacts'
              ? '#entity-contact-form'
              : '#entity-details-form',
        );
        form?.requestSubmit?.();
        return;
      }
      if (ctx.state.navigation.currentRoute?.split('?')[0] === 'settings') {
        const form = ctx.actions.$('#settings-form');
        const save = form && ctx.actions.$('button[type="submit"]', form);
        if (save && !save.disabled) form.requestSubmit?.(save);
        return;
      }
      if (ctx.state.workflow.workflowDirty) {
        ctx.actions.toast('Use the current form’s Save or Record button to save these changes.');
        return;
      }
      ctx.actions.busy(null, async () => {
        await ctx.actions.saveDraft();
        ctx.actions.toast('Draft saved.');
      });
    }
  });
  const modal = ctx.actions.$('#modal');
  if (modal?.addEventListener)
    listen(modal, 'cancel', (event) => {
      if (
        ctx.actions.confirmDiscardSetup?.() === false ||
        ctx.actions.confirmDiscardOutreach?.() === false
      )
        event.preventDefault();
    });
  if (modal?.addEventListener) listen(modal, 'close', () => ctx.actions.setupModalClosed?.());
  if (modal?.addEventListener)
    listen(modal, 'close', () => ctx.actions.discardOutreachPreparation?.());
  if (modal?.addEventListener) listen(modal, 'close', ctx.actions.restoreModalFocus);
  if (modal?.addEventListener)
    listen(modal, 'close', () => {
      // Native close events are queued; a new palette may already own this dialog.
      if (!modal.open || !ctx.actions.$('#command-query')) ctx.actions.disposeCommandPalette();
    });
  const syncNavigation = () =>
    ctx.actions.setSidebarOpen(ctx.actions.$('#sidebar').classList.contains?.('open') || false, {
      focus: false,
    });
  listen(window, 'resize', syncNavigation);
  syncNavigation();
  if (ctx.actions.$('#theme-toggle')) ctx.actions.updateThemeLabel();
  ctx.actions.$$('[data-icon]').forEach((el) => (el.innerHTML = ctx.actions.icon(el.dataset.icon)));
  let disposed = false;
  return () => {
    if (disposed) return;
    disposed = true;
    const errors = [];
    for (const cleanup of [
      ...cleanups.splice(0),
      ...features.map((feature) => () => feature.dispose?.()),
    ]) {
      try {
        cleanup();
      } catch (error) {
        errors.push(error);
      }
    }
    if (errors.length) throw new AggregateError(errors, 'Application event cleanup failed');
  };
}
