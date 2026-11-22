const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { loadApplication } = require('../../../tests/frontend_harness.cjs');
(async () => {
  const context = vm.createContext({
    console,
    window: {},
    document: { documentElement: { dataset: {} } },
  });
  const { application: ctx } = await loadApplication(context, { attach: false });
  ctx.state.navigation.boot = { settings: { regions: [] }, workspace: '/synthetic/data' };
  ctx.actions.api = async () => ({ pending: null });
  let markup = await ctx.actions.settingsPage();
  assert.match(markup, /Export data/);
  assert.match(markup, /Import data/);
  assert.match(markup, /Delete all data/);
  assert.doesNotMatch(markup, /replace its data folder/);
  ctx.actions.api = async () => ({ pending: 'import' });
  markup = await ctx.actions.settingsPage();
  assert.match(markup, /Close and reopen the app to apply\./);
  assert.match(markup, /data-action="cancel-data-change"/);
  assert.doesNotMatch(markup, /data-action="delete-data"/);
  const module = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../../settings/static/settings_events.js'), 'utf8'),
    { context },
  );
  await module.link(
    (specifier) =>
      new vm.SourceTextModule(
        fs.readFileSync(path.resolve(__dirname, '../../settings/static', specifier), 'utf8'),
        { context },
      ),
  );
  await module.evaluate();
  const handlers = module.namespace.createHandlers(ctx);
  let calls = [];
  ctx.actions.api = async (url, options) => {
    calls.push({ url, options });
    return {};
  };
  ctx.actions.modal = (title, html) => {
    markup = html;
  };
  ctx.actions.closeModal = () => {};
  ctx.actions.toast = () => {};
  ctx.actions.route = async () => {};
  let refreshes = 0;
  ctx.actions.refreshSettingsData = async () => {
    refreshes++;
  };
  await handlers.actions['import-data']();
  assert.match(markup, /pattern="IMPORT"/);
  assert.match(markup, /type="file"/);
  await handlers.actions['delete-data']();
  assert.match(markup, /pattern="DELETE"/);
  assert.equal(calls.length, 0, 'Opening a confirmation never changes data');
  await handlers.forms['delete-data-form']({}, { confirmation: 'DELETE' });
  assert.equal(calls[0].url, '/api/data/delete');
  assert.equal(calls[0].options.body.confirmation, 'DELETE');
  const upload = { synthetic: 'multipart' };
  await handlers.forms['import-data-form']({}, {}, upload);
  assert.equal(calls[1].url, '/api/data/import');
  assert.equal(calls[1].options.body, upload);
  await handlers.actions['cancel-data-change']();
  assert.equal(calls[2].url, '/api/data/cancel');
  assert.equal(refreshes, 3, 'Data actions refresh only their panel, preserving preferences');
  console.log('Workspace controls, explicit confirmations, pending state, and cancel passed.');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
