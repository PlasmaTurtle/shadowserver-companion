/** Shared browser capabilities checked through real feature renderers and native Fetch. */
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

(async () => {
  const { escapeHTML, formatCount, formatTimestamp } = await import('../static/format.js');
  const { install: installShared } = await import('../static/shared.js');
  const { install: installSettings } = await import('../../settings/static/settings.js');
  const { install: installData } = await import('../../accretion/static/shadowserver_data.js');
  const { install: installHealth } = await import('../../workspace/static/workspace_health.js');
  const { install: installLibrary } = await import(
    '../../investigations/static/source_intelligence.js'
  );
  const { hasKnownRansomware } = await import('../../library/static/risk.js');
  const model = await import('../../observatory/static/eclipse_model.js');
  const { requestJSON, requestBlob } = await import('../static/request.js');

  assert.equal(escapeHTML('&<>"\' 🛰'), '&amp;&lt;&gt;&quot;&#39; 🛰');
  assert.equal(escapeHTML(null), '');
  assert.equal(formatCount(123456), Number(123456).toLocaleString());
  assert.equal(model.esc, escapeHTML);
  assert.equal(model.num, formatCount);

  const ctx = {
    constants: {},
    actions: { localDay: () => '2026-11-01' },
    state: { navigation: { boot: { settings: { display_timezone: 'Asia/Tokyo' } } }, editor: {} },
  };
  for (const install of [
    installShared,
    installSettings,
    installData,
    installHealth,
    installLibrary,
  ])
    install(ctx);
  const instant = '2026-11-01T06:30:00Z';
  const expected = new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    timeZone: 'Asia/Tokyo',
    timeZoneName: 'short',
  }).format(new Date(instant));
  assert.equal(ctx.actions.stamp(instant), expected);
  const schedule = {
    next_run_at: instant,
    timezone: 'America/New_York',
    config: {},
    history: [{ completed_at: instant, status: 'completed', message: 'Done' }],
  };
  assert(ctx.actions.settingsAutomationMarkup({ schedule }).includes(escapeHTML(expected)));
  ctx.state.apiData.status = { configured: true, schedule };
  const data = ctx.actions.apiAcquisitionMarkup();
  assert(data.includes(escapeHTML(expected)), 'Data uses the same analyst zone');
  const health = ctx.actions.healthMarkup({
    status: 'completed',
    result: {
      ok: true,
      checked_at: instant,
      stores: [],
      storage: {},
      last_verified_backup: { verified_at: instant },
    },
  });
  assert.equal(
    health.split(escapeHTML(expected)).length - 1,
    2,
    'Both health timestamps use the analyst zone',
  );
  assert.equal(formatTimestamp('invalid'), 'Not recorded');
  assert.equal(formatTimestamp(null), 'Not recorded');
  assert.match(ctx.actions.date('2026-11-01'), /Nov 1, 2026/);
  const dst = ['2026-11-01T05:30:00Z', '2026-11-01T06:30:00Z'].map((value) =>
    formatTimestamp(value, { timeZone: 'America/New_York', locale: 'en-US' }),
  );
  assert(dst[0].includes('1:30:00') && dst[1].includes('1:30:00'));
  assert.notEqual(dst[0], dst[1], 'DST repeated hour retains its distinct zone');
  for (const summary of [
    { ransomware: { status: 'known' } },
    { known_ransomware: true },
    { ransomware_known: true },
  ]) {
    assert(hasKnownRansomware(summary));
    assert(model.knownRansomware(summary));
    assert(ctx.actions.hasKnownRansomware(summary));
  }
  for (const summary of [
    {},
    null,
    { ransomware: { status: 'unknown' } },
    { known_ransomware: 'true' },
  ])
    assert.equal(hasKnownRansomware(summary), false);
  assert.match(ctx.actions.intelligenceMarkup({ id: 'CVE-2026-1234' }), /No CISA assessment/);

  // Download resource ownership, including a rejected browser click.
  const urls = [],
    revoked = [],
    clicks = [],
    timers = [];
  let failClick = false;
  const context = vm.createContext({
    URL: {
      createObjectURL(blob) {
        urls.push(blob);
        return 'blob:test-' + urls.length;
      },
      revokeObjectURL(url) {
        revoked.push(url);
      },
    },
    document: {
      createElement() {
        return {
          click() {
            if (failClick) throw Error('Download unavailable');
            clicks.push({ ...this });
          },
        };
      },
    },
    setTimeout(fn, delay) {
      timers.push({ fn, delay });
    },
  });
  const downloadModule = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../static/download.js'), 'utf8'),
    { context },
  );
  await downloadModule.link(() => {
    throw Error('Unexpected dependency');
  });
  await downloadModule.evaluate();
  const blob = new Blob(['diagnostics'], { type: 'application/json' });
  downloadModule.namespace.downloadBlob(blob, 'diagnostics.json');
  assert.equal(urls[0], blob);
  assert.equal(clicks[0].download, 'diagnostics.json');
  assert.equal(revoked.length, 0, 'Click consumers retain the URL until deferred cleanup');
  failClick = true;
  assert.throws(() => downloadModule.namespace.downloadBlob(blob, 'failed.json'), /unavailable/);
  for (const timer of timers) timer.fn();
  assert.deepEqual(revoked, ['blob:test-1', 'blob:test-2']);

  // Native HTTP response/body and AbortController behavior, without mocking Fetch.
  const server = http.createServer((req, res) => {
    if (req.url === '/stall') return;
    if (req.url.startsWith('/disconnect')) return req.socket.destroy();
    if (req.url === '/conflict') {
      res.writeHead(409, { 'Content-Type': 'application/json' });
      return res.end(JSON.stringify({ detail: { code: 'field_revision_changed' } }));
    }
    if (req.url === '/bad') {
      res.writeHead(502, { 'Content-Type': 'text/plain' });
      return res.end('Upstream unavailable');
    }
    if (req.url === '/bytes') return res.end('real bytes');
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ready: true }));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const base = 'http://127.0.0.1:' + server.address().port;
  try {
    assert.deepEqual(await requestJSON(base + '/ok'), { ready: true });
    await assert.rejects(
      requestJSON(base + '/disconnect?query=synthetic-private-value'),
      (error) =>
        error.name === 'ConnectionError' &&
        /local app/.test(error.message) &&
        !error.message.includes('synthetic-private-value') &&
        error.status === undefined,
    );
    await assert.rejects(
      requestJSON(base + '/disconnect', { method: 'POST' }),
      (error) =>
        error.name === 'ConnectionError' && /check the operation’s status/.test(error.message),
    );
    await assert.rejects(
      requestJSON(base + '/conflict'),
      (error) =>
        error.status === 409 &&
        error.detail.code === 'field_revision_changed' &&
        !error.message.includes('[object Object]'),
    );
    await assert.rejects(
      requestJSON(base + '/bad'),
      (error) => error.status === 502 && /502/.test(error.message),
    );
    assert.equal(await (await requestBlob(base + '/bytes')).text(), 'real bytes');
    await assert.rejects(
      requestJSON(base + '/stall', { timeoutMs: 50 }),
      (error) => error.name === 'TimeoutError' && error.code === 'REQUEST_TIMEOUT',
    );
    const controller = new AbortController();
    const cancelled = requestJSON(base + '/stall', { signal: controller.signal, timeoutMs: 1000 });
    controller.abort();
    await assert.rejects(cancelled, (error) => error.name === 'AbortError' && !error.code);
  } finally {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
  console.log(
    'Shared UI helpers: consistent feature timestamps, DST, escaped text, risk meaning, download cleanup, real HTTP errors/bytes/cancellation passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
