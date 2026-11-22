/** Settings hierarchy, persistence feedback, and preservation of in-flight edits. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { loadApplication } = require('../../../tests/frontend_harness.cjs');
const catalog = require('./support/profile_catalog.cjs');

let completed = false;
process.on('beforeExit', () => {
  if (!completed) {
    console.error('Settings suite ended before its assertions completed');
    process.exitCode = 1;
  }
});
(async () => {
  const nodes = new Map();
  const context = vm.createContext({
    console,
    window: {},
    confirm: () => true,
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
  ctx.actions.api = async (url) => (url === '/api/setup' ? catalog : { pending: null });
  let html = await ctx.actions.settingsPage();
  assert.match(html, /<h3>Shadowserver Eclipse<\/h3>/);
  assert(html.indexOf('Notification profile') < html.indexOf('Appearance, branding'));
  assert(html.indexOf('settings-save-button') < html.indexOf('Notification profile'));
  assert.match(html, /id="settings-save-status" role="status" aria-live="polite"/);
  assert.match(html, /<details class="panel settings-danger"><summary>Delete workspace data/);
  assert.match(html, /id="f-interval"[^>]+min="0" max="10" step="any"/);
  assert.match(html, /<\/form><aside id="settings-data-panel"/);
  assert.match(html, /<form id="settings-form"[^>]*novalidate/);
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

  // Shared native validation preserves legacy values until an explicit correction.
  const profileFields = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../static/profile_fields.js'), 'utf8'),
    { context },
  );
  await profileFields.link(() => {
    throw new Error('Profile fields must remain pure');
  });
  await profileFields.evaluate();
  const fields = profileFields.namespace;
  const legacy = {
    agency: 'Legacy agency',
    department: 'Legacy parent',
    display_timezone: 'Europe/London',
    regions: ['North Carolina', 'Unknown saved region'],
  };
  const legacyAgency = fields.agencyFields(
    ctx.actions.esc,
    legacy,
    catalog,
    'f-',
    'settings-agency-preset',
  );
  assert.match(legacyAgency, /<option value="" selected>Review saved agency/);
  assert.match(legacyAgency, /Legacy agency/);
  assert.match(legacyAgency, /Legacy parent/);
  assert.match(
    fields.agencyFields(
      ctx.actions.esc,
      { ...legacy, agency: catalog.agencies[0].name },
      catalog,
      'f-',
      'settings-agency-preset',
    ),
    /<option value="" selected>Review saved agency/,
  );
  assert.match(
    fields.timezoneField(ctx.actions.esc, legacy, catalog, 'display-timezone'),
    /<option value="" selected>Review saved timezone: Europe\/London/,
  );
  const legacyRegions = fields.jurisdictionFields(
    ctx.actions.esc,
    legacy,
    catalog,
    'settings-remove-unsupported-regions',
  );
  assert.match(legacyRegions, /type="hidden" name="regions" value="Unknown saved region"/);
  assert.match(legacyRegions, /Remove unsupported saved jurisdictions/);
  assert.throws(() => fields.requireProfileCatalog({}), /choices could not be loaded/);
  let unsupportedPresent = true;
  let regionMessage = '';
  let nameMessage = '';
  let regionFocused = false;
  const firstRegion = {
    checked: true,
    setCustomValidity: (message) => {
      regionMessage = message;
    },
    focus: () => {
      regionFocused = true;
    },
  };
  const requiredName = {
    value: '   ',
    setCustomValidity: (message) => {
      nameMessage = message;
    },
  };
  const validationForm = {
    querySelectorAll: (selector) =>
      selector === '[data-profile-trim-required]'
        ? [requiredName]
        : selector.includes('[name="regions"]')
          ? [firstRegion]
          : [],
    querySelector: () => (unsupportedPresent ? {} : null),
  };
  fields.validateProfileFields(validationForm);
  assert.match(regionMessage, /Remove unsupported saved jurisdictions/);
  assert.match(nameMessage, /Blank spaces/);
  fields.removeUnsupportedRegions({
    closest: (selector) =>
      selector === 'fieldset'
        ? { querySelector: () => firstRegion }
        : {
            remove: () => {
              unsupportedPresent = false;
            },
          },
  });
  assert(regionFocused);
  firstRegion.checked = false;
  fields.validateProfileFields(validationForm);
  assert.match(regionMessage, /at least one/);
  firstRegion.checked = true;
  requiredName.value = 'Synthetic valid name';
  fields.validateProfileFields(validationForm);
  assert.equal(regionMessage, '');
  assert.equal(nameMessage, '');

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

  // A header theme change must not send stale profile fields back to the server.
  const currentSettings = { ...settings, critical_only: false };
  let persistedSettings = { ...currentSettings, office: 'Newer saved office' };
  ctx.state.navigation.boot.settings = currentSettings;
  ctx.state.navigation.boot.token = 'synthetic-token';
  let themeRequest;
  ctx.actions.api = async (url, request) => {
    assert.equal(url, '/api/settings');
    themeRequest = request;
    persistedSettings = { ...persistedSettings, ...request.body };
    return persistedSettings;
  };
  await ctx.actions.toggleTheme();
  assert.equal(themeRequest.method, 'PUT');
  assert.equal(themeRequest.body.appearance, 'dark');
  assert.deepEqual(Object.keys(themeRequest.body), ['appearance']);
  assert.equal(persistedSettings.office, 'Newer saved office');
  assert.equal(currentSettings.appearance, undefined);
  ctx.state.navigation.boot.settings = settings;
  delete ctx.state.navigation.boot.token;

  const appearanceInputs = ['light', 'dark', 'system'].map((value) => ({
    value,
    checked: value === 'light',
  }));
  const form = {
    id: 'settings-form',
    dataset: { dirty: 'false', editRevision: '0' },
    setAttribute() {},
    removeAttribute() {},
    querySelectorAll: (selector) =>
      selector === 'input[name="appearance"]' ? appearanceInputs : [],
  };
  const status = { textContent: '', dataset: {} };
  nodes.set('#settings-form', form);
  nodes.set('#settings-save-status', status);
  nodes.set('#office-label', { textContent: '' });
  nodes.set('#settings-data-panel', { innerHTML: '' });
  nodes.set('#settings-save-button', { disabled: false });
  ctx.actions.applyPresentation = () => {};
  // Onboarding refreshes have their own suite; this test controls only the settings save.
  ctx.actions.afterSettingsProfileSave = async () => {};
  ctx.actions.toast = () => {};
  ctx.actions.settingsChanged(form);
  assert.equal(ctx.actions.hasUnsavedSettings(), true);
  assert.equal(status.textContent, 'Unsaved changes');

  const module = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../static/settings_events.js'), 'utf8'),
    { context },
  );
  await module.link(
    (specifier) =>
      new vm.SourceTextModule(
        fs.readFileSync(path.resolve(__dirname, '../static', specifier), 'utf8'),
        { context },
      ),
  );
  await module.evaluate();
  const handlers = module.namespace.createHandlers(ctx);

  // Correcting native custom errors updates validity immediately, without another save.
  let liveReasonError = '';
  let liveRegionError = '';
  const liveReason = {
    value: '   ',
    setCustomValidity: (value) => {
      liveReasonError = value;
    },
  };
  const liveRegion = {
    checked: false,
    setCustomValidity: (value) => {
      liveRegionError = value;
    },
  };
  const liveForm = {
    id: 'settings-form',
    dataset: { dirty: 'false', editRevision: '0' },
    querySelectorAll: (selector) =>
      selector === '[data-profile-trim-required]'
        ? [liveReason]
        : selector.includes('[name="regions"]')
          ? [liveRegion]
          : [],
    querySelector: () => null,
  };
  const liveTarget = { closest: (selector) => (selector === '#settings-form' ? liveForm : null) };
  nodes.set('#settings-form', liveForm);
  handlers.input({ target: liveTarget });
  assert.match(liveReasonError, /Blank spaces/);
  assert.match(liveRegionError, /at least one/);
  liveReason.value = 'Specific mission connection';
  handlers.input({ target: liveTarget });
  assert.equal(liveReasonError, '', 'Corrected rationale clears its prior custom error on input');
  liveRegion.checked = true;
  await handlers.change.find((handler) => handler.matches(liveTarget)).run(liveTarget);
  assert.equal(liveRegionError, '', 'Checked jurisdiction clears its prior custom error on change');
  assert.equal(liveForm.dataset.dirty, 'true');
  nodes.set('#settings-form', form);

  // The final visible theme must also be the final saved theme, even on slow requests.
  const originalApplyPresentation = ctx.actions.applyPresentation;
  const pendingThemes = [];
  ctx.state.navigation.boot.token = 'synthetic-token';
  context.document.documentElement.dataset.theme = 'light';
  ctx.actions.api = (url, request) =>
    new Promise((resolve) => {
      pendingThemes.push(() => {
        persistedSettings = { ...persistedSettings, ...request.body };
        resolve(persistedSettings);
      });
    });
  const darkSave = ctx.actions.toggleTheme();
  const lightSave = ctx.actions.toggleTheme();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(pendingThemes.length, 1, 'Only one settings write may be in flight');
  assert.equal(appearanceInputs.find((input) => input.checked).value, 'light');
  assert.equal(form.dataset.dirty, 'true', 'Theme controls retain unrelated unsaved edits');
  pendingThemes[0]();
  await darkSave;
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(pendingThemes.length, 2);
  pendingThemes[1]();
  await lightSave;
  assert.equal(persistedSettings.appearance, 'light');
  assert.equal(ctx.state.navigation.boot.settings.appearance, 'light');
  assert.equal(context.document.documentElement.dataset.theme, 'light');

  // A failed theme write does not poison the queue; its visible selection remains saveable.
  form.dataset.dirty = 'false';
  ctx.actions.api = async () => {
    throw new Error('Synthetic theme save failure');
  };
  await ctx.actions.toggleTheme();
  assert.equal(form.dataset.dirty, 'true');
  assert.equal(appearanceInputs.find((input) => input.checked).value, 'dark');
  ctx.actions.api = async (url, request) => ({ ...settings, ...request.body });
  await ctx.actions.toggleTheme();
  assert.equal(ctx.state.navigation.boot.settings.appearance, 'light');

  // Opening Settings during a header save must render the pending selection, including failures.
  nodes.delete('#settings-form');
  context.document.documentElement.dataset.theme = 'light';
  ctx.state.navigation.boot.settings = { ...settings, appearance: 'light' };
  let finishNavigatingTheme;
  ctx.actions.api = () =>
    new Promise((resolve) => {
      finishNavigatingTheme = resolve;
    });
  const navigatingTheme = ctx.actions.toggleTheme();
  await new Promise((resolve) => setImmediate(resolve));
  const arrivingAppearance = ctx.actions.presentationSettings(ctx.state.navigation.boot.settings);
  assert.match(arrivingAppearance, /name="appearance" value="dark" checked/);
  appearanceInputs.forEach((input) => {
    input.checked = input.value === 'dark';
  });
  form.dataset.dirty = 'false';
  nodes.set('#settings-form', form);
  finishNavigatingTheme({ ...settings, appearance: 'dark' });
  await navigatingTheme;
  assert.equal(appearanceInputs.find((input) => input.checked).value, 'dark');
  assert.equal(form.dataset.dirty, 'false');

  nodes.delete('#settings-form');
  context.document.documentElement.dataset.theme = 'light';
  ctx.state.navigation.boot.settings = { ...settings, appearance: 'light' };
  let rejectNavigatingTheme;
  ctx.actions.api = () =>
    new Promise((resolve, reject) => {
      rejectNavigatingTheme = reject;
    });
  const failingNavigatingTheme = ctx.actions.toggleTheme();
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(
    ctx.actions.presentationSettings(ctx.state.navigation.boot.settings),
    /name="appearance" value="dark" checked/,
  );
  nodes.set('#settings-form', form);
  form.dataset.dirty = 'false';
  rejectNavigatingTheme(new Error('Synthetic theme failure after navigation'));
  await failingNavigatingTheme;
  assert.equal(form.dataset.dirty, 'true', 'The current form must retain the unsaved theme');
  assert.equal(appearanceInputs.find((input) => input.checked).value, 'dark');

  // Failure feedback must not overwrite a newer appearance edit in that form.
  context.document.documentElement.dataset.theme = 'light';
  ctx.actions.api = () =>
    new Promise((resolve, reject) => {
      rejectNavigatingTheme = reject;
    });
  const changedWhilePending = ctx.actions.toggleTheme();
  await new Promise((resolve) => setImmediate(resolve));
  appearanceInputs.forEach((input) => {
    input.checked = input.value === 'system';
  });
  ctx.actions.settingsChanged(form);
  rejectNavigatingTheme(new Error('Synthetic theme failure with newer edit'));
  await changedWhilePending;
  assert.equal(appearanceInputs.find((input) => input.checked).value, 'system');
  delete ctx.state.navigation.boot.token;
  ctx.actions.applyPresentation = originalApplyPresentation;

  // Catalogs resolve before the form is shown, so late metadata cannot replace drafts.
  let resolveSetupStatus;
  ctx.actions.api = (url) =>
    url === '/api/setup'
      ? new Promise((resolve) => {
          resolveSetupStatus = resolve;
        })
      : Promise.resolve({ pending: null });
  let ready = false;
  const loadingSettings = ctx.actions.settingsPage().then((markup) => {
    ready = true;
    return markup;
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(ready, false);
  resolveSetupStatus(catalog);
  const controlled = await loadingSettings;
  assert.match(controlled, /<select id="settings-agency-preset" name="agency" required/);
  assert.doesNotMatch(controlled, /<input[^>]+name="agency"/);
  assert.match(controlled, /id="f-department"[^>]+readonly/);
  assert.match(controlled, /name="regions" value="North Carolina" checked/);
  assert.doesNotMatch(controlled, /<textarea[^>]+name="regions"/);
  assert.match(controlled, /<select id="display-timezone" name="display_timezone" required/);
  assert.match(controlled, /name="analyst_name"[^>]+maxlength="300" required/);
  assert.match(controlled, /name="email"[^>]+maxlength="254"/);
  ctx.actions.api = async (url) => {
    if (url === '/api/setup') throw new Error('Catalog temporarily unavailable');
    return { pending: null };
  };
  await assert.rejects(ctx.actions.settingsPage(), /Catalog temporarily unavailable/);

  const department = { value: 'Synthetic department' };
  const reason = { value: 'Previous mission rationale', required: true };
  const authority = { innerHTML: '' };
  const untouched = { value: 'Unrelated office draft' };
  form.querySelector = (selector) =>
    ({
      '[name="department"]': department,
      '[name="targeted_reason"]': reason,
      '#settings-agency-authority': authority,
      '[name="office"]': untouched,
    })[selector] || null;
  const preset = {
    id: 'settings-agency-preset',
    value: catalog.agencies[1].name,
    closest: () => form,
  };
  // Exercise the same first-matching event dispatch used by UI.
  const agencyHandler = handlers.change.find((handler) => handler.matches(preset));
  await agencyHandler.run(preset);
  assert.equal(department.value, catalog.agencies[1].department);
  assert.equal(reason.value, '', 'Changing agency requires a new purpose-specific explanation');
  assert.match(authority.innerHTML, /FBI synthetic citation/);
  assert.equal(untouched.value, 'Unrelated office draft');
  reason.required = false;
  reason.value = 'Old mission retained while critical';
  await agencyHandler.run(preset);
  assert.equal(
    reason.value,
    '',
    'Changing agency while critical must not reuse a stale rationale when targeted is restored',
  );
  assert.equal(form.dataset.dirty, 'true');

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
  const data = {
    has: () => false,
    getAll: (name) => (name === 'regions' ? ['North Carolina', 'South Carolina'] : []),
  };
  // Native constraints still apply inside collapsed groups, and every invalid group is opened.
  const nested = { open: false, parentElement: { closest: () => outer } };
  const outer = { open: false, parentElement: null };
  const separate = { open: false, parentElement: null };
  let validityReported = false;
  const invalidForm = {
    ...form,
    checkValidity: () => false,
    contains: () => true,
    querySelectorAll: (selector) =>
      selector === ':invalid' ? [{ closest: () => nested }, { closest: () => separate }] : [],
    reportValidity() {
      assert(nested.open && outer.open && separate.open);
      validityReported = true;
    },
  };
  nodes.set('#settings-form', invalidForm);
  ctx.actions.api = async () => {
    throw new Error('Invalid form must not make API requests');
  };
  await handlers.forms['settings-form'](invalidForm, values, data);
  assert.equal(validityReported, true);
  assert.equal(status.dataset.state, 'error');
  assert.match(status.textContent, /highlighted fields/);
  nodes.set('#settings-form', form);

  let saved;
  ctx.actions.api = async (url, request) => {
    saved = request.body;
    return { ...settings, ...saved };
  };
  await handlers.forms['settings-form'](form, values, data);
  assert.deepEqual(Array.from(saved.regions), ['North Carolina', 'South Carolina']);
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
  await new Promise((resolve) => setImmediate(resolve));
  resolveSave(settings);
  await saving;
  assert.equal(
    form.dataset.dirty,
    'true',
    'Edits made during saving must not become falsely clean',
  );
  assert.equal(status.textContent, 'Settings saved. New edits remain unsaved.');

  // Preference saves and theme shortcuts share ordering without posting stale profile fields.
  const pendingWrites = [];
  ctx.state.navigation.boot.token = 'synthetic-token';
  context.document.documentElement.dataset.theme = 'light';
  ctx.actions.api = (url, request) =>
    new Promise((resolve) => {
      pendingWrites.push({ request, resolve });
    });
  const profileSave = handlers.forms['settings-form'](
    form,
    { ...values, appearance: 'light' },
    data,
  );
  await new Promise((resolve) => setImmediate(resolve));
  const followingTheme = ctx.actions.toggleTheme();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(pendingWrites.length, 1);
  const updated = { ...settings, ...pendingWrites[0].request.body };
  pendingWrites[0].resolve(updated);
  await profileSave;
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(pendingWrites.length, 2);
  assert.deepEqual(Object.keys(pendingWrites[1].request.body), ['appearance']);
  pendingWrites[1].resolve({ ...updated, ...pendingWrites[1].request.body });
  await followingTheme;
  assert.equal(ctx.state.navigation.boot.settings.office, values.office);
  assert.equal(ctx.state.navigation.boot.settings.appearance, 'dark');
  delete ctx.state.navigation.boot.token;

  // API key drafts live only in the DOM and participate in navigation/update protection.
  form.dataset.dirty = 'false';
  const keyFeedback = { textContent: '' };
  const keyStatus = { textContent: '' };
  const keyForm = {
    id: 'nvd-key-form',
    dataset: { editRevision: '0' },
    reset() {
      keyInput.value = '';
    },
  };
  const keyInput = {
    value: 'synthetic-first-key',
    closest: (selector) => (selector === '#nvd-key-form' ? keyForm : null),
  };
  const keyPanel = { contains: (candidate) => candidate === keyForm, outerHTML: '' };
  nodes.set('#nvd-key-form', keyForm);
  nodes.set('#nvd-api-key', keyInput);
  nodes.set('#nvd-key-panel', keyPanel);
  nodes.set('#nvd-key-feedback', keyFeedback);
  nodes.set('#nvd-key-status', keyStatus);
  handlers.input({ target: keyInput });
  assert.equal(ctx.actions.hasUnsavedSettings(), true);
  assert.match(keyFeedback.textContent, /has not been saved/);
  let keyCalls = 0;
  ctx.actions.api = async () => {
    keyCalls++;
  };
  await ctx.actions.reviewSoftwareInstall();
  assert.equal(keyCalls, 0, 'Update installation must not proceed with an entered key');
  let resolveKeySave;
  ctx.actions.api = () =>
    new Promise((resolve) => {
      resolveKeySave = resolve;
    });
  const keySaving = ctx.actions.saveNvdKey(keyForm, { api_key: keyInput.value });
  keyInput.value = 'synthetic-new-key';
  handlers.input({ target: keyInput });
  resolveKeySave({ configured: true, source: 'session' });
  await keySaving;
  assert.equal(keyInput.value, 'synthetic-new-key');
  assert.equal(ctx.actions.hasUnsavedSettings(), true);
  assert.match(keyFeedback.textContent, /New key edits remain unsaved/);
  assert.match(keyStatus.textContent, /Key configured/);
  assert.equal(keyPanel.outerHTML, '', 'Completion must not replace newer input');
  assert.equal(JSON.stringify(ctx.state).includes('synthetic-new-key'), false);

  ctx.actions.api = async () => {
    throw new Error('Synthetic key save failure');
  };
  await assert.rejects(
    ctx.actions.saveNvdKey(keyForm, { api_key: keyInput.value }),
    /key save failure/,
  );
  assert.equal(keyInput.value, 'synthetic-new-key');
  assert.match(keyFeedback.textContent, /Your entered key remains here/);
  handlers.actions['clear-nvd-key']();
  assert.equal(keyInput.value, '');
  assert.equal(ctx.actions.hasUnsavedSettings(), false);
  keyInput.value = 'synthetic-discarded-key';
  ctx.actions.settingsChanged(form);
  ctx.actions.discardSettingsChanges();
  assert.equal(keyInput.value, '');
  assert.equal(form.dataset.dirty, 'false');

  keyInput.value = 'synthetic-final-key';
  ctx.actions.api = async () => ({ configured: true, source: 'session' });
  await ctx.actions.saveNvdKey(keyForm, { api_key: keyInput.value });
  assert.equal(keyInput.value, '');
  assert.match(keyPanel.outerHTML, /Key configured/);
  assert.doesNotMatch(keyPanel.outerHTML, /synthetic-final-key/);
  for (const id of [
    '#nvd-key-form',
    '#nvd-api-key',
    '#nvd-key-panel',
    '#nvd-key-feedback',
    '#nvd-key-status',
  ])
    nodes.delete(id);
  ctx.actions.settingsChanged(form);

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
  completed = true;
  console.log(
    'Settings hierarchy, numeric bounds, save feedback, settings edit preservation, and safe data controls passed.',
  );
})().catch((error) => {
  completed = true;
  console.error(error);
  process.exitCode = 1;
});
