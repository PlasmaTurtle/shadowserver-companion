/** Guided setup. Credential values never enter state or browser persistence. */
const STEPS = ['connections', 'profile', 'automation'];
const LABELS = ['API connections', 'Identity & jurisdiction', 'Retrieval schedule'];
const ZONES = [
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Anchorage',
  'Pacific/Honolulu',
  'UTC',
];

export function install(ctx) {
  const state = {
    disposed: false,
    epoch: 0,
    status: null,
    step: 'connections',
    open: false,
    dirty: false,
    busy: false,
    generation: 0,
    timer: null,
    nvd: null,
    shadow: null,
    workspaceChanged: false,
    scheduleDraft: null,
    profileDraft: null,
  };
  async function setupApi(...args) {
    const epoch = state.epoch;
    if (state.disposed) throw new Error('Setup is no longer open.');
    const result = await ctx.actions.api(...args);
    if (state.disposed || epoch !== state.epoch) throw new Error('Setup is no longer open.');
    return result;
  }
  const esc = (value) => ctx.actions.esc(value ?? '');
  const input = (label, name, value = '', options = {}) =>
    `<div class="field ${options.full ? 'full' : ''}"><label for="setup-${name}">${label}</label><input id="setup-${name}" name="${name}" type="${options.type || 'text'}" value="${esc(value)}" maxlength="${options.max || 500}" ${options.required ? 'required' : ''} ${options.autocomplete ? `autocomplete="${options.autocomplete}"` : ''}>${options.help ? `<small>${options.help}</small>` : ''}</div>`;
  const selectedAgency = (profile) =>
    state.status?.agencies?.find((a) => a.id !== 'custom' && a.name === profile.agency)?.id ||
    'custom';
  const notice = (message, kind = 'info') =>
    `<div class="notice ${kind === 'error' ? 'warn' : ''}" role="${kind === 'error' ? 'alert' : 'status'}"><p>${esc(message)}</p></div>`;

  function setupError(error) {
    const node = ctx.actions.$('#setup-error');
    if (node) {
      node.hidden = false;
      node.textContent = error.message || String(error);
      node.focus?.();
    }
  }
  function clearSetupError() {
    const node = ctx.actions.$('#setup-error');
    if (node) {
      node.hidden = true;
      node.textContent = '';
    }
  }
  function stepsMarkup() {
    return `<ol class="setup-steps" aria-label="Setup progress">${STEPS.map((name, index) => `<li ${state.step === name ? 'aria-current="step"' : ''} class="${state.status?.steps?.[name] ? 'done' : ''}"><button type="button" data-action="setup-step" data-step="${name}" ><span>${index + 1}</span>${LABELS[index]}</button></li>`).join('')}</ol>`;
  }
  function connectionsMarkup() {
    const shadow = state.shadow || {},
      nvd = state.nvd || {};
    const running = ['queued', 'running'].includes(shadow.job?.status);
    return `<p class="setup-intro">Connect the services you use. You can also import files manually and add keys later in Settings.</p><div class="setup-connections"><section class="setup-service"><header><h3>Shadowserver</h3><span class="badge ${shadow.connected ? 'green' : 'gray'}">${shadow.connected ? 'Connected' : shadow.configured ? 'Key saved' : 'Not configured'}</span></header><p>Retrieve reports available to your subscription.</p><form id="setup-shadow-form" class="form-grid" autocomplete="off"><div class="field"><label for="setup-shadow-key">API key</label><input id="setup-shadow-key" name="api_key" type="password" autocomplete="new-password" spellcheck="false" maxlength="1024" required></div><div class="field"><label for="setup-shadow-secret">API secret</label><input id="setup-shadow-secret" name="secret" type="password" autocomplete="new-password" spellcheck="false" maxlength="1024" required></div>${shadow.can_remember ? '<label class="checkbox full"><input type="checkbox" name="remember" checked><span>Save in Windows Credential Manager</span></label>' : '<p class="help full">Keys stay in this app session on this platform.</p>'}<div class="actions full"><button type="submit" class="button" ${running ? 'disabled' : ''}>Save &amp; connect</button>${shadow.configured ? `<button type="button" class="button" data-action="setup-connect" ${running ? 'disabled' : ''}>${running ? 'Connecting…' : 'Test connection'}</button>` : ''}</div></form><p id="setup-connection-status" role="status">${esc(shadow.job?.message || '')}</p></section><section class="setup-service"><header><h3>NVD</h3><span class="badge ${nvd.configured ? 'green' : 'gray'}">${nvd.configured ? 'Key saved' : 'Optional'}</span></header><p>Use your NVD API key for vulnerability catalog updates. EPSS and KEV do not require separate keys.</p><form id="setup-nvd-form" class="form-grid" autocomplete="off"><div class="field full"><label for="setup-nvd-key">NVD API key</label><input id="setup-nvd-key" name="api_key" type="password" autocomplete="new-password" spellcheck="false" maxlength="128" required></div>${nvd.remember_supported ? '<label class="checkbox full"><input type="checkbox" name="remember" checked><span>Save in Windows Credential Manager</span></label>' : '<p class="help full">Key stays in this app session on this platform.</p>'}<button type="submit" class="button">Save NVD key</button></form><a href="https://nvd.nist.gov/developers/request-an-api-key" target="_blank" rel="noopener noreferrer">Request an NVD key</a></section></div><div class="setup-footer"><button type="button" class="button" data-action="setup-manual-connections" ${running ? 'disabled' : ''}>Use manual imports for now</button><button type="button" class="button primary" data-action="setup-connections-next" ${running ? 'disabled' : ''}>Continue</button></div>`;
  }
  function agencyOptions(profile) {
    return (state.status?.agencies || [])
      .map(
        (a) =>
          `<option value="${esc(a.id)}" ${a.id === selectedAgency(profile) ? 'selected' : ''}>${esc(a.id === 'custom' ? a.name : `${a.short_name} — ${a.name}`)}</option>`,
      )
      .join('');
  }
  function profileMarkup() {
    const profile = state.profileDraft || state.status.profile;
    const known = new Set(state.status.regions || []);
    const selected = profile.regions || [];
    return `<p class="setup-intro">Identify the sender for new notifications and select the jurisdictions you work. Your office location and report jurisdiction are separate.</p><form id="setup-profile-form" class="form-grid"><div class="field full"><label for="setup-agency-preset">Agency</label><select id="setup-agency-preset">${agencyOptions(profile)}</select><small>Choose Other for state, local, tribal, international or custom organizations.</small></div>${input('Agency name', 'agency', profile.agency, { full: true, required: true })}${input('Department / parent organization', 'department', profile.department, { full: true })}${input('Your name', 'analyst_name', profile.analyst_name, { required: true, max: 300, autocomplete: 'name' })}${input('Title (optional)', 'analyst_title', profile.analyst_title, { max: 300, help: 'Leave blank to show your name without a title.' })}${input('Office / location', 'office', profile.office, { required: true, help: 'For example, a field office or city and state.' })}${input('Contact email (optional)', 'email', profile.email, { type: 'email', autocomplete: 'email' })}<fieldset class="full setup-regions"><legend>Report jurisdictions</legend><p class="help">Available API report choices and workspace scope follow these selections. Agency identity does not grant access to other states.</p><div class="setup-region-grid">${(state.status.regions || []).map((name) => `<label class="checkbox"><input type="checkbox" name="regions" value="${esc(name)}" ${selected.includes(name) ? 'checked' : ''}><span>${esc(name)}</span></label>`).join('')}</div></fieldset><div class="field full"><label for="setup-other-regions">Other report region names (optional)</label><textarea id="setup-other-regions" name="other_regions" rows="2" maxlength="2000">${esc(selected.filter((name) => !known.has(name)).join('\n'))}</textarea><small>Use the exact names supplied by your reports, one per line.</small></div><div class="field"><label for="setup-display_timezone">Display time zone</label><select id="setup-display_timezone" name="display_timezone">${[...new Set([...ZONES, profile.display_timezone].filter(Boolean))].map((zone) => `<option value="${esc(zone)}" ${zone === profile.display_timezone ? 'selected' : ''}>${esc(zone.replaceAll('_', ' '))}</option>`).join('')}</select></div><div class="setup-footer full"><button type="button" class="button" data-action="setup-step" data-step="connections">Back</button><button type="submit" class="button primary">Save profile &amp; continue</button></div></form>`;
  }
  function automationMarkup() {
    const status = state.shadow || {},
      schedule = status.schedule || state.status.schedule || {};
    const defaults = status.selection_defaults || {};
    const config = state.scheduleDraft || {
      ...schedule.config,
      subscription: schedule.config?.subscription || defaults.subscription || '',
      report_types: schedule.config?.report_types?.length
        ? schedule.config.report_types
        : defaults.report_types || [],
    };
    const subscriptions = status.subscriptions || [];
    const types = status.types || [];
    const savedSelection =
      !status.connected && config.subscription
        ? `<p class="help full">Saved selection: ${esc(config.subscription)} · ${esc((config.report_types || []).join(', '))}. Connect in step 1 to review available choices. Timing changes preserve this selection.</p>`
        : '';
    const staleSelection =
      status.connected && config.subscription && !subscriptions.includes(config.subscription)
        ? notice(
            'The saved subscription is no longer available for this jurisdiction or account. Select an available subscription before enabling scheduled reports.',
            'error',
          )
        : '';
    return `<p class="setup-intro">Set a retrieval schedule for the selected services, or leave this schedule off. Report choices follow your saved jurisdiction.</p>${schedule.scope_error ? notice(schedule.scope_error, 'error') : ''}${status.jurisdiction?.notice ? notice(status.jurisdiction.notice) : ''}<form id="setup-schedule-form" class="form-grid"><label class="checkbox full setup-choice"><input name="enabled" type="checkbox" ${config.enabled ? 'checked' : ''}><span><strong>Enable retrieval schedule</strong><small>Controls only the selected services on this schedule. Library has separate daily reference updates.</small></span></label><label class="checkbox"><input name="shadowserver" type="checkbox" ${config.shadowserver ? 'checked' : ''}><span>Shadowserver reports</span></label><label class="checkbox"><input name="reference" type="checkbox" ${config.reference ? 'checked' : ''}><span>NVD, EPSS and KEV reference data</span></label><div class="field"><label for="setup-schedule-time">First check, computer local time</label><input id="setup-schedule-time" name="time" type="time" value="${String(config.hour ?? 6).padStart(2, '0')}:${String(config.minute ?? 0).padStart(2, '0')}" required><small>${esc(schedule.timezone || 'Uses this computer’s time zone')} · this is separate from the display time zone.</small></div>${input('Recheck every (hours)', 'interval_hours', config.interval_hours || 4, { type: 'number' })}${input('Recent days to recheck', 'lookback_days', config.lookback_days || 7, { type: 'number' })}<div class="field"><label for="setup-subscription">Report subscription</label><select id="setup-subscription" name="subscription" ${!status.connected ? 'disabled' : ''}><option value="">${status.connected ? 'Select subscription' : 'Connect Shadowserver to load subscriptions'}</option>${subscriptions.map((name) => `<option value="${esc(name)}" ${name === config.subscription ? 'selected' : ''}>${esc(name)}</option>`).join('')}</select></div>${savedSelection}${staleSelection}<fieldset class="full" ${!status.connected ? 'disabled' : ''}><legend>Report types</legend>${types.length ? `<div class="setup-report-types">${types.map((type) => `<label class="checkbox"><input name="report_types" type="checkbox" value="${esc(type.type)}" ${(config.report_types || []).includes(type.type) ? 'checked' : ''}><span>${esc(type.description || type.type)}</span></label>`).join('')}</div>` : '<p class="help">Connect Shadowserver in step 1 to select available reports. You can still finish with manual imports or reference-only checks.</p>'}</fieldset>${status.can_remember ? `<label class="checkbox full"><input name="background" type="checkbox" ${(state.scheduleDraft?.background ?? schedule.background?.installed) ? 'checked' : ''}><span>Allow checks while the app is closed<small>Uses Windows Task Scheduler while signed in. Selected services need keys saved in Windows Credential Manager.</small></span></label>` : '<p class="help full">This retrieval schedule runs while the app is running. Closed-app runs require the installed Windows application.</p>'}<p class="help full">Review daily NVD catalog and EPSS/KEV update controls in Library after setup. Turning this retrieval schedule off does not disable those updates.</p><div class="setup-review full"><strong>Ready for this workspace</strong><p>${esc(state.status.profile.analyst_name || 'Your profile')} · ${esc(state.status.profile.office || '')}</p><p>Jurisdiction: ${esc((state.status.profile.regions || []).join(', '))}</p><p>Connections: Shadowserver ${status.configured ? 'configured' : 'manual'} · NVD ${state.nvd?.configured ? 'configured' : 'not configured'}</p></div><div class="setup-footer full"><button type="button" class="button" data-action="setup-step" data-step="profile">Back</button><button type="submit" class="button primary">Save choices &amp; finish setup</button></div></form>`;
  }
  function renderSetup() {
    if (state.disposed) return;
    state.open = true;
    ctx.actions.modal(
      'Set up your workspace',
      `<section id="setup-wizard" class="setup-wizard">${stepsMarkup()}<p id="setup-error" class="notice warn" role="alert" tabindex="-1" hidden></p><h2 id="setup-step-heading">${LABELS[STEPS.indexOf(state.step)]}</h2>${state.step === 'connections' ? connectionsMarkup() : state.step === 'profile' ? profileMarkup() : automationMarkup()}<p class="setup-later"><button type="button" class="text-link" data-action="setup-later">Finish later</button><span>Completed steps are saved. Resume from Settings.</span></p></section>`,
    );
    ctx.actions.$('#modal')?.classList?.add('setup-dialog');
    const interval = ctx.actions.$('#setup-interval_hours'),
      lookback = ctx.actions.$('#setup-lookback_days');
    if (interval) {
      interval.min = '1';
      interval.max = '24';
      interval.required = true;
    }
    if (lookback) {
      lookback.min = '1';
      lookback.max = '30';
      lookback.required = true;
    }
  }
  async function refreshSetup() {
    const values = await Promise.all([
      setupApi('/api/setup'),
      setupApi('/api/shadowserver/status'),
      setupApi('/api/nvd/credentials'),
    ]);
    [state.status, state.shadow, state.nvd] = values;
    return state.status;
  }
  async function openSetup(requestedStep = null) {
    if (ctx.actions.hasUnsavedSettings?.()) {
      if (!confirm('Discard unsaved Settings changes and open setup?')) return false;
      const settingsForm = ctx.actions.$('#settings-form');
      if (settingsForm) settingsForm.dataset.dirty = 'false';
      await ctx.actions.route(true);
    }
    await refreshSetup();
    state.step =
      state.status.completed && STEPS.includes(requestedStep)
        ? requestedStep
        : state.status.completed || state.status.established_profile
          ? 'connections'
          : state.status.step;
    state.profileDraft = null;
    state.scheduleDraft = null;
    state.dirty = false;
    renderSetup();
    return true;
  }
  async function maybeStartSetup() {
    if (state.disposed) return false;
    if (ctx.state.navigation.boot?.demo) return false;
    const status = await setupApi('/api/setup');
    state.status = status;
    if (!status.required || ctx.actions.$('#modal')?.open) return false;
    return openSetup();
  }
  function connectionDraft() {
    return ctx.actions
      .$$('#setup-wizard input[type="password"]')
      .some((input) => Boolean(input.value));
  }
  function hasUnsavedSetup() {
    return (
      state.open &&
      (state.dirty ||
        Boolean(state.profileDraft) ||
        Boolean(state.scheduleDraft) ||
        connectionDraft())
    );
  }
  function setupMarkDirty() {
    state.dirty = true;
  }
  function confirmDiscardSetup() {
    if (!state.open) return true;
    if (state.busy) {
      setupError(new Error('Wait for the current setup step to finish.'));
      return false;
    }
    if (
      hasUnsavedSetup() &&
      !confirm('Leave this step without saving your changes? Completed steps are already saved.')
    )
      return false;
    state.dirty = false;
    return true;
  }
  function setupModalCanReplace(title) {
    if (!state.open || title === 'Set up your workspace') return true;
    return false;
  }
  function resumeSetup() {
    state.disposed = false;
  }
  function disposeSetup() {
    state.disposed = true;
    state.epoch++;
    const dialog = ctx.actions.$('#modal');
    if (state.open) dialog?.close?.();
    setupModalClosed();
  }
  function setupModalClosed() {
    if (!state.open) return;
    state.open = false;
    state.dirty = false;
    state.busy = false;
    state.generation++;
    clearTimeout(state.timer);
    state.timer = null;
    state.profileDraft = null;
    state.scheduleDraft = null;
    const dialog = ctx.actions.$('#modal');
    dialog?.classList?.remove('setup-dialog');
    const body = ctx.actions.$('#modal-body');
    if (body?.querySelector?.('#setup-wizard')) body.innerHTML = '';
    const changed = state.workspaceChanged;
    state.workspaceChanged = false;
    if (changed && !state.disposed) void ctx.actions.route(true).catch(() => {});
  }
  function captureDraft() {
    const form = ctx.actions.$(
      state.step === 'profile' ? '#setup-profile-form' : '#setup-schedule-form',
    );
    if (!form || !state.dirty) return;
    const data = new FormData(form),
      values = Object.fromEntries(data);
    if (state.step === 'profile') state.profileDraft = profileValues(values, data);
    else state.scheduleDraft = scheduleValues(values, data);
  }
  async function changeSetupStep(step) {
    if (!STEPS.includes(step) || state.busy || step === state.step) return;
    if (step !== 'connections' && !state.status.steps.connections) {
      setupError(
        new Error('Continue from API connections or choose manual imports before moving on.'),
      );
      return;
    }
    if (step === 'automation' && !state.status.steps.profile) {
      setupError(
        new Error('Save your identity and jurisdiction before setting up the retrieval schedule.'),
      );
      return;
    }
    if (
      state.step === 'connections' &&
      connectionDraft() &&
      !confirm('Leave without saving the entered keys?')
    )
      return;
    if (step === 'automation' && ['queued', 'running'].includes(state.shadow?.job?.status)) {
      setupError(
        new Error(
          'Wait for the report connection to finish before configuring the retrieval schedule.',
        ),
      );
      return;
    }
    captureDraft();
    state.dirty = false;
    state.step = step;
    if (step === 'automation') {
      state.shadow = await setupApi('/api/shadowserver/status');
    }
    renderSetup();
  }
  async function stepOperation(fn) {
    if (state.busy) return;
    state.busy = true;
    clearSetupError();
    const controls = ctx.actions
      .$$('#setup-wizard input, #setup-wizard select, #setup-wizard textarea, #setup-wizard button')
      .map((node) => [node, node.disabled]);
    controls.forEach(([node]) => {
      node.disabled = true;
    });
    try {
      return await fn();
    } catch (error) {
      setupError(error);
      return false;
    } finally {
      state.busy = false;
      controls.forEach(([node, disabled]) => {
        node.disabled = disabled;
      });
    }
  }
  async function pollConnection() {
    const generation = ++state.generation;
    clearTimeout(state.timer);
    const tick = async () => {
      if (!state.open || generation !== state.generation) return;
      try {
        state.shadow = await setupApi('/api/shadowserver/status');
        if (!state.open || generation !== state.generation) return;
        if (['queued', 'running'].includes(state.shadow.job?.status)) {
          const note = ctx.actions.$('#setup-connection-status');
          if (note) note.textContent = state.shadow.job.message || 'Connecting…';
          state.timer = setTimeout(tick, 1000);
        } else if (state.step === 'connections' && !connectionDraft()) renderSetup();
      } catch (error) {
        setupError(error);
      }
    };
    await tick();
  }
  async function saveSetupShadow(form, values) {
    return stepOperation(async () => {
      state.shadow = await setupApi('/api/shadowserver/credentials', {
        method: 'PUT',
        body: {
          api_key: values.api_key,
          secret: values.secret,
          remember: values.remember === 'on',
        },
      });
      form.reset();
      state.dirty = connectionDraft();
      await setupApi('/api/shadowserver/connection', { method: 'POST' });
      await pollConnection();
    });
  }
  async function connectSetup() {
    return stepOperation(async () => {
      await setupApi('/api/shadowserver/connection', { method: 'POST' });
      await pollConnection();
    });
  }
  async function saveSetupNvd(form, values) {
    return stepOperation(async () => {
      state.nvd = await setupApi('/api/nvd/credentials', {
        method: 'PUT',
        body: { api_key: values.api_key, remember: values.remember === 'on' },
      });
      form.reset();
      state.dirty = connectionDraft();
      const heading = form.closest?.('section')?.querySelector?.('.badge');
      if (heading) {
        heading.textContent = 'Key saved';
        heading.classList.add('green');
      }
      ctx.actions.toast('NVD key saved.');
    });
  }
  async function setupConnectionsNext(manual = false) {
    return stepOperation(async () => {
      if (['queued', 'running'].includes(state.shadow?.job?.status))
        throw new Error('Wait for the report connection to finish before continuing.');
      if (connectionDraft() && !confirm('Continue without saving the entered keys?')) return;
      state.status = await setupApi('/api/setup/progress', {
        method: 'PUT',
        body: {
          step: 'connections',
          mode:
            manual || (!state.shadow?.configured && !state.nvd?.configured)
              ? 'manual'
              : 'configured',
        },
      });
      state.dirty = false;
      state.step = 'profile';
      renderSetup();
    });
  }
  function profileValues(values, data) {
    return {
      analyst_name: values.analyst_name,
      analyst_title: values.analyst_title || '',
      agency: values.agency,
      department: values.department || '',
      office: values.office,
      email: values.email || '',
      display_timezone: values.display_timezone,
      regions: [
        ...new Set([
          ...data.getAll('regions'),
          ...String(values.other_regions || '')
            .split('\n')
            .map((s) => s.trim())
            .filter(Boolean),
        ]),
      ],
    };
  }
  async function saveSetupProfile(form, values, data) {
    return stepOperation(async () => {
      const profile = profileValues(values, data);
      if (!profile.regions.length) throw new Error('Select at least one report jurisdiction.');
      const result = await setupApi('/api/setup/profile', { method: 'PUT', body: profile });
      state.status = result.setup;
      state.workspaceChanged = true;
      state.profileDraft = null;
      state.dirty = false;
      ctx.state.navigation.boot.settings = result.settings;
      ctx.actions.applyPresentation?.(result.settings);
      const office = ctx.actions.$('#office-label');
      if (office) office.textContent = result.settings.office;
      state.shadow = await setupApi('/api/shadowserver/status');
      if (state.scheduleDraft && state.shadow.connected) {
        if (!(state.shadow.subscriptions || []).includes(state.scheduleDraft.subscription))
          state.scheduleDraft.subscription = '';
        const types = new Set((state.shadow.types || []).map((item) => item.type));
        state.scheduleDraft.report_types = state.scheduleDraft.report_types.filter((type) =>
          types.has(type),
        );
      }
      state.step = 'automation';
      renderSetup();
    });
  }
  function scheduleValues(values, data) {
    const [hour, minute] = String(values.time || '06:00')
      .split(':')
      .map(Number);
    const saved =
      state.scheduleDraft || state.shadow?.schedule?.config || state.status?.schedule?.config || {};
    const preserveSelection = !state.shadow?.connected;
    return {
      background: data.has('background'),
      enabled: data.has('enabled'),
      shadowserver: data.has('shadowserver'),
      reference: data.has('reference'),
      hour,
      minute,
      interval_hours: Number(values.interval_hours),
      lookback_days: Number(values.lookback_days),
      subscription: preserveSelection ? saved.subscription || '' : values.subscription || '',
      report_types: preserveSelection ? saved.report_types || [] : data.getAll('report_types'),
    };
  }
  async function saveSetupSchedule(form, values, data) {
    return stepOperation(async () => {
      const { background: backgroundRequested, ...config } = scheduleValues(values, data);
      const schedule = await setupApi('/api/schedule', { method: 'PUT', body: config });
      state.workspaceChanged = true;
      const background = backgroundRequested && config.enabled;
      if (Boolean(schedule.background?.installed) !== background)
        await setupApi('/api/schedule/background', {
          method: 'PUT',
          body: { enabled: background },
        });
      state.status = await setupApi('/api/setup/progress', {
        method: 'PUT',
        body: { step: 'automation', mode: config.enabled ? 'configured' : 'manual' },
      });
      state.status = await setupApi('/api/setup/complete', { method: 'POST' });
      state.dirty = false;
      state.profileDraft = null;
      state.scheduleDraft = null;
      state.busy = false;
      state.workspaceChanged = false;
      ctx.actions.closeModal();
      setupModalClosed();
      ctx.actions.toast('Workspace setup complete. You can change these choices in Settings.');
      await ctx.actions.route(true);
      await ctx.actions.maybeShowSoftwareWhatsNew?.();
    });
  }
  async function afterSettingsProfileSave() {
    try {
      state.status = await setupApi('/api/setup');
      const automation = ctx.actions.$('#settings-section-automation');
      if (automation && ctx.actions.settingsAutomationMarkup)
        automation.outerHTML = ctx.actions.settingsAutomationMarkup({
          schedule: state.status.schedule,
        });
    } catch {
      /* Saving preferences has already succeeded. */
    }
  }
  function setupStatusMarkup() {
    return `<section class="settings-setup-card"><div><span class="dm-overline">Workspace setup</span><h2>Identity, connections and retrieval schedule</h2><p>Review the guided setup or update each section below.</p></div><button type="button" class="button" data-action="open-setup">Review setup</button></section>`;
  }
  function applyAgencyPreset(select) {
    const agency = state.status?.agencies?.find((item) => item.id === select.value);
    const prefix = select.id.startsWith('setup-') ? 'setup-' : 'f-';
    if (!agency || agency.id === 'custom') return;
    const name = ctx.actions.$(`#${prefix}agency`),
      department = ctx.actions.$(`#${prefix}department`);
    if (name) name.value = agency.name;
    if (department) department.value = agency.department;
    if (prefix === 'setup-') state.dirty = true;
    else ctx.actions.settingsChanged(select.closest?.('#settings-form'));
  }
  async function loadSettingsSetupStatus() {
    const initial = ctx.actions.$('#settings-agency-preset');
    try {
      state.status = await setupApi('/api/setup');
      const select = ctx.actions.$('#settings-agency-preset');
      if (select && select === initial && !ctx.actions.hasUnsavedSettings?.())
        select.innerHTML = agencyOptions(ctx.state.navigation.boot.settings);
    } catch {
      /* The editable agency fields remain usable offline. */
    }
  }
  Object.assign(ctx.actions, {
    openSetup,
    maybeStartSetup,
    disposeSetup,
    resumeSetup,
    hasUnsavedSetup,
    confirmDiscardSetup,
    setupModalCanReplace,
    setupModalClosed,
    changeSetupStep,
    saveSetupShadow,
    connectSetup,
    saveSetupNvd,
    setupConnectionsNext,
    saveSetupProfile,
    saveSetupSchedule,
    afterSettingsProfileSave,
    setupStatusMarkup,
    applyAgencyPreset,
    loadSettingsSetupStatus,
    setupMarkDirty,
  });
}

