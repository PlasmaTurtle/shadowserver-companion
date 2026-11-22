/** State changes never restore a filtered option or silently pick national scope. */
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
  const config = {
    enabled: true,
    shadowserver: true,
    reference: false,
    hour: 6,
    minute: 0,
    interval_hours: 4,
    lookback_days: 7,
    subscription: 'US-SC',
    report_types: ['scan_http_vulnerable'],
  };
  ctx.state.apiData.status = {
    configured: true,
    connected: true,
    subscriptions: ['united-states', 'US-NC', 'agency-custom'],
    types: [{ type: 'scan_http_vulnerable' }],
    selection_defaults: { subscription: 'US-NC', report_types: ['scan_http_vulnerable'] },
    jurisdiction: { regions: ['North Carolina'], notice: '1 other-state subscription(s) hidden.' },
    schedule: { config, scope_error: 'Select an available subscription.', history: [] },
  };
  ctx.state.apiData.selection = {
    subscription: 'US-SC',
    report_type: 'scan_http_vulnerable',
    start: '2026-11-13',
    end: '2026-11-13',
  };
  let html = ctx.actions.apiAcquisitionMarkup();
  assert.match(html, /Jurisdiction: <strong>North Carolina/);
  assert.match(html, /other-state subscription/);
  assert.doesNotMatch(html, /option value="US-SC"/);
  assert.match(html, /previous report selection is no longer available/);
  assert.match(html, /value="" selected>Select subscription/);
  assert.doesNotMatch(html, /value="united-states" selected/);
  assert.doesNotMatch(html, /value="US-NC" selected/);
  assert.match(html, /data-action="schedule-run" disabled/);

  ctx.state.apiData.selection = null;
  html = ctx.actions.apiAcquisitionMarkup();
  assert.match(html, /value="US-NC" selected/);
  assert.doesNotMatch(html, /value="united-states" selected/);

  // A process restart has no account catalog. A timing-only change must retain
  // the saved choice instead of submitting a blank disabled form control.
  ctx.state.apiData.status.connected = false;
  ctx.state.apiData.status.subscriptions = [];
  ctx.state.apiData.status.types = [];
  html = ctx.actions.apiAcquisitionMarkup();
  assert.match(html, /Saved selection: US-SC/);
  assert.doesNotMatch(html, /option value="US-SC"/);
  await createHandlers(ctx).forms['api-schedule-form'](
    {},
    {
      enabled: undefined,
      shadowserver: 'on',
      time: '07:00',
      interval_hours: '4',
      lookback_days: '7',
    },
    { getAll: () => [] },
  );
  assert.equal(calls[0][1].body.subscription, 'US-SC');
  assert.deepEqual(calls[0][1].body.report_types, ['scan_http_vulnerable']);
  assert.equal(calls[0][1].body.enabled, false);
  assert.equal(calls[0][1].body.hour, 7);
  console.log('Jurisdiction-filtered API choices and stale schedule controls passed.');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
