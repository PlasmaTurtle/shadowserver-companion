/** Imports have no narrative-date control, and source views show component versions. */
const assert = require('node:assert/strict');

(async () => {
  const { install, createHandlers } = await import('../static/shadowserver_data.js');
  const { observedVersion } = await import('../../ui/static/shared.js');
  const calls = [];
  const ctx = {
    state: {},
    actions: {
      esc: (value) => String(value ?? ''),
      localDay: () => '2026-11-12',
      api: async (...args) => calls.push(args),
      route: async () => {},
    },
  };
  install(ctx);
  ctx.state.apiData.status = {
    configured: true,
    connected: true,
    subscriptions: ['synthetic'],
    report_types: ['scan_http_vulnerable'],
    completeness: 'complete',
    reports: [
      {
        id: 'report-1',
        filename: 'report.csv',
        report_type: 'scan_http_vulnerable',
        report_date: '2026-11-11',
        subscription: 'synthetic',
      },
    ],
  };
  const html = ctx.actions.apiAcquisitionMarkup();
  assert.match(html, /Import selected/);
  assert.doesNotMatch(html, /Narrative date|next_day|narrative_date_basis/);
  const handlers = createHandlers(ctx);
  await handlers.forms['api-import-form']({}, { next_day: 'on' }, { getAll: () => ['report-1'] });
  assert.deepEqual(calls, [
    ['/api/shadowserver/import', { method: 'POST', body: { report_ids: ['report-1'] } }],
  ]);
  const entry = {
    source: { fields: { version: '', component_version: 'php:5.4.16;apache:2.4.6' } },
  };
  assert.equal(observedVersion(entry), 'php:5.4.16;apache:2.4.6');
  assert.equal(entry.source.fields.version, '');
  assert.equal(observedVersion({ ...entry, normalized: { raw_version: '' } }), '');
  assert.equal(
    observedVersion({
      source: { fields: { version: '5.0', component_version: 'php:7.3' } },
      normalized: { profile: { version_semantics: 'protocol' } },
    }),
    '5.0',
  );
  console.log(
    'Import form and submission omit narrative dates; component and pinned version displays remain intact.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