export function createHandlers(ctx) {
  return {
    input: (event) => {
      if (event.target.closest?.('#setup-wizard')) ctx.actions.setupMarkDirty?.();
    },
    change: [
      {
        matches: (el) => ['setup-agency-preset', 'settings-agency-preset'].includes(el.id),
        run: (el) => ctx.actions.applyAgencyPreset(el),
      },
      {
        matches: (el) => Boolean(el.closest?.('#setup-wizard')),
        run: () => ctx.actions.setupMarkDirty?.(),
      },
    ],
    click: [],
    actions: {
      'open-setup': () => ctx.actions.openSetup(),
      'open-setup-automation': () => ctx.actions.openSetup('automation'),
      'setup-step': (el) => ctx.actions.changeSetupStep(el.dataset.step),
      'setup-connect': () => ctx.actions.connectSetup(),
      'setup-connections-next': () => ctx.actions.setupConnectionsNext(),
      'setup-manual-connections': () => ctx.actions.setupConnectionsNext(true),
      'setup-later': () => ctx.actions.closeModal(),
    },
    forms: {
      'setup-shadow-form': (form, values) => ctx.actions.saveSetupShadow(form, values),
      'setup-nvd-form': (form, values) => ctx.actions.saveSetupNvd(form, values),
      'setup-profile-form': (form, values, data) =>
        ctx.actions.saveSetupProfile(form, values, data),
      'setup-schedule-form': (form, values, data) =>
        ctx.actions.saveSetupSchedule(form, values, data),
    },
  };
}
