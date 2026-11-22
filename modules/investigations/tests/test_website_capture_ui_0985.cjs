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
  assert.doesNotMatch(
    markup,
    /Main-site fallback|Page navigation|Capture attempts|Website download attempts/,
  );
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
  const observedAt = '2026-11-21T19:45:23Z';
  const activity = {
    attempts: [
      { observed_at: observedAt, outcome: 'canceled', suggestedFilename: 'private-file.zip' },
      { observed_at: observedAt, outcome: 'completed', url: 'blob:private-value' },
      { observed_at: observedAt, outcome: 'unconfirmed' },
    ],
    truncated: true,
  };
  const observed = a.captureProvenance({ capture: { ...redirected, download_activity: activity } });
  assert.match(observed, /Website download attempts \(3\+\)/);
  assert.match(observed, /Browser reported cancellation/);
  assert.match(observed, /Browser reported completion/);
  assert.match(observed, /Outcome unconfirmed/);
  assert.match(observed, /Additional attempts were observed/);
  assert.match(observed, /<time datetime="2026-11-21T19:45:23\.000Z">/);
  assert.doesNotMatch(observed, /private-file|blob:private-value/);
  for (const attempts of [
    [],
    [null, { observed_at: observedAt, outcome: '__proto__' }],
    [{ observed_at: '<img src=x>', outcome: 'canceled' }],
  ]) {
    assert.equal(a.downloadActivityMarkup({ attempts }), '');
  }
  const event = {
    action: 'website_capture_failed',
    detail: 'Website did not load',
    created_at: observedAt,
    metadata: { hostname: 'example.test', download_activity: activity },
  };
  const savedHistory = [{ ...event, metadata: JSON.stringify(event.metadata) }];
  assert.match(a.activities(savedHistory), /Website did not load[\s\S]*Outcome unconfirmed/);
  assert.doesNotMatch(
    a.activities([{ ...event, metadata: 'old record' }]),
    /Website download attempts/,
  );
  const originalApi = a.api;
  a.api = async () => ({ items: [event], total: 1 });
  const activityPage = await a.activityPage(new URLSearchParams());
  assert.match(activityPage, /Website download attempts \(3\+\)/);
  assert.match(activityPage, /example\.test/);
  assert.doesNotMatch(activityPage, /private-file|blob:private-value/);
  s.editor.dirty = false;
  a.api = async (url, options) => {
    if (options?.method === 'POST') return { id: 'failed-job' };
    if (url.includes('website-captures'))
      return { state: 'failed', message: event.detail, download_activity: activity };
    return { ...s.editor.currentLead, history: savedHistory };
  };
  const beforeFailure = structuredClone(s.editor.draft);
  await a.captureWebsite();
  await new Promise((r) => setImmediate(r));
  assert.match(a.captureMarkup(), /Website did not load[\s\S]*Website download attempts/);
  assert.deepEqual(s.editor.currentLead.history, savedHistory);
  assert.deepEqual(s.editor.draft, beforeFailure);
  a.api = async (url, options) => {
    if (options?.method === 'POST') return { id: 'canceled-job' };
    if (url.includes('website-captures'))
      return { state: 'cancelled', message: 'Capture cancelled', download_activity: activity };
    throw new TypeError('History service is temporarily unavailable');
  };
  await a.captureWebsite();
  await new Promise((r) => setImmediate(r));
  assert.match(a.captureMarkup(), /Capture cancelled[\s\S]*Website download attempts/);
  assert.doesNotMatch(a.captureMarkup(), /History service is temporarily unavailable/);
  a.api = originalApi;
  s.editor.dirty = false;
  phase = 0;
  await a.captureWebsite();
  await new Promise((r) => setImmediate(r));
  s.editor.currentLead = { case_id: 'case-b', draft: { narrative: 'Second' } };
  phase = 1;
  await timers.shift()();
  await new Promise((r) => setImmediate(r));
  assert.equal(s.editor.currentLead.case_id, 'case-b');
  assert.doesNotMatch(a.captureMarkup(), /Website download attempts/);
  a.stopWebsiteCapturePolling();
  console.log(
    'Capture evidence, download outcomes, failed-job history, draft preservation and case isolation passed.',
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
