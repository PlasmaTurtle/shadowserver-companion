/** Unknown legacy qualification must not become a positive or negative claim. */
const assert = require('node:assert/strict');
(async () => {
  const { densityStats, statusName } = await import('../../observatory/static/eclipse_model.js');
  assert.equal(statusName('qualification_unknown'), 'Legacy qualification unavailable');
  const density = densityStats([
    {
      id: 'old',
      admission_state: 'legacy_unknown',
      status: 'qualification_unknown',
      dark_matter: true,
      admitted: false,
    },
    { id: 'approved', admitted: true },
    { id: 'observed', admitted: false, dark_matter: true },
  ]);
  assert.equal(density.observation_count, 3);
  assert.equal(density.admitted_density, 1);
  assert.equal(density.dark_matter_density, 1);
  assert.equal(density.legacy_unknown_density, 1);
  const { install } = await import('../../investigations/static/workflow.js');
  const ctx = { constants: {}, state: {}, actions: { esc: String, num: String, date: String } };
  install(ctx);
  const markup = ctx.actions.findingHistoryMarkup({
    basis: 'Exact condition qualification',
    total: 1,
    counts: { qualification_unknown: 1 },
    items: [
      {
        finding: 'CVE-2024-12345',
        hostname: 'example.com',
        ip: '8.8.8.8',
        state: 'qualification_unknown',
        observations: 0,
        reported_observation_count: 2,
        approved_observation_count: 0,
        legacy_unknown_observation_count: 2,
        versions: [],
        first_observed: '',
        last_observed: '',
        notifications: [],
      },
    ],
  });
  assert(markup.includes('Legacy qualification unavailable'));
  assert(markup.includes('2 reported · 0 approved · 2 legacy qualification unavailable'));
  assert(!markup.includes('undefined'));
  console.log('Admission UI checks passed');
})();
