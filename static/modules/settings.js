import { install as installWorkspaceHealth } from './workspace_health.js';
import { install as installCatalog } from './cve_catalog.js';

/** Settings feature. Dependencies and mutable state are provided by the application context. */
export function install(ctx) {
  installCatalog(ctx);
  installWorkspaceHealth(ctx);
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
    if (ctx.state.navigation.boot?.token)
      ctx.actions
        .api('/api/settings', {
          method: 'PUT',
          body: { ...ctx.state.navigation.boot.settings, appearance: theme },
        })
        .then((settings) => {
          ctx.state.navigation.boot.settings = settings;
        })
        .catch((error) =>
          ctx.actions.toast(
            'Appearance changed in this browser; settings could not be saved: ' + error.message,
            true,
          ),
        );
  }

  function presentationSettings(s) {
    const appearance =
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
      )}</div></fieldset><div class="field"><label for="display-timezone">Display timezone</label><input id="display-timezone" name="display_timezone" value="${ctx.actions.esc(s.display_timezone || 'America/New_York')}" placeholder="America/New_York"><small>Event times retain their original UTC values; timestamps display the selected zone.</small></div><div class="policy-card"><span class="tlp-mark">TLP:AMBER</span><p>Share on a need-to-know basis within the receiving organization and its clients. Source-specific additional restrictions still apply. Reports include the marking in the header and footer of every page.</p></div><p class="section-note">Blue: confirmed association or completed workflow. Red: adverse finding. Gray: pending or unknown. Confirmation does not mean remediation.</p></div></section>`;
  }

  async function resourcesPage(params = new URLSearchParams()) {
    if (params.get('item')) ctx.state.resources.resourceId = params.get('item');
    ctx.state.resources.resources = await ctx.actions.api('/api/explainers');
    ctx.state.navigation.boot.explainers = ctx.state.resources.resources;
    if (!ctx.state.resources.resources.some((r) => r.id === ctx.state.resources.resourceId))
      ctx.state.resources.resourceId = ctx.state.resources.resources[0]?.id;
    return (
      ctx.actions.heading(
        'Library',
        '',
        `<button class="button primary" data-action="new-block">${ctx.actions.icon('plus')}New explainer</button>`,
      ) +
      (await ctx.actions.catalogSection(params)) +
      `<h2 class="catalog-explainers-heading">Explainers</h2><div class="resource-layout"><section class="panel resource-list">${ctx.state.resources.resources.map((b) => `<button class="resource-item ${b.id === ctx.state.resources.resourceId ? 'active' : ''}" data-resource="${b.id}">${ctx.actions.icon('book')}<span><strong>${ctx.actions.esc(b.title)}</strong><small>Revision ${b.revision}</small></span>${ctx.actions.icon('arrow')}</button>`).join('')}</section><section id="resource-editor">${ctx.actions.resourceForm()}</section></div>`
    );
  }

  function resourceCitationFields(sources, metadata = []) {
    const details = new Map(metadata.map((item) => [item.url, item]));
    const urls = [
      ...new Set(
        String(sources || '')
          .split('\n')
          .map((x) => x.trim())
          .filter(Boolean),
      ),
    ];
    return (
      urls
        .map((url, index) => {
          const row = details.get(url) || {};
          return `<fieldset class="form-grid" data-citation-row data-citation-url="${ctx.actions.esc(url)}"><legend>${ctx.actions.esc(url)}</legend>${[
            ['publisher', 'Publisher'],
            ['title', 'Source title'],
            ['retrieved_at', 'Retrieval date'],
            ['date_published', 'Published date'],
            ['date_updated', 'Updated date'],
          ]
            .map(
              ([key, label]) =>
                `<div class="field ${key === 'title' ? 'full' : ''}"><label for="citation-${index}-${key}">${label}</label><input id="citation-${index}-${key}" data-citation-key="${key}" value="${ctx.actions.esc(row[key] || '')}" ${key.includes('date') || key === 'retrieved_at' ? 'placeholder="YYYY-MM-DD or ISO timestamp"' : ''}></div>`,
            )
            .join('')}</fieldset>`;
        })
        .join('') || '<p class="section-note">Add source URLs above to record citation details.</p>'
    );
  }

  function readResourceCitations(form) {
    return [...form.querySelectorAll('[data-citation-row]')].map((row) => ({
      url: row.dataset.citationUrl,
      ...Object.fromEntries(
        [...row.querySelectorAll('[data-citation-key]')].map((input) => [
          input.dataset.citationKey,
          input.value.trim(),
        ]),
      ),
    }));
  }

  function resourceForm() {
    const b = ctx.state.resources.resources.find(
      (r) => r.id === ctx.state.resources.resourceId,
    ) || { title: '', body: '', sources: '' };
    const sourceLinks = String(b.sources || '')
      .split('\n')
      .map((url) => url.trim())
      .filter(Boolean)
      .map((url) =>
        /^https?:\/\//i.test(url)
          ? `<li><a href="${ctx.actions.esc(url)}" target="_blank" rel="noopener noreferrer">${ctx.actions.esc(url)}</a></li>`
          : `<li>${ctx.actions.esc(url)}</li>`,
      )
      .join('');
    return `${b.id ? `<article class="dm-library-sheet"><span class="dm-overline">Explainer · Revision ${ctx.actions.num(b.revision)}</span><h2>${ctx.actions.esc(b.title)}</h2><div class="library-copy">${ctx.actions.esc(b.body)}</div>${sourceLinks ? `<footer><span class="dm-overline">Sources</span><ol>${sourceLinks}</ol></footer>` : ''}</article>` : ''}<details class="dm-library-edit" ${b.id ? '' : 'open'}><summary>${b.id ? 'Edit explanation' : 'New explanation'}</summary><p class="section-note">Certified reports retain their original wording.</p><form id="resource-form" class="form-grid">${ctx.actions.field('Title', 'title', b.title, { full: true, draft: false, required: true })}${ctx.actions.field('Explanation', 'body', b.body, { area: true, rows: 10, full: true, draft: false })}${ctx.actions.field('Sources · one URL per line', 'sources', b.sources, { area: true, rows: 4, full: true, draft: false })}<details class="full"><summary>Source citations · publisher, title and dates</summary><p class="section-note">Record dates from the source and your actual retrieval. Leave unavailable details blank. Adding or changing a URL updates these fields when you leave the URL box.</p><div id="resource-citations">${ctx.actions.resourceCitationFields(b.sources, b.source_metadata || [])}</div></details><div class="full"><button class="button primary" type="submit">${ctx.actions.icon('save')}Save explainer</button></div></form></details>`;
  }

  function hasUnsavedSettings() {
    return ctx.actions.$('#settings-form')?.dataset.dirty === 'true';
  }

  function hasUnsavedLibrary() {
    return ctx.actions.$('#resource-form')?.dataset.dirty === 'true';
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

  function nvdKeyMarkup(status = {}) {
    return `<section class="panel" id="nvd-key-panel"><div class="panel-head"><h2>API connections</h2></div><div class="panel-body"><h3>NVD</h3><p id="nvd-key-status" role="status">${status.configured ? `Key configured · ${ctx.actions.esc(status.source === 'windows' ? 'Windows Credential Manager' : status.source === 'environment' ? 'Environment' : 'This session')}` : 'Add your NVD API key for the full CVE catalog and daily updates.'}</p><form id="nvd-key-form"><div class="field"><label for="nvd-api-key">NVD API key</label><input id="nvd-api-key" name="api_key" type="password" autocomplete="off" spellcheck="false" maxlength="128" required placeholder="${status.configured ? 'Replace saved key' : 'API key'}"></div>${status.remember_supported ? '<label class="checkbox"><input name="remember" type="checkbox" checked><span>Remember on this Windows account</span></label>' : '<p class="help">Key stays in this session. NVD_API_KEY is also supported.</p>'}<div class="actions"><button class="button" type="submit">Save NVD key</button>${status.configured && status.source !== 'environment' ? '<button class="button" type="button" data-action="remove-nvd-key">Remove key</button>' : ''}</div></form><p><a href="https://nvd.nist.gov/developers/request-an-api-key" target="_blank" rel="noopener noreferrer">Get an NVD API key</a> · <a href="#library">Open CVE catalog</a></p><h3>Shadowserver</h3><p role="status">${shadowConnection ? (shadowConnection.connected ? 'Connected' : shadowConnection.configured ? 'Key configured · ready to connect' : 'Add your API key and secret to retrieve subscribed reports.') : 'Check your report connection in Shadowserver Data.'}</p><a href="#data?tab=api" class="button">${shadowConnection?.connected ? 'Open reports API' : 'Connect reports API'}</a></div></section>`;
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
    const status = await ctx.actions.api('/api/nvd/credentials', {
      method: 'PUT',
      body: { api_key: values.api_key, remember: values.remember === 'on' },
    });
    form.reset();
    const panel = ctx.actions.$('#nvd-key-panel');
    if (panel && panel.contains(form)) panel.outerHTML = nvdKeyMarkup(status);
    ctx.actions.toast('NVD key saved. Open Library to download the catalog.');
  }

  async function removeNvdKey() {
    const status = await ctx.actions.api('/api/nvd/credentials', { method: 'DELETE' });
    const panel = ctx.actions.$('#nvd-key-panel');
    if (panel) panel.outerHTML = nvdKeyMarkup(status);
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
    return `<section class="panel" id="settings-section-automation"><div class="panel-head"><h2>Retrieval schedule</h2></div><div class="panel-body settings-automation-summary"><div><strong>${config.enabled ? 'Enabled' : 'Off'}</strong><p>${config.enabled ? `Every ${ctx.actions.esc(config.interval_hours)} hours · ${ctx.actions.esc(schedule.timezone || 'computer local time')}` : 'This retrieval schedule is off. Library daily reference updates are managed separately.'}</p>${schedule.next_run_at ? `<small>Next check: ${ctx.actions.esc(new Date(schedule.next_run_at).toLocaleString())}</small>` : ''}${schedule.scope_error ? `<p class="notice warn">${ctx.actions.esc(schedule.scope_error)}</p>` : ''}<p class="help">${schedule.background?.installed ? 'Windows also checks while the app is closed and you are signed in.' : 'Closed-app checks can be enabled on the installed Windows app.'}</p></div><button type="button" class="button" data-action="open-setup-automation">Configure</button><div id="settings-library-automation" class="full">${libraryAutomationMarkup()}</div></div></section>`;
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
    const dataStatus = await ctx.actions.api('/api/data/status');
    const profile = `<section class="panel" id="settings-section-profile"><div class="panel-head"><div><h2>Notification profile</h2><p>Identity used for new notifications. Earlier certified reports keep their saved sender.</p></div></div><div class="panel-body form-grid"><div class="field settings-agency-preset"><label for="settings-agency-preset">Agency preset</label><select id="settings-agency-preset"><option value="custom">Current agency / custom organization</option></select><small>A preset fills the agency and department. Your jurisdiction is selected separately.</small></div>${ctx.actions.field('Analyst name', 'analyst_name', s.analyst_name, { draft: false })}${ctx.actions.field('Title (optional)', 'analyst_title', s.analyst_title, { draft: false, help: 'Leave blank to show your name without a title.' })}${ctx.actions.field('Office / location', 'office', s.office, { draft: false, help: 'Your office or work location; not a jurisdiction filter.' })}${ctx.actions.field('Contact email', 'email', s.email, { draft: false, type: 'email' })}${ctx.actions.field('Agency', 'agency', s.agency, { draft: false, full: true })}${ctx.actions.field('Department', 'department', s.department, { draft: false, full: true })}</div></section>`;
    const jurisdiction = `<section class="panel" id="settings-section-jurisdiction"><div class="panel-head"><div><h2>Jurisdiction</h2><p>Scope for new intake, report API choices and workspace views.</p></div></div><div class="panel-body form-grid">${ctx.actions.field('Jurisdictions · one region per line', 'regions', s.regions.join('\n'), { draft: false, area: true, rows: 3, full: true, help: 'Use report region names, such as North Carolina. Out-of-jurisdiction API choices are excluded. Changing scope does not delete existing records.' })}<p class="help full">Use guided setup for a state checklist. Review the retrieval schedule after changing jurisdiction; a previously saved subscription may no longer be available.</p></div></section>`;
    const intake = `<section class="panel" id="settings-section-reports"><div class="panel-head"><div><h2>Review &amp; import defaults</h2><p>Changes apply to new imports and reports you choose to re-evaluate.</p></div></div><div class="panel-body form-grid"><div class="field"><label for="outreach-mode">Outreach scope</label><select id="outreach-mode" name="outreach_mode">${ctx.actions.optionList(
      [
        ['critical', 'Critical or known exploited'],
        ['targeted', 'Targeted outreach'],
      ],
      s.outreach_mode || 'critical',
    )}</select></div>${ctx.actions.field('Targeted outreach reason', 'targeted_reason', s.targeted_reason || '', { draft: false, full: true, required: s.outreach_mode === 'targeted', help: 'Record why this finding or report type is appropriate for targeted review.' })}<details class="full settings-help"><summary>Agency priorities</summary><div class="form-grid">${ctx.actions.field('Priority cities', 'accretion_priority_cities', (s.accretion_priority_cities || []).join('\n'), { draft: false, area: true, rows: 2, help: 'Optional · one city per line or separated by commas.' })}${ctx.actions.field('Priority products', 'accretion_priority_products', (s.accretion_priority_products || []).join('\n'), { draft: false, area: true, rows: 2, help: 'Optional · one product per line or separated by commas.' })}<p class="help full">Matching cities and products increase urgency. Intake requirements still apply.</p></div></details><label class="checkbox full"><input type="checkbox" name="watch_inbox" ${s.watch_inbox ? 'checked' : ''}><span>Check the inbox folder automatically</span></label><details class="full settings-help"><summary>Import formats and lookup options</summary><div class="form-grid">${reportProfileSetting(s)}${ctx.actions.field('Worksheet name', 'sheet', s.sheet, { draft: false, full: true, help: 'Leave blank to use the first worksheet. CSV reports do not use this setting.' })}${settingsNumber('timeout', 'Lookup timeout', s.timeout ?? 10, 1, 60, 'any')}${settingsNumber('retries', 'Network retries', s.retries ?? 1, 0, 3, 1)}${settingsNumber('interval', 'Minimum lookup interval', s.interval ?? 0.25, 0, 10, 'any')}</div></details><details class="full settings-help"><summary>How rows qualify</summary><p class="help">Default outreach admits supported critical findings or locally verified KEVs. Required values: tag, hostname, IP and an in-jurisdiction region. Version requirements depend on the report type: HTTP findings without a CVE and all end-of-life findings require a software version. Supported service and incident reports may omit it. Original rows are preserved. Private IPs are retained and flagged. One exact registration or DNS match qualifies a hostname group; partial registration-name matches require review.</p></details></div></section>`;
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
      `<nav class="settings-section-nav" aria-label="Settings sections">${sections.map(([id, label]) => `<button type="button" data-action="settings-section" data-section="${id}">${label}</button>`).join('')}</nav><div class="settings-layout"><form id="settings-form" class="settings-main" data-dirty="false" data-edit-revision="0"><div class="settings-savebar"><div><strong>Workspace preferences</strong><p id="settings-save-status" role="status" aria-live="polite" data-state="${dataStatus.pending ? 'paused' : 'saved'}">${dataStatus.pending ? 'Restart or cancel the pending data change before saving settings.' : 'No unsaved changes'}</p></div><button id="settings-save-button" class="button primary" type="submit" ${dataStatus.pending ? 'disabled' : ''}>${ctx.actions.icon('save')}Save settings</button></div>${profile}${jurisdiction}${intake}<details class="settings-appearance" id="settings-section-display"><summary>Appearance, branding &amp; display</summary>${ctx.actions.presentationSettings(s)}</details></form><aside id="settings-data-panel" aria-label="Connections, retrieval schedule, software and workspace recovery">${nvdKeyMarkup()}${settingsAutomationMarkup()}${ctx.actions.softwareUpdatesMarkup?.() || ''}<div id="settings-data-controls">${ctx.actions.settingsDataMarkup(dataStatus)}</div></aside></div>`
    );
  }
  Object.assign(ctx.actions, {
    nvdKeyMarkup,
    settingsAutomationMarkup,
    libraryAutomationMarkup,
    loadSettingsLibraryAutomation,
    scrollSettingsSection,
    loadNvdKeyStatus,
    saveNvdKey,
    removeNvdKey,
    updateThemeLabel,
    applyPresentation,
    toggleTheme,
    presentationSettings,
    resourcesPage,
    resourceCitationFields,
    readResourceCitations,
    resourceForm,
    settingsPage,
    hasUnsavedSettings,
    hasUnsavedLibrary,
    settingsSaveStatus,
    settingsChanged,
    settingsDataMarkup,
    refreshSettingsData,
  });
}
