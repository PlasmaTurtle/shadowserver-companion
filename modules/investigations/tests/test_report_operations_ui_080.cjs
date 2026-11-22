/** Report requests terminate visibly, PDF bytes are fetched once, and buttons recover. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('../../../tests/frontend_harness.cjs');
(async () => {
  let requests = 0;
  const context = vm.createContext({
    document: { querySelector() {}, querySelectorAll: () => [] },
    window: {},
    console,
    URLSearchParams,
    FormData,
    structuredClone,
    setTimeout,
    clearTimeout,
    AbortController,
    fetch: async (_url, { signal }) => {
      requests++;
      return new Promise((_resolve, reject) =>
        signal.addEventListener('abort', () => reject(Error('aborted'))),
      );
    },
  });
  const { application: app } = await loadApplication(context, { attach: false });
  app.state.navigation.boot = { token: 'synthetic' };
  await assert.rejects(
    app.actions.api('/api/test', { method: 'POST', body: {}, timeoutMs: 5 }),
    (error) => error.code === 'REQUEST_TIMEOUT' && /may still finish/.test(error.message),
  );
  assert.equal(requests, 1, 'A timed-out mutation is never retried');

  // The timeout covers reading the response body as well as receiving headers.
  context.fetch = async (_url, { signal }) => ({
    ok: true,
    blob: () =>
      new Promise((_resolve, reject) =>
        signal.addEventListener('abort', () => reject(Error('aborted body'))),
      ),
  });
  await assert.rejects(app.actions.api('/api/test.pdf', { blob: true, timeoutMs: 5 }), /timed out/);

  let status = null,
    latest = null,
    closed = 0,
    resolveWork;
  Object.assign(app.actions, {
    $: () => status,
    modal: (title, html) => {
      latest = { title, html };
      const id = html.match(/data-operation="(\d+)"/);
      status = id ? { dataset: { operation: id[1] } } : null;
    },
    closeModal: () => {
      closed++;
      status = null;
    },
  });
  const work = app.actions.reportOperation(
    'Validating',
    () =>
      new Promise((resolve) => {
        resolveWork = resolve;
      }),
  );
  assert.match(latest.html, /role="status"/);
  await assert.rejects(
    app.actions.reportOperation('Duplicate', () => {}),
    /already running/,
  );
  resolveWork('complete');
  assert.equal(await work, 'complete');
  assert.equal(closed, 1);
  await assert.rejects(
    app.actions.reportOperation('Preview', () => {
      throw Error('Evidence <missing>');
    }),
    /Evidence/,
  );
  assert.match(latest.html, /Evidence &lt;missing&gt;/);
  assert.match(latest.html, /role="alert"/);
  assert.equal(closed, 1, 'Error remains visible until dismissed');

  let fetched = 0,
    created = 0;
  const revoked = [];
  context.URL = {
    createObjectURL: () => 'blob:preview-' + ++created,
    revokeObjectURL: (url) => revoked.push(url),
  };
  Object.assign(app.actions, {
    api: async (url, options) => {
      fetched++;
      assert.equal(url, '/api/leads/synthetic/preview.pdf?case_id=case');
      assert.equal(options.timeoutMs, 120000);
      assert.equal(options.blob, true);
      return { type: 'application/pdf' };
    },
    historicalReportNotice: () => '',
    leadURL: () => '/api/leads/synthetic/preview.pdf?case_id=case',
  });
  app.state.editor.currentLead = { case_id: 'case' };
  await app.actions.previewReport();
  assert.equal(fetched, 1);
  assert.match(latest.html, /src="blob:preview-1"/);
  assert(!latest.html.includes('/preview.pdf'), 'The iframe never starts another server render');
  await app.actions.previewReport();
  assert.deepEqual(revoked, ['blob:preview-1']);
  app.actions.disposeReportPreview();
  assert.deepEqual(revoked, ['blob:preview-1', 'blob:preview-2']);
  // A late PDF must not appear over a different notification or a destroyed app.
  let resolvePDF;
  app.actions.api = () =>
    new Promise((resolve) => {
      resolvePDF = resolve;
    });
  let delayed = app.actions.previewReport();
  app.state.editor.currentLead = { case_id: 'other-case' };
  resolvePDF({ type: 'application/pdf' });
  await delayed;
  assert.equal(created, 2);
  delayed = app.actions.previewReport();
  app.actions.disposeReportPreview();
  resolvePDF({ type: 'application/pdf' });
  await delayed;
  assert.equal(created, 2);

  // Autosave also uses the request bound and preserves later edits/navigation.
  let resolveSave;
  app.actions.api = (_url, options) => {
    assert.equal(options.timeoutMs, 120000);
    return new Promise((resolve) => {
      resolveSave = resolve;
    });
  };
  app.state.editor.currentLead = { case_id: 'saving', draft_revision: 1 };
  app.state.editor.draft = { notes: 'Submitted edits' };
  let saving = app.actions.saveDraft({ timeoutMs: 120000 });
  app.state.editor.draft.notes = 'Newer unsaved edits';
  resolveSave({ case_id: 'saving', draft_revision: 2, draft: { notes: 'Submitted edits' } });
  await assert.rejects(saving, /newer edits remain unsaved/);
  assert.equal(app.state.editor.draft.notes, 'Newer unsaved edits');
  assert.equal(app.state.editor.currentLead.draft_revision, 2);
  assert.equal(app.state.editor.dirty, true);
  saving = app.actions.saveDraft({ timeoutMs: 120000 });
  app.state.editor.currentLead = { case_id: 'different' };
  app.state.editor.draft = { notes: 'Different case notes' };
  resolveSave({ case_id: 'saving', draft_revision: 3, draft: { notes: 'Newer unsaved edits' } });
  await saving;
  assert.equal(app.state.editor.currentLead.case_id, 'different');
  assert.equal(app.state.editor.draft.notes, 'Different case notes');

  // Exercise the production certification event handler with a late response.
  const fs = require('node:fs'),
    path = require('node:path');
  const eventsModule = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../static/editor_events.js'), 'utf8'),
    { context },
  );
  await eventsModule.link(() => {
    throw Error('Unexpected event-module dependency');
  });
  await eventsModule.evaluate();
  const handlers = eventsModule.namespace.createHandlers(app);
  let resolveCertification,
    rerouted = 0;
  app.actions.api = () =>
    new Promise((resolve) => {
      resolveCertification = resolve;
    });
  app.actions.toast = () => {};
  app.actions.route = async () => {
    rerouted++;
  };
  app.state.editor.currentLead = { case_id: 'certifying', readiness: [], status: 'in_progress' };
  app.state.editor.dirty = false;
  const certifying = handlers.actions.finalize();
  app.state.editor.currentLead = { case_id: 'other-case' };
  app.state.editor.draft = { notes: 'Unsaved current-case notes' };
  app.state.editor.dirty = true;
  resolveCertification({ id: 'report', revision: 1 });
  await certifying;
  assert.equal(rerouted, 0);
  assert.equal(app.state.editor.dirty, true);
  assert.equal(app.state.editor.draft.notes, 'Unsaved current-case notes');
  console.log(
    'Bounded report fetch/body reads, no mutation retry, single-flight progress, visible failures and one-fetch PDF previews passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
