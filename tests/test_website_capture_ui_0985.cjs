/** Capture completion preserves unsaved narrative and ignores a departed case. */
const assert = require('node:assert/strict'),
  vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');
(async () => {
  const nodes = new Map(),
    timers = [];
  const node = (id) => {
    if (!nodes.has(id)) nodes.set(id, { innerHTML: '', value: 'mail.example.com' });
    return nodes.get(id);
  };
  const context = vm.createContext({
    console,
    URL,
    URLSearchParams,
    structuredClone,
    setTimeout: (fn) => {
      timers.push(fn);
      return timers.length;
    },
    clearTimeout() {},
    clearInterval() {},
    document: { querySelector: node, querySelectorAll: () => [] },
    window: { Eclipse: { destroy() {} } },
  });
  const { application: app } = await loadApplication(context, { attach: false });
  const { actions: a, state: s } = app;
  a.toast = () => {};
  a.editorContent = () => '<div>Updated evidence</div>';
  a.leadURL = () => '/case/current';
  s.editor.currentLead = {
    id: 'entity',
    case_id: 'case-a',
    case: { version: 4 },
    hostnames: [{ name: 'mail.example.com' }],
    draft: { narrative: 'Saved' },
    evidence: [],
  };
  s.editor.draft = { narrative: 'Saved' };
  let phase = 0;
  const calls = [];
  a.api = async (url, options) => {
    calls.push([url, options]);
    if (options?.method === 'POST') return { id: 'capture' };
    if (url.includes('website-captures'))
      return phase
        ? { state: 'completed', message: 'Viewport captured', prior_version: 4, case_version: 5 }
        : { state: 'running' };
    return {
      ...s.editor.currentLead,
      case: { version: 5 },
      draft: { narrative: 'Saved' },
      evidence: [{ id: 'image' }],
    };
  };
  assert.match(a.captureMarkup(), /Capture website/);
  await a.captureWebsite();
  await new Promise((r) => setImmediate(r));
  assert.equal(calls[0][1].body.hostname, 'mail.example.com');
  s.editor.dirty = true;
  s.editor.draft.narrative = 'Unsaved work while capture runs';
  phase = 1;
  await timers.shift()();
  await new Promise((r) => setImmediate(r));
  assert.equal(s.editor.draft.narrative, 'Unsaved work while capture runs');
  assert.equal(s.editor.currentLead.case.version, 5);
  assert.equal(s.editor.currentLead.evidence[0].id, 'image');
  const markup = a.captureProvenance({
    sha256: 'a'.repeat(64),
    capture: {
      title: '<script>bad</script>',
      final_url: 'javascript:alert(1)',
      requested_url: 'https://example.com',
      capture_status: 'challenge',
      viewport: { width: 1440, height: 900 },
    },
  });
  assert.doesNotMatch(markup, /<script>|href="javascript/);
  assert.match(markup, /Access challenge/);
  assert.match(markup, /&lt;script&gt;/);
  s.editor.dirty = false;
  phase = 0;
  await a.captureWebsite();
  await new Promise((r) => setImmediate(r));
  s.editor.currentLead = { case_id: 'case-b', draft: { narrative: 'Second' } };
  phase = 1;
  await timers.shift()();
  await new Promise((r) => setImmediate(r));
  assert.equal(s.editor.currentLead.case_id, 'case-b');
  a.stopWebsiteCapturePolling();
  console.log(
    'Website capture UI: scope, provenance escaping, dirty-draft preservation and case navigation isolation passed.',
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
