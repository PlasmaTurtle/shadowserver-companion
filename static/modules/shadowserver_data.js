/** API acquisition and schedules. Credentials never enter browser persistence. */
export function install(ctx) {
  ctx.state.apiData = { status: null, selection: null, timer: null, generation: 0 };

  function stopApiAcquisitionPolling() {
    clearTimeout(ctx.state.apiData.timer);
    ctx.state.apiData.timer = null;
    ctx.state.apiData.generation += 1;
  }

  async function loadApiAcquisition() {
    stopApiAcquisitionPolling();
    const generation = ctx.state.apiData.generation;
    const status = await ctx.actions.api('/api/shadowserver/status');
    if (generation !== ctx.state.apiData.generation) return status;
    ctx.state.apiData.status = status;
    const apiWasActive = ['queued', 'running'].includes(status.job?.status);
    if (
      ['queued', 'running'].includes(status.job?.status) ||
      ['retrieving', 'importing'].includes(status.schedule?.run?.status)
    ) {
      ctx.state.apiData.timer = setTimeout(async () => {
        if (!document.querySelector('#shadowserver-api')) return;
        try {
          const status = await ctx.actions.loadApiAcquisition();
          if (ctx.state.apiData.status !== status || !document.querySelector('#shadowserver-api'))
            return;
          const progress = document.querySelector('#api-job-progress');
          if (progress) progress.innerHTML = apiJobMarkup(status.job);
          const scheduleProgress = document.querySelector('#schedule-progress');
          if (scheduleProgress)
            scheduleProgress.innerHTML = scheduleProgressMarkup(status.schedule);
          const scheduleActive = ['retrieving', 'importing'].includes(status.schedule?.run?.status);
          document.querySelectorAll('#api-schedule-form button').forEach((button) => {
            button.disabled =
              scheduleActive ||
              (button.dataset.action && !status.schedule?.config?.enabled) ||
              (button.dataset.action === 'schedule-run' && Boolean(status.schedule?.scope_error));
          });
          if (
            apiWasActive &&
            status.job &&
            !['queued', 'running'].includes(status.job.status) &&
            !['retrieving', 'importing'].includes(status.schedule?.run?.status)
          )
            await ctx.actions.route(true);
        } catch (error) {
          if (error?.name === 'AbortError') return;
          ctx.actions.toast(error.message, true);
        }
      }, 1500);
    }
    return ctx.state.apiData.status;
  }

  function apiJobMarkup(job) {
    if (!job) return '';
    const esc = ctx.actions.esc;
    const active = ['queued', 'running'].includes(job.status);
    const title = active
      ? { connection: 'Connecting…', catalog: 'Finding reports…', import: 'Importing reports…' }[
          job.kind
        ]
      : {
          completed: 'Completed',
          cancelled: 'Cancelled',
          failed: 'Retrieval failed',
          partial: 'Partially completed',
        }[job.status] || job.status;
    return `<div class="notice ${['failed', 'partial'].includes(job.status) ? 'warn' : ''}" role="status"><div><strong>${esc(title)}</strong>${job.total ? `<p>${job.completed} / ${job.total}</p>` : ''}${job.message ? `<p>${esc(job.message)}</p>` : ''}</div>${active ? `<button class="button small" data-action="api-cancel" data-job="${esc(job.id)}">Cancel</button>` : ''}</div>${job.results?.length ? `<details><summary>Imported reports (${job.results.length})</summary><ul>${job.results.map((r) => `<li>${esc(r.filename)} · ${r.duplicate ? 'Already imported' : 'Queued'}</li>`).join('')}</ul></details>` : ''}`;
  }

  function scheduleProgressMarkup(schedule) {
    const esc = ctx.actions.esc;
    if (!schedule) return '';
    const run = schedule.run;
    return `${schedule.configuration_error ? `<p class="notice warn">${esc(schedule.configuration_error)}</p>` : ''}${schedule.scope_error ? `<p class="notice warn" role="status"><strong>Scheduled reports need a selection</strong> ${esc(schedule.scope_error)}</p>` : ''}${run ? `<p role="status"><strong>${esc(run.status)}</strong> · ${esc(run.message || '')}${run.imports?.length ? ` · ${run.intake_completed || 0}/${run.imports.length} imports completed` : ''}</p>` : ''}${schedule.next_run_at && !schedule.scope_error ? `<p class="section-note">Next check: ${esc(new Date(schedule.next_run_at).toLocaleString())}</p>` : ''}${schedule.history?.length ? `<details><summary>Recent scheduled checks</summary><ul>${schedule.history.map((r) => `<li>${esc(new Date(r.completed_at).toLocaleString())} · ${esc(r.status)} · ${esc(r.message)}</li>`).join('')}</ul></details>` : ''}`;
  }

  function scheduleMarkup(status) {
    const schedule = status.schedule;
    if (!schedule) return '';
    const config = schedule.config || {};
    const esc = ctx.actions.esc;
    const active = ['retrieving', 'importing'].includes(schedule.run?.status);
    const types = new Map((status.types || []).map((x) => [x.type, x.description || x.type]));
    const subscriptions = status.subscriptions || [];
    const subscription = config.subscription || status.selection_defaults?.subscription || '';
    const selectedTypes = config.report_types?.length
      ? config.report_types
      : status.selection_defaults?.report_types || [];
    const selectionLocked = !status.connected ? 'disabled' : '';
    const savedSelection =
      !status.connected && config.subscription
        ? `<p class="section-note full">Saved selection: ${esc(config.subscription)} · ${esc((config.report_types || []).join(', '))}. Connect above to review available choices. Timing changes preserve this selection.</p>`
        : '';
    const staleSelection =
      status.connected && config.subscription && !subscriptions.includes(config.subscription)
        ? '<p class="notice warn full">The saved subscription is unavailable for this jurisdiction or account. Select a permitted subscription before enabling scheduled reports.</p>'
        : '';
    return `<details class="section-gap"><summary>Scheduled intake${config.enabled ? ' · enabled' : ''}</summary><div id="schedule-progress">${scheduleProgressMarkup(schedule)}</div><form id="api-schedule-form" class="form-grid"><label class="full"><input name="enabled" type="checkbox" ${config.enabled ? 'checked' : ''}> Enable schedule</label><label><input name="shadowserver" type="checkbox" ${config.shadowserver ? 'checked' : ''}> Shadowserver reports</label><label><input name="reference" type="checkbox" ${config.reference ? 'checked' : ''}> NVD, EPSS and KEV daily</label><div class="field"><label>First check, local time</label><input type="time" name="time" value="${String(config.hour ?? 6).padStart(2, '0')}:${String(config.minute ?? 0).padStart(2, '0')}" required></div><div class="field"><label>Recheck every (hours)</label><input type="number" name="interval_hours" value="${config.interval_hours || 4}" min="1" max="24" required></div><div class="field"><label>Recheck recent days</label><input type="number" name="lookback_days" value="${config.lookback_days || 7}" min="1" max="30" required></div><div class="field"><label>Subscription</label><select name="subscription" ${selectionLocked}><option value="" ${!subscriptions.includes(subscription) ? 'selected' : ''}>Select subscription</option>${subscriptions.map((x) => `<option value="${esc(x)}" ${x === subscription ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select></div><div class="field full"><label>Report types</label><select name="report_types" multiple size="6" ${selectionLocked}>${[...types].map(([name, label]) => `<option value="${esc(name)}" ${selectedTypes.includes(name) ? 'selected' : ''}>${esc(label)}</option>`).join('')}</select></div>${savedSelection}${staleSelection}<p class="section-note full">Late reports are rechecked; missed dates catch up automatically. A run completes after Accretion finishes. Connect above to load available report types.</p><div class="actions full"><button class="button primary" ${active ? 'disabled' : ''}>Save schedule</button><button type="button" class="button" data-action="schedule-run" ${!config.enabled || active || schedule.scope_error ? 'disabled' : ''}>Run now</button>${status.can_remember ? `<button type="button" class="button" data-action="schedule-background" data-enabled="${!schedule.background?.installed}" ${!config.enabled || active ? 'disabled' : ''}>${schedule.background?.installed ? 'Disable closed-app runs' : 'Enable closed-app runs'}</button>` : ''}</div><p class="section-note full">${schedule.background?.installed ? 'Windows checks hourly while you are signed in, even with the app closed. Missed runs resume when available.' : 'Scheduled checks run while the app is running. Checks with the app closed require Windows and saved API credentials.'}</p></form></details>`;
  }

  function apiAcquisitionMarkup() {
    const state = ctx.state.apiData;
    const status = state.status || {};
    const esc = ctx.actions.esc;
    const active = ['queued', 'running'].includes(status.job?.status);
    const disabled = active ? 'disabled' : '';
    const selection = state.selection || {
      subscription: status.selection_defaults?.subscription || '',
      report_type: status.selection_defaults?.report_types?.[0] || '',
      start: ctx.actions.localDay(),
      end: ctx.actions.localDay(),
    };
    const staleSelection =
      selection.subscription && !(status.subscriptions || []).includes(selection.subscription);
    const options = (items, selected) =>
      items
        .map(
          (x) =>
            `<option value="${esc(x.value)}" ${x.value === selected ? 'selected' : ''}>${esc(x.label)}</option>`,
        )
        .join('');
    return `<section id="shadowserver-api" class="panel"><div class="panel-head"><h2>Shadowserver API</h2><span class="badge ${status.connected ? 'green' : 'gray'}">${status.connected ? 'Connected' : status.configured ? 'Configured' : 'Not configured'}</span></div><div class="panel-body"><details ${!status.configured ? 'open' : ''}><summary>Credentials${status.configured ? ` · ${status.storage === 'windows' ? 'Saved on this computer' : 'Current session'}` : ''}</summary><form id="api-credentials-form" class="form-grid" autocomplete="off"><div class="field"><label for="api-key">API key</label><input id="api-key" name="api_key" type="password" autocomplete="new-password" required maxlength="1024" ${disabled}></div><div class="field"><label for="api-secret">Secret</label><input id="api-secret" name="secret" type="password" autocomplete="new-password" required maxlength="1024" ${disabled}></div>${status.can_remember ? `<label class="full"><input type="checkbox" name="remember" checked ${disabled}> Save in Windows Credential Manager</label>` : '<p class="section-note full">Credentials are kept for this app session.</p>'}<div class="actions full"><button type="submit" class="button primary" ${disabled}>Save &amp; connect</button>${status.configured ? `<button type="button" class="button" data-action="api-forget" ${disabled}>Remove credentials</button>` : ''}</div></form></details>${status.configured && !status.connected ? `<p><button class="button" data-action="api-connect" ${disabled}>Connect</button></p>` : ''}<div id="api-job-progress">${apiJobMarkup(status.job)}</div>${status.jurisdiction ? `<p class="section-note">Jurisdiction: <strong>${esc(status.jurisdiction.regions.join(', '))}</strong>. ${esc(status.jurisdiction.notice)}</p>` : ''}${staleSelection ? '<p class="notice warn">The previous report selection is no longer available. Select a permitted subscription.</p>' : ''}${status.connected && !status.subscriptions?.length ? '<p class="notice warn">No subscriptions are available for the configured jurisdiction. Review Jurisdiction in Settings or update the account’s Shadowserver subscriptions.</p>' : ''}${
      status.connected
        ? `<form id="api-catalog-form" class="form-grid"><div class="field"><label for="api-subscription">Subscription</label><select id="api-subscription" name="subscription" required ${disabled}><option value="" ${!selection.subscription || staleSelection ? 'selected' : ''}>Select subscription</option>${options(
            (status.subscriptions || []).map((x) => ({ value: x, label: x })),
            selection.subscription,
          )}</select></div><div class="field"><label for="api-report-type">Report type</label><select id="api-report-type" name="report_type" required ${disabled}><option value="">Select report type</option>${options(
            (status.types || []).map((x) => ({
              value: x.type,
              label: x.description ? `${x.type} · ${x.description}` : x.type,
            })),
            selection.report_type,
          )}</select></div><div class="field"><label for="api-start">From</label><input id="api-start" name="start" type="date" value="${esc(selection.start)}" required ${disabled}></div><div class="field"><label for="api-end">Through</label><input id="api-end" name="end" type="date" value="${esc(selection.end)}" required ${disabled}></div><div class="actions full"><button type="submit" class="button" ${disabled}>Find reports</button></div></form>`
        : ''
    }${status.completeness ? `<div class="api-catalog-results"><h3>Available reports (${status.reports?.length || 0})</h3>${status.completeness !== 'complete' ? '<p class="notice warn">Partial listing</p>' : ''}${status.reports?.length ? `<form id="api-import-form"><div class="table-wrap"><table><thead><tr><th>Select</th><th>Report</th><th>Date</th><th>Subscription</th></tr></thead><tbody>${status.reports.map((r) => `<tr><td><input type="checkbox" name="report_ids" value="${esc(r.id)}" checked aria-label="Select ${esc(r.filename)}" ${disabled}></td><td>${esc(r.filename)}<small>${esc(r.report_type)}</small></td><td>${esc(r.report_date)}</td><td>${esc(r.subscription)}</td></tr>`).join('')}</tbody></table></div><div class="actions"><button class="button primary" type="submit" ${disabled}>Import selected</button></div></form>` : '<p class="section-note">No reports returned for this selection.</p>'}</div>` : ''}${scheduleMarkup(status)}</div></section>`;
  }

  Object.assign(ctx.actions, {
    apiAcquisitionMarkup,
    loadApiAcquisition,
    stopApiAcquisitionPolling,
  });
}

export function createHandlers(ctx) {
  async function refresh() {
    await ctx.actions.route(true);
  }
  return {
    click: [],
    change: [],
    actions: {
      'schedule-run': async () => {
        await ctx.actions.api('/api/schedule/run', { method: 'POST' });
        await refresh();
      },
      'schedule-background': async (el) => {
        await ctx.actions.api('/api/schedule/background', {
          method: 'PUT',
          body: { enabled: el.dataset.enabled === 'true' },
        });
        await refresh();
      },
      'api-connect': async () => {
        await ctx.actions.api('/api/shadowserver/connection', { method: 'POST' });
        await refresh();
      },
      'api-forget': async () => {
        await ctx.actions.api('/api/shadowserver/credentials', { method: 'DELETE' });
        await refresh();
      },
      'api-cancel': async (el) => {
        await ctx.actions.api('/api/shadowserver/jobs/' + el.dataset.job + '/cancel', {
          method: 'POST',
        });
        await refresh();
      },
    },
    forms: {
      'api-schedule-form': async (form, obj, data) => {
        const [hour, minute] = obj.time.split(':').map(Number);
        const status = ctx.state.apiData.status || {};
        const saved = status.schedule?.config || {};
        const preserveSelection = status.connected === false;
        await ctx.actions.api('/api/schedule', {
          method: 'PUT',
          body: {
            enabled: obj.enabled === 'on',
            shadowserver: obj.shadowserver === 'on',
            reference: obj.reference === 'on',
            hour,
            minute,
            interval_hours: Number(obj.interval_hours),
            lookback_days: Number(obj.lookback_days),
            subscription: preserveSelection ? saved.subscription || '' : obj.subscription,
            report_types: preserveSelection
              ? saved.report_types || []
              : data.getAll('report_types'),
          },
        });
        await refresh();
      },
      'api-credentials-form': async (form, obj) => {
        await ctx.actions.api('/api/shadowserver/credentials', {
          method: 'PUT',
          body: { api_key: obj.api_key, secret: obj.secret, remember: obj.remember === 'on' },
        });
        form.reset();
        await ctx.actions.api('/api/shadowserver/connection', { method: 'POST' });
        await refresh();
      },
      'api-catalog-form': async (form, obj) => {
        ctx.state.apiData.selection = { ...obj };
        await ctx.actions.api('/api/shadowserver/catalog', { method: 'POST', body: obj });
        await refresh();
      },
      'api-import-form': async (form, obj, data) => {
        const ids = data.getAll('report_ids');
        if (!ids.length) throw Error('Select at least one report.');
        await ctx.actions.api('/api/shadowserver/import', {
          method: 'POST',
          body: {
            report_ids: ids,
          },
        });
        await refresh();
      },
    },
  };
}
