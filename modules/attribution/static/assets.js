/** Asset lookup jobs keep progress separate from the unsaved report draft. */
import { observedVersion } from '../../ui/static/shared.js';

export function install(ctx) {
  const state = { cases: new Map(), timers: new Map(), generation: 0 };
  ctx.state.assetAttribution = state;
  const active = (job) => ['queued', 'running', 'cancelling'].includes(job?.status);
  const labels = {
    evidence_unavailable: 'Evidence unavailable',
    matched: 'Attribution supported',
    review: 'Review required',
    no_match: 'No match',
    incomplete: 'Lookup incomplete',
    deferred: 'Retry available',
    no_eligible_ip: 'Not eligible',
    not_checked: 'Not checked',
    nonpublic_or_invalid: 'Private / nonpublic or invalid',
  };
  function redraw(caseId) {
    if (ctx.state.editor.currentLead?.case_id === caseId && ctx.state.editor.tab === 'assets') {
      const content = ctx.actions.$('#editor-content');
      if (!content) return;
      const opened = [
        ...(content.querySelectorAll?.('details[open][data-asset-detail]') || []),
      ].map((item) => item.dataset.assetDetail);
      const focused = typeof document === 'undefined' ? null : document.activeElement;
      const restoreFocus = !!focused && !!content.contains?.(focused);
      const identity = restoreFocus
        ? ['data-action', 'data-attribute-asset', 'data-asset-result', 'data-entry'].flatMap(
            (key) => (focused.getAttribute?.(key) ? [[key, focused.getAttribute(key)]] : []),
          )
        : [];
      const summaryId =
        restoreFocus && focused.tagName === 'SUMMARY'
          ? focused.parentElement?.dataset.assetDetail
          : null;
      content.innerHTML = assetsMarkup();
      const details = [...(content.querySelectorAll?.('details[data-asset-detail]') || [])];
      for (const item of details) if (opened.includes(item.dataset.assetDetail)) item.open = true;
      if (restoreFocus) {
        const summary =
          summaryId &&
          details.find((item) => item.dataset.assetDetail === summaryId)?.querySelector('summary');
        const control =
          identity.length &&
          [...(content.querySelectorAll?.('button') || [])].find(
            (item) =>
              !item.disabled && identity.every(([key, value]) => item.getAttribute(key) === value),
          );
        (summary || control || content.querySelector?.('#asset-status-summary'))?.focus?.({
          preventScroll: true,
        });
      }
    }
  }
  function schedule(caseId) {
    clearTimeout(state.timers.get(caseId));
    if (active(state.cases.get(caseId)?.job))
      state.timers.set(
        caseId,
        setTimeout(() => loadAssetAttribution(caseId), 1200),
      );
  }
  async function loadAssetAttribution(caseId = ctx.state.editor.currentLead?.case_id) {
    if (!caseId) return;
    const generation = state.generation;
    try {
      const result = await ctx.actions.api(`/api/cases/${caseId}/assets/attribution`, {
        timeoutMs: 20000,
      });
      if (generation !== state.generation) return;
      state.cases.set(caseId, result);
      redraw(caseId);
      schedule(caseId);
    } catch (error) {
      if (generation !== state.generation) return;
      const prior = state.cases.get(caseId) || { case_id: caseId };
      state.cases.set(caseId, { ...prior, error: error.message });
      redraw(caseId);
      // Explicit refresh resumes polling after a connection failure.
    }
  }
  async function startAssetAttribution(entryId = null) {
    const caseId = ctx.state.editor.currentLead.case_id;
    const job = await ctx.actions.api(`/api/cases/${caseId}/assets/attribution`, {
      method: 'POST',
      body: { entry_id: entryId },
      timeoutMs: 20000,
    });
    const prior = state.cases.get(caseId) || { case_id: caseId };
    state.cases.set(caseId, { ...prior, error: null, job });
    redraw(caseId);
    schedule(caseId);
  }
  async function cancelAssetAttribution() {
    const caseId = ctx.state.editor.currentLead.case_id;
    const current = state.cases.get(caseId);
    if (!active(current?.job)) return;
    current.job = await ctx.actions.api(`/api/asset-attribution/jobs/${current.job.id}/cancel`, {
      method: 'POST',
    });
    redraw(caseId);
    schedule(caseId);
  }
  function assetsMarkup() {
    const lead = ctx.state.editor.currentLead,
      saved = state.cases.get(lead.case_id),
      byId = new Map((saved?.assets || []).map((asset) => [asset.entry_id, asset])),
      running = active(saved?.job),
      job = saved?.job;
    const progress = job
      ? `<div class="notice ${job.errors?.length ? 'warn' : ''}" role="status"><div><strong>${ctx.actions.esc(job.status === 'cancelling' ? 'Stopping after the current lookup' : job.status === 'completed' ? 'Asset attribution finished' : job.status === 'cancelled' ? 'Asset attribution stopped' : job.status === 'failed' ? 'Asset attribution failed' : 'Checking asset attribution')}</strong><p>${ctx.actions.num(job.completed)} of ${ctx.actions.num(job.total)} assets checked${job.current_asset ? ` · ${ctx.actions.esc(job.current_asset.hostname)} / ${ctx.actions.esc(job.current_asset.ip)}` : ''}</p>${job.errors?.length ? `<details data-asset-detail="lookup-errors"><summary>${job.errors.length} lookup errors</summary>${job.errors.map((error) => `<p>${ctx.actions.esc(error.error)}</p>`).join('')}</details>` : ''}${running ? `<button class="button small" data-action="cancel-asset-attribution" ${job.status === 'cancelling' ? 'disabled' : ''}>Stop lookups</button>` : ''}</div></div>`
      : '';
    const supported = (saved?.assets || []).filter((asset) => asset.supported).length;
    return `<section class="panel"><div class="panel-head"><div><h2>Reported assets</h2><p>Related assets use the retained group attribution. Run an individual lookup when more direct evidence is useful.</p></div><div class="actions"><button class="button small" data-action="refresh-asset-attribution" title="Reload saved status without starting a new lookup">Refresh status</button><button class="button small primary" data-action="attribute-remaining" ${running || !saved?.remaining ? 'disabled' : ''}>${ctx.actions.icon('search')}Try remaining assets${saved ? ` (${ctx.actions.num(saved.remaining)})` : ''}</button></div></div><div class="panel-body"><div class="asset-status-summary" id="asset-status-summary" tabindex="-1" aria-label="Saved asset attribution summary"><span><strong>${ctx.actions.num(lead.entries.length)}</strong> report observation${lead.entries.length === 1 ? '' : 's'}</span>${saved ? `<span><strong>${ctx.actions.num(supported)}</strong> with attribution support</span><span><strong>${ctx.actions.num(saved.remaining)}</strong> distinct check${saved.remaining === 1 ? '' : 's'} remaining</span>` : ''}</div><p class="section-note">A saved lookup does not change the report. Open its evidence and choose “Use attribution” on an exact match to include it.</p>${saved?.error ? `<div class="notice warn" role="alert">${ctx.actions.esc(saved.error)} Use Refresh status to reconnect.</div>` : !saved ? '<p role="status">Loading saved attribution…</p>' : ''}${progress}</div><div class="table-wrap"><table><thead><tr><th scope="col">Hostname / IP</th><th scope="col">Finding</th><th scope="col">Source row</th><th scope="col">Attribution</th><th scope="col">Actions</th></tr></thead><tbody>${
      lead.entries
        .map((entry, index) => {
          const asset = byId.get(entry.id),
            lookup = asset?.latest_lookup;
          const identity = ctx.actions.esc(`${entry.source.fields.hostname} / ${entry.ip}`);
          return `<tr><td><strong>${ctx.actions.esc(entry.source.fields.hostname)}</strong><small>${ctx.actions.esc(entry.ip)}</small></td><td>${ctx.actions.esc(observedVersion(entry))}<small>${ctx.actions.esc(entry.source.fields.tag)}</small></td><td><details data-asset-detail="source-${ctx.actions.esc(entry.id)}"><summary>Row ${ctx.actions.esc(entry.source.row)}</summary><small>${ctx.actions.esc(entry.source.workbook)}<br>${ctx.actions.esc(entry.source.sheet)}</small></details></td><td>${asset ? `<span class="badge ${asset.supported ? 'green' : asset.status === 'review' ? 'amber' : 'gray'}">${ctx.actions.esc(asset.support_basis === 'group_attribution' ? 'Covered by group attribution' : asset.support_basis === 'matched_address' ? 'Original matched address' : labels[asset.status] || asset.status)}</span>` : '<span class="section-note">Loading status…</span>'}${lookup?.created_at ? `<small>Checked ${ctx.actions.esc(ctx.actions.stamp(lookup.created_at))}</small>` : ''}${lookup ? `<small><button class="text-button" data-asset-result="${ctx.actions.esc(lookup.id)}" aria-label="View saved attribution for ${identity}">View saved lookup</button></small>` : ''}${asset && !asset.eligible ? '<small>Requires a public IP and a hostname within the attributed root.</small>' : ''}</td><td><div class="actions"><button class="button small" data-attribute-asset="${ctx.actions.esc(entry.id)}" aria-label="${asset?.latest_lookup || asset?.supported ? 'Retry' : 'Try'} attribution for ${identity}" ${running || !asset?.eligible ? 'disabled' : ''}>${asset?.latest_lookup || asset?.supported ? 'Retry attribution' : 'Try attribution'}</button><button class="button small" data-entry="${index}" aria-label="View original report fields for ${identity}">View row fields</button></div></td></tr>`;
        })
        .join('') ||
      '<tr><td colspan="5">No report observations are associated with this notification.</td></tr>'
    }</tbody></table></div></section>`;
  }
  async function showAssetResult(id) {
    const saved = await ctx.actions.api(`/api/asset-attribution/results/${id}`),
      result = saved.result;
    const cards = [...result.evidence, ...result.partial_evidence]
      .map((evidence) => {
        const snapshot = saved.snapshots[evidence.snapshot_id];
        return `<article class="match-card"><h3>${ctx.actions.esc(evidence.source_name)}</h3><p>${ctx.actions.esc(evidence.ip)} · ${ctx.actions.esc(evidence.match.value)}</p><p><a class="text-link" href="${ctx.actions.safeHref(evidence.source_url)}" target="_blank" rel="noopener">Source response${ctx.actions.icon('external')}</a></p><small>Retrieved ${ctx.actions.stamp(evidence.retrieved_at)}${evidence.from_cache ? ' · Preserved cached response' : ''}</small><details><summary>Source identifiers</summary><dl><dt>Matched field</dt><dd>${ctx.actions.esc(evidence.match.field_path)}</dd><dt>SHA-256</dt><dd>${ctx.actions.esc(snapshot?.body_sha256)}</dd></dl></details><details><summary>Preserved response</summary><pre>${ctx.actions.esc(JSON.stringify(saved.records[evidence.snapshot_id], null, 2))}</pre></details></article>`;
      })
      .join('');
    const editable =
      ctx.state.editor.currentLead?.case_id === saved.case_id &&
      ctx.state.editor.currentLead.case.stage === 'in_progress';
    ctx.actions.modal(
      'Saved asset attribution',
      `<p id="asset-result-summary" tabindex="-1"><strong>${ctx.actions.esc(labels[result.status] || result.status)}</strong> · ${ctx.actions.esc(result.root_domain)}</p>${result.status === 'review' ? '<p class="section-note">A registration-name match requires analyst review and is not an exact attribution match.</p>' : ''}${cards}<details ${cards ? '' : 'open'}><summary>Lookup attempts</summary>${result.attempts.map((attempt) => `<p><strong>${ctx.actions.esc(attempt.method)} · ${ctx.actions.esc(attempt.status)}</strong><br>${ctx.actions.esc(attempt.message || attempt.reason)}</p>`).join('')}</details><div class="modal-actions"><a class="button" href="/api/asset-attribution/results/${id}/evidence.zip">${ctx.actions.icon('download')}Download evidence</a>${result.status === 'matched' && editable ? `<button class="button primary" data-adopt-asset="${ctx.actions.esc(id)}" aria-label="Use this saved attribution in the current report">Use attribution</button>` : ''}</div>${result.status === 'matched' && !editable ? '<p class="section-note">To change a frozen report, use its existing revision or section reopen actions first.</p>' : ''}`,
    );
    ctx.actions.$('#asset-result-summary')?.focus?.();
  }
  async function adoptAssetAttribution(id) {
    if (ctx.state.editor.dirty) await ctx.actions.saveDraft();
    const lead = ctx.state.editor.currentLead;
    await ctx.actions.api(`/api/asset-attribution/results/${id}/adopt`, {
      method: 'POST',
      body: { expected_revision: lead.draft_revision },
    });
    ctx.actions.closeModal();
    await ctx.actions.route(true);
    await loadAssetAttribution(lead.case_id);
    ctx.actions.toast('Saved attribution selected for this report.');
  }
  function stopAssetAttributionPolling() {
    state.generation++;
    for (const timer of state.timers.values()) clearTimeout(timer);
    state.timers.clear();
  }
  Object.assign(ctx.actions, {
    assetsMarkup,
    loadAssetAttribution,
    startAssetAttribution,
    cancelAssetAttribution,
    showAssetResult,
    adoptAssetAttribution,
    stopAssetAttributionPolling,
  });
}
