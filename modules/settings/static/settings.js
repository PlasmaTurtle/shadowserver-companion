import {
  requireProfileCatalog,
  profileInput,
  agencyFields,
  jurisdictionFields,
  timezoneField,
  targetedFields,
  applyAgencySelection,
  validateProfileFields,
  removeUnsupportedRegions,
} from './profile_fields.js';

/** Application preferences, identity and service configuration owned by Settings. No startup requests or event listeners are installed here. */
export function install(ctx) {
  let settingsWrites = Promise.resolve();
  let pendingAppearance = null;
  let themeRevision = 0;
  let profileCatalog = null;

  function persistSettings(values) {
    const saved = settingsWrites.then(async () => {
      const settings = await ctx.actions.api('/api/settings', { method: 'PUT', body: values });
      ctx.state.navigation.boot.settings = settings;
      return settings;
    });
    settingsWrites = saved.catch(() => {});
    return saved;
  }

  function updateThemeLabel() {
    const dark = document.documentElement?.dataset.theme === 'dark',
      button = ctx.actions.$('#theme-toggle');
    if (button) {
      button.textContent = dark ? 'Light mode' : 'Dark mode';
      button.setAttribute?.(
        'aria-label',
        dark ? 'Switch to light workspace' : 'Switch to dark workspace',
      );
    }
  }

  function applyPresentation(settings) {
    document.documentElement.dataset.timezone = settings.display_timezone || 'America/New_York';
    const appearance =
      pendingAppearance ||
      settings.appearance ||
      window.CompanionPresentation?.preference() ||
      document.documentElement.dataset.theme ||
      'light';
    if (window.CompanionPresentation)
      window.CompanionPresentation.apply(appearance, settings.brand_profile || 'companion');
    else {
      document.documentElement.dataset.theme = appearance === 'dark' ? 'dark' : 'light';
      document.documentElement.dataset.brand = settings.brand_profile || 'companion';
    }
    ctx.actions.updateThemeLabel();
  }

  function toggleTheme() {
    const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    const revision = ++themeRevision;
    const form = ctx.actions.$('#settings-form');
    form?.querySelectorAll?.('input[name="appearance"]').forEach((input) => {
      input.checked = input.value === theme;
    });
    if (window.CompanionPresentation)
      window.CompanionPresentation.apply(
        theme,
        ctx.state.navigation.boot?.settings?.brand_profile || 'companion',
      );
    else {
      document.documentElement.dataset.theme = theme;
      try {
        localStorage.setItem('companion-theme', theme);
      } catch {}
    }
    ctx.actions.updateThemeLabel();
    if (!ctx.state.navigation.boot?.token) return;
    pendingAppearance = theme;
    return persistSettings({ appearance: theme })
      .then((settings) => {
        if (revision !== themeRevision) return;
        pendingAppearance = null;
        ctx.actions.applyPresentation(settings);
      })
      .catch((error) => {
        if (revision !== themeRevision) return;
        pendingAppearance = null;
        settingsChanged(ctx.actions.$('#settings-form'));
        ctx.actions.toast(
          'Appearance changed in this browser; settings could not be saved: ' + error.message,
          true,
        );
      });
  }

  function presentationSettings(s) {
    const appearance =
      pendingAppearance ||
      s.appearance ||
      window.CompanionPresentation?.preference() ||
      document.documentElement.dataset.theme ||
      'light';
    return `<section class="panel presentation-section"><div class="panel-head"><div><h2>Appearance &amp; branding</h2><p>Workspace appearance does not change saved report branding.</p></div></div><div class="panel-body"><div class="field"><label for="brand-profile">Agency branding</label><select id="brand-profile" name="brand_profile">${ctx.actions.optionList(
      [
        ['companion', 'Companion'],
        ['usss', 'USSS'],
      ],
      s.brand_profile || 'companion',
    )}</select></div><div class="palette-preview" aria-label="USSS digital colors"><i style="background:#010101" title="Beast Black · #010101"></i><i style="background:#002d61" title="Lincoln Blue · #002d61"></i><i style="background:#b4a471" title="Centurion Gold · #b4a471"></i><i style="background:#5f88b0" title="Detail Blue · #5f88b0"></i><i style="background:#d5cca8" title="Legacy Gold · #d5cca8"></i></div><p class="branding-note">USSS colors are restricted to approved mission-related use. Selecting this profile does not grant approval or add an official seal. Existing reports retain their saved presentation.</p><fieldset><legend>Workspace appearance</legend><div class="theme-options">${[
      ['light', 'Light', 'Clear, bright workspace'],
      ['dark', 'Dark Matter', 'Low-light workspace'],
      ['system', 'System', 'Follow this computer'],
    ]
      .map(
        ([value, title, help]) =>
          `<label class="theme-choice"><input type="radio" name="appearance" value="${value}" ${appearance === value ? 'checked' : ''}><span><strong>${title}</strong><small>${help}</small></span></label>`,
      )
      .join(
        '',
      )}</div></fieldset>${timezoneField(ctx.actions.esc, s, requireProfileCatalog(profileCatalog), 'display-timezone')}<div class="policy-card"><span class="tlp-mark">TLP:AMBER</span><p>Share on a need-to-know basis within the receiving organization and its clients. Source-specific additional restrictions still apply. Reports include the marking in the header and footer of every page.</p></div><p class="section-note">Blue: confirmed association or completed workflow. Red: adverse finding. Gray: pending or unknown. Confirmation does not mean remediation.</p></div></section>`;
  }

  function hasUnsavedSettings() {
    return (
      ctx.actions.$('#settings-form')?.dataset.dirty === 'true' ||
      Boolean(ctx.actions.$('#nvd-api-key')?.value)
    );
  }

  function discardSettingsChanges() {
    const form = ctx.actions.$('#settings-form');
    if (form) form.dataset.dirty = 'false';
    ctx.actions.$('#nvd-key-form')?.reset();
  }

  function validateSettingsForm(form) {
    validateProfileFields(form);
    if (!form.checkValidity || form.checkValidity()) return true;
    for (const input of form.querySelectorAll(':invalid')) {
      let details = input.closest('details');
      while (details && form.contains(details)) {
        details.open = true;
        details = details.parentElement?.closest('details');
      }
    }
    settingsSaveStatus('Review the highlighted fields before saving.', 'error', form);
    form.reportValidity();
    return false;
  }

  function settingsSaveStatus(message, state = 'saved', expectedForm = null) {
    const form = ctx.actions.$('#settings-form');
    if (expectedForm && form !== expectedForm) return;
    const status = ctx.actions.$('#settings-save-status');
    if (!status) return;
    status.textContent = message;
    status.dataset.state = state;
  }

  function settingsChanged(form) {
    if (!form || form.id !== 'settings-form') return;
    validateProfileFields(form);
    form.dataset.dirty = 'true';
    form.dataset.editRevision = String(Number(form.dataset.editRevision || 0) + 1);
    ctx.actions.settingsSaveStatus('Unsaved changes', 'unsaved', form);
  }

  function settingsDataMarkup(dataStatus) {
    const backup = dataStatus.backup || {};
    const points = backup.restore_points || [];
    const pending = dataStatus.pending;
    const backupDate = backup.last_export?.verified_at
      ? ctx.actions.stamp(backup.last_export.verified_at)
      : 'No verified export recorded';
    return `<details class="panel"><summary>About</summary><div class="panel-body"><h3>${ctx.actions.esc(ctx.state.navigation.boot.release?.app_name || 'Shadowserver Eclipse')}</h3><p>Version ${ctx.actions.esc(ctx.state.navigation.boot.release?.version || ctx.state.navigation.boot.version)} · ${ctx.actions.esc({ stable: 'Release', candidate: 'Release candidate', unstable: 'Development release' }[ctx.state.navigation.boot.release?.channel] || 'Release details unavailable')}</p></div></details><section class="panel"><div class="panel-head"><div><h2>Backup &amp; recovery</h2><p>Keep a verified copy of your workspace.</p></div></div><div class="panel-body"><div class="settings-summary"><span>Last verified export</span><strong>${backupDate}</strong></div>${pending ? `<div class="notice warn" role="status"><div><strong>${pending === 'import' ? 'Import' : 'Deletion'} is ready to apply.</strong><p>Close and reopen the app to apply. Changes are paused until then.${dataStatus.restore_point_skipped ? ' No new restore point of current data was saved.' : ''}</p></div></div><button class="button full-width" type="button" data-action="cancel-data-change">Cancel pending change</button>` : `<div class="settings-data-actions"><button class="button primary full-width" type="button" data-action="backup">${ctx.actions.icon('download')}Export data</button><button class="button full-width" type="button" data-action="import-data">Import data</button></div><p class="help">Import replaces this workspace after a restore point is saved. You review and confirm it before restarting.</p>`}<details class="settings-help"><summary>Backup contents and limits</summary><p class="help">Includes records, original reports, evidence, completed reports, inbox files, settings and operation history. Each export is checked by restoring an isolated copy.</p><p class="help">Up to 2 GiB compressed and 8 GiB expanded. The latest ${backup.retention || 3} automatic restore points are retained.</p></details>${points.length ? `<details class="settings-help"><summary>Saved restore points (${points.length})</summary><ul>${points.map((point) => `<li><a class="text-link" href="/api/data/restore-points/${ctx.actions.esc(point.id)}">${ctx.actions.stamp(point.created_at)}</a></li>`).join('')}</ul></details>` : ''}<details class="settings-help"><summary>Workspace folder</summary><code class="code-path">${ctx.actions.esc(ctx.state.navigation.boot.workspace)}</code></details></div></section>${ctx.actions.workspaceHealthPanel(pending)}${pending ? '' : `<details class="panel settings-danger"><summary>Delete workspace data</summary><div class="panel-body"><p>Removes current records and managed restore points after restart. Exported copies elsewhere are not deleted.</p><button class="button danger full-width" type="button" data-action="delete-data">Delete all data</button></div></details>`}`;
  }

  async function refreshSettingsData() {
    const original = ctx.actions.$('#settings-data-panel');
    const status = await ctx.actions.api('/api/data/status');
    if (ctx.actions.$('#settings-data-panel') !== original) return;
    const panel = ctx.actions.$('#settings-data-panel');
    if (panel) {
      const retained = ['#nvd-key-panel', '#settings-section-automation', '#software-updates-panel']
        .map((id) => panel.querySelector?.(id))
        .filter(Boolean);
      panel.innerHTML = `<div id="settings-data-controls">${ctx.actions.settingsDataMarkup(status)}</div>`;
      for (const section of retained.reverse()) panel.prepend(section);
    }
    const button = ctx.actions.$('#settings-save-button');
    if (button) button.disabled = Boolean(status.pending);
    if (status.pending)
      ctx.actions.settingsSaveStatus(
        'Restart or cancel the pending data change before saving settings.',
        'paused',
      );
    else if (!ctx.actions.hasUnsavedSettings())
      ctx.actions.settingsSaveStatus('No unsaved changes');
  }

  function settingsNumber(name, label, value, min, max, step) {
    return `<div class="field"><label for="f-${name}">${label}</label><input id="f-${name}" name="${name}" type="number" value="${ctx.actions.esc(value)}" min="${min}" max="${max}" step="${step}" required><small>${min}–${max}${name === 'retries' ? ' retries' : ' seconds'}</small></div>`;
  }

  function reportProfileSetting(settings) {
    const selected = settings.report_type || 'auto';
    const choices = [
      ['auto', 'Auto - use the reported type or recognized filename'],
      ...(ctx.state.navigation.boot.notification_profiles || []).map((profile) => [
        profile.id,
        profile.name + (profile.notification_mode === 'targeted' ? ' - targeted review' : ''),
      ]),
    ];
    if (!choices.some(([id]) => id === selected))
      choices.push([selected, `Saved profile: ${selected}`]);
    return `<div class="field full"><label for="f-report_type">Report profile</label><select id="f-report_type" name="report_type" aria-describedby="report-profile-help">${ctx.actions.optionList(choices, selected)}</select><small id="report-profile-help">Auto uses a declared report type or recognized report filename. For a renamed file with no declared type, choose its actual report type. A manual choice applies to every new import until you return to Auto. RDP, MS-RPC and compromised-device or website reports require Targeted outreach and a recorded reason.</small></div>`;
  }

  let shadowConnection = null;

  let libraryAutomationStatus = null;

  function nvdKeyStatus(status) {
    if (!status.configured)
      return 'Add your NVD API key for the full CVE catalog and daily updates.';
    const source =
      status.source === 'windows'
        ? 'Windows Credential Manager'
        : status.source === 'environment'
          ? 'Environment'
          : 'This session';
    return `Key configured · ${source}`;
  }

  function nvdKeyFeedback(form, message) {
    if (ctx.actions.$('#nvd-key-form') !== form) return;
    const feedback = ctx.actions.$('#nvd-key-feedback');
    if (feedback) feedback.textContent = message;
  }

  function nvdKeyChanged(form) {
    form.dataset.editRevision = String(Number(form.dataset.editRevision || 0) + 1);
    nvdKeyFeedback(
      form,
      ctx.actions.$('#nvd-api-key')?.value ? 'Entered key has not been saved.' : '',
    );
  }

  function clearNvdKey() {
    const form = ctx.actions.$('#nvd-key-form');
    if (!form) return;
    form.reset();
    nvdKeyChanged(form);
    nvdKeyFeedback(form, 'Entered key cleared. Your saved connection is unchanged.');
  }

  function finishNvdKeyOperation(form, editRevision, status, message) {
    const panel = ctx.actions.$('#nvd-key-panel');
    if (!panel || !panel.contains(form)) return;
    if ((form.dataset?.editRevision || '0') !== editRevision) {
      const label = ctx.actions.$('#nvd-key-status');
      if (label) label.textContent = nvdKeyStatus(status);
      nvdKeyFeedback(
        form,
        `${message} ${ctx.actions.$('#nvd-api-key')?.value ? 'New key edits remain unsaved.' : 'The entry is clear.'}`,
      );
    } else {
      form.reset();
      panel.outerHTML = nvdKeyMarkup(status);
    }
  }

  function nvdKeyMarkup(status = {}) {
    return `<section class="panel" id="nvd-key-panel"><div class="panel-head"><h2>API connections</h2></div><div class="panel-body"><h3>NVD</h3><p id="nvd-key-status" role="status">${ctx.actions.esc(nvdKeyStatus(status))}</p><form id="nvd-key-form" data-edit-revision="0"><div class="field"><label for="nvd-api-key">NVD API key</label><input id="nvd-api-key" name="api_key" type="password" autocomplete="off" spellcheck="false" maxlength="128" required placeholder="${status.configured ? 'Replace saved key' : 'API key'}"></div>${status.remember_supported ? '<label class="checkbox"><input name="remember" type="checkbox" checked><span>Remember on this Windows account</span></label>' : '<p class="help">Key stays in this session. NVD_API_KEY is also supported.</p>'}<div class="actions"><button class="button" type="submit">Save NVD key</button><button class="button" type="button" data-action="clear-nvd-key">Clear entry</button>${status.configured && status.source !== 'environment' ? '<button class="button" type="button" data-action="remove-nvd-key">Remove key</button>' : ''}</div><p id="nvd-key-feedback" role="status" aria-live="polite"></p></form><p><a href="https://nvd.nist.gov/developers/request-an-api-key" target="_blank" rel="noopener noreferrer">Get an NVD API key</a> · <a href="#library">Open CVE catalog</a></p><h3>Shadowserver</h3><p role="status">${shadowConnection ? (shadowConnection.connected ? 'Connected' : shadowConnection.configured ? 'Key configured · ready to connect' : 'Add your API key and secret to retrieve subscribed reports.') : 'Check your report connection in Shadowserver Data.'}</p><a href="#data?tab=api" class="button">${shadowConnection?.connected ? 'Open reports API' : 'Connect reports API'}</a></div></section>`;
  }

  async function loadNvdKeyStatus() {
    const panel = ctx.actions.$('#nvd-key-panel');
    if (!panel) return;
    if (ctx.actions.$('#settings-section-automation')) void loadSettingsLibraryAutomation();
    try {
      const [nvd, shadowserver] = await Promise.allSettled([
        ctx.actions.api('/api/nvd/credentials'),
        ctx.actions.api('/api/shadowserver/status'),
      ]);
      if (ctx.actions.$('#nvd-key-panel') !== panel) return;
      if (shadowserver.status === 'fulfilled') {
        shadowConnection = shadowserver.value;
        const automation = ctx.actions.$('#settings-section-automation');
        if (automation) automation.outerHTML = settingsAutomationMarkup(shadowConnection);
      }
      if (nvd.status === 'rejected' || panel.querySelector('input[name="api_key"]')?.value) return;
      panel.outerHTML = nvdKeyMarkup(nvd.value);
    } catch {
      /* Keep the key entry usable; save reports explicit errors. */
    }
  }

  async function saveNvdKey(form, values) {
    const editRevision = form.dataset?.editRevision || '0';
    nvdKeyFeedback(form, 'Saving key…');
    try {
      const status = await ctx.actions.api('/api/nvd/credentials', {
        method: 'PUT',
        body: { api_key: values.api_key, remember: values.remember === 'on' },
      });
      finishNvdKeyOperation(form, editRevision, status, 'NVD key saved.');
      ctx.actions.toast('NVD key saved. Open Library to download the catalog.');
    } catch (error) {
      nvdKeyFeedback(form, 'Could not save: ' + error.message + ' Your entered key remains here.');
      throw error;
    }
  }

  async function removeNvdKey() {
    const form = ctx.actions.$('#nvd-key-form');
    if (!form) return;
    if (
      ctx.actions.$('#nvd-api-key')?.value &&
      !confirm('Remove the saved NVD key and discard the entered replacement?')
    )
      return;
    const editRevision = form.dataset?.editRevision || '0';
    nvdKeyFeedback(form, 'Removing saved key…');
    try {
      const status = await ctx.actions.api('/api/nvd/credentials', { method: 'DELETE' });
      finishNvdKeyOperation(form, editRevision, status, 'Saved NVD key removed.');
    } catch (error) {
      nvdKeyFeedback(form, 'Could not remove the key: ' + error.message);
      throw error;
    }
  }

  function libraryAutomationMarkup(status = libraryAutomationStatus) {
    const catalog = status?.enabled,
      risk = status?.risk?.enabled;
    const enabled = catalog === true || risk === true;
    const known = typeof catalog === 'boolean' && typeof risk === 'boolean';
    const sources = [catalog === true ? 'NVD catalog' : '', risk === true ? 'EPSS & KEV' : '']
      .filter(Boolean)
      .join(' and ');
    return `<strong>Library daily reference updates: ${enabled ? 'Enabled' : known ? 'Off' : 'Status unavailable'}</strong><p>${enabled ? `${ctx.actions.esc(sources)} updates are enabled separately from the retrieval schedule.` : known ? 'Daily updates are off in Library. This does not stop a reference-data run from the retrieval schedule.' : 'Check Library for the current NVD catalog and EPSS/KEV update settings.'}</p><a href="#library">Manage daily updates in Library</a>`;
  }

  async function loadSettingsLibraryAutomation() {
    const form = ctx.actions.$('#settings-form');
    let status = null;
    try {
      status = await ctx.actions.api('/api/cve-catalog/status');
    } catch {
      /* Optional catalog status never blocks Settings. */
    }
    if (ctx.actions.$('#settings-form') !== form) return;
    libraryAutomationStatus = status;
    const summary = ctx.actions.$('#settings-library-automation');
    if (summary) summary.innerHTML = libraryAutomationMarkup();
  }

  function settingsAutomationMarkup(status = shadowConnection || {}) {
    const schedule = status.schedule || {},
      config = schedule.config || {};
    return `<section class="panel" id="settings-section-automation"><div class="panel-head"><h2>Retrieval schedule</h2></div><div class="panel-body settings-automation-summary"><div><strong>${config.enabled ? 'Enabled' : 'Off'}</strong><p>${config.enabled ? `Every ${ctx.actions.esc(config.interval_hours)} hours · ${ctx.actions.esc(schedule.timezone || 'computer local time')}` : 'This retrieval schedule is off. Library daily reference updates are managed separately.'}</p>${schedule.next_run_at ? `<small>Next check: ${ctx.actions.esc(ctx.actions.stamp(schedule.next_run_at))}</small>` : ''}${schedule.scope_error ? `<p class="notice warn">${ctx.actions.esc(schedule.scope_error)}</p>` : ''}<p class="help">${schedule.background?.installed ? 'Windows also checks while the app is closed and you are signed in.' : 'Closed-app checks can be enabled on the installed Windows app.'}</p></div><button type="button" class="button" data-action="open-setup-automation">Configure</button><div id="settings-library-automation" class="full">${libraryAutomationMarkup()}</div></div></section>`;
  }

  function scrollSettingsSection(id) {
    const section = ctx.actions.$('#' + id);
    if (!section) return;
    if (section.tagName === 'DETAILS') section.open = true;
    section.scrollIntoView?.({
      behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
        ? 'auto'
        : 'smooth',
      block: 'start',
    });
    section.setAttribute?.('tabindex', '-1');
    section.focus?.({ preventScroll: true });
  }

  async function settingsPage() {
    const s = ctx.state.navigation.boot.settings;
    const [dataStatus, catalog] = await Promise.all([
      ctx.actions.api('/api/data/status'),
      ctx.actions.api('/api/setup'),
    ]);
    profileCatalog = requireProfileCatalog(catalog);
    const esc = ctx.actions.esc;
    const profile = `<section class="panel" id="settings-section-profile"><div class="panel-head"><div><h2>Notification profile</h2><p>Identity used for new notifications. Earlier certified reports keep their saved sender.</p></div></div><div class="panel-body form-grid">${agencyFields(esc, s, profileCatalog, 'f-', 'settings-agency-preset')}${profileInput(esc, 'f-', 'Analyst name', 'analyst_name', s.analyst_name, { required: true, max: 300, autocomplete: 'name' })}${profileInput(esc, 'f-', 'Title (optional)', 'analyst_title', s.analyst_title, { max: 300, help: 'Leave blank to show your name without a title.' })}${profileInput(esc, 'f-', 'Office / location', 'office', s.office, { required: true, help: 'Your office or work location; not a jurisdiction filter.' })}${profileInput(esc, 'f-', 'Contact email (optional)', 'email', s.email, { type: 'email', max: 254, autocomplete: 'email' })}</div></section>`;
    const jurisdiction = `<section class="panel" id="settings-section-jurisdiction"><div class="panel-head"><div><h2>Jurisdiction</h2><p>Scope for new intake, report API choices and workspace views.</p></div></div><div class="panel-body form-grid">${jurisdictionFields(esc, s, profileCatalog, 'settings-remove-unsupported-regions')}<p class="help full">Review the retrieval schedule after changing jurisdiction; a previously saved subscription may no longer be available.</p></div></section>`;
    const intake = `<section class="panel" id="settings-section-reports"><div class="panel-head"><div><h2>Review &amp; import defaults</h2><p>Changes apply to new imports and reports you choose to re-evaluate.</p></div></div><div class="panel-body form-grid"><div class="field"><label for="outreach-mode">Outreach scope</label><select id="outreach-mode" name="outreach_mode">${ctx.actions.optionList(
      [
        ['critical', 'Critical or known exploited'],
        ['targeted', 'Targeted outreach'],
      ],
      s.outreach_mode || 'critical',
    )}</select></div>${targetedFields(esc, s, profileCatalog, 'f-', 'settings-agency-authority')}<details class="full settings-help"><summary>Agency priorities</summary><div class="form-grid">${ctx.actions.field('Priority cities', 'accretion_priority_cities', (s.accretion_priority_cities || []).join('\n'), { draft: false, area: true, rows: 2, help: 'Optional · one city per line or separated by commas.' })}${ctx.actions.field('Priority products', 'accretion_priority_products', (s.accretion_priority_products || []).join('\n'), { draft: false, area: true, rows: 2, help: 'Optional · one product per line or separated by commas.' })}<p class="help full">Matching cities and products increase urgency. Intake requirements still apply.</p></div></details><label class="checkbox full"><input type="checkbox" name="watch_inbox" ${s.watch_inbox ? 'checked' : ''}><span>Check the inbox folder automatically</span></label><details class="full settings-help"><summary>Import formats and lookup options</summary><div class="form-grid">${reportProfileSetting(s)}${profileInput(esc, 'f-', 'Worksheet name', 'sheet', s.sheet, { max: 100, full: true, help: 'Leave blank to use the first worksheet. CSV reports do not use this setting.' })}${settingsNumber('timeout', 'Lookup timeout', s.timeout ?? 10, 1, 60, 'any')}${settingsNumber('retries', 'Network retries', s.retries ?? 1, 0, 3, 1)}${settingsNumber('interval', 'Minimum lookup interval', s.interval ?? 0.25, 0, 10, 'any')}</div></details><details class="full settings-help"><summary>How rows qualify</summary><p class="help">Default outreach admits supported critical findings or locally verified KEVs. Required values: tag, hostname, IP and an in-jurisdiction region. Version requirements depend on the report type: HTTP findings without a CVE and all end-of-life findings require a software version. Supported service and incident reports may omit it. Original rows are preserved. Private IPs are retained and flagged. One exact registration or DNS match qualifies a hostname group; partial registration-name matches require review.</p></details></div></section>`;
    const sections = [
      ['settings-section-profile', 'Profile'],
      ['settings-section-jurisdiction', 'Jurisdiction'],
      ['nvd-key-panel', 'Connections'],
      ['settings-section-automation', 'Automation'],
      ['settings-section-reports', 'Reports'],
      ['settings-section-display', 'Display'],
      ['settings-data-controls', 'Data & recovery'],
      ['software-updates-panel', 'Software'],
    ];
    return (
      ctx.actions.heading('Settings', 'Configure this workspace and keep it ready for daily use.') +
      (ctx.actions.setupStatusMarkup?.() || '') +
      `<nav class="settings-section-nav" aria-label="Settings sections">${sections.map(([id, label]) => `<button type="button" data-action="settings-section" data-section="${id}">${label}</button>`).join('')}</nav><div class="settings-layout"><form id="settings-form" class="settings-main" novalidate data-dirty="false" data-edit-revision="0"><div class="settings-savebar"><div><strong>Workspace preferences</strong><p id="settings-save-status" role="status" aria-live="polite" data-state="${dataStatus.pending ? 'paused' : 'saved'}">${dataStatus.pending ? 'Restart or cancel the pending data change before saving settings.' : 'No unsaved changes'}</p></div><button id="settings-save-button" class="button primary" type="submit" ${dataStatus.pending ? 'disabled' : ''}>${ctx.actions.icon('save')}Save settings</button></div>${profile}${jurisdiction}${intake}<details class="settings-appearance" id="settings-section-display"><summary>Appearance, branding &amp; display</summary>${ctx.actions.presentationSettings(s)}</details></form><aside id="settings-data-panel" aria-label="Connections, retrieval schedule, software and workspace recovery">${nvdKeyMarkup()}${settingsAutomationMarkup()}${ctx.actions.softwareUpdatesMarkup?.() || ''}<div id="settings-data-controls">${ctx.actions.settingsDataMarkup(dataStatus)}</div></aside></div>`
    );
  }
  function applySettingsAgency(select) {
    applyAgencySelection(select, profileCatalog, ctx.actions.esc, 'settings-agency-authority');
    settingsChanged(select.closest('#settings-form'));
  }
  function settingsOutreachChanged(select) {
    const form = select.closest('#settings-form');
    const reason = form.querySelector('[name="targeted_reason"]');
    const authority = form.querySelector('#settings-agency-authority');
    const targeted = select.value === 'targeted';
    if (reason) {
      reason.required = targeted;
      reason.toggleAttribute('data-profile-trim-required', targeted);
      reason.setCustomValidity('');
    }
    if (authority) authority.hidden = !targeted;
    settingsChanged(form);
  }
  function removeSettingsUnsupportedRegions(button) {
    const form = button.closest('#settings-form');
    removeUnsupportedRegions(button);
    settingsChanged(form);
    validateProfileFields(form);
  }
  const actions = {
    applySettingsAgency,
    settingsOutreachChanged,
    removeSettingsUnsupportedRegions,
    nvdKeyMarkup,
    settingsAutomationMarkup,
    libraryAutomationMarkup,
    loadSettingsLibraryAutomation,
    scrollSettingsSection,
    loadNvdKeyStatus,
    saveNvdKey,
    removeNvdKey,
    nvdKeyChanged,
    clearNvdKey,
    updateThemeLabel,
    applyPresentation,
    toggleTheme,
    presentationSettings,
    settingsPage,
    hasUnsavedSettings,
    discardSettingsChanges,
    validateSettingsForm,
    persistSettings,
    settingsSaveStatus,
    settingsChanged,
    settingsDataMarkup,
    refreshSettingsData,
  };
  Object.assign(ctx.actions, actions);
  return actions;
}
