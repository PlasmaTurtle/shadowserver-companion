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
    hostnames: ['mail.example.com'],
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
    assert.ok(html.includes('href="https://example.com/"'));
    assert.ok(html.includes('href="https://mail.example.com/"'));
    assert.ok(html.includes('>www.example.com</a>'));
    assert.ok(html.includes('Captured 2026-11-21T12:00:00Z'));
    assert.ok(html.includes('/image?original=true'));
  }
  assert.deepEqual(calls, ['/api/pending-leads?q=&status=pending', '/api/pending-leads/lead-one']);
  lead.website.final_url = 'javascript:alert(1)';
  const invalid = await ui.pendingLeadPage(lead.id);
  assert.doesNotMatch(invalid, /javascript:|<img/);
  assert.match(invalid, /Website screenshot unavailable/);
});

test('decisions on a mixed lead advance the same queue and update both finding views', async (t) => {
  const { install } = await import('../static/entity_leads.js');
  const { createHandlers } = await import('../static/entity_leads_events.js');
  const savedLocation = global.location;
  global.location = { hash: '#leads/mixed' };
  t.after(() => {
    global.location = savedLocation;
  });
  let rows = [
    { id: 'mixed', finding_kinds: ['cve', 'eol'] },
    { id: 'cve-only', finding_kinds: ['cve'] },
    { id: 'eol-only', finding_kinds: ['eol'] },
  ].map((row) => ({ ...row, domain: 'example.com', revision: 1, observations: 1 }));
  const ctx = {
    state: { navigation: { renderId: 1, returns: new Map() }, intakeLeads: {} },
    actions: {
      esc,
      date: String,
      num: String,
      icon: () => '',
      heading: () => '',
      empty: () => '',
      linkButton: () => '',
      toast: () => {},
      refreshNavigationCounts: () => {},
      api: async (url, options) => {
        if (!options) return rows;
        const id = url.split('/')[3];
        assert.equal(options.body.expected_revision, 1);
        rows = rows.filter((row) => row.id !== id);
        return { case_id: 'notification' };
      },
    },
  };
  const ui = install(ctx);
  const actions = createHandlers(ctx).actions;
  const params = new URLSearchParams('q=example&lens=eol&sort=priority&status=pending');
  const first = await ui.pendingLeadsPage(params);
  assert.match(first, /End of life<strong>2/);
  assert.match(first, /CVE<strong>2/);
  ctx.state.intakeLeads.current = rows[0];
  await actions['start-lead']();
  assert.equal(global.location.hash, 'leads/eol-only');
  assert.equal(
    new URLSearchParams(ctx.state.navigation.returns.get('leads').split('?')[1]).get('lens'),
    'eol',
  );
  ctx.state.intakeLeads.current = rows.find((r) => r.id === 'eol-only');
  await actions['dismiss-lead']();
  assert.match(global.location.hash, /^leads\?/);
  const emptied = await ui.pendingLeadsPage(params);
  assert.match(emptied, /End of life<strong>0/);
  assert.match(emptied, /CVE<strong>1/);
});
