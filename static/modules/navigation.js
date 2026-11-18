/** Navigation feature. Dependencies and mutable state are provided by the application context. */
export function install(ctx) {
  const mobileNavigation = () => window.matchMedia?.('(max-width: 760px)')?.matches || false;

  function setSidebarOpen(requested, { returnFocus = false, focus = true } = {}) {
    const sidebar = ctx.actions.$('#sidebar');
    const toggle = ctx.actions.$('#menu-toggle');
    const mobile = mobileNavigation();
    const open = mobile && requested;
    const focusWasInside = sidebar.contains?.(document.activeElement);
    sidebar.classList.toggle('open', open);
    sidebar.inert = mobile && !open;
    if (mobile && !open) sidebar.setAttribute?.('aria-hidden', 'true');
    else sidebar.removeAttribute?.('aria-hidden');
    if (open) {
      sidebar.setAttribute?.('role', 'dialog');
      sidebar.setAttribute?.('aria-modal', 'true');
      sidebar.setAttribute?.('aria-label', 'Main navigation');
    } else {
      sidebar.removeAttribute?.('role');
      sidebar.removeAttribute?.('aria-modal');
      sidebar.removeAttribute?.('aria-label');
    }
    toggle?.setAttribute?.('aria-expanded', String(open));
    const shell = ctx.actions.$('.shell');
    if (shell) shell.inert = open;
    const backdrop = ctx.actions.$('#sidebar-backdrop');
    if (backdrop) backdrop.hidden = !open;
    document.body?.classList?.toggle('navigation-open', open);
    if (open && focus) {
      const target =
        ctx.actions.$('#sidebar [aria-current="page"]') ||
        ctx.actions.$('#close-navigation') ||
        sidebar;
      target?.focus?.();
    } else if (!open && mobile && (returnFocus || focusWasInside)) toggle?.focus?.();
  }

  function navigationKeydown(event) {
    const sidebar = ctx.actions.$('#sidebar');
    if (!mobileNavigation() || !sidebar.classList.contains('open') || ctx.actions.$('#modal')?.open)
      return false;
    if (event.key === 'Escape') {
      event.preventDefault();
      setSidebarOpen(false, { returnFocus: true });
      return true;
    }
    if (event.key === 'Tab') {
      const targets = ctx.actions
        .$$('a[href],button:not(:disabled),[tabindex="0"]', sidebar)
        .filter((el) => !el.hidden && (!el.getClientRects || el.getClientRects().length));
      const first = targets[0],
        last = targets.at(-1);
      if (
        first &&
        (!sidebar.contains(document.activeElement) ||
          (event.shiftKey && document.activeElement === first) ||
          (!event.shiftKey && document.activeElement === last))
      ) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      }
      return true;
    }
    return false;
  }
  function canonicalRoute(value) {
    const [path, query = ''] = value.split('?');
    const aliases = {
      dashboard: 'workspace',
      cases: 'workspace/notifications',
      investigations: 'workspace/notifications',
      reports: 'workspace/completed',
      imports: 'data',
      reviews: 'attribution',
      resources: 'library',
    };
    let target = aliases[path] || path || 'workspace';
    if (path.startsWith('investigations/')) target = 'workspace/notifications/' + path.slice(15);
    if (path.startsWith('case/')) target = 'workspace/notifications/' + path.slice(5);
    if (path.startsWith('lead/')) target = 'entity/' + path.slice(5);
    return target + (query ? '?' + query : '');
  }

  async function route(force = false) {
    const wanted = canonicalRoute(location.hash.slice(1) || 'workspace');
    const previous = ctx.state.navigation.currentRoute;
    const [path, query = ''] = wanted.split('?');
    const parts = path.split('/'),
      page = parts[0],
      params = new URLSearchParams(query);
    const notificationId = page === 'workspace' && parts[1] === 'notifications' ? parts[2] : null;
    const sameCase =
      notificationId &&
      ctx.state.editor.currentLead?.case_id === notificationId &&
      previous.split('?')[0] === path;
    const unsafe =
      (!sameCase && ctx.state.editor.dirty) ||
      ctx.state.workflow.workflowDirty ||
      ctx.state.entities.dirty ||
      ctx.actions.hasUnsavedSetup?.() ||
      ctx.actions.hasUnsavedOutreach?.() ||
      ctx.actions.hasUnsavedSettings?.() ||
      ctx.actions.hasUnsavedLibrary?.();
    if (unsafe && !force && !confirm('Leave without saving your changes?')) {
      history.replaceState(null, '', '#' + previous);
      return;
    }
    if (
      force &&
      (ctx.state.editor.dirty ||
        ctx.state.workflow.workflowDirty ||
        ctx.state.entities.dirty ||
        ctx.actions.hasUnsavedSetup?.() ||
        ctx.actions.hasUnsavedOutreach?.() ||
        ctx.actions.hasUnsavedSettings?.() ||
        ctx.actions.hasUnsavedLibrary?.())
    )
      return;
    if (wanted !== previous) ctx.actions.discardOutreachPreparation?.({ close: true });
    if (previous) ctx.state.navigation.positions.set(previous, window.scrollY || 0);
    if (['entities', 'leads'].includes(previous.split('?')[0]))
      ctx.state.navigation.returns.set(previous.split('?')[0], previous);
    if (previous.split('?')[0] === 'workspace/notifications')
      ctx.state.navigation.returns.set('notifications', previous);
    if (location.hash !== '#' + wanted) history.replaceState(null, '', '#' + wanted);
    if (!sameCase) ctx.state.editor.dirty = false;
    ctx.state.workflow.workflowDirty = false;
    ctx.state.entities.dirty = false;
    ctx.state.entities.changedForms.clear();
    ctx.actions.beginViewRequests?.();
    window.Eclipse?.destroy();
    ctx.actions.stopContactDiscoveryPolling();
    ctx.actions.stopApiAcquisitionPolling();
    ctx.actions.stopAssetAttributionPolling?.();
    ctx.actions.stopWebsiteCapturePolling?.();
    ctx.actions.stopCatalogPolling?.();
    if (ctx.state.resources.catalog) ctx.state.resources.catalog.generation++;
    clearTimeout(ctx.state.editor.narrativeRefreshTimer);
    ctx.state.editor.narrativeRefreshId++;
    if (ctx.state.editor.pendingCveRefresh?.running) {
      ctx.state.editor.pendingCveRefresh.detached = true;
      ctx.state.editor.pendingCveRefresh.running = false;
    }
    ctx.state.navigation.currentRoute = wanted;
    const id = ++ctx.state.navigation.renderId;
    const nav =
      page === 'entity' ? 'entities' : page === 'workspace' && parts[1] ? 'investigations' : page;
    document.body.dataset.view = notificationId ? 'investigation' : nav;
    document.body.classList.toggle('eclipse-view', page === 'eclipse');
    document.body.classList.toggle('observatory-loading', page === 'eclipse');
    if (!notificationId) ctx.state.editor.currentLead = null;
    if (page !== 'entity') ctx.state.entities.current = null;
    if (!(page === 'leads' && parts[1])) ctx.state.intakeLeads.current = null;
    ctx.actions.$$('.sidebar [data-nav]').forEach((e) => {
      const active = e.dataset.nav === nav;
      e.classList.toggle('active', active);
      if (active) e.setAttribute?.('aria-current', 'page');
      else e.removeAttribute?.('aria-current');
    });
    const title =
      nav === 'investigations' ? 'Investigations' : ctx.constants.titles[page] || 'Workspace';
    ctx.actions.$('#page-label').textContent = 'Opening ' + title + '…';
    ctx.actions.setSidebarOpen(false, { focus: false });
    const main = ctx.actions.$('#main');
    main.inert = true;
    main.setAttribute?.('aria-busy', 'true');
    if (['entities', 'entity', 'data'].includes(page)) {
      main.innerHTML = `<section class="panel" role="status"><div class="panel-body"><span class="spinner" aria-hidden="true"></span> Loading ${ctx.actions.esc(title)}…</div></section>`;
      main.inert = false;
    }
    try {
      let html, eclipseData;
      if (page === 'eclipse') {
        // Paint the destination before waiting on the local data service.
        main.innerHTML = window.Eclipse.loading();
        main.inert = false;
        ctx.actions.$('#page-label').textContent = title;
        const product = params.get('product');
        // One scoped Observatory response owns graph, map, history, records and counts.
        // Mount the frame immediately; the controller requests that response once.
        eclipseData = {
          observations: [],
          findings: [],
          entities: [],
          catalog_selection: product ? { product_id: product } : null,
        };
        if (id !== ctx.state.navigation.renderId) return;
        html = window.Eclipse.render(eclipseData);
      } else if (notificationId) {
        html =
          sameCase && !force
            ? ctx.actions.leadMarkup()
            : await ctx.actions.leadPage(notificationId, true);
        const requested = params.get('tab');
        if (requested === 'entity') {
          location.hash = 'entity/' + encodeURIComponent(ctx.state.editor.currentLead.id);
          return;
        }
        if (['notification', 'assets', 'contact', 'closing', 'activity'].includes(requested)) {
          ctx.state.editor.tab = requested;
          const section = params.get('section');
          if (requested === 'notification' && ctx.constants.reportSections.includes(section))
            ctx.state.editor.reportSection = section;
          html = ctx.actions.leadMarkup();
        }
      } else if (page === 'workspace' && parts[1] === 'notifications')
        html =
          ctx.actions.workspaceNavigation('notifications') + (await ctx.actions.casesPage(params));
      else if (page === 'workspace' && parts[1] === 'completed')
        html = ctx.actions.workspaceNavigation('completed') + (await ctx.actions.reportsPage());
      else if (page === 'entity' && parts[1]) html = await ctx.actions.entityPage(parts[1], params);
      else if (page === 'entities') html = await ctx.actions.entitiesPage(params);
      else if (page === 'leads' && parts[1]) html = await ctx.actions.pendingLeadPage(parts[1]);
      else if (page === 'leads') html = await ctx.actions.pendingLeadsPage(params);
      else if (page === 'activity') html = await ctx.actions.activityPage(params);
      else if (page === 'attribution') html = await ctx.actions.reviewsPage();
      else if (page === 'data') html = await ctx.actions.importsPage(params);
      else if (page === 'library') html = await ctx.actions.resourcesPage(params);
      else if (page === 'settings') html = await ctx.actions.settingsPage();
      else html = await ctx.actions.dashboard();
      if (id !== ctx.state.navigation.renderId) return;
      main.innerHTML = html;
      if (notificationId && ctx.state.editor.tab === 'contact')
        void ctx.actions.loadContactDiscovery();
      if (notificationId && ctx.state.editor.tab === 'assets')
        void ctx.actions.loadAssetAttribution();
      if (page === 'entity' && ctx.state.entities.tab === 'contacts')
        void ctx.actions.loadContactDiscovery(ctx.state.entities.current.id);
      if (page === 'entities' || (page === 'entity' && ctx.state.entities.tab === 'overview'))
        void ctx.actions.loadEntityContactOverviews();
      if (page === 'eclipse') window.Eclipse.mount(main, eclipseData);
      if (page === 'data' && ctx.actions.$('#dropzone')) ctx.actions.wireDropzone();
      if (page === 'settings') {
        void ctx.actions.loadNvdKeyStatus();
        void ctx.actions.loadSettingsSetupStatus?.();
        void ctx.actions.loadSoftwareStatus?.().catch((error) => {
          if (id === ctx.state.navigation.renderId && error.name !== 'AbortError')
            ctx.actions.toast('Could not refresh software status: ' + error.message, true);
        });
      }
      if (page === 'settings')
        ctx.actions.$('#f-targeted_reason').required =
          ctx.actions.$('#outreach-mode').value === 'targeted';
      if (!force)
        window.scrollTo({
          top: ctx.state.navigation.positions.get(wanted) || 0,
          behavior: 'instant',
        });
      document.title =
        title + ' · ' + (ctx.state.navigation.boot?.release?.app_name || 'Shadowserver Eclipse');
      void ctx.actions.refreshNavigationCounts();
    } catch (error) {
      if (id === ctx.state.navigation.renderId && error.name !== 'AbortError')
        main.innerHTML = ctx.actions.heading(
          'Unable to open this view',
          ctx.actions.esc(error.message),
          '<button class="button" data-action="reload">Try again</button><a class="button" href="#workspace">Workspace</a>',
        );
    } finally {
      if (id === ctx.state.navigation.renderId) {
        main.inert = false;
        document.body.classList.toggle('observatory-loading', false);
        main.setAttribute?.('aria-busy', 'false');
        ctx.actions.$('#page-label').textContent = title;
        if (!force && !ctx.actions.$('#modal')?.open) main.focus?.({ preventScroll: true });
      }
    }
  }

  function globalSearch() {
    if (ctx.actions.openCommandPalette) return ctx.actions.openCommandPalette();
    ctx.actions.modal(
      'Find a business',
      '<form id="global-search-form"><div class="input-search">' +
        ctx.actions.icon('search') +
        '<input name="q" aria-label="Search company or root domain" placeholder="Company or root domain…" autofocus></div><div class="modal-actions"><button type="submit" class="button primary">Search businesses</button></div></form>',
    );
    ctx.actions.$('#modal input').focus();
  }
  Object.assign(ctx.actions, {
    route,
    canonicalRoute,
    globalSearch,
    setSidebarOpen,
    navigationKeydown,
  });
}

