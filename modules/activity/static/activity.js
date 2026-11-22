/** Search saved chronology without changing records or inferring historical authors. */
export function install(ctx) {
  function failedCaptureActivity(event) {
    if (event.action !== 'website_capture_failed') return '';
    let metadata = event.metadata;
    if (typeof metadata === 'string') {
      try {
        metadata = JSON.parse(metadata);
      } catch {
        return '';
      }
    }
    return ctx.actions.downloadActivityMarkup(metadata?.download_activity);
  }

  function activities(items) {
    return items.length
      ? items
          .map(
            (e) =>
              `<div class="activity-row"><span class="activity-mark">${ctx.actions.icon(e.action === 'completed' ? 'check' : e.action === 'evidence_added' ? 'image' : 'clock')}</span><div>${e.lead_id ? `<a href="#${e.case_id ? 'workspace/notifications/' + e.case_id : 'entity/' + e.lead_id}">${ctx.actions.esc(e.detail)}</a>` : ctx.actions.esc(e.detail)}<small>${ctx.actions.stamp(e.created_at)}</small>${failedCaptureActivity(e)}</div></div>`,
          )
          .join('')
      : '<p class="section-note">Activity appears as you work through notifications.</p>';
  }

  async function activityPage(params) {
    const request = new URLSearchParams();
    for (const key of ['q', 'actor', 'action', 'entity_id', 'case_id', 'before'])
      if (params.get(key)) request.set(key, params.get(key));
    const result = await ctx.actions.api('/api/activity?' + request);
    const newest = new URLSearchParams(request);
    newest.delete('before');
    const older = new URLSearchParams(request);
    if (result.next_before) older.set('before', result.next_before);
    const filtered = [...request.keys()].some((key) => key !== 'before');
    const advanced = !!(request.get('actor') || request.get('action'));
    const rows = result.items
      .map((item) => {
        const target = item.case_id
          ? '#workspace/notifications/' + encodeURIComponent(item.case_id)
          : item.lead_id
            ? '#entity/' + encodeURIComponent(item.lead_id)
            : '';
        const context = { ...item.metadata };
        const downloads = failedCaptureActivity(item);
        if (item.action === 'website_capture_failed') delete context.download_activity;
        return `<article class="dm-event"><div class="dm-event-time"><span>${ctx.actions.stamp(item.created_at)}</span><small>${ctx.actions.esc(item.actor || 'Operator not recorded')}</small></div><div class="dm-event-body"><h2>${ctx.actions.esc(item.action.replaceAll('_', ' '))}</h2><p>${ctx.actions.esc(item.detail)}</p>${downloads}${Object.keys(context).length ? `<details><summary>Recorded context</summary><pre>${ctx.actions.esc(JSON.stringify(context, null, 2))}</pre></details>` : ''}</div>${target ? `<a class="text-link" href="${target}" aria-label="Open record for ${ctx.actions.esc(item.action.replaceAll('_', ' '))}">Open ${ctx.actions.icon('arrow')}</a>` : ''}</article>`;
      })
      .join('');
    const empty = ctx.actions.empty(
      filtered
        ? 'No matching events'
        : request.get('before')
          ? 'No older events'
          : 'No activity recorded yet',
      filtered
        ? 'Try a shorter search or clear the filters. Operator and action filters require an exact match.'
        : request.get('before')
          ? 'Return to the newest events to continue reviewing this chronology.'
          : 'Saved decisions and completed actions will appear here.',
      filtered
        ? ctx.actions.linkButton('#activity', 'Clear filters', '', 'search')
        : request.get('before')
          ? ctx.actions.linkButton('#activity', 'Newest events', '', 'clock')
          : '',
    );
    return (
      ctx.actions.heading('Activity', '') +
      `<section class="panel"><form id="activity-search" class="activity-filters panel-body"><div class="activity-search-row"><div class="field"><label for="activity-query">Search activity</label><input id="activity-query" type="search" name="q" maxlength="200" value="${ctx.actions.esc(request.get('q') || '')}" placeholder="Decision, reason or name"></div><button type="submit" class="button primary">Search</button>${filtered ? '<a class="text-link" href="#activity">Clear filters</a>' : ''}</div><details class="activity-advanced" ${advanced ? 'open' : ''}><summary>Filter by operator or action</summary><div class="form-grid"><div class="field"><label for="activity-operator">Recorded operator</label><input id="activity-operator" name="actor" maxlength="200" value="${ctx.actions.esc(request.get('actor') || '')}" placeholder="Exact recorded name"></div><div class="field"><label for="activity-action">Action code</label><input id="activity-action" name="action" maxlength="100" value="${ctx.actions.esc(request.get('action') || '')}" placeholder="For example, outreach_policy_changed"></div><p class="section-note full">These optional filters use exact matches. The main search also finds words within an action name.</p></div></details>${['entity_id', 'case_id'].map((key) => (request.get(key) ? `<input type="hidden" name="${key}" value="${ctx.actions.esc(request.get(key))}">` : '')).join('')}</form><div class="panel-body activity-result-summary"><p class="section-note" role="status">Showing ${ctx.actions.num(result.items.length)} of ${ctx.actions.num(result.total)} ${filtered ? 'matching ' : ''}recorded ${result.total === 1 ? 'event' : 'events'}.${request.get('case_id') ? ' Filtered to one notification.' : request.get('entity_id') ? ' Filtered to one business.' : ''}</p><p class="section-note">Older records may have no recorded operator.</p></div>${rows ? `<div class="dm-activity-stream">${rows}</div>` : empty}${request.get('before') || result.next_before ? `<nav class="panel-body activity-pagination" aria-label="Activity pages">${request.get('before') ? `<a class="button" href="#activity?${ctx.actions.esc(newest.toString())}">Newest events</a>` : '<span class="section-note">Newest events</span>'}${result.next_before ? `<a class="button" href="#activity?${ctx.actions.esc(older.toString())}">Older events ${ctx.actions.icon('arrow')}</a>` : '<span class="section-note">End of matching activity</span>'}</nav>` : ''}</section>`
    );
  }
  Object.assign(ctx.actions, { activities, activityPage });
}
