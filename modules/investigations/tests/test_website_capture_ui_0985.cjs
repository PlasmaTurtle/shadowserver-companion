/** Capture completion preserves unsaved narrative and ignores a departed case. */
const assert = require('node:assert/strict'),
  vm = require('node:vm');
const { loadApplication } = require('../../../tests/frontend_harness.cjs');
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
  assert.doesNotMatch(markup, /Main-site fallback|Page navigation|Capture attempts/);
  const redirected = {
    requested_url: 'http://mail.example.com/',
    final_url: 'https://www.example.com/contact/',
    root_domain: 'example.com',
    title: 'Example business',
    capture_status: 'captured',
    viewport: { width: 1440, height: 900 },
    http_status: 200,
    redirects: ['http://mail.example.com/', 'https://www.example.com/contact/'],
    attempts: [
      {
        url: 'http://mail.example.com/',
        outcome: 'captured',
        final_url: 'https://www.example.com/contact/',
        http_status: 200,
      },
    ],
    fallback_used: false,
  };
  const direct = a.captureProvenance({ sha256: 'b'.repeat(64), capture: redirected });
  assert.match(direct, /Requested<\/dt><dd>http:\/\/mail\.example\.com\//);
  assert.match(direct, /Final page<\/dt><dd>https:\/\/www\.example\.com\/contact\//);
  assert.match(direct, /Page navigation/);
  assert.match(direct, /Capture attempts/);
  assert.match(direct, /HTTP 200/);
  assert.doesNotMatch(direct, /Main-site fallback/);
  const fallback = a.captureProvenance({
    sha256: 'c'.repeat(64),
    capture: {
      ...redirected,
      fallback_used: true,
      attempts: [
        {
          url: 'http://mail.example.com/',
          outcome: 'load_failed',
          reason: 'Network request timed out',
        },
        {
          url: 'https://example.com/',
          outcome: 'captured',
          final_url: 'https://www.example.com/contact/',
          http_status: 200,
        },
      ],
    },
  });
  assert.match(fallback, /Main-site fallback/);
  assert.match(fallback, /Page load failed/);
  assert.match(fallback, /Network request timed out/);
  assert.match(fallback, /https:\/\/example\.com\//);
  for (const length of [5, 6]) {
    const completeHistory = a.captureProvenance({
      capture: {
        ...redirected,
        fallback_used: true,
        attempts: [
          ...Array.from({ length: length - 1 }, (_, index) => ({
            url: `https://attempt-${index}.example.com/`,
            outcome: 'load_failed',
          })),
          { url: 'https://successful-main-site.example/', outcome: 'captured', http_status: 200 },
        ],
      },
    });
    assert.match(completeHistory, /https:\/\/successful-main-site\.example\//);
    assert.match(completeHistory, /Viewport captured · HTTP 200/);
    assert.doesNotMatch(completeHistory, /Showing \d+ of \d+ attempts/);
  }
  const hostile = a.captureProvenance({
    sha256: 'd'.repeat(64),
    capture: {
      ...redirected,
      redirects: [
        'https://example.com/<script>bad</script>',
        ...Array(9).fill('safe'),
        'hidden-hop',
      ],
      attempts: [
        {
          url: '<img src=x onerror=bad()>',
          outcome: '<script>bad</script>',
          reason: '<script>bad</script>',
        },
        { url: 'safe', outcome: 'load_failed', reason: 'r'.repeat(300) },
        { outcome: 'toString' },
        { outcome: '__proto__' },
        ...Array(4).fill({ url: 'safe', outcome: 'load_failed' }),
        { url: 'hidden-attempt', outcome: 'captured' },
      ],
    },
  });
  assert.doesNotMatch(hostile, /<script>|<img src=x|hidden-hop|hidden-attempt/);
  assert.doesNotMatch(hostile, /function toString|\[object Object\]/);
  assert.match(hostile, /&lt;script&gt;/);
  assert.match(hostile, /&lt;img/);
  assert.doesNotMatch(hostile, new RegExp('r'.repeat(241)));
  assert.match(hostile, /Showing 10 of 11 navigation steps/);
  assert.match(hostile, /Showing 8 of 9 attempts/);
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
