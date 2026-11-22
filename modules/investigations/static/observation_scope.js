/** Review recipient scope without altering original imported observations. */
export function install(ctx) {
  let caseId = '',
    query = '',
    page = 0,
    pending = null;
  const pageSize = 50;
  function markup() {
    const lead = ctx.state.editor.currentLead;
    const scope = lead?.observation_scope;
    if (!scope) return '';
    if (caseId !== lead.case_id) {
      caseId = lead.case_id;
      query = '';
      page = 0;
    }
    const esc = ctx.actions.esc;
    const rows = (scope.rows || []).filter((row) =>
      [row.hostname, row.ip, row.finding, row.reason, row.source?.workbook].some((value) =>
        String(value || '')
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    );
    page = Math.min(page, Math.max(0, Math.ceil(rows.length / pageSize) - 1));
    const shown = rows.slice(page * pageSize, (page + 1) * pageSize);
    return `<section class="panel" id="observation-scope-panel"><div class="panel-head"><div><h2>Recipient report scope</h2><p>${esc(scope.included)} included source observations${scope.finding_observations != null && scope.finding_observations < scope.included ? ` · ${esc(scope.finding_observations)} with findings` : ''} · ${esc(scope.excluded)} excluded · ${esc(scope.unresolved)} need review</p></div></div><div class="panel-body">${scope.unresolved ? '<p class="notice" role="status">Nonpublic or invalid addresses cannot establish public exposure. Review these source rows before certifying a new or revised report. The original evidence stays in the internal record.</p>' : ''}<p class="section-note">Exclusions affect this notification only. Source records and previous certified reports remain unchanged. A supporting attribution record may still establish the business association without being a notified finding.</p>${scope.editable && scope.unresolved ? `<button class="button" data-action="scope-exclude-anomalies">Review ${Math.min(scope.unresolved, 1000)} flagged observations</button>` : ''}<details ${scope.unresolved ? 'open' : ''}><summary>Review source observations (${esc(scope.total)})</summary><form id="scope-search" class="actions"><label for="scope-query">Find observation</label><input id="scope-query" name="q" value="${esc(query)}" placeholder="Hostname, IP, finding or source"><button class="button small" type="submit">Search</button></form><div class="table-wrap"><table><thead><tr><th scope="col">Observation</th><th scope="col">Source</th><th scope="col">Report decision</th><th scope="col">Action</th></tr></thead><tbody>${shown.map((row) => `<tr><td><strong>${esc(row.hostname || row.ip)}</strong><small>${esc(row.ip)} · ${esc(row.service)}</small><small>${esc(row.finding)}</small>${row.issue ? `<p class="badge warning">${esc(row.issue)}</p>` : ''}</td><td>${esc(row.source?.workbook)}<small>${esc(row.source?.sheet)} · row ${esc(row.source?.row)}</small><small>${esc(row.observed_at)}</small></td><td>${row.included ? 'Included' : 'Excluded'}${row.reason ? `<p>${esc(row.reason)}</p><small>${esc(row.actor)} · ${esc(row.decided_at)}</small>` : ''}</td><td>${scope.editable && (row.included || !row.issue) ? `<button class="button small" data-action="scope-review-row" data-entry-id="${esc(row.entry_id)}">${row.included ? 'Exclude' : 'Include'}</button>` : ''}</td></tr>`).join('') || '<tr><td colspan="4">No observations match.</td></tr>'}</tbody></table></div><div class="actions"><button class="button small" data-action="scope-page-previous" ${page === 0 ? 'disabled' : ''}>Previous</button><span role="status">${rows.length ? page * pageSize + 1 : 0}–${Math.min((page + 1) * pageSize, rows.length)} of ${rows.length}</span><button class="button small" data-action="scope-page-next" ${(page + 1) * pageSize >= rows.length ? 'disabled' : ''}>Next</button></div></details></div></section>`;
  }
  function refresh() {
    const node = ctx.actions.$('#observation-scope-panel');
    if (node) node.outerHTML = markup();
  }
  async function open(ids, decision) {
    const context = ctx.actions.notificationContext();
    if (ctx.state.editor.dirty) await ctx.actions.saveDraft();
    if (!ctx.actions.notificationContextCurrent(context)) return;
    const lead = ctx.state.editor.currentLead;
    if (!lead.observation_scope?.editable)
      throw Error('Revise the report before changing its scope.');
    const rows = lead.observation_scope.rows.filter((row) => ids.includes(row.entry_id));
    if (rows.length !== ids.length)
      throw Error('These observations changed. Reload before reviewing.');
    pending = {
      context: ctx.actions.notificationContext(),
      ids,
      decision,
      version: lead.case.version,
      revision: lead.draft_revision,
    };
    const esc = ctx.actions.esc;
    const frozen = (lead.section_reviews || []).some((item) => item.status !== 'draft');
    ctx.actions.modal(
      'Review notification scope',
      `<form id="observation-scope-form" data-case="${esc(lead.case_id)}"><p>${decision === 'exclude' ? 'Exclude from' : 'Include in'} this recipient notification: <strong>${rows.length} observation${rows.length === 1 ? '' : 's'}</strong>.</p><p>${rows
        .slice(0, 5)
        .map((row) =>
          esc(`${row.hostname} · ${row.ip} · ${row.source?.workbook} row ${row.source?.row}`),
        )
        .join(
          '<br>',
        )}${rows.length > 5 ? `<br>and ${rows.length - 5} more` : ''}</p><p>Original evidence remains in the internal record. This does not assert remediation or change an earlier certified report.</p><div class="field"><label for="scope-reason">Reason for this scope decision</label><textarea id="scope-reason" name="reason" required maxlength="5000"></textarea></div>${frozen ? '<label class="checkbox"><input type="checkbox" name="reopen_affected" value="true" required><span>Reopen affected frozen sections for review using this reason.</span></label>' : ''}<div class="modal-actions"><button class="button" type="button" data-close-modal>Cancel</button><button class="button primary" type="submit">Save scope decision</button></div></form>`,
    );
  }
  async function submit(form, obj) {
    const saved = pending;
    if (
      !saved ||
      form.dataset.case !== saved.context.caseId ||
      !ctx.actions.notificationContextCurrent(saved.context)
    )
      throw Error('This notification changed. Reopen its scope review.');
    const result = await ctx.actions.api(
      `/api/cases/${encodeURIComponent(saved.context.caseId)}/observation-scope`,
      {
        method: 'POST',
        body: {
          expected_version: saved.version,
          expected_revision: saved.revision,
          entry_ids: saved.ids,
          decision: saved.decision,
          reason: obj.reason,
          reopen_affected: obj.reopen_affected === 'true',
        },
      },
    );
    if (!ctx.actions.notificationContextCurrent(saved.context)) return;
    if (pending === saved) {
      pending = null;
      if (form.isConnected) ctx.actions.closeModal();
    }
    ctx.actions.applyNotificationMutation(result, saved.context);
    ctx.actions.toast(
      `Scope saved.${result.scope_reopened_sections?.length ? ` Review reopened sections: ${result.scope_reopened_sections.join(', ')}.` : ''}`,
    );
  }
  Object.assign(ctx.actions, {
    observationScopeMarkup: markup,
    openScopeRow: (button) => {
      const row = ctx.state.editor.currentLead?.observation_scope?.rows.find(
        (item) => item.entry_id === button.dataset.entryId,
      );
      if (!row) throw Error('Observation unavailable. Reload this notification.');
      return open([row.entry_id], row.included ? 'exclude' : 'include');
    },
    openScopeAnomalies: () =>
      open(
        ctx.state.editor.currentLead.observation_scope.rows
          .filter((row) => row.requires_review)
          .slice(0, 1000)
          .map((row) => row.entry_id),
        'exclude',
      ),
    scopeSearch: (value) => {
      query = value || '';
      page = 0;
      refresh();
    },
    scopePage: (delta) => {
      page = Math.max(0, page + delta);
      refresh();
    },
    submitObservationScope: submit,
  });
}

export function createHandlers(ctx) {
  return {
    change: [],
    click: [],
    actions: {
      'scope-review-row': (button) => ctx.actions.openScopeRow(button),
      'scope-exclude-anomalies': () => ctx.actions.openScopeAnomalies(),
      'scope-page-previous': () => ctx.actions.scopePage(-1),
      'scope-page-next': () => ctx.actions.scopePage(1),
    },
    forms: {
      'scope-search': (form, obj) => ctx.actions.scopeSearch(obj.q),
      'observation-scope-form': (form, obj) => ctx.actions.submitObservationScope(form, obj),
    },
  };
}
