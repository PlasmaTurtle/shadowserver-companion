/** Background asset checks preserve draft input and ignore stale application replies. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');
(async () => {
  const timers = new Map();
  let counter = 0;
  const context = vm.createContext({
    console,
    setTimeout(fn) {
      timers.set(++counter, fn);
      return counter;
    },
    clearTimeout(id) {
      timers.delete(id);
    },
  });
  const { application: app } = await loadApplication(context, { attach: false });
  app.state.editor.currentLead = {
    case_id: 'case-a',
    entries: [
      {
        id: 'row-a',
        ip: '8.8.8.8',
        source: {
          fields: {
            hostname: 'mail.example.com',
            version: '',
            component_version: 'php:7.3',
            tag: 'eol-php',
          },
          workbook: 'fixture.csv',
          sheet: 'Report',
          row: 2,
        },
      },
    ],
  };
  app.state.editor.draft = { narrative: 'Keep unsaved text' };
  app.state.editor.dirty = true;
  app.state.editor.tab = 'assets';
  let renders = 0;
  const node = {
    set innerHTML(value) {
      renders++;
      this.html = value;
    },
  };
  app.actions.$ = () => node;
  const state = {
    case_id: 'case-a',
    assets: [{ entry_id: 'row-a', eligible: true, supported: false, status: 'not_checked' }],
    remaining: 1,
  };
  app.actions.api = async (url, options) => {
    assert.equal(url, '/api/cases/case-a/assets/attribution');
    if (options.method === 'POST')
      return {
        id: 'job-a',
        case_id: 'case-a',
        status: 'running',
        total: 1,
        completed: 0,
        errors: [],
      };
    return state;
  };
  await app.actions.loadAssetAttribution();
  assert.match(node.html, /php:7.3/);
  assert.match(node.html, /Try remaining assets \(1\)/);
  assert.match(node.html, /data-attribute-asset="row-a"/);
  assert.doesNotMatch(node.html, /Attribution entry/);
  await app.actions.startAssetAttribution('row-a');
  assert.match(node.html, /Stop lookups/);
  assert.equal(timers.size, 1);
  assert.equal(app.state.editor.draft.narrative, 'Keep unsaved text');
  assert.equal(app.state.editor.dirty, true);
  app.state.editor.currentLead = { ...app.state.editor.currentLead, case_id: 'case-b' };
  const before = renders;
  await app.actions.loadAssetAttribution('case-a');
  assert.equal(renders, before, 'Background updates never repaint another case');
  let reply;
  app.actions.api = () => new Promise((resolve) => (reply = resolve));
  const pending = app.actions.loadAssetAttribution('case-a');
  app.actions.stopAssetAttributionPolling();
  reply({ ...state, remaining: 99 });
  await pending;
  assert.equal(
    app.state.assetAttribution.cases.get('case-a').remaining,
    1,
    'Destroyed application ignores stale network replies',
  );
  assert.equal(timers.size, 0);
  app.actions.api = async () => {
    throw Error('Fixture connection lost');
  };
  await app.actions.loadAssetAttribution('case-b');
  assert.match(node.html, /Fixture connection lost/);
  assert.equal(timers.size, 0, 'Connection errors stop polling until explicit refresh');
  app.state.assetAttribution.cases.set('case-b', {
    case_id: 'case-b',
    remaining: 0,
    assets: [
      { entry_id: 'row-a', eligible: false, supported: false, status: 'nonpublic_or_invalid' },
    ],
  });
  const finalMarkup = app.actions.assetsMarkup();
  assert.match(finalMarkup, /Requires a public IP and a hostname within the attributed root/);
  assert.match(finalMarkup, /aria-label="Try attribution for mail.example.com \/ 8.8.8.8"/);
  assert.match(finalMarkup, /data-asset-detail="source-row-a"/);
  assert.match(finalMarkup, /distinct checks remaining/);
  assert.match(finalMarkup, /<th scope="col">Actions<\/th>/);
  console.log(
    'Asset controls, bounded polling, draft preservation, case isolation, and cleanup passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
