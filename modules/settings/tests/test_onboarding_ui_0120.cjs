/** Guided setup retains user choices, protects drafts and ignores disposed requests. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
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
  department: 'DHS',
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
async function fixture({ completed = false, connected = true } = {}) {
  const steps = completed ? { connections: {}, profile: {}, automation: {} } : {};
  const status = {
    required: !completed,
    completed,
    established_profile: false,
    step: 'connections',
    steps,
    profile: clone(profile),
    regions: ['North Carolina', 'South Carolina'],
    agencies: [
      { id: 'usss', short_name: 'USSS', name: profile.agency, department: 'DHS' },
      { id: 'fbi', short_name: 'FBI', name: 'Federal Bureau of Investigation', department: 'DOJ' },
      { id: 'custom', name: 'Other agency' },
    ],
  };
  const shadow = {
    connected,
    configured: connected,
    can_remember: true,
    subscriptions: connected ? ['US-NC'] : [],
    types: connected ? [{ type: 'scan_http_vulnerable', description: 'Vulnerable HTTP' }] : [],
    schedule: { config: clone(config), background: { installed: false } },
    selection_defaults: { subscription: 'US-NC', report_types: ['scan_http_vulnerable'] },
  };
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
  await mod.link(() => {
    throw new Error('Unexpected dependency');
  });
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
        if (url === '/api/nvd/credentials') return { configured: false };
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
    status,
    shadow,
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
    assert.equal(f.status.steps.connections.mode, 'manual');
    const name = { value: '' },
      department = { value: '' },
      region = { checked: true };
    f.nodes.set('#setup-agency', name);
    f.nodes.set('#setup-department', department);
    f.nodes.set('#region-nc', region);
    a.applyAgencyPreset({ id: 'setup-agency-preset', value: 'fbi' });
    assert.equal(name.value, 'Federal Bureau of Investigation');
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
