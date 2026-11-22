/** Release notes, unsaved-work protection and safe update retries. */
const assert = require('node:assert/strict');

async function checkStatusOrdering(install) {
  const originalSet = global.setTimeout;
  const originalClear = global.clearTimeout;
  const timers = new Map();
  let nextTimer = 0;
  global.setTimeout = (fn) => {
    timers.set(++nextTimer, fn);
    return nextTimer;
  };
  global.clearTimeout = (id) => timers.delete(id);
  const base = { current_version: '0.12.0', can_install: true };
  const ctx = {
    state: { navigation: {} },
    actions: { esc: String, stamp: String, $: () => null, modal: () => {} },
  };
  install(ctx);
  const a = ctx.actions;
  const runPoll = () => {
    const [id, fn] = timers.entries().next().value;
    timers.delete(id);
    return fn();
  };
  try {
    let finishOld;
    a.api = (_url, options) =>
      options?.method === 'POST'
        ? Promise.resolve({ ...base, phase: 'checking', message: 'Checking new operation' })
        : new Promise((resolve) => {
            finishOld = resolve;
          });
    const oldRead = a.loadSoftwareStatus();
    await a.softwareOperation('check');
    finishOld({ ...base, phase: 'idle', message: 'Old idle snapshot' });
    await oldRead;
    assert.match(a.softwareUpdatesMarkup(), /Checking new operation/);
    assert.equal(timers.size, 1, 'The new operation must keep polling');

    // A status read requested during a POST waits for its mutation to finish.
    let finishCheck;
    let statusReads = 0;
    a.api = (_url, options) => {
      if (options?.method === 'POST')
        return new Promise((resolve) => {
          finishCheck = resolve;
        });
      statusReads++;
      return Promise.resolve({ ...base, phase: 'current', message: 'Fresh completed check' });
    };
    const checking = a.softwareOperation('check');
    const duringCheck = a.loadSoftwareStatus();
    await Promise.resolve();
    assert.equal(statusReads, 0);
    finishCheck({ ...base, phase: 'checking', message: 'Checking' });
    await Promise.all([checking, duringCheck]);
    assert.equal(statusReads, 1);
    assert.match(a.softwareUpdatesMarkup(), /Fresh completed check/);
    assert.equal(timers.size, 0);

    a.api = async () => ({ ...base, phase: 'checking', message: 'Previous lifecycle' });
    await a.loadSoftwareStatus();
    let rejectOld;
    a.api = () =>
      new Promise((_resolve, reject) => {
        rejectOld = reject;
      });
    const oldPoll = runPoll();
    a.disposeSoftwareUpdates();
    a.resumeSoftwareUpdates();
    a.api = async () => ({ ...base, phase: 'current', message: 'New lifecycle current' });
    await a.loadSoftwareStatus();
    rejectOld(new Error('Old poll aborted'));
    await oldPoll;
    assert.match(a.softwareUpdatesMarkup(), /New lifecycle current/);
    assert.doesNotMatch(a.softwareUpdatesMarkup(), /Could not refresh/);

    let rejectOldOperation;
    a.api = () =>
      new Promise((_resolve, reject) => {
        rejectOldOperation = reject;
      });
    const oldOperation = a.softwareOperation('check');
    a.disposeSoftwareUpdates();
    a.resumeSoftwareUpdates();
    a.api = async () => ({ ...base, phase: 'current', message: 'Resumed after old operation' });
    await a.loadSoftwareStatus();
    rejectOldOperation(new Error('Superseded operation aborted'));
    await oldOperation;
    assert.match(a.softwareUpdatesMarkup(), /Resumed after old operation/);

    // A current polling failure still provides actionable feedback.
    a.api = async () => ({ ...base, phase: 'checking', message: 'Current check' });
    await a.loadSoftwareStatus();
    a.api = async () => {
      throw new Error('Synthetic connection failure');
    };
    await runPoll();
    assert.match(a.softwareUpdatesMarkup(), /Could not refresh update status/);
  } finally {
    a.disposeSoftwareUpdates();
    global.setTimeout = originalSet;
    global.clearTimeout = originalClear;
  }
}

