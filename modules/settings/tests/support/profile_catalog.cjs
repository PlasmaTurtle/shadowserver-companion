/** Synthetic profile catalog for the module's DOM harnesses; HTTP tests cover catalog content. */
const agencies = [
  ['usss', 'USSS', 'United States Secret Service', 'U.S. Department of Homeland Security'],
  ['fbi', 'FBI', 'Federal Bureau of Investigation', 'U.S. Department of Justice'],
  [
    'cisa',
    'CISA',
    'Cybersecurity and Infrastructure Security Agency',
    'U.S. Department of Homeland Security',
  ],
].map(([id, short_name, name, department]) => ({
  id,
  short_name,
  name,
  department,
  authority: {
    id: `${id}-mission`,
    revision: '1',
    title: `${short_name} mission and authority`,
    purpose_statement: `Synthetic ${short_name} mission reference.`,
    authorities: [
      {
        citation: `${short_name} synthetic citation`,
        description: 'Synthetic authority description.',
        url: 'https://example.org/authority',
      },
    ],
  },
}));
module.exports = {
  agencies,
  regions: ['North Carolina', 'South Carolina'],
  timezones: [
    'America/New_York',
    'America/Chicago',
    'America/Denver',
    'America/Los_Angeles',
    'America/Anchorage',
    'Pacific/Honolulu',
    'UTC',
  ],
};
