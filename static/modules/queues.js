/** Queues feature. Dependencies and mutable state are provided by the application context. */
export function install(ctx) {
  function leadTable(rows, filtered = false) {
    if (!rows.length)
      return ctx.actions.empty(
        filtered ? 'No businesses match these filters' : 'No business entities yet',
        filtered
          ? 'Clear the search or intelligence filter to see the rest of your queue.'
          : 'Import a report to find your next notification.',
        filtered
          ? ctx.actions.linkButton('#entities', 'Clear filters', '', 'search')
          : ctx.actions.linkButton('#data', 'Import a report'),
      );
    return `<div class="table-wrap"><table><thead><tr><th scope="col">Select</th><th scope="col">Organization / hostname</th><th scope="col">Reported finding</th><th scope="col">Assets</th><th scope="col">Notifications</th><th scope="col">Last activity</th><th scope="col">Actions</th></tr></thead><tbody>${rows.map((r, i) => `<tr class="clickable ${ctx.state.contacts.selectedEntityIds?.has(r.id) ? 'is-selected' : ''}" data-open-lead="${r.id}"><td><input type="checkbox" data-contact-select="${ctx.actions.esc(r.id)}" aria-label="Select ${ctx.actions.esc(r.company || r.domain)} for contact discovery" ${ctx.state.contacts.selectedEntityIds?.has(r.id) ? 'checked' : ''}></td><td><a class="business" href="#entity/${r.id}"><span class="business-avatar color-${i % 4}">${ctx.actions.esc((r.company || r.domain).slice(0, 2).toUpperCase())}</span><span><strong>${ctx.actions.esc(r.company || r.domain)}</strong><small>${ctx.actions.esc(r.company ? r.domain : 'Attribution recorded')}</small></span></a></td><td><span class="software">${ctx.actions.esc((r.versions || '').split(',')[0] || 'Version not reported')}</span><small>${ctx.actions.esc(/eol/i.test(r.tags) ? 'End-of-life software' : /cve-/i.test(r.tags) ? 'Reported CVE' : r.tags)}</small></td><td><strong>${ctx.actions.num(r.assets)}</strong><small>${ctx.actions.num(r.observations)} observations · ${ctx.actions.num(r.hostname_count)} hostnames</small></td><td>${ctx.actions.num(r.open_cases)} open / ${ctx.actions.num(r.case_count)} total${r.unassigned_observations ? `<small class="save-dirty">${ctx.actions.num(r.unassigned_observations)} observations awaiting review</small>` : ''}</td><td>${ctx.actions.date(r.updated_at)}</td><td class="row-end"><a class="button small" href="#entity/${encodeURIComponent(r.id)}?tab=contact" aria-label="Contacts for ${ctx.actions.esc(r.company || r.domain)}">Contacts</a></td></tr>`).join('')}</tbody></table></div>`;
  }

  function importConfig(r) {
    try {
      return typeof r.config === 'string' ? JSON.parse(r.config || '{}') : r.config || {};
    } catch {
      return {};
    }
  }

  function ignoredEmptyRows(r) {
    return Number(r.ignored_empty_rows ?? importConfig(r).intake_stats?.ignored_empty_rows ?? 0);
  }

  function accretionSummary(r) {
    const stats = importConfig(r).intake_stats?.accretion;
    return stats
      ? `<span>${ctx.actions.num(stats.admitted_rows)} admitted rows</span><span>${ctx.actions.num(stats.filtered_rows)} filtered out</span><span>${ctx.actions.num(stats.leads)} leads</span>`
      : `<span>${ctx.actions.num(r.valid_rows)} eligible rows</span>`;
  }

  function accretionIntakeMarkup(data = {}) {
    const esc = ctx.actions.esc,
      num = ctx.actions.num;
    const r = data.current,
      p = r?.progress || {},
      stats = r?.stats || {},
      jobs = r?.jobs || {};
    const busy = r && ['queued', 'running'].includes(r.status);
    const done = r?.status === 'done' || p.phase === 'complete';
    const read = p.read_rows ?? r?.rows_read ?? 0;
    const admitted = stats.admitted_rows ?? r?.valid_rows ?? 0;
    const excluded = stats.filtered_rows ?? p.filtered_rows ?? 0;
    const total = r?.groups_total || 0,
      checked = r?.groups_done || 0;
    const attributed = jobs.qualified || 0,
      review = jobs.review || 0,
      retry = jobs.deferred || 0;
    const temperatures = ['cool', 'warm', 'hot', 'blazing'];
    const ranked = temperatures.reduce((sum, key) => sum + Number(r?.temperatures?.[key] || 0), 0);
    const phaseStates = [
      p.filter_complete || total || done ? 'complete' : busy ? 'active' : 'waiting',
      review || retry
        ? 'attention'
        : done
          ? 'complete'
          : busy && p.phase === 'qualify'
            ? 'active'
            : 'waiting',
      done ? 'complete' : ranked || p.phase === 'urgency' ? 'active' : 'waiting',
      done ? 'complete' : p.phase === 'associate' ? 'active' : 'waiting',
    ];
    const card = (i, title, metric, label, description, content) =>
      `<li class="accretion-phase" data-stage="${['filter', 'qualify', 'urgency', 'associate'][i]}" data-state="${phaseStates[i]}"><div class="accretion-phase-top"><span>0${i + 1}</span><strong>${title}</strong><i aria-hidden="true"></i></div><div class="accretion-phase-number">${num(metric)}<small>${label}</small></div><p>${description}</p>${content}</li>`;
    const fraction = total ? Math.min(100, Math.max(0, (checked / total) * 100)) : 0;
    const catalog = data.catalog || {};
    const catalogWarnings = {
      missing: [
        'CVE catalog not downloaded',
        'Scores are limited to the available report and reference data. Critical vulnerabilities may receive similar priorities until the catalog is downloaded.',
      ],
      partial: [
        'CVE catalog download incomplete',
        'Only part of the local catalog is available. Finish the download before relying on lead temperatures.',
      ],
      unavailable: [
        'CVE catalog unavailable',
        'Local vulnerability scoring cannot be confirmed. Check the catalog before relying on lead temperatures.',
      ],
      stale: [
        'CVE catalog update overdue',
        'Stored CVEs remain available, but recent changes may be missing.',
      ],
    };
    const warning = catalogWarnings[catalog.state];
    const catalogNotice = warning
      ? `<div class="notice warn accretion-catalog-warning" role="status"><div><strong>${warning[0]}</strong><p>${warning[1]}</p></div><a class="button" href="#library" data-accretion-control="catalog">${catalog.state === 'missing' ? 'Download CVE catalog' : 'Open CVE catalog'}</a></div>`
      : '';
    const patterns = data.recent || {};
    const patternList = (values, empty) =>
      (values || [])
        .slice(0, 4)
        .map(
          (value) =>
            `<li><span>${esc(value.label)}</span><strong>${num(value.count)}</strong></li>`,
        )
        .join('') || `<li class="muted">${empty}</li>`;
    const stateText = !r
      ? 'Ready for reports'
      : r.status === 'error'
        ? 'Intake needs attention'
        : r.status === 'paused'
          ? 'Paused'
          : retry
            ? 'Lookup retry needed'
            : review
              ? 'Attribution review available'
              : busy
                ? r.stage
                : 'Intake complete';
    const controls = r
      ? `<button class="button small" data-import="${esc(r.id)}" data-accretion-control="details">Details</button>${busy ? `<button class="button small" data-pause="${esc(r.id)}" data-accretion-control="pause">Pause</button>` : ['paused', 'needs_retry', 'error'].includes(r.status) ? `<button class="button small" data-retry="${esc(r.id)}" data-accretion-control="resume">Resume import</button>` : ''}`
      : '';
    return `<section id="accretion-console" class="accretion-intake accretion-console" tabindex="-1"><div class="accretion-intake-title"><div><span class="dm-overline">Lead intake</span><h2>Accretion</h2></div><a class="text-link" href="#leads" data-accretion-control="leads">Ranked leads ${ctx.actions.icon('arrow')}</a></div>${catalogNotice}<div class="accretion-run"><div><strong>${r ? esc(r.name) : 'From incoming reports to focused outreach'}</strong><p data-accretion-live-status role="status" aria-live="polite">${busy ? '<span class="spinner" aria-hidden="true"></span>' : ''}${esc(stateText)}${data.queued ? ` · ${num(data.queued)} queued` : ''}</p></div><div class="actions">${controls}</div></div>${r?.error ? `<div class="notice warn">${esc(r.error)}</div>` : ''}<ol class="accretion-phases">${
      card(
        0,
        'Filter',
        read,
        'rows read',
        'Required fields, jurisdiction and finding eligibility.',
        `<div class="accretion-phase-stats"><span><b>${num(admitted)}</b> admitted</span><span><b>${num(excluded)}</b> filtered out</span></div>${phaseStates[0] === 'active' ? '<div class="accretion-working" aria-label="Reading and filtering source rows"></div>' : ''}`,
      ) +
      card(
        1,
        'Qualify',
        attributed,
        'groups attributed',
        'Reuse applicable history; examine new or changed endpoints.',
        `<div class="progress" role="progressbar" aria-label="Attribution groups checked" aria-valuemin="0" aria-valuemax="${Math.max(1, total)}" aria-valuenow="${Math.min(checked, Math.max(1, total))}"><span style="width:${fraction}%"></span></div><div class="accretion-phase-stats"><span>${num(checked)} / ${num(total)} checked</span>${p.reused_groups ? `<span>${num(p.reused_groups)} reused evidence</span>` : ''}${review ? `<a href="#attribution">${num(review)} to review</a>` : ''}${retry ? `<span>${num(retry)} to retry</span>` : ''}</div>`,
      ) +
      card(
        2,
        'Urgency',
        ranked,
        'groups ranked',
        'Combine evidence quality, vulnerability risk and agency priorities.',
        `<div class="accretion-temperatures">${temperatures.map((key) => `<span data-temperature="${key}"><i aria-hidden="true"></i>${key[0].toUpperCase() + key.slice(1)} <b>${num(r?.temperatures?.[key] || 0)}</b></span>`).join('')}</div>${r?.catalog_at_scoring && ['missing', 'partial', 'unavailable'].includes(r.catalog_at_scoring.state) ? '<p class="accretion-limited">Scored with limited local CVE coverage</p>' : ''}`,
      ) +
      card(
        3,
        'Associate',
        p.associated_groups ?? (done ? checked : 0),
        'groups processed',
        'Commit findings, repeat history and entity links without duplicating work.',
        `<div class="accretion-phase-stats"><span>${num(attributed)} attributed</span><span>${num(Math.max(0, checked - attributed))} unresolved</span></div>${phaseStates[3] === 'active' ? '<div class="accretion-working" aria-label="Associating observations with findings"></div>' : ''}`,
      )
    }</ol><details class="accretion-insights"><summary>Intake patterns <span>${num(patterns.files || 0)} recent source files</span></summary><p>${num(patterns.admitted_rows || 0)} admitted of ${num(patterns.source_rows || 0)} rows · latest evaluation per original file</p><div class="accretion-pattern-grid"><section><h3>Most common exclusions</h3><ul>${patternList(patterns.failures, 'No exclusions recorded')}</ul></section><section><h3>Accepted products</h3><ul>${patternList(patterns.products, 'No product details recorded')}</ul></section><section><h3>Accepted locations</h3><ul>${patternList(patterns.cities, 'No locations recorded')}</ul></section></div></details></section>`;
  }

  async function refreshAccretion() {
    const panel = ctx.actions.$('#accretion-console');
    if (!panel) return;
    const route = ctx.state.navigation.currentRoute;
    try {
      const data = await ctx.actions.api('/api/intake/progress');
      if (
        ctx.actions.$('#accretion-console') !== panel ||
        ctx.state.navigation.currentRoute !== route ||
        ctx.actions.$('#modal')?.open
      )
        return;
      const history = ctx.actions.$('#accretion-history');
      if (history?.open) {
        const rows = await ctx.actions.api('/api/imports');
        if (
          ctx.actions.$('#accretion-console') !== panel ||
          ctx.state.navigation.currentRoute !== route
        )
          return;
        const body = history.querySelector('.panel-body');
        if (body) body.innerHTML = rows.map(importRow).join('');
      }
      const expanded = !!panel.querySelector('.accretion-insights')?.open;
      const focused = panel.contains(document.activeElement)
        ? document.activeElement?.dataset?.accretionControl
        : null;
      const holder = document.createElement('div');
      holder.innerHTML = accretionIntakeMarkup(data);
      const replacement = holder.firstElementChild;
      const details = replacement.querySelector('.accretion-insights');
      if (details) details.open = expanded;
      panel.replaceWith(replacement);
      if (focused) replacement.querySelector(`[data-accretion-control="${focused}"]`)?.focus();
    } catch {
      if (
        ctx.actions.$('#accretion-console') === panel &&
        ctx.state.navigation.currentRoute === route
      ) {
        const status = panel.querySelector('[data-accretion-live-status]');
        if (status) status.textContent = 'Progress update unavailable · retrying automatically';
      }
    }
  }

  function importRow(r) {
    const progress =
      r.status === 'done'
        ? 100
        : r.groups_total
          ? Math.round((r.groups_done / r.groups_total) * 100)
          : 0;
    return `<div class="import-row"><div class="file-icon">${ctx.actions.icon('file')}</div><div class="import-info"><div class="import-title"><button class="text-button" data-import="${r.id}">${ctx.actions.esc(r.name)}</button>${ctx.actions.statusBadge(r.status)}</div><p>${ctx.actions.esc(r.stage)}${r.error ? ' · ' + ctx.actions.esc(r.error) : ''}</p>${r.status !== 'done' ? `<div class="progress"><span style="width:${progress}%"></span></div>` : ''}<div class="inline-stats"><span>${ctx.actions.num(r.rows_read)} observations</span>${ctx.actions.ignoredEmptyRows(r) ? `<span>${ctx.actions.num(ctx.actions.ignoredEmptyRows(r))} empty rows ignored</span>` : ''}${accretionSummary(r)}<span>${ctx.actions.num(r.qualified)} attributed groups</span></div></div></div>`;
  }

  function activities(items) {
    return items.length
      ? items
          .map(
            (e) =>
              `<div class="activity-row"><span class="activity-mark">${ctx.actions.icon(e.action === 'completed' ? 'check' : e.action === 'evidence_added' ? 'image' : 'clock')}</span><div>${e.lead_id ? `<a href="#${e.case_id ? 'workspace/notifications/' + e.case_id : 'entity/' + e.lead_id}">${ctx.actions.esc(e.detail)}</a>` : ctx.actions.esc(e.detail)}<small>${ctx.actions.stamp(e.created_at)}</small></div></div>`,
          )
          .join('')
      : '<p class="section-note">Activity appears as you work through notifications.</p>';
  }

  async function dashboard() {
    const [data, priorityWork] = await Promise.all([
      ctx.actions.api('/api/workspace/brief?as_of=' + ctx.actions.localDay()),
      ctx.actions.api('/api/workspace/queue?as_of=' + ctx.actions.localDay()),
    ]);
    const c = data.counts,
      w = data.workflow;
    const items = (priorityWork.items || []).slice(0, 8);
    const active = data.imports.find((r) => ['queued', 'running'].includes(r.status));
    const stages = [
      ['in_progress', 'In progress', 'var(--accent)'],
      ['pending_notification', 'Ready to notify', 'var(--dm-cyan)'],
      ['notification_completed', 'Awaiting closure', 'var(--dm-violet)'],
    ];
    const stageTotal = stages.reduce((sum, [key]) => sum + Number(w[key] || 0), 0);
    const leadRows = (data.leads || [])
      .map(
        (lead, index) =>
          `<a class="dm-priority-row dm-lead-row" data-temperature="${['cool', 'warm', 'hot', 'blazing'].includes(lead.intake_score?.temperature) ? lead.intake_score.temperature : 'unscored'}" href="#leads/${encodeURIComponent(lead.id)}"><span class="dm-rank">${String(index + 1).padStart(2, '0')}</span><div><strong>${ctx.actions.esc(lead.entity_name || lead.domain)}</strong><p>${ctx.actions.esc(lead.domain)}</p>${lead.intake_score ? ctx.actions.intakeTemperatureMarkup(lead.intake_score, { compact: true }) : ''}<span class="dm-next">Open lead ${ctx.actions.icon('arrow')}</span></div></a>`,
      )
      .join('');
    const priorityRows = items
      .map(
        (r, i) =>
          `<a class="dm-priority-row" data-temperature="${['cool', 'warm', 'hot', 'blazing'].includes(r.intake_score?.temperature) ? r.intake_score.temperature : 'unscored'}" href="${workspaceActionURL(r)}"><span class="dm-rank">${String(i + 1).padStart(2, '0')}</span><div><strong>${ctx.actions.esc(r.company || r.domain)}</strong><p>${ctx.actions.esc(r.domain)}${r.priority_reasons?.[0] ? ' · ' + ctx.actions.esc(r.priority_reasons[0]) : ''}</p><span class="dm-next">${ctx.actions.esc(r.suggested_action)} ${ctx.actions.icon('arrow')}</span>${r.intake_score ? ctx.actions.intakeTemperatureMarkup(r.intake_score, { compact: true }) : ''}</div>${ctx.actions.statusBadge(r.stage)}</a>`,
      )
      .join('');
    return `<div class="dm-workspace"><header class="dm-work-mast"><div><span class="dm-overline">${ctx.actions.esc(ctx.actions.date(ctx.actions.localDay()))}</span><h1>Workspace<span class="dm-live" aria-hidden="true"></span></h1></div>${ctx.actions.linkButton('#data', 'Import report', '', 'upload')}</header>
      <div class="dm-ledger" aria-label="Workspace totals"><a href="#leads"><strong>${ctx.actions.num(c.leads)}</strong><span>Leads</span></a><a href="#investigations"><strong>${ctx.actions.num(stageTotal)}</strong><span>Active investigations</span></a><a href="#workspace/notifications?due_before=${ctx.actions.localDay()}"><strong>${ctx.actions.num(w.due)}</strong><span>Follow-ups due</span></a><a href="#workspace/notifications?stage=closed"><strong>${ctx.actions.num(w.closed)}</strong><span>Completed</span></a></div>
      ${active ? `<a class="progress-notice" href="#data"><span class="spinner"></span><span>${ctx.actions.esc(active.name)} · ${ctx.actions.esc(active.stage)} · ${active.groups_done} / ${active.groups_total} hostname groups</span>${ctx.actions.icon('arrow')}</a>` : ''}
      <div class="dm-board"><section class="dm-work-index"><div class="dm-board-head"><h2>Priority work</h2><a href="#investigations" class="text-link">All investigations ${ctx.actions.icon('arrow')}</a></div><div class="dm-queue-meta"><span>${ctx.actions.num(priorityWork.total)} actionable</span><span>${ctx.actions.num(priorityWork.held)} held</span></div>${priorityRows || ctx.actions.empty('No work awaiting action', 'New findings begin in Leads. Saved investigations remain available.', ctx.actions.linkButton('#leads', 'Open leads', '', 'arrow'))}<details class="queue-explanation"><summary>How this list is ordered</summary><p class="section-note">${ctx.actions.esc(priorityWork.basis)}</p></details>${c.review ? `<a href="#attribution" class="dm-incoming"><span><strong>${ctx.actions.num(c.review)}</strong> attribution groups awaiting review</span>${ctx.actions.icon('arrow')}</a>` : ''}</section>
      <aside class="dm-board-aside"><section class="dm-lead-preview"><div class="dm-board-head"><h2>Leads</h2><a href="#leads" class="text-link">All leads ${ctx.actions.icon('arrow')}</a></div>${leadRows || '<p class="section-note">No qualified leads awaiting work.</p>'}</section><a class="dm-observe" href="#eclipse"><svg class="dm-eclipse-art" viewBox="0 0 420 260" aria-hidden="true"><defs><radialGradient id="dm-corona"><stop stop-color="#8be6df" stop-opacity=".8"/><stop offset=".4" stop-color="#9873f4" stop-opacity=".22"/><stop offset="1" stop-color="#9873f4" stop-opacity="0"/></radialGradient></defs><circle cx="300" cy="128" r="130" fill="url(#dm-corona)"/><g class="dm-orbit"><ellipse cx="300" cy="128" rx="113" ry="72" fill="none" stroke="#bba5ff" stroke-opacity=".5" transform="rotate(-38 300 128)"/><ellipse cx="300" cy="128" rx="96" ry="38" fill="none" stroke="#8be6df" stroke-opacity=".45" transform="rotate(35 300 128)"/><circle cx="215" cy="170" r="3" fill="#8be6df"/><circle cx="364" cy="71" r="3" fill="#bba5ff"/></g><circle cx="300" cy="128" r="61" fill="#080c12" stroke="#bba5ff" stroke-opacity=".8"/><path d="M279 72a61 61 0 0 0 14 116" fill="none" stroke="#d2fff7" stroke-width="2"/></svg><span class="dm-overline">Eclipse Observatory</span><h2>See the<br>Dark Matter.</h2><p>Explore the connections behind the work.</p><strong>Explore the field ${ctx.actions.icon('arrow')}</strong></a>
      <section class="dm-stage-strip"><div class="dm-board-head"><h2>In motion</h2><span>${ctx.actions.num(stageTotal)}</span></div><div class="dm-stage-band" aria-hidden="true">${stages.map(([key, , color]) => `<i style="width:${stageTotal ? (Number(w[key] || 0) / stageTotal) * 100 : 0}%;background:${color}"></i>`).join('')}</div><div class="dm-stage-legend">${stages.map(([key, label, color]) => `<a href="#workspace/notifications?stage=${key}"><i style="background:${color}"></i><strong>${ctx.actions.num(w[key])}</strong><span>${label}</span></a>`).join('')}</div></section>
      <section class="dm-mini-activity"><div class="dm-board-head"><h2>Recent activity</h2><a href="#activity" class="text-link">Activity ${ctx.actions.icon('arrow')}</a></div>${ctx.actions.activities(data.events.slice(0, 3))}</section></aside></div>
      </div>`;
  }

  function workspaceActionURL(row) {
    const tab = ['notification', 'assets', 'contact', 'closing', 'activity'].includes(
      row.action_tab,
    )
      ? row.action_tab
      : 'notification';
    const section =
      tab === 'notification' && ctx.constants.reportSections.includes(row.action_section)
        ? '&section=' + encodeURIComponent(row.action_section)
        : '';
    return '#workspace/notifications/' + encodeURIComponent(row.id) + '?tab=' + tab + section;
  }

  function workspaceActionTable(rows) {
    if (!rows.length)
      return ctx.actions.empty(
        'No action due',
        'Held and closed records return here when their reconsideration date arrives. You can still review all notifications.',
        ctx.actions.linkButton('#workspace/notifications', 'View all notifications', '', 'file'),
      );
    return `<div class="table-wrap"><table class="workspace-action-table" role="table" aria-label="Suggested next actions"><thead><tr role="row"><th scope="col">Business / notification</th><th scope="col">Why now</th><th scope="col">Next action</th><th scope="col">Status</th></tr></thead><tbody>${rows.map((r) => `<tr role="row"><td role="cell" data-label="Business / notification"><a class="text-link" href="${workspaceActionURL(r)}"><strong>${ctx.actions.esc(r.company || r.domain)}</strong></a><small>${ctx.actions.esc(r.title)}</small>${r.intake_score ? ctx.actions.intakeTemperatureMarkup(r.intake_score, { compact: true }) : ''}</td><td role="cell" data-label="Why now">${r.priority_reasons.map((reason) => `<small>${ctx.actions.esc(reason)}</small>`).join('')}</td><td role="cell" data-label="Next action"><a class="text-link" href="${workspaceActionURL(r)}">${ctx.actions.esc(r.suggested_action)}</a></td><td role="cell" data-label="Status">${ctx.actions.statusBadge(r.stage)}${r.outreach_policy.state !== 'active' ? `<small class="save-dirty">${ctx.actions.esc(r.outreach_policy.state.replaceAll('_', ' '))} · ${ctx.actions.esc(r.outreach_policy.reason)}</small>` : ''}</td></tr>`).join('')}</tbody></table></div>`;
  }

  function bars(values, ic) {
    const total = Object.values(values).reduce((a, b) => a + b, 0);
    return (
      Object.entries(values)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)
        .map(
          ([name, count]) =>
            `<div class="region-row"><div>${ctx.actions.icon(ic)}<span>${ctx.actions.esc(name)}</span><strong>${ctx.actions.num(count)}</strong></div><div class="progress"><span style="width:${total ? (count / total) * 100 : 0}%"></span></div></div>`,
        )
        .join('') || '<p class="section-note">Available after your first qualified lead.</p>'
    );
  }

  async function leadsPage(params) {
    const q = params.get('q') || '',
      signal = params.get('signal') || 'all';
    const allRows = await ctx.actions.api('/api/leads?' + new URLSearchParams({ q }));
    const rows = allRows.filter((r) =>
      signal === 'kev'
        ? r.kev === true
        : signal === 'ransomware'
          ? ctx.actions.hasKnownRansomware(r)
          : true,
    );
    ctx.state.contacts.batchEntityIds = rows.map((row) => row.id);
    ctx.state.contacts.selectedEntityIds ||= new Set();
    for (const row of rows)
      ctx.state.contacts.entityNames.set(row.id, row.company || row.domain || 'Business entity');
    return (
      ctx.actions.heading(
        'Entities',
        '',
        ctx.actions.linkButton('#workspace/notifications', 'Notifications', '', 'file'),
      ) +
      ctx.actions.contactBatchMarkup() +
      `<section class="panel"><div class="filter-bar"><span>${ctx.actions.num(rows.length)} business ${rows.length === 1 ? 'entity' : 'entities'}</span><form id="lead-search" class="input-search">${ctx.actions.icon('search')}<input name="q" aria-label="Search businesses" placeholder="Search company or hostname…" value="${ctx.actions.esc(q)}"><select name="signal" aria-label="Filter business intelligence" data-submit-filter>${ctx.actions.signalOptions(signal)}</select><button class="button small" type="submit">Apply</button></form></div>${ctx.actions.leadTable(rows, !!q || signal !== 'all')}</section>`
    );
  }

  async function importsPage(params = new URLSearchParams()) {
    const apiTab = params.get('tab') !== 'files';
    const progress = await ctx.actions.api('/api/intake/progress');
    const tabs = `<nav class="tabs record-tabs" aria-label="Data acquisition"><a class="tab ${apiTab ? 'active' : ''}" href="#data?tab=api" ${apiTab ? 'aria-current="page"' : ''}>API</a><a class="tab ${!apiTab ? 'active' : ''}" href="#data?tab=files" ${!apiTab ? 'aria-current="page"' : ''}>Files</a></nav>`;
    if (apiTab) {
      await ctx.actions.loadApiAcquisition();
      return (
        ctx.actions.heading('Shadowserver Data', '') +
        tabs +
        accretionIntakeMarkup(progress) +
        ctx.actions.apiAcquisitionMarkup()
      );
    }
    const rows = await ctx.actions.api('/api/imports');
    return (
      ctx.actions.heading(
        'Shadowserver Data',
        '',
        `<button class="button" data-action="scan">${ctx.actions.icon('refresh')}Check inbox</button>`,
      ) +
      tabs +
      accretionIntakeMarkup(progress) +
      `<section class="dropzone" id="dropzone"><div class="empty-icon">${ctx.actions.icon('upload')}</div><h2>Import report files</h2><p>Drop workbooks here, or select files from your computer.</p><label class="button primary" for="report-files">${ctx.actions.icon('plus')}Choose reports</label><input class="upload-hidden" id="report-files" type="file" accept=".xlsx,.xlsm,.csv,.csv.gz" multiple><small>XLSX, XLSM, CSV or CSV.gz · up to 50 MiB each · original files preserved</small></section>` +
      `<div class="notice">${ctx.actions.icon('file')}<div>Or place reports in <code>${ctx.actions.esc(ctx.state.navigation.boot.workspace)}${ctx.state.navigation.boot.workspace.includes('\\') ? '\\' : '/'}inbox</code>. ${ctx.state.navigation.boot.settings.watch_inbox ? 'The inbox is checked automatically every 30 seconds.' : 'Automatic checks are off in Settings.'}</div></div>` +
      `<details id="accretion-history" class="panel accretion-history"><summary>Import history <span class="badge gray">${rows.length} imports</span></summary><div class="panel-body">${rows.map(ctx.actions.importRow).join('') || '<p class="section-note">No reports imported yet.</p>'}</div></details>`
    );
  }

  async function showImport(id) {
    const r = await ctx.actions.api('/api/imports/' + id),
      reasons = JSON.parse(r.rejected || '{}');
    const config = typeof r.config === 'string' ? JSON.parse(r.config || '{}') : r.config || {};
    const profiles = config.report_profiles || [];
    const rejectionExamples = config.intake_stats?.rejection_examples || {};
    const acquisition = r.acquisition;
    ctx.actions.modal(
      r.name,
      `<div class="inline-stats">${ctx.actions.statusBadge(r.status)}<span>${ctx.actions.num(r.rows_read)} observations</span>${ctx.actions.ignoredEmptyRows(r) ? `<span>${ctx.actions.num(ctx.actions.ignoredEmptyRows(r))} empty rows ignored</span>` : ''}${accretionSummary(r)}<span>${ctx.actions.num(r.qualified)} attributed groups</span></div><p>${ctx.actions.esc(r.message || r.stage)}</p>${r.error ? `<div class="notice warn">${ctx.actions.esc(r.error)}</div>` : ''}${profiles.length ? `<h3>Report interpretation</h3><div class="key-value">${profiles.map((p) => `<span>${ctx.actions.esc(p.name || p.id)}</span><strong>${ctx.actions.esc(p.capability_label || (p.capability === 'eligible' ? 'Eligible profile' : p.capability === 'interpreted' ? 'Interpreted' : 'Retained only'))}</strong>`).join('')}</div><details><summary>Report types and interpretation</summary><pre>${ctx.actions.esc(JSON.stringify({ profiles, inventory: config.profile_inventory }, null, 2))}</pre></details>` : ''}${acquisition ? `<h3>Acquisition dates</h3><div class="key-value"><span>Report date</span><strong>${ctx.actions.esc(acquisition.report_date || 'Not recorded')}</strong><span>Retrieved</span><strong>${ctx.actions.esc(acquisition.retrieved_at || 'Not recorded')}</strong><span>Catalog coverage</span><strong>${ctx.actions.esc(acquisition.catalog_coverage || 'Unknown')}</strong></div>` : ''}<h3>Accretion · Filter</h3>${
        Object.entries(reasons).length
          ? `<div class="key-value">${Object.entries(reasons)
              .map(
                ([key, value]) =>
                  `<span>${ctx.actions.esc(key.replaceAll('_', ' '))}</span><strong>${ctx.actions.num(value)}</strong>`,
              )
              .join('')}</div>`
          : '<p class="muted">No exclusions recorded.</p>'
      }${
        Object.keys(rejectionExamples).length
          ? `<details><summary>Examples of excluded rows</summary>${Object.entries(
              rejectionExamples,
            )
              .map(
                ([reason, examples]) =>
                  `<h4>${ctx.actions.esc(reason.replaceAll('_', ' '))}</h4><pre>${ctx.actions.esc(JSON.stringify(examples, null, 2))}</pre>`,
              )
              .join('')}</details>`
          : ''
      }${config.schema_observation ? `<details><summary>Source field details</summary><pre>${ctx.actions.esc(JSON.stringify(config.schema_observation, null, 2))}</pre></details>` : ''}<h3>Hostname groups</h3><div class="table-wrap"><table><thead><tr><th scope="col">Root domain</th><th scope="col">Result</th><th scope="col">Lookups</th></tr></thead><tbody>${r.groups.map((g) => `<tr><td><button class="text-button" data-group="${g.id}">${ctx.actions.esc(g.domain)}</button>${g.error ? `<small>${ctx.actions.esc(g.error)}</small>` : ''}</td><td>${ctx.actions.statusBadge(g.status)}</td><td>${JSON.parse(g.attempts).length}</td></tr>`).join('')}</tbody></table></div><details><summary>Original file fingerprint</summary><pre>${ctx.actions.esc(r.sha256)}</pre></details><div class="modal-actions"><a class="button" href="/api/imports/${r.id}/original">${ctx.actions.icon('download')}Original file</a>${!['running', 'queued'].includes(r.status) ? `<button class="button" data-reevaluate-import="${r.id}">Re-evaluate import</button>` : ''}${['running', 'queued'].includes(r.status) ? `<button class="button" data-pause="${r.id}">Pause after current group</button>` : ['paused', 'needs_retry', 'error'].includes(r.status) ? `<button class="button primary" data-retry="${r.id}">Resume import</button>` : ''}</div>`,
    );
  }

  async function upload(files) {
    if (!files.length) return;
    const data = new FormData();
    [...files].forEach((f) => data.append('files', f));
    ctx.actions.modal(
      'Adding reports',
      '<div class="initial-loading"><span class="spinner"></span>Preserving originals and queuing Accretion…</div>',
    );
    try {
      const results = await ctx.actions.api('/api/imports', { method: 'POST', body: data });
      ctx.actions.closeModal();
      for (const r of results)
        ctx.actions.toast(
          r.error
            ? `${r.name}: ${r.error}`
            : `${r.name}: ${r.duplicate ? 'already imported' : 'queued for Accretion'}`,
          !!r.error,
        );
      await ctx.actions.route(true);
    } catch (e) {
      ctx.actions.closeModal();
      ctx.actions.toast(e.message, true);
    }
  }

  async function reportsPage() {
    const rows = await ctx.actions.api('/api/reports');
    return (
      ctx.actions.heading(
        'Packages',
        '',
        `<span class="dm-overline">${ctx.actions.num(rows.length)} certified revisions</span>`,
      ) +
      `<section class="dm-packages">${rows.length ? rows.map((r) => `<article class="dm-package-row"><div class="dm-package-identity"><span class="dm-overline">Revision ${ctx.actions.num(r.revision)} · ${ctx.actions.date(r.created_at)}</span><h2><a href="#workspace/notifications/${encodeURIComponent(r.case_id)}">${ctx.actions.esc(r.company || r.domain)}</a></h2><p>${ctx.actions.esc(r.domain)}</p>${r.sent_at ? `<span class="badge green">Delivery recorded · ${ctx.actions.date(r.sent_at)}</span>` : '<span class="badge gray">Delivery not recorded</span>'}</div>${r.files_available ? `<div class="dm-package-download"><span class="dm-overline">Recipient</span><a class="button primary" href="/api/reports/${r.id}/recipient-zip">${ctx.actions.icon('download')}Recipient package</a><div><a class="text-link" href="/api/reports/${r.id}/pdf" target="_blank" rel="noopener">PDF</a><a class="text-link" href="/api/reports/${r.id}/docx">DOCX</a></div>${r.supporting_appendix_available ? `<details><summary>Separate appendix</summary><a class="text-link" href="/api/reports/${r.id}/appendix-pdf" target="_blank" rel="noopener">PDF</a><a class="text-link" href="/api/reports/${r.id}/appendix-docx">DOCX</a></details>` : ''}</div><div class="dm-package-download"><span class="dm-overline">Internal record</span><a class="button" href="/api/reports/${r.id}/zip">${ctx.actions.icon('download')}Evidence &amp; records</a><p>Searchable reader, source records and chronology.</p></div>` : '<div class="notice warn">Package files missing. Restore from backup.</div>'}</article>`).join('') : ctx.actions.empty('No certified reports yet', 'Certify a reviewed draft to save its PDF, DOCX, evidence and source snapshot.', ctx.actions.linkButton('#investigations', 'Open investigations'))}</section>`
    );
  }

  function wireDropzone() {
    const el = ctx.actions.$('#dropzone');
    if (!el) return;
    el.addEventListener('dragover', (e) => {
      e.preventDefault();
      el.classList.add('drag');
    });
    el.addEventListener('dragleave', () => el.classList.remove('drag'));
    el.addEventListener('drop', (e) => {
      e.preventDefault();
      el.classList.remove('drag');
      ctx.actions.upload(e.dataTransfer.files);
    });
  }
  Object.assign(ctx.actions, {
    leadTable,
    ignoredEmptyRows,
    accretionSummary,
    accretionIntakeMarkup,
    refreshAccretion,
    importRow,
    activities,
    dashboard,
    workspaceActionTable,
    workspaceActionURL,
    bars,
    leadsPage,
    importsPage,
    showImport,
    upload,
    reportsPage,
    wireDropzone,
  });
}