(async () => {
  const { install, createHandlers } = await import('../static/software_updates.js');
  await checkStatusOrdering(install);
  const calls = [];
  const modals = [];
  const toasts = [];
  let modalOpen = false;
  let modalAllowed = true;
  let unsavedSetup = false;
  let value = {
    phase: 'unpublished',
    message: 'No compatible release is published.',
    current_version: '0.12.0',
    can_install: true,
  };
  let notice = {
    version: '0.12.0',
    title: 'Setup <script>unsafe</script>',
    highlights: ['A <b>plain text</b> change.'],
    should_show: true,
  };
  const ctx = {
    state: { navigation: {} },
    actions: {
      esc: (text) =>
        String(text).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;'),
      stamp: (text) => text,
      $: (selector) => (selector === '#modal' ? { open: modalOpen } : null),
      hasUnsavedSetup: () => unsavedSetup,
      toast: (text) => toasts.push(text),
      modal: (title, body) => {
        if (!modalAllowed) return false;
        modals.push({ title, body });
      },
      closeModal: () => {
        modalOpen = false;
      },
      api: async (url, options) => {
        calls.push({ url, options });
        if (url === '/api/software/whats-new') return notice;
        if (url === '/api/software/whats-new/seen') {
          notice = { ...notice, should_show: false };
          return {};
        }
        return value;
      },
    },
  };
  install(ctx);
  const handlers = createHandlers(ctx).actions;
  await ctx.actions.loadSoftwareStatus();
  let html = ctx.actions.softwareUpdatesMarkup();
  assert.match(html, /No compatible release is published/);
  assert.doesNotMatch(html, /up to date|data-action="software-download"/);

  modalOpen = true;
  assert.equal(await ctx.actions.maybeShowSoftwareWhatsNew(), false);
  assert.equal(calls.filter((call) => call.url.endsWith('/seen')).length, 0);
  modalOpen = false;
  modalAllowed = false;
  assert.equal(await ctx.actions.maybeShowSoftwareWhatsNew(), false);
  assert.equal(calls.filter((call) => call.url.endsWith('/seen')).length, 0);
  modalAllowed = true;
  assert.equal(await ctx.actions.maybeShowSoftwareWhatsNew(), true);
  assert.match(modals.at(-1).body, /&lt;script>/);
  assert.doesNotMatch(modals.at(-1).body, /<script>|<b>/);
  assert.equal(await ctx.actions.maybeShowSoftwareWhatsNew(), false);
  assert.equal(await handlers['software-whats-new'](), true);
  assert.equal(calls.filter((call) => call.url.endsWith('/seen')).length, 2);

  value = {
    ...value,
    phase: 'ready',
    message: 'The verified installer is ready.',
    candidate: {
      version: '0.12.1',
      channel: 'candidate',
      installer_sha256: 'a'.repeat(64),
      title: 'Next release',
      highlights: ['A fix.'],
    },
  };
  unsavedSetup = true;
  await handlers['software-install-review']();
  await handlers['software-install']();
  assert.equal(toasts.length, 2);
  assert.equal(calls.filter((call) => call.url.endsWith('/install')).length, 0);
  unsavedSetup = false;
  await handlers['software-install-review']();
  assert.equal(modals.at(-1).title, 'Install software update');
  assert.match(modals.at(-1).body, /0.12.1/);
  value = {
    ...value,
    candidate: { ...value.candidate, version: '0.12.2', installer_sha256: 'b'.repeat(64) },
  };
  await ctx.actions.loadSoftwareStatus();
  value = { ...value, phase: 'installing' };
  await handlers['software-install']();
  assert.equal(calls.filter((call) => call.url.endsWith('/install')).length, 1);
  assert.deepEqual(calls.find((call) => call.url.endsWith('/install')).options.body, {
    version: '0.12.1',
    channel: 'candidate',
    installer_sha256: 'a'.repeat(64),
  });
  assert.equal(modals.at(-1).title, 'Installing software update');
  await handlers['software-install']();
  assert.equal(calls.filter((call) => call.url.endsWith('/install')).length, 1);
  assert.match(toasts.at(-1), /Review the available update/);
  value = { ...value, phase: 'ready', message: 'The installer could not start. Try again.' };
  await ctx.actions.loadSoftwareStatus();
  assert.equal(modals.at(-1).title, 'Update could not start');
  assert.match(ctx.actions.softwareUpdatesMarkup(), /data-action="software-install-review"/);
  ctx.actions.disposeSoftwareUpdates();
  assert.equal(await ctx.actions.maybeShowSoftwareWhatsNew(), false);
  ctx.actions.resumeSoftwareUpdates();
  const initialApi = ctx.actions.api;
  let finishOldRequest;
  ctx.actions.api = () =>
    new Promise((resolve) => {
      finishOldRequest = resolve;
    });
  const oldNotice = ctx.actions.showSoftwareWhatsNew();
  const modalCount = modals.length;
  ctx.actions.disposeSoftwareUpdates();
  ctx.actions.resumeSoftwareUpdates();
  finishOldRequest({ ...notice, should_show: true });
  assert.equal(await oldNotice, false);
  assert.equal(modals.length, modalCount);
  ctx.actions.api = initialApi;
  assert.equal(await ctx.actions.showSoftwareWhatsNew(), true);
  ctx.actions.disposeSoftwareUpdates();
  console.log('Software update controls, unsaved setup and release notes passed.');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
