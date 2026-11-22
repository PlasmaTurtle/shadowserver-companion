/** Workspace dashboard and current-work composition. No startup requests or event listeners are installed here. */
export function install(ctx) {
  async function dashboard() {
    const day = ctx.actions.localDay();
    const [data, priorityWork] = await Promise.all([
      ctx.actions.api('/api/workspace/brief?as_of=' + day),
      ctx.actions.api('/api/workspace/queue?as_of=' + day),
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
    return `<div class="dm-workspace"><header class="dm-work-mast"><div><span class="dm-overline">${ctx.actions.esc(ctx.actions.date(day))}</span><h1>Workspace<span class="dm-live" aria-hidden="true"></span></h1></div>${ctx.actions.linkButton('#data', 'Import report', '', 'upload')}</header>
      <div class="dm-ledger" aria-label="Workspace totals"><a href="#leads"><strong>${ctx.actions.num(c.leads)}</strong><span>Leads</span></a><a href="#investigations"><strong>${ctx.actions.num(stageTotal)}</strong><span>Active investigations</span></a><a href="#workspace/notifications?due_before=${day}"><strong>${ctx.actions.num(w.due)}</strong><span>Follow-ups due</span></a><a href="#workspace/notifications?stage=closed"><strong>${ctx.actions.num(w.closed)}</strong><span>Completed</span></a></div>
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

  const actions = { dashboard, workspaceActionURL };
  Object.assign(ctx.actions, actions);
  return actions;
}
