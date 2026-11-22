/** Software distribution and bundled release notes; no requests on import. */
export function install(ctx) {
  let status = null;
  let timer = null;
  let disposed = false;
  let generation = 0;
  let statusRequest = 0;
  let pendingOperation = null;
  let installReview = null;

  const escape = (value) => ctx.actions.esc(String(value ?? ''));
  const busyPhase = () => ['checking', 'downloading', 'installing'].includes(status?.phase);
  const notes = (value) =>
    `<ul>${(value?.highlights || []).map((line) => `<li>${escape(line)}</li>`).join('')}</ul>`;

  function softwareUpdatesMarkup() {
    const version = status?.current_version || ctx.state.navigation?.boot?.release?.version || '';
    const candidate = status?.candidate;
    const progress =
      status?.phase === 'downloading' && status.total_bytes
        ? `<progress class="full-width" max="${Number(status.total_bytes)}" value="${Number(status.downloaded_bytes || 0)}" aria-label="Installer download"></progress><p class="help">${Math.floor(((status.downloaded_bytes || 0) * 100) / status.total_bytes)}% downloaded</p>`
        : '';
    const download =
      candidate && ['available', 'failed'].includes(status?.phase)
        ? '<button class="button primary" type="button" data-action="software-download">Download update</button>'
        : '';
    const ready =
      status?.phase === 'ready'
        ? `<button class="button primary" type="button" data-action="software-install-review" ${status.can_install ? '' : 'disabled'}>Install and restart</button>${!status.can_install ? '<p class="help">Automatic installation is available in the installed Windows application.</p>' : ''}`
        : '';
    return `<section id="software-updates-panel" class="panel"><div class="panel-head"><div><h2>Software updates</h2><p>Installed version ${escape(version)}</p></div></div><div class="panel-body"><p role="status" aria-live="polite">${escape(status?.message || 'View installed changes or check published releases.')}</p>${progress}${candidate ? `<div class="notice"><div><strong>${escape(candidate.title || `Version ${candidate.version}`)}</strong>${notes(candidate)}</div></div>` : ''}<div class="settings-data-actions"><button class="button" type="button" data-action="software-check" ${busyPhase() ? 'disabled' : ''}>Check for updates</button><button class="button" type="button" data-action="software-whats-new">What’s new</button>${download}${ready}</div><p class="help">Updates use this application’s release channel. Downloaded installers are checked against the published SHA-256 before installation. Your workspace is retained.</p>${status?.checked_at ? `<p class="help">Last check: ${escape(ctx.actions.stamp(status.checked_at))}</p>` : ''}</div></section>`;
  }

  function paint() {
    const panel = ctx.actions.$('#software-updates-panel');
    if (panel) panel.outerHTML = softwareUpdatesMarkup();
  }

  function poll() {
    clearTimeout(timer);
    if (!disposed && busyPhase())
      timer = setTimeout(() => loadSoftwareStatus({ polling: true }), 1000);
  }

  async function loadSoftwareStatus({ polling = false } = {}) {
    const requestGeneration = generation;
    if (pendingOperation) await pendingOperation.catch(() => {});
    if (disposed || requestGeneration !== generation) return status;
    const request = ++statusRequest;
    let value;
    try {
      value = await ctx.actions.api('/api/software/status');
    } catch (error) {
      if (disposed || requestGeneration !== generation || request !== statusRequest) return status;
      if (!polling) throw error;
      // Connection loss is expected once the verified installer has started.
      if (status?.phase !== 'installing') {
        status = {
          ...status,
          phase: 'failed',
          message:
            'Could not refresh update status. Check again when the application is available.',
        };
        paint();
      }
      return status;
    }
    if (disposed || requestGeneration !== generation || request !== statusRequest) return value;
    const failedHandoff =
      status?.phase === 'installing' && ['ready', 'failed'].includes(value.phase);
    status = value;
    paint();
    poll();
    if (failedHandoff)
      ctx.actions.modal(
        'Update could not start',
        `<p>${escape(value.message)}</p><div class="modal-actions"><button class="button" type="button" data-close-modal>Return to Settings</button></div>`,
      );
    return value;
  }

  async function softwareOperation(operation, body) {
    if (pendingOperation) throw new Error('Wait for the current update request to finish.');
    const requestGeneration = generation;
    const request = ++statusRequest;
    clearTimeout(timer);
    let value;
    const pending = ctx.actions.api(`/api/software/${operation}`, {
      method: 'POST',
      ...(body ? { body } : {}),
    });
    pendingOperation = pending;
    try {
      value = await pending;
    } catch (error) {
      if (pendingOperation === pending) pendingOperation = null;
      if (disposed || requestGeneration !== generation) return status;
      await loadSoftwareStatus().catch(() => {});
      throw error;
    } finally {
      if (pendingOperation === pending) pendingOperation = null;
    }
    if (disposed || requestGeneration !== generation || request !== statusRequest) return value;
    status = value;
    paint();
    poll();
    return status;
  }

  function unsaved() {
    return Boolean(
      ctx.state.editor?.dirty ||
        ctx.state.entities?.dirty ||
        ctx.state.workflow?.workflowDirty ||
        ctx.actions.hasUnsavedSettings?.() ||
        ctx.actions.hasUnsavedSetup?.() ||
        ctx.actions.hasUnsavedLibrary?.() ||
        ctx.actions.hasUnsavedOutreach?.(),
    );
  }

  async function reviewSoftwareInstall() {
    installReview = null;
    const requestGeneration = generation;
    if (unsaved()) {
      ctx.actions.toast('Save or discard your unsaved changes before installing an update.');
      return;
    }
    await loadSoftwareStatus();
    if (disposed || requestGeneration !== generation) return;
    if (status?.phase !== 'ready' || !status.can_install) return;
    const shown = ctx.actions.modal(
      'Install software update',
      `<p>Install version <strong>${escape(status.candidate.version)}</strong>?</p><p>The workspace will close while the verified installer replaces the application, then reopen. Your records and settings are retained.</p>${notes(status.candidate)}<div class="modal-actions"><button class="button" type="button" data-close-modal>Keep working</button><button class="button primary" type="button" data-action="software-install">Install and restart</button></div>`,
    );
    if (shown !== false)
      installReview = {
        version: status.candidate.version,
        channel: status.candidate.channel,
        installer_sha256: status.candidate.installer_sha256,
      };
  }

  async function installSoftwareUpdate() {
    const requestGeneration = generation;
    if (unsaved()) {
      ctx.actions.toast('Save or discard your unsaved changes before installing an update.');
      return;
    }
    if (!installReview) {
      ctx.actions.toast('Review the available update before installing.');
      return;
    }
    const review = installReview;
    installReview = null;
    const value = await softwareOperation('install', review);
    if (disposed || requestGeneration !== generation) return;
    if (value.phase === 'installing')
      ctx.actions.modal(
        'Installing software update',
        '<p>The verified installer is starting. The application will close and reopen after installation.</p><p>If Windows presents an installer error, your working records are retained. Reopen the app after resolving the error.</p>',
      );
  }

  async function showSoftwareWhatsNew({ automatic = false } = {}) {
    const requestGeneration = generation;
    const value = await ctx.actions.api('/api/software/whats-new');
    if (
      disposed ||
      requestGeneration !== generation ||
      (automatic && (!value.should_show || ctx.actions.$('#modal')?.open))
    )
      return false;
    const shown = ctx.actions.modal(
      'What’s new',
      `<p class="dm-overline">Installed version ${escape(value.version)}</p><h3>${escape(value.title)}</h3>${notes(value)}<div class="modal-actions"><button class="button primary" type="button" data-action="software-whats-new-dismiss">Continue</button></div>`,
    );
    if (shown === false) return false;
    // Record presentation, including dismissal through Escape or the modal X.
    await ctx.actions.api('/api/software/whats-new/seen', {
      method: 'POST',
      body: { version: value.version },
    });
    return true;
  }

  function disposeSoftwareUpdates() {
    disposed = true;
    generation++;
    statusRequest++;
    pendingOperation = null;
    installReview = null;
    clearTimeout(timer);
  }

  function resumeSoftwareUpdates() {
    disposed = false;
    generation++;
  }

  Object.assign(ctx.actions, {
    softwareUpdatesMarkup,
    loadSoftwareStatus,
    softwareOperation,
    reviewSoftwareInstall,
    installSoftwareUpdate,
    showSoftwareWhatsNew,
    maybeShowSoftwareWhatsNew: () => showSoftwareWhatsNew({ automatic: true }),
    disposeSoftwareUpdates,
    resumeSoftwareUpdates,
  });
}

export function createHandlers(ctx) {
  return {
    change: [],
    click: [],
    forms: {},
    actions: {
      'software-check': () => ctx.actions.softwareOperation('check'),
      'software-download': () => ctx.actions.softwareOperation('download'),
      'software-install-review': () => ctx.actions.reviewSoftwareInstall(),
      'software-install': () => ctx.actions.installSoftwareUpdate(),
      'software-whats-new': () => ctx.actions.showSoftwareWhatsNew(),
      'software-whats-new-dismiss': () => ctx.actions.closeModal(),
    },
  };
}
