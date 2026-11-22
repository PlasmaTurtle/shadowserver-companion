/** Guided setup retains user choices, protects drafts and ignores disposed requests. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const catalog = require('./support/profile_catalog.cjs');
const clone = (value) => JSON.parse(JSON.stringify(value));
class Data {
  constructor(form = {}) {
    this.entries = form.entries || [];
  }
  getAll(key) {
    return this.entries.filter(([name]) => name === key).map(([, value]) => value);
  }
  has(key) {
    return this.entries.some(([name]) => name === key);
  }
  [Symbol.iterator]() {
    return this.entries[Symbol.iterator]();
  }
}
const profile = {
  analyst_name: 'Synthetic Analyst',
  analyst_title: '',
  agency: 'United States Secret Service',
  department: catalog.agencies[0].department,
  office: 'Charlotte',
  email: '',
  regions: ['North Carolina'],
  display_timezone: 'America/New_York',
};
const config = {
  enabled: false,
  shadowserver: true,
  reference: true,
  hour: 6,
  minute: 0,
  interval_hours: 4,
  lookback_days: 7,
  subscription: 'US-NC',
  report_types: ['scan_http_vulnerable'],
};
async function fixture({
  completed = false,
  connected = true,
  configured = connected,
  nvdConfigured = false,
  connectionMode = null,
  establishedProfile = false,
} = {}) {
  const steps = completed ? { connections: {}, profile: {}, automation: {} } : {};
  if (connectionMode) steps.connections = { mode: connectionMode };
  const status = {
    required: !completed && !establishedProfile,
    completed,
    established_profile: establishedProfile,
    step: 'connections',
    steps,
    profile: clone(profile),
    ...clone(catalog),
  };
  const shadow = {
    connected,
    configured,
    can_remember: true,
    subscriptions: connected ? ['US-NC'] : [],
    types: connected ? [{ type: 'scan_http_vulnerable', description: 'Vulnerable HTTP' }] : [],
    schedule: { config: clone(config), background: { installed: false } },
    selection_defaults: { subscription: 'US-NC', report_types: ['scan_http_vulnerable'] },
  };
  const nvd = { configured: nvdConfigured, source: 'session', remember_supported: true };
  const passwords = [],
    controls = [{ disabled: false }, { disabled: true }],
    nodes = new Map(),
    renders = [],
    calls = [];
  const error = { hidden: true, textContent: '', focus() {} };
  const body = {
    innerHTML: '',
    querySelector: () => (body.innerHTML.includes('setup-wizard') ? {} : null),
  };
  const modal = {
    open: false,
    classList: { add() {}, remove() {} },
    close() {
      this.open = false;
    },
  };
  nodes.set('#setup-error', error);
  nodes.set('#modal-body', body);
  nodes.set('#modal', modal);
  let confirmResult = true,
    routes = 0;
  const context = vm.createContext({
    console,
    setTimeout,
    clearTimeout,
    FormData: Data,
    confirm: () => confirmResult,
  });
  const mod = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../static/onboarding.js'), 'utf8'),
    { context },
  );
  await mod.link(
    (specifier) =>
      new vm.SourceTextModule(
        fs.readFileSync(path.resolve(__dirname, '../static', specifier), 'utf8'),
        { context },
      ),
  );
  await mod.evaluate();
  const ctx = {
    state: {
      navigation: { boot: { settings: clone(profile) } },
      apiData: { selection: { subscription: 'US-NC', date: '2026-11-01' } },
    },
    actions: {
      esc: (x) =>
        String(x).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;'),
      $: (id) => nodes.get(id),
      $$: (selector) => (selector.includes('password') ? passwords : controls),
      modal(title, html) {
        renders.push(html);
        body.innerHTML = html;
        modal.open = true;
      },
      closeModal() {
        if (ctx.actions.confirmDiscardSetup()) {
          modal.open = false;
          ctx.actions.setupModalClosed();
        }
      },
      route: async () => {
        routes++;
      },
      toast() {},
      applyPresentation() {},
      settingsChanged() {},
      api: async (url, options = {}) => {
        calls.push({ url, options });
        if (url === '/api/setup/progress') {
          status.steps[options.body.step] = { mode: options.body.mode };
          return clone(status);
        }
        if (url === '/api/setup/profile') {
          status.profile = clone(options.body);
          status.steps.profile = {};
          return { setup: clone(status), settings: clone(status.profile) };
        }
        if (url === '/api/setup/complete') {
          status.completed = true;
          status.required = false;
          return clone(status);
        }
        if (url === '/api/setup') return clone(status);
        if (url === '/api/shadowserver/status') return clone(shadow);
        if (url === '/api/shadowserver/credentials') {
          shadow.configured = true;
          return clone(shadow);
        }
        if (url === '/api/shadowserver/connection') {
          shadow.connected = true;
          shadow.job = { status: 'completed' };
          return clone(shadow.job);
        }
        if (url === '/api/nvd/credentials') {
          if (options.method === 'PUT') nvd.configured = true;
          return clone(nvd);
        }
        if (url === '/api/schedule') {
          shadow.schedule.config = clone(options.body);
          return clone(shadow.schedule);
        }
        if (url === '/api/schedule/background') {
          shadow.schedule.background.installed = options.body.enabled;
          return clone(shadow.schedule);
        }
        throw new Error('Unexpected API ' + url);
      },
    },
  };
  mod.namespace.install(ctx);
  return {
    ctx,
    handlers: mod.namespace.createHandlers(ctx),
    status,
    shadow,
    nvd,
    passwords,
    controls,
    nodes,
    renders,
    calls,
    error,
    modal,
    body,
    setConfirm: (value) => {
      confirmResult = value;
    },
    routes: () => routes,
  };
}
(async () => {
  {
    const f = await fixture({ completed: true });
    await f.ctx.actions.openSetup('profile');
    let reasonError = '',
      regionError = '';
    const reason = {
      value: '   ',
      setCustomValidity: (value) => {
        reasonError = value;
      },
    };
    const region = {
      checked: false,
      setCustomValidity: (value) => {
        regionError = value;
      },
    };
    const form = {
      querySelectorAll: (selector) =>
        selector === '[data-profile-trim-required]'
          ? [reason]
          : selector.includes('[name="regions"]')
            ? [region]
            : [],
      querySelector: () => null,
    };
    f.nodes.set('#setup-profile-form', form);
    const target = { closest: (selector) => (selector === '#setup-wizard' ? form : null) };
    const calls = f.calls.length,
      renders = f.renders.length;
    f.handlers.input({ target });
    assert.match(reasonError, /Blank spaces/);
    assert.match(regionError, /at least one/);
    reason.value = 'Specific mission connection';
    f.handlers.input({ target });
    assert.equal(reasonError, '', 'Corrected setup rationale clears its custom error immediately');
    region.checked = true;
    await f.handlers.change.find((handler) => handler.matches(target)).run(target);
    assert.equal(
      regionError,
      '',
      'Corrected setup jurisdiction clears its custom error immediately',
    );
    assert.equal(f.calls.length, calls);
    assert.equal(f.renders.length, renders);
    assert.equal(f.ctx.actions.hasUnsavedSetup(), true);
  }

  {
    const f = await fixture({ completed: true });
    f.status.profile.outreach_mode = 'targeted';
    f.status.profile.targeted_reason = 'Previously reviewed mission rationale';
    await f.ctx.actions.openSetup('profile');
    assert.match(f.renders.at(-1), /id="setup-agency-authority"/);
    assert.match(f.renders.at(-1), /USSS synthetic citation/);
    assert.match(f.renders.at(-1), /name="targeted_reason"[^>]+required/);
    assert.doesNotMatch(f.renders.at(-1), /name="outreach_mode"/);
    const reason = { value: f.status.profile.targeted_reason, required: true };
    const department = { value: profile.department };
    const authority = { innerHTML: '' };
    const form = {
      querySelector: (key) =>
        ({
          '[name="department"]': department,
          '[name="targeted_reason"]': reason,
          '#setup-agency-authority': authority,
        })[key],
    };
    f.ctx.actions.applyAgencyPreset({ value: catalog.agencies[1].name, closest: () => form });
    assert.equal(reason.value, '');
    assert.match(authority.innerHTML, /FBI synthetic citation/);
    let reported = false;
    const invalid = {
      checkValidity: () => false,
      reportValidity: () => {
        reported = true;
      },
    };
    const before = f.calls.length;
    await f.ctx.actions.saveSetupProfile(invalid, profile, new Data());
    assert(reported);
    assert.equal(f.calls.length, before, 'Invalid profile sends no writes');
    const nextProfile = {
      ...profile,
      agency: catalog.agencies[1].name,
      department: catalog.agencies[1].department,
      targeted_reason: 'Specific synthetic mission connection',
    };
    await f.ctx.actions.saveSetupProfile(
      {},
      nextProfile,
      new Data({ entries: [['regions', 'North Carolina']] }),
    );
    const saved = f.calls.find((call) => call.url === '/api/setup/profile').options.body;
    assert.equal(saved.targeted_reason, nextProfile.targeted_reason);
    assert(!Object.hasOwn(saved, 'outreach_mode'));
  }
  {
    const f = await fixture({ completed: true });
    Object.assign(f.status.profile, {
      agency: 'Legacy unknown agency',
      department: 'Legacy department',
      display_timezone: 'Europe/London',
      regions: ['North Carolina', 'Legacy region'],
    });
    await f.ctx.actions.openSetup('profile');
    const values = {
      ...f.status.profile,
      agency: '',
      display_timezone: '',
      office: 'Retained new office',
    };
    f.nodes.set('#setup-profile-form', {
      entries: [
        ...Object.entries(values).filter(([key]) => key !== 'regions'),
        ...values.regions.map((region) => ['regions', region]),
      ],
    });
    f.ctx.actions.setupMarkDirty();
    await f.ctx.actions.changeSetupStep('connections');
    await f.ctx.actions.changeSetupStep('profile');
    const html = f.renders.at(-1);
    assert.match(html, /Legacy unknown agency/);
    assert.match(html, /Legacy department/);
    assert.match(html, /Review saved timezone: Europe\/London/);
    assert.match(html, /type="hidden" name="regions" value="Legacy region"/);
    assert.match(html, /Remove unsupported saved jurisdictions/);
    assert.match(html, /Retained new office/);
  }

  for (const [configured, nvdConfigured] of [
    [false, false],
    [true, false],
    [false, true],
    [true, true],
  ]) {
    const f = await fixture({ connected: false, configured, nvdConfigured });
    const a = f.ctx.actions;
    await a.openSetup();
    const html = f.renders.at(-1);
    assert.match(html, /class="setup-connections"/);
    assert.match(html, /data-action="setup-connections-next"/);
    const shadowMarkup = html.split('<h3>Shadowserver</h3>')[1].split('</section>')[0];
    const nvdMarkup = html.split('<h3>NVD</h3>')[1].split('</section>')[0];
    if (configured) {
      assert.doesNotMatch(shadowMarkup, /id="setup-shadow-(?:form|key|secret)"/);
      assert.match(shadowMarkup, /complete|key detected/i);
      assert.match(shadowMarkup, /data-action="setup-connect"/);
      assert.match(shadowMarkup, /Test connection/);
      assert.doesNotMatch(
        shadowMarkup,
        />Connected</,
        'Detected credentials are not a live connection',
      );
    } else {
      assert.match(shadowMarkup, /id="setup-shadow-form"/);
      assert.match(shadowMarkup, /id="setup-shadow-key"[^>]*type="password"/);
      assert.match(shadowMarkup, /id="setup-shadow-secret"[^>]*type="password"/);
    }
    if (nvdConfigured) {
      assert.doesNotMatch(nvdMarkup, /id="setup-nvd-(?:form|key)"/);
      assert.doesNotMatch(nvdMarkup, /request-an-api-key/);
      assert.match(nvdMarkup, /complete|key detected/i);
    } else {
      assert.match(nvdMarkup, /id="setup-nvd-form"/);
      assert.match(nvdMarkup, /request-an-api-key/);
    }
    const automaticWrites = f.calls.filter(
      ({ options }) => options.method && options.method !== 'GET',
    );
    if (configured && nvdConfigured) {
      assert.equal(automaticWrites.length, 1);
      assert.equal(automaticWrites[0].url, '/api/setup/progress');
      assert.equal(automaticWrites[0].options.body.step, 'connections');
      assert.equal(automaticWrites[0].options.body.mode, 'configured');
      assert.equal(f.status.steps.connections.mode, 'configured');
      assert.match(html, /<li[^>]*class="done"[^>]*><button[^>]*data-step="connections"/);
      assert.match(html, /aria-label="API connections, completed"/);
    } else {
      assert.deepEqual(automaticWrites, []);
      assert.equal(f.status.steps.connections, undefined);
    }
    assert.equal(f.calls.filter(({ url }) => url === '/api/shadowserver/connection').length, 0);
    assert.equal(f.shadow.connected, false);
    assert.equal(a.hasUnsavedSetup(), false);
    await a.setupConnectionsNext();
    assert.match(f.renders.at(-1), /id="setup-profile-form"/);
    assert.equal(
      f.status.steps.connections.mode,
      configured || nvdConfigured ? 'configured' : 'manual',
    );
    assert.equal(f.calls.filter(({ url }) => url === '/api/shadowserver/connection').length, 0);
    a.disposeSetup();
  }
  {
    const f = await fixture({
      connected: false,
      configured: true,
      nvdConfigured: true,
      establishedProfile: true,
    });
    const a = f.ctx.actions;
    await a.openSetup();
    assert.doesNotMatch(f.renders.at(-1), /id="setup-(?:nvd|shadow)-form"/);
    assert.match(f.renders.at(-1), /Credential setup is complete/);
    assert.equal(f.status.required, false);
    assert.equal(f.status.steps.connections, undefined);
    assert.equal(
      f.calls.filter(({ options }) => options.method && options.method !== 'GET').length,
      0,
      'Reviewing detected keys must not start mandatory setup for an established workspace',
    );
    await a.setupConnectionsNext();
    assert.equal(f.status.steps.connections.mode, 'configured');
    assert.equal(f.calls.filter(({ url }) => url === '/api/setup/progress').length, 1);
    assert.match(f.renders.at(-1), /id="setup-profile-form"/);
    a.disposeSetup();
  }
  {
    const f = await fixture({
      completed: true,
      connected: false,
      configured: true,
      nvdConfigured: true,
      connectionMode: 'manual',
    });
    await f.ctx.actions.openSetup('connections');
    assert.equal(
      f.status.steps.connections.mode,
      'manual',
      'Detection preserves an existing manual choice',
    );
    assert.equal(f.calls.filter(({ url }) => url === '/api/setup/progress').length, 0);
    assert.doesNotMatch(f.renders.at(-1), /id="setup-(?:nvd|shadow)-form"/);
    f.ctx.actions.disposeSetup();
  }
  {
    const f = await fixture({ connected: false, configured: true });
    const a = f.ctx.actions;
    await a.openSetup();
    await a.saveSetupNvd({ reset() {} }, { api_key: 'synthetic-nvd-key' });
    const html = f.renders.at(-1);
    assert.doesNotMatch(html, /id="setup-(?:nvd|shadow)-form"/);
    assert.doesNotMatch(html, /request-an-api-key|synthetic-nvd-key/);
    assert.match(html, /complete|key detected/i);
    assert.equal(f.calls.filter(({ url }) => url === '/api/shadowserver/connection').length, 0);
    await a.setupConnectionsNext();
    assert.equal(f.status.steps.connections.mode, 'configured');
    assert.match(f.renders.at(-1), /id="setup-profile-form"/);
    a.disposeSetup();
  }
  {
    const f = await fixture({ connected: false });
    const a = f.ctx.actions;
    await a.openSetup();
    const enteredShadowKey = { value: 'synthetic-unsubmitted-shadow-key' };
    const enteredShadowSecret = { value: 'synthetic-unsubmitted-shadow-secret' };
    f.passwords.push(enteredShadowKey, enteredShadowSecret);
    const previousRenders = f.renders.length;
    const nvdCard = { innerHTML: '' };
    await a.saveSetupNvd(
      { reset() {}, closest: (selector) => (selector === 'section' ? nvdCard : null) },
      { api_key: 'synthetic-saved-nvd-key' },
    );
    assert.match(nvdCard.innerHTML, /Complete/);
    assert.doesNotMatch(nvdCard.innerHTML, /id="setup-nvd-form"|request-an-api-key/);
    assert.equal(f.renders.length, previousRenders, 'Do not replace the other service draft');
    assert.equal(enteredShadowKey.value, 'synthetic-unsubmitted-shadow-key');
    assert.equal(enteredShadowSecret.value, 'synthetic-unsubmitted-shadow-secret');
    assert.equal(a.hasUnsavedSetup(), true);
    assert.equal(f.shadow.configured, false);
    assert.equal(f.calls.filter(({ url }) => url === '/api/shadowserver/credentials').length, 0);
    assert.equal(f.calls.filter(({ url }) => url === '/api/shadowserver/connection').length, 0);
    assert.equal(f.status.steps.connections, undefined);
    a.disposeSetup();
  }
  {
    const f = await fixture({ connected: false, nvdConfigured: true });
    const a = f.ctx.actions;
    await a.openSetup();
    await a.saveSetupShadow(
      { reset() {} },
      { api_key: 'synthetic-shadow-key', secret: 'synthetic-shadow-secret' },
    );
    const html = f.renders.at(-1);
    assert.doesNotMatch(html, /id="setup-(?:nvd|shadow)-form"/);
    assert.doesNotMatch(html, /synthetic-shadow-key|synthetic-shadow-secret/);
    assert.match(html, /complete|key detected/i);
    assert.equal(
      f.calls.filter(({ url }) => url === '/api/shadowserver/connection').length,
      1,
      'Save & connect remains an explicit connection action',
    );
    await a.setupConnectionsNext();
    assert.equal(f.status.steps.connections.mode, 'configured');
    assert.match(f.renders.at(-1), /id="setup-profile-form"/);
    a.disposeSetup();
  }
  {
    const f = await fixture();
    const a = f.ctx.actions;
    await a.maybeStartSetup();
    assert.match(f.renders.at(-1), /type="password" autocomplete="new-password"/);
    await a.changeSetupStep('profile');
    assert.match(f.error.textContent, /Continue from API connections/);
    f.passwords.push({ value: 'unsaved-secret' });
    assert.equal(a.hasUnsavedSetup(), true);
    f.setConfirm(false);
    assert.equal(a.confirmDiscardSetup(), false);
    assert(f.modal.open);
    f.passwords[0].value = '';
    f.setConfirm(true);
    await a.setupConnectionsNext(true);
    assert.match(f.renders.at(-1), /setup-profile-form/);
    assert.match(f.renders.at(-1), /<select id="setup-agency-preset" name="agency" required/);
    assert.doesNotMatch(
      f.renders.at(-1),
      /name="(?:other_regions|agency)"[^>]*type="text"|id="setup-other-regions"/,
    );
    assert.match(f.renders.at(-1), /id="setup-department"[^>]+readonly/);
    assert.match(
      f.renders.at(-1),
      /<select id="setup-display_timezone" name="display_timezone" required/,
    );
    assert.doesNotMatch(f.renders.at(-1), /setup-targeted_reason/);
    assert.equal(f.status.steps.connections.mode, 'manual');
    const department = { value: '' },
      region = { checked: true };
    f.nodes.set('#setup-department', department);
    f.nodes.set('#region-nc', region);
    const agencyForm = {
      querySelector: (selector) => (selector === '[name="department"]' ? department : null),
    };
    a.applyAgencyPreset({
      id: 'setup-agency-preset',
      value: catalog.agencies[1].name,
      closest: () => agencyForm,
    });
    assert.equal(department.value, catalog.agencies[1].department);
    assert.equal(region.checked, true);
    await a.saveSetupProfile({}, profile, new Data({ entries: [['regions', 'North Carolina']] }));
    assert.match(f.renders.at(-1), /setup-schedule-form/);
    assert.match(f.renders.at(-1), /Enable retrieval schedule/);
    assert.match(
      f.renders.at(-1),
      /Turning this retrieval schedule off does not disable those updates/,
    );
    assert.doesNotMatch(
      f.renders.at(-1),
      /keep this workspace manual|run imports and reference updates manually/,
    );
    assert.doesNotMatch(f.renders.at(-1), /option value="US-SC"/);
    assert.equal(f.ctx.state.navigation.boot.settings.analyst_title, '');
    a.disposeSetup();
    assert.equal(f.modal.open, false);
    assert.equal(f.body.innerHTML, '');
  }
  {
    const f = await fixture({ completed: true, connected: false });
    const a = f.ctx.actions;
    await a.openSetup('automation');
    assert.match(f.renders.at(-1), /Saved selection: US-NC/);
    assert.match(f.renders.at(-1), /name="subscription" disabled/);
    const values = { time: '09:15', interval_hours: '6', lookback_days: '3' };
    await a.saveSetupSchedule(
      {},
      values,
      new Data({
        entries: [
          ['shadowserver', 'on'],
          ['reference', 'on'],
        ],
      }),
    );
    const saved = f.calls.find((x) => x.url === '/api/schedule').options.body;
    assert.equal(saved.subscription, 'US-NC');
    assert.deepEqual(saved.report_types, ['scan_http_vulnerable']);
    assert.equal(saved.hour, 9);
    assert.equal(saved.enabled, false);
    assert(!Object.hasOwn(saved, 'background'));
  }
  {
    const f = await fixture({ completed: true });
    const a = f.ctx.actions;
    await a.openSetup('automation');
    f.nodes.set('#setup-schedule-form', {
      entries: [
        ['time', '08:30'],
        ['interval_hours', '2'],
        ['lookback_days', '5'],
        ['subscription', 'US-NC'],
        ['report_types', 'scan_http_vulnerable'],
        ['enabled', 'on'],
        ['shadowserver', 'on'],
        ['background', 'on'],
      ],
    });
    a.setupMarkDirty();
    await a.changeSetupStep('profile');
    await a.saveSetupProfile(
      {},
      { ...profile, office: 'New office' },
      new Data({ entries: [['regions', 'North Carolina']] }),
    );
    assert.match(f.renders.at(-1), /value="08:30"/);
    assert.match(f.renders.at(-1), /name="background" type="checkbox" checked/);
    assert.match(f.renders.at(-1), /name="interval_hours"[^>]*value="2"/);
    const selection = f.ctx.state.apiData.selection;
    await a.afterSettingsProfileSave();
    assert.equal(f.ctx.state.apiData.selection, selection);
    a.confirmDiscardSetup();
    a.setupModalClosed();
    await Promise.resolve();
    assert.equal(
      f.routes(),
      1,
      'Closing after saved identity refreshes the underlying Settings form',
    );
  }
  {
    const f = await fixture();
    const a = f.ctx.actions;
    let resolve;
    const original = a.api;
    a.api = (url, options) =>
      url === '/api/setup'
        ? new Promise((r) => {
            resolve = r;
          })
        : original(url, options);
    const pending = a.openSetup();
    a.disposeSetup();
    resolve(clone(f.status));
    await assert.rejects(pending, /no longer open/);
    assert.equal(f.renders.length, 0);
    a.resumeSetup();
    a.api = original;
    await a.openSetup();
    assert.equal(f.renders.length, 1);
    a.disposeSetup();
  }
  {
    const f = await fixture({ completed: true });
    const a = f.ctx.actions;
    await a.openSetup('profile');
    const editedProfile = { ...profile, analyst_name: 'New Synthetic Analyst' };
    const profileForm = {
      entries: [
        ...Object.entries(editedProfile).filter(([name]) => name !== 'regions'),
        ['regions', 'North Carolina'],
      ],
    };
    f.nodes.set('#setup-profile-form', profileForm);
    a.setupMarkDirty();
    await a.changeSetupStep('automation');
    const scheduleForm = {
      entries: [
        ['time', '09:15'],
        ['interval_hours', '6'],
        ['lookback_days', '3'],
        ['subscription', 'US-NC'],
        ['report_types', 'scan_http_vulnerable'],
        ['shadowserver', 'on'],
        ['reference', 'on'],
      ],
    };
    f.nodes.set('#setup-schedule-form', scheduleForm);
    a.setupMarkDirty();
    const scheduleData = new Data(scheduleForm);
    const scheduleValues = Object.fromEntries(scheduleData);
    const previousCalls = f.calls.length;
    const previousRender = f.renders.at(-1);
    assert.equal(await a.saveSetupSchedule(scheduleForm, scheduleValues, scheduleData), false);
    assert.equal(
      f.calls.length,
      previousCalls,
      'No schedule or setup writes before profile review',
    );
    assert.equal(f.renders.at(-1), previousRender, 'Keep the edited schedule form in place');
    assert.match(f.error.textContent, /unsaved identity or jurisdiction changes/);
    assert.match(f.error.textContent, /Save profile & continue/);
    assert.equal(f.status.profile.analyst_name, profile.analyst_name);
    assert.equal(a.hasUnsavedSetup(), true);
    assert.equal(f.modal.open, true);
    assert.equal(f.controls[0].disabled, false);

    await a.changeSetupStep('profile');
    assert.match(f.renders.at(-1), /value="New Synthetic Analyst"/);
    const originalApi = a.api;
    a.api = async (url, options) => {
      if (url === '/api/setup/profile') throw new Error('Synthetic profile save failure');
      return originalApi(url, options);
    };
    assert.equal(
      await a.saveSetupProfile(profileForm, editedProfile, new Data(profileForm)),
      false,
    );
    assert.match(f.error.textContent, /Synthetic profile save failure/);
    assert.equal(a.hasUnsavedSetup(), true);
    assert.equal(f.modal.open, true);
    assert.equal(f.status.profile.analyst_name, profile.analyst_name);

    await a.changeSetupStep('automation');
    assert.match(f.renders.at(-1), /value="09:15"/);
    assert.match(f.renders.at(-1), /name="interval_hours"[^>]*value="6"/);
    assert.equal(await a.saveSetupSchedule(scheduleForm, scheduleValues, scheduleData), false);
    await a.changeSetupStep('profile');
    assert.match(f.renders.at(-1), /value="New Synthetic Analyst"/);
    a.api = originalApi;
    await a.saveSetupProfile(profileForm, editedProfile, new Data(profileForm));
    assert.equal(f.status.profile.analyst_name, editedProfile.analyst_name);
    assert.match(f.renders.at(-1), /value="09:15"/);
    await a.saveSetupSchedule(scheduleForm, scheduleValues, scheduleData);
    assert.equal(f.shadow.schedule.config.hour, 9);
    assert.equal(f.shadow.schedule.config.minute, 15);
    assert.equal(f.shadow.schedule.config.interval_hours, 6);
    assert.equal(a.hasUnsavedSetup(), false);
    assert.equal(f.modal.open, false);
    a.disposeSetup();
  }
  {
    const f = await fixture({ completed: true });
    const a = f.ctx.actions;
    await a.openSetup();
    let reject;
    const original = a.api;
    a.api = (url, options) =>
      url === '/api/setup/profile'
        ? new Promise((_, r) => {
            reject = r;
          })
        : original(url, options);
    const pending = a.saveSetupProfile(
      {},
      profile,
      new Data({ entries: [['regions', 'North Carolina']] }),
    );
    assert(f.controls.every((node) => node.disabled));
    assert.equal(a.confirmDiscardSetup(), false);
    reject(new Error('Synthetic save failure'));
    await pending;
    assert.match(f.error.textContent, /Synthetic save failure/);
    assert.equal(f.controls[0].disabled, false);
    assert.equal(f.controls[1].disabled, true);
    a.disposeSetup();
  }
  console.log('Guided setup choices, dirty guards, secrets, scope and lifecycle checks passed.');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
