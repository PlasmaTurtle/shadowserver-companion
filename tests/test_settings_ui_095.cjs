/** Settings hierarchy, persistence feedback, and preservation of in-flight edits. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');

(async () => {
  const nodes = new Map();
  const context = vm.createContext({
    console,
    window: {},
    document: {
      documentElement: { dataset: {} },
      querySelector: (selector) => nodes.get(selector) || null,
    },
  });
  const { application: ctx } = await loadApplication(context, { attach: false });
  const settings = {
    regions: ['North Carolina'],
    office: 'Synthetic office',
    interval: 0.25,
    timeout: 10,
    retries: 1,
  };
  ctx.state.navigation.boot = {
    settings,
    workspace: '/synthetic/data',
    notification_profiles: [
      {
        id: 'scan_http_vulnerable',
        name: 'Vulnerable HTTP',
        notification_mode: 'critical_or_targeted',
      },
      { id: 'scan_rdp', name: 'Accessible RDP', notification_mode: 'targeted' },
    ],
  };
  ctx.actions.api = async () => ({ pending: null });
  let html = await ctx.actions.settingsPage();
  assert.match(html, /<h3>Shadowserver Eclipse<\/h3>/);
  assert(html.indexOf('Notification profile') < html.indexOf('Appearance, branding'));
  assert(html.indexOf('settings-save-button') < html.indexOf('Notification profile'));
  assert.match(html, /id="settings-save-status" role="status" aria-live="polite"/);
  assert.match(html, /<details class="panel settings-danger"><summary>Delete workspace data/);
  assert.match(html, /id="f-interval"[^>]+min="0" max="10" step="any"/);
  assert.match(html, /<\/form><aside id="settings-data-panel"/);
  assert.doesNotMatch(html, /Prioritize \.com/);
  assert.doesNotMatch(html, /name="(?:com_only|exclude_numeric_roots)"/);
  assert.match(html, /Title \(optional\)/);
  assert.match(html, /Leave blank to show your name without a title\./);
  const titleInput = html.match(/<input[^>]*name="analyst_title"[^>]*>/)?.[0];
  assert(titleInput, 'Sender title input is present');
  assert.doesNotMatch(titleInput, /\brequired\b/);
  assert.match(html, /Version requirements depend on the report type/);
  assert.match(html, /name="accretion_priority_cities"/);
  assert.match(html, /name="accretion_priority_products"/);
  assert.match(
    html,
    /HTTP findings without a CVE and all end-of-life findings require a software version/,
  );
  assert.match(html, /Supported service and incident reports may omit it/);
  assert.match(html, /<select id="f-report_type" name="report_type"/);
  assert.match(html, /<option value="scan_http_vulnerable"[^>]*>Vulnerable HTTP<\/option>/);
  assert.match(html, /<option value="scan_rdp"[^>]*>Accessible RDP - targeted review<\/option>/);
  assert.match(html, /manual choice applies to every new import until you return to Auto/);
  settings.report_type = 'previous_custom_profile';
  html = await ctx.actions.settingsPage();
  assert.match(
    html,
    /<option value="previous_custom_profile" selected>Saved profile: previous_custom_profile<\/option>/,
  );
  delete settings.report_type;

  // Release status belongs in About; legacy edition identifiers are not branding.
  for (const [channel, label] of [
    ['stable', 'Release'],
    ['candidate', 'Release candidate'],
    ['unstable', 'Development release'],
  ]) {
    ctx.state.navigation.boot.release = {
      app_name: 'Shadowserver Eclipse <Review>',
      version: '0.9.96',
      channel,
      edition: 'chaos',
    };
    const about = await ctx.actions.settingsPage();
    assert(about.includes('Shadowserver Eclipse &lt;Review&gt;'));
    assert(about.includes(`Version 0.9.96 · ${label}`));
    assert.doesNotMatch(about, /workstation acceptance pending|Home validation|Chaos/);
  }
  delete ctx.state.navigation.boot.release;

  // Theme persistence must send the current settings: the API requires regions,
  // and appearance changes must not reset the user's other saved preferences.
  const currentSettings = { ...settings, critical_only: false };
  ctx.state.navigation.boot.settings = currentSettings;
  ctx.state.navigation.boot.token = 'synthetic-token';
  let themeRequest;
  ctx.actions.api = async (url, request) => {
    assert.equal(url, '/api/settings');
    themeRequest = request;
    return request.body;
  };
  ctx.actions.toggleTheme();
  await Promise.resolve();
  assert.equal(themeRequest.method, 'PUT');
  assert.equal(themeRequest.body.appearance, 'dark');
  for (const [key, value] of Object.entries(currentSettings))
    assert.equal(themeRequest.body[key], value);
  assert.equal(currentSettings.appearance, undefined);
  ctx.state.navigation.boot.settings = settings;
  delete ctx.state.navigation.boot.token;

  const form = {
    id: 'settings-form',
    dataset: { dirty: 'false', editRevision: '0' },
    setAttribute() {},
    removeAttribute() {},
  };
  const status = { textContent: '', dataset: {} };
  nodes.set('#settings-form', form);
  nodes.set('#settings-save-status', status);
  nodes.set('#office-label', { textContent: '' });
  nodes.set('#settings-data-panel', { innerHTML: '' });
  nodes.set('#settings-save-button', { disabled: false });
  ctx.actions.applyPresentation = () => {};
  ctx.actions.toast = () => {};
  ctx.actions.settingsChanged(form);
  assert.equal(ctx.actions.hasUnsavedSettings(), true);
  assert.equal(status.textContent, 'Unsaved changes');

  const module = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../static/modules/settings_events.js'), 'utf8'),
    { context },
  );
  await module.link(() => {
    throw Error('Unexpected import');
  });
  await module.evaluate();
  const handlers = module.namespace.createHandlers(ctx);
  const values = {
    regions: 'North Carolina\nSouth Carolina',
    timeout: '10.25',
    retries: '1',
    interval: '0.03',
    outreach_mode: 'critical',
    office: 'New synthetic office',
    analyst_title: '',
    accretion_priority_cities: 'Charlotte, Burnsville\n Asheville ',
    accretion_priority_products: 'Exchange\nPHP, Roundcube',
  };
  const data = { has: () => false };
  let saved;
  ctx.actions.api = async (url, request) => {
    saved = request.body;
    return { ...settings, ...saved };
  };
  await handlers.forms['settings-form'](form, values, data);
  assert.equal(saved.interval, 0.03);
  assert.equal(saved.timeout, 10.25);
  assert.equal(saved.com_only, undefined);
  assert.equal(saved.exclude_numeric_roots, undefined);
  assert.equal(saved.watch_inbox, false);
  assert.equal(saved.analyst_title, '');
  assert.equal(
    JSON.stringify(saved.accretion_priority_cities),
    JSON.stringify(['Charlotte', 'Burnsville', 'Asheville']),
  );
  assert.equal(
    JSON.stringify(saved.accretion_priority_products),
    JSON.stringify(['Exchange', 'PHP', 'Roundcube']),
  );
  assert.equal(form.dataset.dirty, 'false');
  assert.equal(status.textContent, 'Settings saved.');

  ctx.actions.settingsChanged(form);
  ctx.actions.api = async () => {
    throw Error('Synthetic save failure');
  };
  await assert.rejects(
    handlers.forms['settings-form'](form, values, data),
    /Synthetic save failure/,
  );
  assert.equal(form.dataset.dirty, 'true');
  assert.equal(status.dataset.state, 'error');
  assert.match(status.textContent, /Your edits remain here/);

  let resolveSave;
  ctx.actions.api = () =>
    new Promise((resolve) => {
      resolveSave = resolve;
    });
  const saving = handlers.forms['settings-form'](form, values, data);
  ctx.actions.settingsChanged(form);
  resolveSave(settings);
  await saving;
  assert.equal(
    form.dataset.dirty,
    'true',
    'Edits made during saving must not become falsely clean',
  );
  assert.equal(status.textContent, 'Settings saved. New edits remain unsaved.');

  const originalForm = nodes.get('#settings-form');
  ctx.actions.api = async () => ({ pending: null, backup: {} });
  await ctx.actions.refreshSettingsData();
  assert.equal(nodes.get('#settings-form'), originalForm);
  assert.equal(form.dataset.dirty, 'true');
  assert.match(nodes.get('#settings-data-panel').innerHTML, /Backup &amp; recovery/);
  ctx.actions.api = async () => ({ pending: 'import' });
  await ctx.actions.refreshSettingsData();
  assert.equal(nodes.get('#settings-save-button').disabled, true);
  assert.match(status.textContent, /pending data change/);
  assert.doesNotMatch(nodes.get('#settings-data-panel').innerHTML, /data-action="delete-data"/);

  let modal;
  ctx.actions.modal = (_title, markup) => {
    modal = markup;
  };
  await handlers.actions['import-data']();
  assert.match(modal, /<details class="full settings-help"><summary>Recovery option/);
  assert.match(modal, /pattern="IMPORT"/);
  await handlers.actions['delete-data']();
  assert.match(modal, /class="button danger"/);
  assert.match(modal, /pattern="DELETE"/);
  const resource = { dataset: { dirty: 'false', editRevision: '0' } };
  nodes.set('#resource-form', resource);
  const resourceInput = {
    target: { closest: (selector) => (selector === '#resource-form' ? resource : null) },
  };
  handlers.input(resourceInput);
  assert.equal(ctx.actions.hasUnsavedLibrary(), true);
  let resourceResolve;
  ctx.actions.api = () =>
    new Promise((resolve) => {
      resourceResolve = resolve;
    });
  ctx.actions.readResourceCitations = () => [];
  let routeCalls = 0;
  ctx.actions.route = async () => {
    routeCalls++;
  };
  const resourceSaving = handlers.forms['resource-form'](resource, {
    title: 'Original',
    body: 'Original wording',
  });
  handlers.input(resourceInput);
  resourceResolve({ id: 'saved-explainer' });
  await resourceSaving;
  assert.equal(ctx.state.resources.resourceId, 'saved-explainer');
  assert.equal(
    ctx.actions.hasUnsavedLibrary(),
    true,
    'New wording remains dirty after an older save response',
  );
  assert.equal(routeCalls, 0, 'Saving does not replace newer edits');
  ctx.actions.api = async () => ({ id: 'saved-explainer' });
  await handlers.forms['resource-form'](resource, { title: 'Updated', body: 'Updated wording' });
  assert.equal(ctx.actions.hasUnsavedLibrary(), false);
  assert.equal(routeCalls, 1);
  console.log(
    'Settings hierarchy, numeric bounds, save feedback, settings and Library edit preservation, and safe data controls passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
