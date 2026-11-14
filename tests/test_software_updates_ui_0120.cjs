/** Release notes, unsaved-work protection and safe update retries. */
const assert = require('node:assert/strict');

(async () => {
  const { install, createHandlers } = await import('../static/modules/software_updates.js');
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
    candidate: { version: '0.12.1', title: 'Next release', highlights: ['A fix.'] },
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
  value = { ...value, phase: 'installing' };
  await handlers['software-install']();
  assert.equal(calls.filter((call) => call.url.endsWith('/install')).length, 1);
  assert.equal(modals.at(-1).title, 'Installing software update');
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
