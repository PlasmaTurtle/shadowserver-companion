/** Scheduled API selection, visible completion and credential-free forms. */
const assert = require('node:assert/strict');
(async () => {
  const { install, createHandlers } = await import('../static/shadowserver_data.js');
  const calls = [];
  const ctx = {
    state: {},
    actions: {
      esc: (value) =>
        String(value ?? '')
          .replaceAll('<', '&lt;')
          .replaceAll('"', '&quot;'),
      localDay: () => '2026-11-13',
      route: async () => {},
      api: async (url, options) => {
        calls.push([url, options]);
        return {};
      },
    },
  };
  install(ctx);
  ctx.state.apiData.status = {
    configured: true,
    can_remember: true,
    schedule: {
      config: {
        enabled: true,
        shadowserver: true,
        reference: true,
        hour: 6,
        minute: 15,
        interval_hours: 4,
        lookback_days: 7,
        subscription: 'sample',
        report_types: ['scan_http_vulnerable'],
      },
      run: { status: 'importing', message: 'Waiting for Accretion to complete', imports: ['one'] },
      background: { installed: true },
      history: [],
    },
  };
  let html = ctx.actions.apiAcquisitionMarkup();
  assert.match(html, /Waiting for Accretion to complete/);
  assert.match(html, /0\/1 imports completed/);
  assert.match(html, /value="06:15"/);
  assert.match(html, /scan_http_vulnerable/);
  assert.match(html, /signed in, even with the app closed/);
  const handlers = createHandlers(ctx);
  await handlers.forms['api-schedule-form'](
    {},
    {
      enabled: 'on',
      shadowserver: 'on',
      reference: 'on',
      time: '06:15',
      interval_hours: '4',
      lookback_days: '7',
      subscription: 'sample',
    },
    { getAll: () => ['scan_http_vulnerable', 'scan_exchange'] },
  );
  assert.equal(calls[0][0], '/api/schedule');
  assert.deepEqual(calls[0][1].body.report_types, ['scan_http_vulnerable', 'scan_exchange']);
  assert.equal(calls[0][1].body.minute, 15);
  assert(!('api_key' in calls[0][1].body));
  await handlers.actions['schedule-background']({ dataset: { enabled: 'false' } });
  assert.deepEqual(calls[1][1].body, { enabled: false });
  console.log('Scheduled intake controls and status passed.');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