export async function start(ctx, isCurrent = () => true) {
  try {
    const boot = await ctx.actions.api('/api/bootstrap');
    if (!isCurrent()) return;
    ctx.state.navigation.boot = boot;
    const release = ctx.state.navigation.boot.release;
    const version = release?.version || ctx.state.navigation.boot.version;
    const appName = release?.app_name || 'Shadowserver Eclipse';
    ctx.actions.$('#release-status').textContent = `v${version}`;
    ctx.actions.$('#release-status').title =
      `${appName} · Version ${version}. Details are available in Settings.`;
    ctx.actions.$('#release-version').textContent = `Version ${version}`;
    ctx.actions.applyPresentation(ctx.state.navigation.boot.settings);
    if (!ctx.state.navigation.boot.settings.appearance) {
      ctx.actions
        .api('/api/settings', {
          method: 'PUT',
          body: {
            ...ctx.state.navigation.boot.settings,
            appearance:
              window.CompanionPresentation?.preference() ||
              document.documentElement.dataset.theme ||
              'light',
          },
        })
        .then((value) => {
          if (isCurrent()) ctx.state.navigation.boot.settings = value;
        })
        .catch(() => {});
    }
    ctx.actions.$('#office-label').textContent = ctx.state.navigation.boot.settings.office;
    ctx.actions.$('#avatar').textContent = (
      ctx.state.navigation.boot.settings.analyst_name || 'Shadowserver Eclipse'
    )
      .split(' ')
      .map((x) => x[0])
      .slice(0, 2)
      .join('');
    ctx.actions.$('#demo-banner').hidden = !ctx.state.navigation.boot.demo;
    await ctx.actions.route();
    if (!isCurrent()) return;
    if (!boot.demo) {
      try {
        const setupOpened = await ctx.actions.maybeStartSetup?.();
        if (!isCurrent()) return;
        if (!setupOpened) await ctx.actions.maybeShowSoftwareWhatsNew?.();
      } catch {
        if (isCurrent())
          ctx.actions.toast('Setup or release notes could not load. Reopen them from Settings.');
      }
      if (!isCurrent()) return;
    }
    let polling = false;
    ctx.state.navigation.poll = setInterval(async () => {
      if (
        polling ||
        ctx.state.editor.dirty ||
        ctx.state.entities.dirty ||
        ctx.state.workflow.workflowDirty ||
        ctx.actions.$('#modal').open ||
        !['data', 'workspace', 'attribution', 'leads', 'entities', 'entity'].includes(
          ctx.state.navigation.currentRoute.split(/[?\/]/)[0],
        )
      )
        return;
      polling = true;
      const renderId = ctx.state.navigation.renderId;
      try {
        if (
          ctx.state.navigation.currentRoute.split('?')[0] === 'data' &&
          ctx.actions.refreshAccretion
        ) {
          await ctx.actions.refreshAccretion();
          return;
        }
        if (
          ctx.state.navigation.currentRoute.split(/[?\/]/)[0] === 'entities' ||
          ctx.state.navigation.currentRoute.startsWith('entity/')
        ) {
          await ctx.actions.loadEntityContactOverviews?.();
          return;
        }
        const rows = await ctx.actions.api('/api/imports');
        if (!isCurrent() || renderId !== ctx.state.navigation.renderId) return;
        if (rows.some((r) => ['queued', 'running'].includes(r.status)) || window.hadActiveImport) {
          window.hadActiveImport = rows.some((r) => ['queued', 'running'].includes(r.status));
          await ctx.actions.route(true);
        }
      } catch {
        // The next scheduled poll can retry; no overlapping request is started.
      } finally {
        polling = false;
      }
    }, 3000);
  } catch (e) {
    if (!isCurrent()) return;
    ctx.actions.$('#main').innerHTML = ctx.actions.heading(
      'Unable to connect',
      ctx.actions.esc(e.message),
      '<button class="button" data-action="reload">Retry</button>',
    );
  }
}
