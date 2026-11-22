/** Intake progress, import review and upload presentation owned by Accretion. No startup requests or event listeners are installed here. */
export function install(ctx) {
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

  function retainedRowSummary(stats, validRows) {
    const retained = stats?.admitted_rows ?? validRows;
    const context = stats?.context_rows;
    const num = ctx.actions.num;
    if (context == null) return `<span>${num(retained)} rows retained</span>`;
    return `<span>${num(retained - context)} eligible rows</span>${context ? `<span>${num(context)} context rows</span>` : ''}`;
  }

  function retryReasonsMarkup(reasons) {
    const rows = Object.entries(reasons || {}).sort(
      (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
    );
    if (!rows.length) return '';
    return `<ul class="section-note" aria-label="Reasons to retry">${rows.map(([label, count]) => `<li>${ctx.actions.esc(label)} · ${ctx.actions.num(count)} ${count === 1 ? 'group' : 'groups'}</li>`).join('')}</ul>`;
  }

  function accretionSummary(r) {
    const stats = importConfig(r).intake_stats?.accretion;
    return (
      retainedRowSummary(stats, r.valid_rows) +
      (stats
        ? `<span>${ctx.actions.num(stats.filtered_rows)} rows filtered out</span><span>${ctx.actions.num(stats.leads)} root-domain groups</span>`
        : '')
    );
  }

  function accretionIntakeMarkup(data = {}) {
    const esc = ctx.actions.esc,
      num = ctx.actions.num;
    const r = data.current,
      p = r?.progress || {},
      stats = r?.stats || {},
      jobs = r?.jobs || {};
    const busy = r && ['queued', 'running'].includes(r.status);
    const done = r?.status === 'done';
    const read = p.read_rows ?? r?.rows_read ?? 0;
    const excluded = stats.filtered_rows ?? p.filtered_rows ?? 0;
    const total = r?.groups_total || 0,
      checked = r?.groups_done || 0;
    const attributed = r?.stage_totals?.qualified ?? jobs.qualified ?? r?.qualified ?? 0,
      review = jobs.review || 0,
      retry = jobs.deferred || 0;
    const associated =
      r?.stage_totals?.published ?? Math.min(attributed, p.associated_groups ?? attributed);
    const excludedByAssociate = r?.stage_totals?.excluded_by_associate || 0;
    const associateRetry = r?.stage_totals
      ? Math.max(0, attributed - associated - excludedByAssociate)
      : 0;
    const qualifyRetry = Math.max(0, retry - associateRetry);
    const notQualified = Math.max(0, checked - attributed - review - qualifyRetry);
    const temperatures = ['cool', 'warm', 'hot', 'blazing'];
    const ranked =
      r?.stage_totals?.evaluated ??
      temperatures.reduce((sum, key) => sum + Number(r?.temperatures?.[key] || 0), 0);
    const downstreamState = (count, phase) =>
      busy && p.phase === phase
        ? 'active'
        : !count
          ? 'waiting'
          : review || retry
            ? 'attention'
            : done
              ? 'complete'
              : 'waiting';
    const phaseStates = [
      p.filter_complete || total || done ? 'complete' : busy ? 'active' : 'waiting',
      review || qualifyRetry
        ? 'attention'
        : done && total
          ? 'complete'
          : busy && p.phase === 'qualify'
            ? 'active'
            : 'waiting',
      downstreamState(ranked, 'evaluate'),
      associateRetry ? 'attention' : downstreamState(associated + excludedByAssociate, 'associate'),
    ];
    const qualificationGate =
      (review || qualifyRetry) && !busy
        ? '<p class="muted">Unresolved groups wait for qualification.</p>'
        : done && !attributed
          ? `<p class="muted">${total ? 'No groups passed qualification.' : 'No groups passed filtering.'}</p>`
          : '';
    const card = (i, title, metric, label, description, content) =>
      `<li class="accretion-phase" data-stage="${['filter', 'qualify', 'evaluate', 'associate'][i]}" data-state="${phaseStates[i]}"><div class="accretion-phase-top"><span>0${i + 1}</span><strong>${title}</strong><i aria-hidden="true"></i></div><div class="accretion-phase-number">${num(metric)}<small>${label}</small></div><p>${description}</p>${content}</li>`;
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
          : r.status === 'needs_retry' || retry
            ? associateRetry && !qualifyRetry
              ? 'Association needs retry'
              : 'Qualification needs retry'
            : review
              ? 'Attribution review available'
              : busy
                ? r.stage
                : 'Intake complete';
    const timeLabel =
      r?.elapsed_seconds == null
        ? ''
        : ' · elapsed ' +
          Math.floor(r.elapsed_seconds / 60) +
          'm ' +
          (r.elapsed_seconds % 60) +
          's';
    const controls = r
      ? `<button class="button small" data-import="${esc(r.id)}" data-accretion-control="details">Details</button>${busy ? `<button class="button small" data-pause="${esc(r.id)}" data-accretion-control="pause">Pause</button>` : ['paused', 'needs_retry', 'error'].includes(r.status) ? `<button class="button small" data-retry="${esc(r.id)}" data-accretion-control="resume">Resume import</button>` : ''}`
      : '';
    return `<section id="accretion-console" class="accretion-intake accretion-console" tabindex="-1"><div class="accretion-intake-title"><div><span class="dm-overline">Lead intake</span><h2>Accretion</h2></div><a class="text-link" href="#leads" data-accretion-control="leads">Ranked leads ${ctx.actions.icon('arrow')}</a></div>${catalogNotice}<div class="accretion-run"><div><strong>${r ? esc(r.name) : 'From incoming reports to focused outreach'}</strong><p data-accretion-live-status role="status" aria-live="polite">${busy ? '<span class="spinner" aria-hidden="true"></span>' : ''}${esc(stateText)}${esc(timeLabel)}${data.queued ? ` · ${num(data.queued)} queued` : ''}</p></div><div class="actions">${controls}</div></div>${r?.error ? `<div class="notice warn">${esc(r.error)}</div>` : ''}<ol class="accretion-phases">${
      card(
        0,
        'Filter',
        read,
        'rows read',
        'Required fields, jurisdiction and finding eligibility.',
        `<div class="accretion-phase-stats">${retainedRowSummary(stats, r?.valid_rows)}<span>${num(excluded)} rows filtered out</span>${phaseStates[0] === 'complete' ? `<span>${num(total)} root-domain groups</span>` : ''}</div>${phaseStates[0] === 'active' ? '<div class="accretion-working" aria-label="Reading and filtering source rows"></div>' : ''}`,
      ) +
      card(
        1,
        'Qualify',
        attributed,
        'qualified leads',
        'Actionable findings, a functioning website screenshot and proven attribution.',
        `<div class="progress" role="progressbar" aria-label="Root-domain groups checked" aria-valuemin="0" aria-valuemax="${Math.max(1, total)}" aria-valuenow="${Math.min(checked, Math.max(1, total))}"><span style="width:${fraction}%"></span></div><div class="accretion-phase-stats"><span>${num(checked)} / ${num(total)} root-domain groups checked</span>${p.reused_groups ? `<span>${num(p.reused_groups)} reused evidence</span>` : ''}${review ? `<a href="#attribution">${num(review)} to review</a>` : ''}${qualifyRetry ? `<span>${num(qualifyRetry)} to retry</span>` : ''}${r?.status === 'needs_retry' && jobs.pending ? `<span>${num(jobs.pending)} groups awaiting resume</span>` : ''}${notQualified ? `<span>${num(notQualified)} not qualified</span>` : ''}</div>${retryReasonsMarkup(r?.retry_reasons)}`,
      ) +
      card(
        2,
        'Evaluate',
        ranked,
        'groups ranked',
        'Combine evidence quality, vulnerability risk and agency priorities.',
        `<div class="accretion-temperatures">${temperatures.map((key) => `<span data-temperature="${key}"><i aria-hidden="true"></i>${key[0].toUpperCase() + key.slice(1)} <b>${num(r?.temperatures?.[key] || 0)}</b></span>`).join('')}</div>${qualificationGate}${ranked && r?.catalog_at_scoring && ['missing', 'partial', 'unavailable'].includes(r.catalog_at_scoring.state) ? '<p class="accretion-limited">Scored with limited local CVE coverage</p>' : ''}`,
      ) +
      card(
        3,
        'Associate',
        associated,
        'groups associated',
        'Check external referrals, outreach holds and previous notifications before publishing.',
        `${qualificationGate}${associateRetry ? `<p>${num(associateRetry)} need fresh evidence for the remaining sources</p>` : ''}${excludedByAssociate ? `<p>${num(excludedByAssociate)} excluded by Associate</p>` : ''}<button class="text-button" data-action="show-deconfliction">External deconfliction list</button>${phaseStates[3] === 'active' ? '<div class="accretion-working" aria-label="Associating observations with findings"></div>' : ''}`,
      )
    }</ol><details class="accretion-insights"><summary>Intake patterns <span>${num(patterns.files || 0)} recent source files</span></summary><details><summary>Current run criteria and results</summary><p>Filter checks individual rows. Qualify requires a rendered page identifying the business and related registration evidence. Evaluate ranks admitted findings. Associate checks prior notification and external references.</p><h4>Eligibility decisions by row</h4>${
      Object.entries(r?.eligibility_checks || {})
        .map(([key, count]) => `<p>${esc(key.replaceAll('_', ' '))} · ${num(count)}</p>`)
        .join('') || '<p>No eligibility checks recorded.</p>'
    }<h4>Evidence indicators</h4><p>${num(stats.kev_admitted_rows || 0)} admitted by known exploitation · ${num(stats.catalog_critical_rows || 0)} with critical catalog severity. A row can appear in both counts.</p><h4>Final group exclusions</h4>${
      Object.entries(r?.group_rejections || {})
        .map(([key, count]) => `<p>${esc(key.replaceAll('_', ' '))} · ${num(count)}</p>`)
        .join('') || '<p>No group exclusions recorded.</p>'
    }</details><p>${num(patterns.admitted_rows || 0)} retained of ${num(patterns.source_rows || 0)} rows · latest evaluation per original file</p><div class="accretion-pattern-grid"><section><h3>Most common exclusions</h3><ul>${patternList(patterns.failures, 'No exclusions recorded')}</ul></section><section><h3>Accepted products</h3><ul>${patternList(patterns.products, 'No product details recorded')}</ul></section><section><h3>Accepted locations</h3><ul>${patternList(patterns.cities, 'No locations recorded')}</ul></section></div></details></section>`;
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

  async function showDeconfliction(editId) {
    const entries = await ctx.actions.api('/api/intake/deconfliction');
    const esc = ctx.actions.esc;
    if (editId == null) {
      const rows = entries
        .map(
          (item) =>
            `<tr><td>${esc(item.identifier)}</td><td>${item.scope === 'domain' ? 'Whole domain' : 'Exact hostname'}</td><td>${esc(item.external_reference)}</td><td>${esc(item.reason)}</td><td><button class="button small" data-edit-deconfliction="${esc(item.id)}">Edit</button></td></tr>`,
        )
        .join('');
      ctx.actions.modal(
        'External deconfliction',
        `<p>Associate checks these entries before publishing incoming findings.</p>${entries.length ? `<div class="table-wrap"><table><thead><tr><th>Identifier</th><th>Matching scope</th><th>Reference</th><th>Reason</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p>No external entries recorded.</p>'}<button class="button primary" data-edit-deconfliction="">Add entry</button>`,
      );
      return;
    }
    const item = entries.find((value) => value.id === editId);
    if (editId && !item) throw new Error('The deconfliction entry is no longer available.');
    ctx.actions.modal(
      item ? 'Edit deconfliction entry' : 'Add deconfliction entry',
      `<form id="deconfliction-form" data-id="${esc(editId)}" class="form-grid">
      <label>Matching scope<select name="scope"><option value="host">Exact hostname</option><option value="domain" ${item?.scope === 'domain' ? 'selected' : ''}>Whole domain</option></select></label>
      <label>Identifier<input name="identifier" required maxlength="254" value="${esc(item?.identifier || '')}"></label>
      <label>External reference<input name="external_reference" required maxlength="500" value="${esc(item?.external_reference || '')}"></label>
      <label>Reason<textarea name="reason" required maxlength="2000">${esc(item?.reason || '')}</textarea></label>
      <div class="modal-actions"><button type="button" class="button" data-action="show-deconfliction">Back to list</button>${item ? `<button type="button" class="button" data-remove-deconfliction="${esc(item.id)}">Remove entry</button>` : ''}<button type="submit" class="button primary">Save entry</button></div></form>`,
    );
  }

  function importRow(r) {
    const progress =
      r.status === 'done'
        ? 100
        : r.groups_total
          ? Math.round((r.groups_done / r.groups_total) * 100)
          : 0;
    return `<div class="import-row"><div class="file-icon">${ctx.actions.icon('file')}</div><div class="import-info"><div class="import-title"><button class="text-button" data-import="${r.id}">${ctx.actions.esc(r.name)}</button>${ctx.actions.statusBadge(r.status)}</div><p>${ctx.actions.esc(r.status === 'needs_retry' ? 'Qualification needs retry' : r.stage)}${r.error ? ' · ' + ctx.actions.esc(r.error) : ''}</p>${r.status !== 'done' ? `<div class="progress"><span style="width:${progress}%"></span></div>` : ''}<div class="inline-stats"><span>${ctx.actions.num(r.rows_read)} observations</span>${ctx.actions.ignoredEmptyRows(r) ? `<span>${ctx.actions.num(ctx.actions.ignoredEmptyRows(r))} empty rows ignored</span>` : ''}${accretionSummary(r)}<span>${ctx.actions.num(r.qualified)} published groups</span></div></div></div>`;
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
      `<div class="inline-stats">${ctx.actions.statusBadge(r.status)}<span>${ctx.actions.num(r.rows_read)} observations</span>${ctx.actions.ignoredEmptyRows(r) ? `<span>${ctx.actions.num(ctx.actions.ignoredEmptyRows(r))} empty rows ignored</span>` : ''}${accretionSummary(r)}<span>${ctx.actions.num(r.qualified)} published groups</span></div>${r.stage_totals ? `<p>${ctx.actions.num(r.stage_totals.qualified)} passed Qualify · ${ctx.actions.num(r.stage_totals.evaluated)} ranked · ${ctx.actions.num(r.stage_totals.published)} published · ${ctx.actions.num(r.stage_totals.excluded_by_associate)} excluded by Associate</p>` : ''}<p>${ctx.actions.esc(r.message || r.stage)}</p>${r.error ? `<div class="notice warn">${ctx.actions.esc(r.error)}</div>` : ''}${profiles.length ? `<h3>Report interpretation</h3><div class="key-value">${profiles.map((p) => `<span>${ctx.actions.esc(p.name || p.id)}</span><strong>${ctx.actions.esc(p.capability_label || (p.capability === 'eligible' ? 'Eligible profile' : p.capability === 'interpreted' ? 'Interpreted' : 'Retained only'))}</strong>`).join('')}</div><details><summary>Report types and interpretation</summary><pre>${ctx.actions.esc(JSON.stringify({ profiles, inventory: config.profile_inventory }, null, 2))}</pre></details>` : ''}${acquisition ? `<h3>Acquisition dates</h3><div class="key-value"><span>Report date</span><strong>${ctx.actions.esc(acquisition.report_date || 'Not recorded')}</strong><span>Retrieved</span><strong>${ctx.actions.esc(acquisition.retrieved_at || 'Not recorded')}</strong><span>Catalog coverage</span><strong>${ctx.actions.esc(acquisition.catalog_coverage || 'Unknown')}</strong></div>` : ''}<h3>Accretion · Filter</h3>${
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
      }${config.schema_observation ? `<details><summary>Source field details</summary><pre>${ctx.actions.esc(JSON.stringify(config.schema_observation, null, 2))}</pre></details>` : ''}<h3>Root-domain groups</h3>${retryReasonsMarkup(r.retry_reasons)}<div class="table-wrap"><table><thead><tr><th scope="col">Root domain</th><th scope="col">Result</th><th scope="col">Lookups</th></tr></thead><tbody>${r.groups.map((g) => `<tr><td><button class="text-button" data-group="${g.id}">${ctx.actions.esc(g.domain)}</button>${g.error ? `<small>${ctx.actions.esc(g.retry_label || g.error)}</small>` : ''}</td><td>${ctx.actions.statusBadge(g.status)}</td><td>${JSON.parse(g.attempts).length}</td></tr>`).join('')}</tbody></table></div><details><summary>Original file fingerprint</summary><pre>${ctx.actions.esc(r.sha256)}</pre></details><div class="modal-actions"><a class="button" href="/api/imports/${r.id}/original">${ctx.actions.icon('download')}Original file</a>${!['running', 'queued'].includes(r.status) ? `<button class="button" data-reevaluate-import="${r.id}">Re-evaluate import</button>` : ''}${['running', 'queued'].includes(r.status) ? `<button class="button" data-pause="${r.id}">Pause after current group</button>` : ['paused', 'needs_retry', 'error'].includes(r.status) ? `<button class="button primary" data-retry="${r.id}">Resume import</button>` : ''}</div>`,
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

  let releaseDropzone = null;
  function disposeIntakeDropzone() {
    releaseDropzone?.();
    releaseDropzone = null;
  }
  function wireDropzone() {
    disposeIntakeDropzone();
    const el = ctx.actions.$('#dropzone');
    if (!el) return;
    const listeners = {
      dragover: (event) => {
        event.preventDefault();
        el.classList.add('drag');
      },
      dragleave: () => el.classList.remove('drag'),
      drop: (event) => {
        event.preventDefault();
        el.classList.remove('drag');
        ctx.actions.upload(event.dataTransfer.files);
      },
    };
    for (const [type, listener] of Object.entries(listeners)) el.addEventListener(type, listener);
    releaseDropzone = () => {
      for (const [type, listener] of Object.entries(listeners))
        el.removeEventListener(type, listener);
      el.classList.remove('drag');
    };
  }
  const actions = {
    showDeconfliction,
    ignoredEmptyRows,
    accretionSummary,
    accretionIntakeMarkup,
    refreshAccretion,
    importRow,
    importsPage,
    showImport,
    upload,
    wireDropzone,
    disposeIntakeDropzone,
  };
  Object.assign(ctx.actions, actions);
  return actions;
}
