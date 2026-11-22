/** Viewport capture never replaces unsaved narrative or starts a report render. */
export function install(ctx) {
  let timer = null,
    generation = 0,
    running = null,
    lastMessage = '',
    lastDownloadActivity = null,
    lastCaseId = null;
  const esc = (...args) => ctx.actions.esc(...args);
  function captureMarkup() {
    const lead = ctx.state.editor.currentLead;
    const hosts = [...new Set((lead.hostnames || []).map((h) => h.name).filter(Boolean))];
    const active = !!running;
    return `<div class="website-capture"><div class="field"><label for="capture-hostname">Reported hostname</label><select id="capture-hostname" ${active ? 'disabled' : ''}>${hosts.map((h) => `<option value="${esc(h)}">${esc(h)}</option>`).join('')}</select></div><button class="button primary" type="button" data-action="capture-website" ${active || !hosts.length ? 'disabled' : ''}>Capture website</button>${active ? '<button class="button" type="button" data-action="cancel-website-capture">Cancel</button>' : ''}<p class="website-capture-status" role="status">${esc(active ? 'Capturing desktop viewport…' : (lastCaseId === lead.case_id && lastMessage) || '1440 × 900 · viewport only')}</p>${!active && lastCaseId === lead.case_id ? ctx.actions.downloadActivityMarkup(lastDownloadActivity) : ''}</div>`;
  }
  function provenance(item) {
    const c = item.capture;
    if (!c) return '';
    const labels = {
      captured: 'Viewport captured',
      partial: 'Incomplete page',
      challenge: 'Access challenge',
      login_required: 'Login page',
      load_failed: 'Page load failed',
    };
    const text = (value, limit = 4096) =>
      esc(typeof value === 'string' ? value.replace(/\s+/g, ' ').trim().slice(0, limit) : '');
    const label = (status, fallback) => (Object.hasOwn(labels, status) ? labels[status] : fallback);
    const redirects = Array.isArray(c.redirects) ? c.redirects : [];
    const attempts = Array.isArray(c.attempts) ? c.attempts : [];
    const navigation = redirects.length
      ? `<p><strong>Page navigation</strong></p><ol>${redirects
          .slice(0, 10)
          .map((url) => `<li><code>${text(url)}</code></li>`)
          .join(
            '',
          )}</ol>${redirects.length > 10 ? `<p>Showing 10 of ${redirects.length} navigation steps.</p>` : ''}`
      : '';
    const outcomes = attempts.length
      ? `<p><strong>Capture attempts</strong></p><ol>${attempts
          .slice(0, 8)
          .map((attempt) => {
            const a = attempt && typeof attempt === 'object' ? attempt : {};
            const status =
              Number.isInteger(a.http_status) && a.http_status >= 100 && a.http_status <= 599
                ? ` · HTTP ${a.http_status}`
                : '';
            return `<li><code>${text(a.url)}</code> — ${esc(label(a.outcome, 'Capture attempt'))}${status}${a.reason ? ` · ${text(a.reason, 240)}` : ''}${a.final_url && a.final_url !== a.url ? `<br>Final page: <code>${text(a.final_url)}</code>` : ''}</li>`;
          })
          .join(
            '',
          )}</ol>${attempts.length > 8 ? `<p>Showing 8 of ${attempts.length} attempts.</p>` : ''}`
      : '';
    return `<span class="badge ${c.capture_status === 'captured' ? 'gray' : 'amber'}">${esc(label(c.capture_status, 'Capture'))}</span>${c.fallback_used === true ? '<span class="badge amber">Main-site fallback</span>' : ''}<details class="capture-provenance"><summary>Capture details</summary><dl><dt>Requested</dt><dd>${esc(c.requested_url)}</dd><dt>Final page</dt><dd>${esc(c.final_url)}</dd>${c.root_domain ? `<dt>Main site</dt><dd>${text(c.root_domain, 253)}</dd>` : ''}<dt>Title</dt><dd>${esc(c.title || 'Untitled')}</dd><dt>Viewport</dt><dd>${esc(c.viewport?.width)} × ${esc(c.viewport?.height)}</dd><dt>HTTP status</dt><dd>${esc(c.http_status || 'Unavailable')}</dd>${c.blocked_requests > 0 ? `<dt>Limited requests</dt><dd>${esc(c.blocked_requests)}</dd>` : ''}<dt>SHA-256</dt><dd><code>${esc(item.sha256)}</code></dd></dl>${ctx.actions.downloadActivityMarkup(c.download_activity)}${navigation}${outcomes}${
      (c.resource_failures || []).length
        ? `<ul>${c.resource_failures
            .slice(0, 8)
            .map((failure) => `<li>${esc(failure.stage)}: ${esc(failure.reason)}</li>`)
            .join('')}</ul>`
        : ''
    }</details>`;
  }
  function repaint() {
    const slot = ctx.actions.$('#website-capture-controls');
    if (slot && ctx.state.editor.currentLead) slot.innerHTML = captureMarkup();
  }
  function stopWebsiteCapturePolling() {
    generation++;
    clearTimeout(timer);
    timer = null;
    running = null;
  }
  async function poll(token) {
    if (!running || token !== generation) return;
    const watch = running;
    try {
      const result = await ctx.actions.api('/api/website-captures/' + watch.id);
      if (token !== generation) return;
      if (['queued', 'running'].includes(result.state)) {
        timer = setTimeout(() => poll(token), 750);
        return;
      }
      running = null;
      lastMessage = result.message;
      lastDownloadActivity = ['failed', 'cancelled'].includes(result.state)
        ? result.download_activity
        : null;
      lastCaseId = watch.caseId;
      const lead = ctx.state.editor.currentLead;
      if (lead?.case_id === watch.caseId && result.state === 'completed') {
        const fresh = await ctx.actions.api(ctx.actions.leadURL(''));
        if (token !== generation || ctx.state.editor.currentLead?.case_id !== watch.caseId) return;
        const current = ctx.state.editor.currentLead;
        if (!ctx.state.editor.dirty) {
          ctx.state.editor.currentLead = fresh;
          ctx.state.editor.draft = structuredClone(fresh.draft);
        } else if (
          current.case?.version === result.prior_version &&
          fresh.case?.version === result.case_version
        ) {
          ctx.state.editor.currentLead = fresh;
          // Keep every unsaved field; capture only invalidates the reviewed flag.
          ctx.state.editor.draft.reviewed = false;
        } else {
          lastMessage += '. Saved; reopen this notification after saving your edits to view it.';
        }
        const region = ctx.actions.$('#editor-content');
        if (region) region.innerHTML = ctx.actions.editorContent();
      } else if (lead?.case_id === watch.caseId && lastDownloadActivity) {
        repaint();
        // A failed history refresh must not hide the terminal job result.
        const fresh = await ctx.actions.api(ctx.actions.leadURL('')).catch(() => null);
        if (token !== generation || ctx.state.editor.currentLead?.case_id !== watch.caseId) return;
        if (fresh) {
          ctx.state.editor.currentLead.history = fresh.history;
          const region = ctx.actions.$('#editor-content');
          if (region && ctx.state.editor.tab === 'activity')
            region.innerHTML = ctx.actions.editorContent();
        }
      }
      repaint();
      ctx.actions.toast(lastMessage);
    } catch (error) {
      if (token !== generation) return;
      running = null;
      lastMessage = error.message;
      lastDownloadActivity = null;
      lastCaseId = watch.caseId;
      repaint();
      ctx.actions.toast(error.message);
    }
  }
  async function captureWebsite() {
    if (running) return;
    if (ctx.state.editor.dirty) await ctx.actions.saveDraft();
    if (ctx.state.editor.dirty) return;
    const token = generation;
    const caseId = ctx.state.editor.currentLead.case_id;
    const hostname = ctx.actions.$('#capture-hostname')?.value;
    const job = await ctx.actions.api(
      '/api/cases/' + encodeURIComponent(caseId) + '/website-capture',
      { method: 'POST', body: { hostname } },
    );
    if (token !== generation) return;
    running = { id: job.id, caseId };
    lastMessage = '';
    lastDownloadActivity = null;
    repaint();
    poll(++generation);
  }
  async function cancelWebsiteCapture() {
    if (running)
      await ctx.actions.api('/api/website-captures/' + running.id + '/cancel', {
        method: 'POST',
        body: {},
      });
  }
  Object.assign(ctx.actions, {
    captureMarkup,
    captureProvenance: provenance,
    captureWebsite,
    cancelWebsiteCapture,
    stopWebsiteCapturePolling,
  });
}
