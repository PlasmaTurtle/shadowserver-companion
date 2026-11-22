/** Leads display retained evidence without starting another website capture. */
const assert = require('node:assert/strict');
const test = require('node:test');

const esc = (value) =>
  String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('"', '&quot;');

test('lead list and detail use the saved screenshot and working destination', async () => {
  const { install } = await import('../static/entity_leads.js');
  const calls = [];
  const lead = {
    id: 'lead-one',
    domain: 'example.com',
    ips: ['8.8.8.8'],
    observations: 1,
    status: 'pending',
    active_cases: [],
    website: {
      id: 'capture-one',
      final_url: 'http://www.example.com/login?next=%2F&session=public',
      captured_at: '2026-11-21T12:00:00Z',
    },
  };
  const ctx = {
    state: { navigation: { renderId: 1, returns: new Map() }, intakeLeads: {} },
    actions: {
      esc,
      num: String,
      stamp: String,
      date: String,
      icon: () => '',
      heading: (title) => `<h1>${title}</h1>`,
      linkButton: () => '',
      sharedIpMarkup: () => '',
      statusBadge: () => '',
      api: async (url) => {
        calls.push(url);
        return url.startsWith('/api/pending-leads?') ? [lead] : lead;
      },
    },
  };
  const ui = install(ctx);
  for (const html of [await ui.pendingLeadsPage(), await ui.pendingLeadPage(lead.id)]) {
    assert.match(html, /src="\/api\/website-evidence\/capture-one\/image"/);
    assert.match(html, /loading="lazy"/);
    assert.match(html, /href="http:\/\/www\.example\.com\/login\?next=%2F&amp;session=public"/);
    assert.doesNotMatch(html, /href="https:\/\/example\.com"/);
  }
  assert.deepEqual(calls, ['/api/pending-leads?q=&status=pending', '/api/pending-leads/lead-one']);
  lead.website.final_url = 'javascript:alert(1)';
  const invalid = await ui.pendingLeadPage(lead.id);
  assert.doesNotMatch(invalid, /javascript:|<img/);
  assert.match(invalid, /Website screenshot unavailable/);
});
