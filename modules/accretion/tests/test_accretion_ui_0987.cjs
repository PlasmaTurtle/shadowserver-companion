/** Accretion surfaces saved scores without changing workflow or claiming missing evidence. */
const assert = require('node:assert/strict');

(async () => {
  const { install: installEntities } = await import('../../entities/static/entities.js');
  const { install } = await import('../../leads/static/entity_leads.js');
  const { install: installIntake } = await import('../static/intake.js');
  const esc = (value) =>
    String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;');
  const ctx = {
    state: {
      navigation: {
        renderId: 1,
        returns: new Map(),
        boot: { workspace: '/workspace', settings: {} },
      },
      intakeLeads: {},
    },
    actions: {
      esc,
      num: (value) => Number(value || 0).toLocaleString('en-US'),
      stamp: esc,
      date: esc,
      icon: () => '',
      heading: (title, _subtitle, buttons) => `<h1>${title}</h1>${buttons || ''}`,
      linkButton: (href, label) => `<a href="${href}">${label}</a>`,
      statusBadge: (status) => esc(status),
      empty: (title) => `<p>${title}</p>`,
    },
  };
  install(ctx);
  installEntities(ctx);
  installIntake(ctx);
  const score = {
    schema_version: 1,
    policy_version: 1,
    quality: 84,
    urgency: 86,
    aggregate: 85,
    temperature: 'blazing',
    scored_at: '2026-11-12T00:00:00Z',
    factors: {
      quality: [
        {
          label: 'Finding specificity',
          points: 34,
          weight: 40,
          reason: 'Source <version> present',
        },
      ],
      urgency: [{ label: 'KEV', points: 35, weight: 35, reason: 'Listed in imported feed' }],
    },
    cves: [
      {
        id: 'CVE-2026-12345',
        status: 'available',
        cvss: 9.8,
        epss: { score: 0.42 },
        kev: { listed: true },
      },
    ],
    warnings: ['A <source> refresh is due'],
  };
  const before = structuredClone(score);
  let html = ctx.actions.intakeScoreMarkup(score);
  assert.match(html, /data-temperature="blazing"/);
  assert.match(html, /<dt>Quality<\/dt><dd>84/);
  assert.match(html, /<dt>Urgency<\/dt><dd>86/);
  assert.match(html, /<dt>Aggregate<\/dt><dd>85/);
  assert.match(html, /<details class="accretion-explanation"><summary>Why this temperature/);
  assert.doesNotMatch(html, /accretion-explanation" open/);
  assert.match(html, /Source &lt;version&gt; present/);
  assert.match(html, /A &lt;source&gt; refresh is due/);
  assert.match(html, /42.00%/);
  assert.match(html, /<td>Listed<\/td>/);
  assert.deepEqual(score, before, 'Rendering preserves the saved snapshot.');
  assert.match(ctx.actions.intakeTemperatureMarkup(null), /Unscored/);
  assert.doesNotMatch(ctx.actions.intakeTemperatureMarkup(null), /Cool|>0</);
  assert.match(
    ctx.actions.intakeTemperatureMarkup({ aggregate: null, temperature: 'cool' }),
    /Unscored/,
  );
  assert.doesNotMatch(
    ctx.actions.intakeTemperatureMarkup({ aggregate: 85, temperature: '\"><script>' }),
    /<script>/,
  );
  html = ctx.actions.intakeScoreMarkup({ ...score, cves: [{ id: 'CVE-2026-12345' }] });
  assert.equal(
    (html.match(/<td>Unknown<\/td>/g) || []).length,
    4,
    'Missing CVSS, KEV, EPSS and catalog state stay unknown.',
  );

  const lead = (id, day, intake_score) => ({
    id,
    domain: `${id}.com`,
    ips: ['8.8.8.8'],
    findings: ['CVE-2026-12345'],
    association_state: 'new',
    observations: 1,
    status: 'pending',
    observed_to: day,
    created_at: day,
    intake_score,
  });
  const rows = [
    lead('legacy', '2026-11-12'),
    lead('warm', '2026-11-11', { ...score, aggregate: 50, temperature: 'warm' }),
    lead('blazing', '2026-11-01', score),
  ];
  ctx.actions.api = async () => structuredClone(rows);
  html = await ctx.actions.pendingLeadsPage(new URLSearchParams());
  assert(html.indexOf('href="#leads/blazing"') < html.indexOf('href="#leads/warm"'));
  assert(html.indexOf('href="#leads/warm"') < html.indexOf('href="#leads/legacy"'));
  assert.match(html, /<option value="priority" selected>Highest priority/);
  assert.match(html, /Outreach priority/);
  assert.match(html, /Quality 84 · Urgency 86/);
  html = await ctx.actions.pendingLeadsPage(new URLSearchParams({ sort: 'latest' }));
  assert(html.indexOf('href="#leads/legacy"') < html.indexOf('href="#leads/blazing"'));
  assert.match(html, /<option value="latest" selected>Latest observation/);
  // Priority sorting applies before lens pagination, and remains in generated links.
  const large = Array.from({ length: 85 }, (_, index) => ({
    ...lead(`large-${index}`, '2026-11-12', { ...score, aggregate: index }),
    finding_kinds: index < 65 ? ['cve'] : ['eol'],
  }));
  ctx.actions.api = async () => structuredClone(large);
  html = await ctx.actions.pendingLeadsPage(new URLSearchParams({ lens: 'cve', page: '2' }));
  const rendered = [...html.matchAll(/href="#leads\/(large-\d+)"/g)].map((match) => match[1]);
  assert.equal(rendered.length, 25);
  assert.equal(rendered[0], 'large-24');
  assert.equal(rendered.at(-1), 'large-0');
  assert.match(html, /sort=priority&amp;page=1/);
  assert.match(html, /41–65 of 65/);
  assert.match(html, /Outreach priority: /);
  ctx.actions.api = async () => ({ ...rows[2], active_cases: [], entries: [] });
  html = await ctx.actions.pendingLeadPage('blazing');
  assert.match(html, /Why this temperature/);
  assert.match(html, /Source observations/);
  assert.match(html, /data-action="defer-lead"/);
  assert.match(html, /data-action="dismiss-lead"/);

  const imported = {
    id: 'import',
    status: 'done',
    name: 'Example.csv',
    rows_read: 100,
    valid_rows: 12,
    qualified: 3,
    config: {
      intake_stats: {
        ignored_empty_rows: 2,
        accretion: { admitted_rows: 12, context_rows: 3, filtered_rows: 88, leads: 4 },
      },
    },
  };
  html = ctx.actions.importRow(imported);
  assert.match(html, /9 eligible rows/);
  assert.match(html, /3 context rows/);
  assert.match(html, /88 rows filtered out/);
  assert.match(html, /4 root-domain groups/);
  assert.match(html, /3 published groups/);
  assert.match(html, /2 empty rows ignored/);
  assert.match(ctx.actions.importRow({ ...imported, config: '{}' }), /12 rows retained/);
  assert.doesNotMatch(ctx.actions.importRow({ ...imported, config: '{}' }), /filtered out/);
  assert.match(ctx.actions.accretionIntakeMarkup(), /Accretion/);
  assert.match(ctx.actions.accretionIntakeMarkup(), /Filter/);
  assert.match(ctx.actions.accretionIntakeMarkup(), /Qualify/);
  assert.match(ctx.actions.accretionIntakeMarkup(), /Evaluate/);
  const progress = (changes = {}) =>
    ctx.actions.accretionIntakeMarkup({
      current: {
        id: 'funnel',
        name: 'Funnel.csv',
        status: 'done',
        groups_total: 1,
        groups_done: 1,
        qualified: 0,
        jobs: { no_match: 1 },
        progress: { phase: 'complete', associated_groups: 1 },
        catalog_at_scoring: { state: 'missing' },
        ...changes,
      },
    });
  const stage = (markup, name) =>
    markup.match(new RegExp(`<li class="accretion-phase" data-stage="${name}"[^]*?</li>`))[0];
  const assertNotReached = (markup, name, label) => {
    const card = stage(markup, name);
    assert.match(card, /data-state="waiting"/);
    assert.match(card, new RegExp(`>0<small>${label}</small>`));
    assert.doesNotMatch(card, /Scored with limited|accretion-working/);
  };
  html = progress();
  assert.doesNotMatch(stage(html, 'filter'), /eligible rows/);
  assert.match(stage(html, 'qualify'), /data-state="complete"/);
  assert.match(stage(html, 'qualify'), /1 not qualified/);
  assertNotReached(html, 'evaluate', 'groups ranked');
  assertNotReached(html, 'associate', 'groups associated');
  assert.match(html, /No groups passed qualification/);
  html = progress({
    rows_read: 1400,
    valid_rows: 1380,
    stats: { admitted_rows: 1380, context_rows: 80, filtered_rows: 20 },
    groups_done: 408,
    groups_total: 408,
    jobs: { no_match: 408 },
  });
  assert.match(stage(html, 'filter'), /1,300 eligible rows/);
  assert.match(stage(html, 'filter'), /80 context rows/);
  assert.match(stage(html, 'filter'), /20 rows filtered out/);
  assert.match(stage(html, 'filter'), /408 root-domain groups/);
  assert.match(stage(html, 'qualify'), /408 \/ 408 root-domain groups checked/);
  assert.match(stage(html, 'qualify'), /408 not qualified/);
  html = progress({
    status: 'needs_retry',
    stage: 'Intake complete',
    jobs: { deferred: 408 },
    retry_reasons: { 'Capture browser could not start': 408 },
    groups_total: 408,
    groups_done: 408,
  });
  assert.match(html, /Qualification needs retry/);
  assert.doesNotMatch(html, /Intake complete/);
  assert.match(stage(html, 'qualify'), /Capture browser could not start · 408 groups/);
  assert.match(stage(html, 'qualify'), /408 to retry/);
  assert.doesNotMatch(stage(html, 'qualify'), /not qualified/);
  assert.match(
    ctx.actions.importRow({ ...imported, status: 'needs_retry', stage: 'Intake complete' }),
    /Qualification needs retry/,
  );
  for (const outcome of ['review', 'deferred']) {
    html = progress({
      jobs: { [outcome]: 1 },
      status: outcome === 'review' ? 'done' : 'needs_retry',
    });
    assert.match(stage(html, 'qualify'), /data-state="attention"/);
    assertNotReached(html, 'evaluate', 'groups ranked');
    assertNotReached(html, 'associate', 'groups associated');
    assert.match(html, /Unresolved groups wait for qualification/);
  }
  html = progress({ groups_total: 0, groups_done: 0, jobs: {} });
  assert.match(stage(html, 'qualify'), /data-state="waiting"/);
  assertNotReached(html, 'evaluate', 'groups ranked');
  assertNotReached(html, 'associate', 'groups associated');
  assert.match(html, /No groups passed filtering/);
  html = progress({
    groups_total: 2,
    groups_done: 2,
    qualified: 1,
    jobs: { qualified: 1, review: 1 },
    temperatures: { warm: 1 },
    progress: { phase: 'complete', associated_groups: 2 },
  });
  assert.match(stage(html, 'evaluate'), /data-state="attention"/);
  assert.match(stage(html, 'evaluate'), />1<small>groups ranked/);
  assert.match(stage(html, 'associate'), /data-state="attention"/);
  assert.match(stage(html, 'associate'), />1<small>groups associated/);
  html = progress({ qualified: 1, jobs: { qualified: 1 }, temperatures: { warm: 1 } });
  assert.match(stage(html, 'evaluate'), /data-state="complete"/);
  assert.match(stage(html, 'associate'), /data-state="complete"/);
  for (const status of ['running', 'error', 'paused']) {
    html = progress({
      status,
      qualified: 1,
      jobs: { qualified: 1 },
      temperatures: { warm: 1 },
      progress: { phase: 'complete', associated_groups: 1 },
    });
    assert.doesNotMatch(stage(html, 'qualify'), /data-state="complete"/);
    assert.doesNotMatch(stage(html, 'evaluate'), /data-state="complete"/);
    assert.doesNotMatch(stage(html, 'associate'), /data-state="complete"/);
  }
  for (const phase of ['evaluate', 'associate']) {
    html = progress({
      status: 'running',
      groups_done: 0,
      jobs: { pending: 1 },
      progress: { phase },
    });
    assert.match(stage(html, phase), /data-state="active"/);
  }
  console.log(
    'Accretion score snapshots, temperature ordering, unknown evidence, escaping, import accounting and qualification gates passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
