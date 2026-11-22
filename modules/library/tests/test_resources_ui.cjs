/** Library editing works without installing Settings and preserves concurrent edits. */
const assert = require('node:assert/strict');
const test = require('node:test');

const escape = (value) =>
  String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('"', '&quot;');
async function fixture() {
  const { install } = await import('../static/resources.js');
  const { createHandlers } = await import('../static/library_events.js');
  const nodes = new Map();
  const ctx = {
    state: { resources: { resourceId: 'one', resources: [] }, navigation: { boot: {} } },
    actions: {
      $: (selector) => nodes.get(selector),
      $$: () => [],
      esc: escape,
      icon: () => '',
      num: String,
      heading: (title) => `<h1>${title}</h1>`,
      field: (_label, name, value) => `<textarea name="${name}">${escape(value)}</textarea>`,
      catalogSection: async () => '<section>Catalog boundary</section>',
      toast() {},
      route: async () => {},
    },
  };
  const api = install(ctx);
  return { ctx, api, nodes, handlers: createHandlers(ctx) };
}

test('Library loads an explainer and renders safe source citations without Settings', async () => {
  const { ctx, api, nodes } = await fixture();
  assert.equal(ctx.actions.settingsPage, undefined);
  assert.equal(ctx.actions.applyPresentation, undefined);
  ctx.actions.api = async (url) => {
    assert.equal(url, '/api/explainers?include_archived=true');
    return [
      {
        id: 'one',
        title: 'Reference <script>',
        body: 'Retained wording',
        revision: 2,
        sources: 'https://example.com/source\njavascript:alert(1)',
        source_metadata: [],
      },
    ];
  };
  const shell = await api.resourcesPage(new URLSearchParams({ item: 'one' }));
  assert.match(shell, /Loading explanations/);
  const region = { innerHTML: '', setAttribute() {}, removeAttribute() {} };
  nodes.set('#library-explainers', region);
  await api.loadLibraryExplainers();
  const html = region.innerHTML;
  assert.match(html, /Reference &lt;script>/);
  assert.match(html, /Retained wording/);
  assert.match(html, /href="https:\/\/example.com\/source"/);
  assert.doesNotMatch(html, /href="javascript:/);
  assert.deepEqual(ctx.state.navigation.boot.explainers, ctx.state.resources.resources);
});

test('Library save keeps citation metadata, newer edits and detached forms intact', async () => {
  const { ctx, api, nodes, handlers } = await fixture();
  const form = {
    dataset: { dirty: 'false', editRevision: '0', blockId: 'one', expectedRevision: '2' },
    querySelectorAll: () => [
      {
        dataset: { citationUrl: 'https://example.com/source' },
        querySelectorAll: () => [{ dataset: { citationKey: 'publisher' }, value: ' First party ' }],
      },
    ],
  };
  nodes.set('#resource-form', form);
  const input = {
    target: { closest: (selector) => (selector === '#resource-form' ? form : null) },
  };
  handlers.input(input);
  assert.equal(api.hasUnsavedLibrary(), true);
  let resolveSave,
    request,
    routeCalls = 0;
  ctx.actions.api = (url, options) => {
    request = { url, ...options };
    return new Promise((resolve) => {
      resolveSave = resolve;
    });
  };
  ctx.actions.renderResourceList = () => {
    routeCalls++;
  };
  let pending = handlers.forms['resource-form'](form, {
    title: 'Original',
    body: 'Original wording',
  });
  handlers.input(input);
  resolveSave({ id: 'one', revision: 3 });
  await pending;
  assert.equal(request.url, '/api/explainers/one');
  assert.equal(request.method, 'PUT');
  assert.equal(request.body.expected_revision, 2);
  assert.equal(form.dataset.expectedRevision, '3');
  assert.deepEqual(request.body.source_metadata, [
    { url: 'https://example.com/source', publisher: 'First party' },
  ]);
  assert.equal(api.hasUnsavedLibrary(), true);
  assert.equal(routeCalls, 0);
  ctx.actions.api = async () => ({ id: 'one', revision: 4 });
  await handlers.forms['resource-form'](form, { title: 'Updated', body: 'Current wording' });
  assert.equal(api.hasUnsavedLibrary(), false);
  assert.equal(routeCalls, 1);

  ctx.actions.api = () =>
    new Promise((resolve) => {
      resolveSave = resolve;
    });
  handlers.input(input);
  pending = handlers.forms['resource-form'](form, { title: 'Detached', body: 'Earlier page' });
  const replacement = { dataset: { dirty: 'true' } };
  nodes.set('#resource-form', replacement);
  resolveSave({ id: 'another-record', revision: 2 });
  await pending;
  assert.equal(ctx.state.resources.resourceId, 'one');
  assert.equal(replacement.dataset.dirty, 'true');
  assert.equal(routeCalls, 1);
});

test('Library retains dirty edits when switching explainers is cancelled', async (t) => {
  const { ctx, nodes, handlers } = await fixture();
  const original = global.confirm;
  t.after(() => {
    if (original === undefined) delete global.confirm;
    else global.confirm = original;
  });
  global.confirm = () => false;
  nodes.set('#resource-form', { dataset: { dirty: 'true' } });
  const editor = { innerHTML: 'Unsubmitted explanation' };
  nodes.set('#resource-editor', editor);
  const button = { dataset: { resource: 'two' } };
  await handlers.click.find((handler) => handler.matches(button)).run(button);
  assert.equal(ctx.state.resources.resourceId, 'one');
  assert.equal(editor.innerHTML, 'Unsubmitted explanation');
  await handlers.actions['new-block']();
  assert.equal(ctx.state.resources.resourceId, 'one');
  assert.equal(editor.innerHTML, 'Unsubmitted explanation');
});

test('A stale save preserves the draft and requires explicit revision comparison before retry', async () => {
  const { ctx, api, nodes, handlers } = await fixture();
  const form = {
    dataset: { blockId: 'one', expectedRevision: '1', dirty: 'true' },
    querySelectorAll: () => [],
  };
  const status = { innerHTML: '', textContent: '' };
  nodes.set('#resource-form', form);
  nodes.set('#resource-status', status);
  const current = {
    id: 'one',
    revision: 2,
    title: '<New title>',
    body: 'Other window wording',
    sources: '',
    archived_at: '',
  };
  let calls = 0;
  ctx.actions.api = async (_url, options) => {
    calls++;
    assert.equal(options.body.body, 'My retained draft');
    assert.equal(options.body.expected_revision, calls === 1 ? 1 : 2);
    if (calls === 1)
      throw Object.assign(new Error('Changed in another window'), {
        status: 409,
        detail: { current },
      });
    return { ...current, revision: 3, body: options.body.body };
  };
  await handlers.forms['resource-form'](form, {
    title: 'Mine',
    body: 'My retained draft',
    sources: '',
  });
  assert.equal(calls, 1);
  assert.equal(form.dataset.expectedRevision, '1');
  assert.equal(api.hasUnsavedLibrary(), true);
  assert.match(status.innerHTML, /Other window wording/);
  assert.match(status.innerHTML, /&lt;New title>/);
  await handlers.actions['resource-rebase']();
  assert.equal(form.dataset.expectedRevision, '2');
  assert.equal(api.hasUnsavedLibrary(), true);
  await handlers.forms['resource-form'](form, {
    title: 'Mine',
    body: 'My retained draft',
    sources: '',
  });
  assert.equal(calls, 2);
  assert.equal(form.dataset.expectedRevision, '3');
  assert.equal(api.hasUnsavedLibrary(), false);
});

test('Saving a new explainer during typing assigns its ID and revision without losing later edits', async () => {
  const { ctx, nodes, handlers } = await fixture();
  const form = {
    dataset: { blockId: '', dirty: 'true', editRevision: '1' },
    querySelectorAll: () => [],
  };
  nodes.set('#resource-form', form);
  let finish, firstRequest;
  ctx.actions.api = (url, options) => {
    firstRequest = { url, ...options };
    return new Promise((resolve) => {
      finish = resolve;
    });
  };
  const pending = handlers.forms['resource-form'](form, {
    title: 'New',
    body: 'Initial',
    sources: '',
  });
  form.dataset.editRevision = '2';
  await handlers.forms['resource-form'](form, { title: 'New', body: 'Newer', sources: '' });
  assert.equal(firstRequest.method, 'POST');
  assert.equal(firstRequest.body.expected_revision, undefined);
  finish({ id: 'created', revision: 1, title: 'New', body: 'Initial', sources: '' });
  await pending;
  assert.equal(form.dataset.blockId, 'created');
  assert.equal(form.dataset.expectedRevision, '1');
  assert.equal(form.dataset.dirty, 'true');
  ctx.actions.api = async (url, options) => {
    assert.equal(url, '/api/explainers/created');
    assert.equal(options.method, 'PUT');
    assert.equal(options.body.expected_revision, 1);
    return { id: 'created', revision: 2, title: 'New', body: 'Newer', sources: '' };
  };
  await handlers.forms['resource-form'](form, { title: 'New', body: 'Newer', sources: '' });
  assert.equal(form.dataset.dirty, 'false');
});

test('History compares complete retained wording and citations without disturbing an editor draft', async () => {
  const { ctx, nodes, api } = await fixture();
  const history = { innerHTML: '' },
    comparison = { innerHTML: '' };
  const form = { dataset: { dirty: 'true' } };
  nodes.set('#resource-history', history);
  nodes.set('#resource-comparison', comparison);
  nodes.set('#resource-form', form);
  ctx.actions.api = async (url) => {
    if (url.endsWith('/history'))
      return {
        items: [{ revision: 7, action: 'legacy_current', updated_at: '2026-11-21', actor: '' }],
        earliest_revision: 7,
        next_before: null,
      };
    const revision = url.endsWith('/revisions/7') ? 7 : 8;
    return {
      revision,
      title: 'Title',
      body: 'Text ' + revision,
      sources: 'https://example.test',
      source_metadata: [{ url: 'https://example.test', publisher: '<Publisher ' + revision + '>' }],
    };
  };
  await api.resourceHistory();
  assert.match(history.innerHTML, /Earlier Library wording was not retained/);
  assert.match(history.innerHTML, /Restore as new revision/);
  await api.compareResource(7);
  assert.match(comparison.innerHTML, /Text 7/);
  assert.match(comparison.innerHTML, /Text 8/);
  assert.match(comparison.innerHTML, /&lt;Publisher 7>/);
  assert.equal(form.dataset.dirty, 'true');
});
