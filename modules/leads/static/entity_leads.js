import { observedVersion } from '../../ui/static/shared.js';
import { entityName } from '../../entities/static/entities.js';
/** Qualified lead queue, priority and explicit investigation-start presentation. No startup requests or event listeners are installed here. */
export function install(ctx) {
  const esc = (value) => ctx.actions.esc(value ?? '');

  const encode = encodeURIComponent;

  const list = (value) => (Array.isArray(value) ? value : []);

  const temperatures = { cool: 'Cool', warm: 'Warm', hot: 'Hot', blazing: 'Blazing' };

  const scoreNumber = (value) =>
    typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100
      ? value
      : null;

  const scoreText = (value) => scoreNumber(value) ?? '—';

  function intakeTemperatureMarkup(score, { compact = false } = {}) {
    const temperature = Object.hasOwn(temperatures, score?.temperature)
      ? score.temperature
      : 'unscored';
    if (temperature === 'unscored' || scoreNumber(score?.aggregate) === null)
      return '<span class="intake-temperature" data-temperature="unscored">Unscored</span>';
    return `<span class="intake-temperature" data-temperature="${temperature}" title="Outreach priority · ${scoreText(score.aggregate)} / 100"><i aria-hidden="true"></i><span class="dossier-sr-only">Outreach priority: </span>${temperatures[temperature]}${compact ? '' : `<strong>${scoreText(score.aggregate)}</strong>`}</span>`;
  }

  function intakeScoreMarkup(score) {
    if (scoreNumber(score?.aggregate) === null)
      return '<section class="accretion-score accretion-unscored"><h2>Accretion</h2><span class="intake-temperature" data-temperature="unscored">Unscored</span><p>No intake score was saved for this lead.</p></section>';
    const factorTable = (key, title) =>
      `<section class="accretion-factor-group"><h3>${title}</h3><div class="table-wrap"><table><thead><tr><th>Factor</th><th>Points</th><th>Basis</th></tr></thead><tbody>${list(
        score.factors?.[key],
      )
        .map(
          (factor) =>
            `<tr><td>${esc(factor.label)}</td><td>${scoreText(factor.points)} / ${scoreText(factor.weight)}</td><td>${esc(factor.reason)}</td></tr>`,
        )
        .join('')}</tbody></table></div></section>`;
    return `<section class="accretion-score" data-temperature="${Object.hasOwn(temperatures, score.temperature) ? score.temperature : 'unscored'}"><div class="accretion-score-head"><h2>Accretion</h2>${intakeTemperatureMarkup(score)}</div><dl class="accretion-metrics"><div><dt>Quality</dt><dd>${scoreText(score.quality)}<small>/ 100</small></dd></div><div><dt>Urgency</dt><dd>${scoreText(score.urgency)}<small>/ 100</small></dd></div><div><dt>Aggregate</dt><dd>${scoreText(score.aggregate)}<small>/ 100</small></dd></div></dl><details class="accretion-explanation"><summary>Why this temperature</summary><p class="section-note">Temperature ranks outreach priority from Quality and Urgency.</p>${list(
      score.ranking_adjustments,
    )
      .map(
        (a) =>
          `<p class="notice"><strong>${esc(a.label)}</strong> · ${Number.isFinite(a.multiplier) ? Math.round((1 - a.multiplier) * 100) : '—'}% rank reduction. ${esc(a.reason)}</p>`,
      )
      .join(
        '',
      )}${factorTable('quality', 'Quality')}${factorTable('urgency', 'Urgency')}${score.strongest_finding?.id ? `<p>Strongest urgency signal: <strong>${esc(score.strongest_finding.id)}</strong> · ${esc({ local_cve: 'Local CVE catalog', reported_severity: 'Reported severity' }[score.strongest_finding.basis] || String(score.strongest_finding.basis || '').replaceAll('_', ' '))}</p>` : ''}${list(score.warnings).length ? `<ul class="accretion-warnings">${score.warnings.map((warning) => `<li>${esc(warning)}</li>`).join('')}</ul>` : ''}${
      list(score.cves).length
        ? `<details><summary>Local CVE evidence · ${score.cves.length}</summary><div class="table-wrap"><table><thead><tr><th>CVE</th><th>CVSS</th><th>KEV</th><th>EPSS</th><th>Catalog</th></tr></thead><tbody>${score.cves
            .map(
              (record) =>
                `<tr><td>${esc(record.id)}</td><td>${scoreNumber(record.cvss) === null ? 'Unknown' : scoreText(record.cvss)}</td><td>${record.kev?.listed === true ? 'Listed' : record.kev?.listed === false ? 'Not listed' : 'Unknown'}</td><td>${typeof record.epss?.score === 'number' && record.epss.score >= 0 && record.epss.score <= 1 ? (record.epss.score * 100).toFixed(2) + '%' : 'Unknown'}</td><td>${esc(record.status || 'Unknown')}${record.catalog_stale ? '<small>Refresh due</small>' : ''}${list(
                  record.warnings,
                )
                  .map((warning) => `<small>${esc(warning)}</small>`)
                  .join('')}</td></tr>`,
            )
            .join('')}</tbody></table></div></details>`
        : ''
    }<p class="section-note">Policy ${esc(score.policy_version ?? '—')} · ${score.scored_at ? ctx.actions.stamp(score.scored_at) : 'Scoring date not recorded'}</p><details><summary>Saved scoring record</summary><pre>${esc(JSON.stringify(score, null, 2))}</pre></details></details></section>`;
  }

  function association(lead) {
    if (lead.association_state === 'review')
      return '<span class="badge amber">Match needs review</span>';
    if (lead.association_state === 'new')
      return `${lead.entity_id ? `<a class="text-link" href="#entity/${encode(lead.entity_id)}">${esc(lead.entity_name || lead.domain)}</a> ` : ''}<span class="badge gray">New entity</span>`;
    return lead.entity_id
      ? `<a class="text-link" href="#entity/${encode(lead.entity_id)}">${esc(lead.entity_name || lead.domain)}</a>`
      : '<span class="badge gray">New entity</span>';
  }

  function websiteMarkup(lead, { compact = false } = {}) {
    const capture = lead.website;
    if (!capture?.id || !/^https?:\/\//i.test(capture.final_url || ''))
      return '<span class="dossier-quiet">Website screenshot unavailable</span>';
    const image = '/api/website-evidence/' + encode(capture.id) + '/image';
    return `<figure class="lead-website${compact ? ' lead-website-compact' : ''}"><a href="${esc(image)}" target="_blank" rel="noopener noreferrer" aria-label="View retained website screenshot for ${esc(lead.domain)}"><img src="${esc(image)}" alt="Website captured for ${esc(lead.domain)}" width="${compact ? 144 : 480}" height="${compact ? 90 : 300}" loading="lazy"></a><figcaption><a class="text-link" href="${esc(capture.final_url)}" target="_blank" rel="noopener noreferrer">Open website</a>${compact ? '' : `<small>Captured ${ctx.actions.stamp(capture.captured_at)}</small>`}</figcaption></figure>`;
  }

  async function pendingLeadsPage(params = new URLSearchParams()) {
    const q = params.get('q') || '',
      status = params.get('status') || 'pending';
    const all = await ctx.actions.api('/api/pending-leads?' + new URLSearchParams({ q, status }));
    const lenses = [
      ['all', 'All', () => true],
      ['known', 'Known entity', (r) => r.association_state === 'known'],
      ['new', 'New entity', (r) => r.association_state === 'new'],
    ];
    const lens = lenses.find((item) => item[0] === params.get('lens')) || lenses[0];
    const sort = ['priority', 'latest', 'oldest', 'observations'].includes(params.get('sort'))
      ? params.get('sort')
      : 'priority';
    const filtered = all
      .filter(lens[2])
      .sort((a, b) =>
        sort === 'priority'
          ? (scoreNumber(b.intake_score?.aggregate) ?? -1) -
            (scoreNumber(a.intake_score?.aggregate) ?? -1)
          : sort === 'observations'
            ? b.observations - a.observations || a.domain.localeCompare(b.domain)
            : (sort === 'oldest' ? 1 : -1) *
                (a.observed_to || a.created_at || '').localeCompare(
                  b.observed_to || b.created_at || '',
                ) || a.id.localeCompare(b.id),
      );
    const totalPages = Math.max(1, Math.ceil(filtered.length / 40));
    const page = Math.min(
      totalPages,
      Math.max(1, Number.parseInt(params.get('page') || '1', 10) || 1),
    );
    const rows = filtered.slice((page - 1) * 40, page * 40);
    const url = (changes) =>
      '#leads?' + new URLSearchParams({ q, status, lens: lens[0], sort, ...changes });
    const pagination = `<div class="queue-page"><span>${filtered.length ? `${(page - 1) * 40 + 1}–${Math.min(page * 40, filtered.length)} of ${ctx.actions.num(filtered.length)}` : '0 leads'} · Page ${page} of ${totalPages}</span><div class="actions">${page > 1 ? `<a class="button small" href="${esc(url({ page: page - 1 }))}">Previous</a>` : '<button class="button small" disabled>Previous</button>'}${page < totalPages ? `<a class="button small" href="${esc(url({ page: page + 1 }))}">Next</a>` : '<button class="button small" disabled>Next</button>'}</div></div>`;
    return (
      '<section class="dossier-index lead-index">' +
      ctx.actions.heading(
        'Leads',
        '',
        ctx.actions.linkButton('#data', 'Import reports', '', 'upload') +
          '<button class="button" data-action="refresh-leads">Refresh</button>',
      ) +
      `<nav class="lead-lenses" aria-label="Lead lenses">${lenses.map(([key, label, predicate]) => `<a class="${lens[0] === key ? 'active' : ''}" href="${esc(url({ lens: key, page: 1 }))}" ${lens[0] === key ? 'aria-current="page"' : ''}>${label}<strong>${ctx.actions.num(all.filter(predicate).length)}</strong></a>`).join('')}</nav>` +
      `<section class="lead-index-body"><div class="filter-bar dossier-index-tools"><span>${ctx.actions.num(filtered.length)} leads</span><form id="pending-lead-search" class="dossier-filter-form"><input name="q" value="${esc(q)}" aria-label="Search leads" placeholder="Hostname, IP or finding…"><input type="hidden" name="lens" value="${esc(lens[0])}"><select name="status" aria-label="Lead status" data-submit-filter>${[
        ['pending', 'Awaiting action'],
        ['deferred', 'Deferred'],
      ]
        .map(
          ([value, label]) =>
            `<option value="${value}" ${value === status ? 'selected' : ''}>${label}</option>`,
        )
        .join('')}</select><select name="sort" aria-label="Sort leads" data-submit-filter>${[
        ['priority', 'Highest priority'],
        ['latest', 'Latest observation'],
        ['oldest', 'Oldest observation'],
        ['observations', 'Most observations'],
      ]
        .map(
          ([value, label]) =>
            `<option value="${value}" ${value === sort ? 'selected' : ''}>${label}</option>`,
        )
        .join(
          '',
        )}</select><button type="submit" class="button small">Search</button></form></div>${rows.length ? `<div class="table-wrap dossier-directory lead-directory"><table><thead><tr><th>Reported hostname</th><th>Website</th><th>Outreach priority</th><th>Finding</th><th>Entity</th><th>Observations</th><th></th></tr></thead><tbody>${rows.map((r) => `<tr class="intake-priority-row" data-temperature="${Object.hasOwn(temperatures, r.intake_score?.temperature) ? r.intake_score.temperature : 'unscored'}"><td><a class="text-link" href="#leads/${encode(r.id)}"><strong>${esc(r.domain)}</strong></a><small>${list(r.ips).map(esc).join(', ')}</small></td><td>${websiteMarkup(r, { compact: true })}</td><td>${intakeTemperatureMarkup(r.intake_score)}${scoreNumber(r.intake_score?.aggregate) !== null ? `<small class="intake-score-pair">Quality ${scoreText(r.intake_score.quality)} · Urgency ${scoreText(r.intake_score.urgency)}</small>` : ''}</td><td>${list(r.findings).slice(0, 3).map(esc).join('<br>')}${list(r.findings).length > 3 ? `<small>+${r.findings.length - 3} more</small>` : ''}</td><td>${association(r)}<small>${esc(r.association_basis)}</small></td><td>${ctx.actions.num(r.observations)}<small>${ctx.actions.date(r.observed_to)}</small></td><td><button class="text-button" data-action="ignore-queue-lead" data-lead="${esc(r.id)}" data-revision="${esc(r.revision)}">Ignore</button></td></tr>`).join('')}</tbody></table></div>` : ctx.actions.empty('No leads in this view', '', ctx.actions.linkButton('#leads', 'Clear filters'))}${pagination}</section></section>`
    );
  }

  async function pendingLeadPage(id) {
    const renderId = ctx.state.navigation.renderId;
    const lead = await ctx.actions.api('/api/pending-leads/' + encode(id));
    if (renderId !== ctx.state.navigation.renderId) return '';
    ctx.state.intakeLeads.current = lead;
    if (lead.superseded_by || lead.suppression_reason) {
      return ctx.actions.empty(
        'This lead is no longer current',
        'Its admitted findings and source history remain in the entity record.',
        ctx.actions.linkButton(
          lead.superseded_by ? '#leads/' + encode(lead.superseded_by) : '#leads',
          'Current leads',
        ),
      );
    }
    const back = ctx.state.navigation.returns.get('leads') || 'leads';
    const active = list(lead.active_cases).filter((c) => c.stage === 'in_progress');
    const frozen = list(lead.active_cases).find((c) => c.stage === 'pending_notification');
    const actions = lead.can_start
      ? active.length
        ? `<form id="lead-start-form" class="actions" data-lead="${esc(lead.id)}"><select name="case_id" aria-label="Active notification">${active.map((c) => `<option value="${esc(c.id)}">${esc(c.title)}</option>`).join('')}</select><button class="button primary" type="submit">Add to active notification</button></form>`
        : frozen
          ? `<a class="button" href="#workspace/notifications/${encode(frozen.id)}">Open active notification</a>`
          : `<button class="button primary" data-action="start-lead">Start notification</button>`
      : lead.job_id
        ? `<button class="button" data-group="${esc(lead.job_id)}">Attribution</button>`
        : '';
    return (
      `<section class="lead-dossier"><a class="page-back" href="#${esc(back)}">${ctx.actions.icon('back')}Leads</a>` +
      ctx.actions.heading(esc(lead.domain), '', actions) +
      websiteMarkup(lead) +
      intakeScoreMarkup(lead.intake_score) +
      (lead.delta
        ? `<p class="section-note">${ctx.actions.num(lead.delta.new || 0)} new · ${ctx.actions.num(lead.delta.repeated || 0)} recurring · ${ctx.actions.num(lead.delta.retired || 0)} retired findings</p>`
        : '') +
      ctx.actions.sharedIpMarkup(lead.shared_ip_associations) +
      `<section class="panel"><div class="panel-body"><div class="lead-association"><h2>${association(lead)}</h2><p>${esc(lead.association_basis)}</p></div>${lead.association_state === 'review' && list(lead.candidate_entities).length ? `<form id="lead-associate-form" class="actions"><select name="entity_id" aria-label="Associate entity" required><option value="">Select entity</option>${lead.candidate_entities.map((e) => `<option value="${esc(e.id)}">${esc(entityName(e))}</option>`).join('')}</select><button class="button" type="submit">Associate</button></form>` : ''}<div class="key-value"><span>Findings</span><strong>${list(lead.findings).map(esc).join(', ') || 'Not recorded'}</strong><span>Hostnames</span><strong>${list(lead.hostnames).map(esc).join(', ')}</strong><span>IPs</span><strong>${list(lead.ips).map(esc).join(', ')}</strong><span>Observed</span><strong>${ctx.actions.date(lead.observed_from)} – ${ctx.actions.date(lead.observed_to)}</strong><span>Attribution</span><strong>${ctx.actions.statusBadge(lead.attribution_status)}</strong><span>Source</span><strong>${lead.import_id ? `<button class="text-button" data-import="${esc(lead.import_id)}">${esc(lead.import_name)}</button>` : esc(lead.import_name)}</strong></div></div></section>` +
      `<section class="panel"><div class="panel-head"><h2>Source observations</h2><span>${ctx.actions.num(lead.observations)}</span></div><div class="table-wrap"><table><thead><tr><th>Hostname</th><th>IP</th><th>Finding / version</th><th>Observed</th><th>Source row</th></tr></thead><tbody>${list(
        lead.entries,
      )
        .map((entry) => {
          const f = entry.source?.fields || entry.normalized || entry;
          return `<tr><td>${esc(entry.hostname || f.hostname)}</td><td>${esc(entry.ip || f.ip)}</td><td>${esc(entry.tag || f.tag)}<small>${esc(observedVersion(entry))}</small></td><td>${esc(entry.observed_at || f.timestamp)}</td><td>${esc(entry.source?.sheet || '')} ${esc(entry.source?.row || entry.row || '')}</td></tr>`;
        })
        .join(
          '',
        )}</tbody></table></div></section><div class="actions lead-disposition">${lead.status === 'pending' ? '<button class="button" data-action="defer-lead">Defer</button><button class="text-button" data-action="dismiss-lead">Ignore</button>' : '<button class="button" data-action="restore-lead">Return to leads</button>'}</div></section>`
    );
  }
  const actions = { intakeTemperatureMarkup, intakeScoreMarkup, pendingLeadsPage, pendingLeadPage };
  Object.assign(ctx.actions, actions);
  return actions;
}
