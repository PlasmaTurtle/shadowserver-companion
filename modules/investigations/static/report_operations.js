/** One bounded report action at a time, with visible progress and recoverable errors. */
export function install(ctx) {
  let pending = null;
  let previewURL = null;
  let sequence = 0;

  async function reportOperation(title, work) {
    if (pending) throw Error('A report action is already running. Wait for it to finish.');
    const operation = {
      id: ++sequence,
      caseId: ctx.state.editor.currentLead?.case_id,
      serverId: null,
      timer: null,
    };
    pending = operation;
    ctx.actions.modal(
      title,
      `<p id="report-operation-status" data-operation="${operation.id}" role="status"><span class="spinner"></span> Preparing notification content…</p><p class="section-note">Closing this dialog leaves the operation running. You can check its status in Recent report activity.</p><div class="modal-actions"><button id="report-operation-cancel" class="button" disabled>Stop preparation</button><button id="report-operation-history" class="button">Recent report activity</button></div>`,
    );
    const ownsDialog = () =>
      sequence === operation.id &&
      ctx.actions.$('#report-operation-status')?.dataset.operation === String(operation.id);
    const bindControls = () => {
      ctx.actions.$('#report-operation-cancel')?.addEventListener?.('click', async () => {
        if (!operation.serverId) return;
        const button = ctx.actions.$('#report-operation-cancel');
        if (button) button.disabled = true;
        try {
          await ctx.actions.api(
            `/api/report-operations/${encodeURIComponent(operation.serverId)}/cancel`,
            { method: 'POST', body: {}, timeoutMs: 10000 },
          );
        } catch (error) {
          ctx.actions.toast?.(error.message, true);
          const status = ctx.actions.$('#report-operation-status');
          if (status) status.textContent = error.message;
        }
      });
      ctx.actions.$('#report-operation-history')?.addEventListener?.('click', showReportActivity);
    };
    bindControls();
    const poll = async () => {
      if (pending !== operation) return;
      try {
        const query = operation.caseId
          ? `?case_id=${encodeURIComponent(operation.caseId)}&limit=5`
          : '?limit=5';
        const response = await ctx.actions.api('/api/report-operations' + query, {
          timeoutMs: 5000,
        });
        if (pending !== operation) return;
        const rows = response.operations || [];
        const record = operation.serverId
          ? rows.find((row) => row.id === operation.serverId)
          : rows.find((row) => ['running', 'cancelling', 'committing'].includes(row.state));
        if (record) {
          operation.serverId = record.id;
          if (ownsDialog()) {
            const status = ctx.actions.$('#report-operation-status');
            if (status)
              status.textContent = `${record.phase} · ${Math.round(record.elapsed_seconds || 0)} seconds`;
            const button = ctx.actions.$('#report-operation-cancel');
            if (button) button.disabled = !record.cancellable;
          }
        }
      } catch {
        if (pending === operation && ownsDialog()) {
          const status = ctx.actions.$('#report-operation-status');
          if (status)
            status.textContent =
              'Progress updates are temporarily unavailable. Preparation may still be running; use Recent report activity to check its status.';
        }
        // The original action determines success/failure. A status request is
        // observational and never causes a mutation to be retried.
      }
      if (pending === operation) operation.timer = setTimeout(poll, 1000);
    };
    operation.timer = setTimeout(poll, 750);
    try {
      return await work(
        { timeoutMs: 120000 },
        () =>
          sequence === operation.id && ctx.state.editor.currentLead?.case_id === operation.caseId,
      );
    } catch (error) {
      if (ownsDialog())
        ctx.actions.modal(
          'Report action needs attention',
          `<p role="alert">${ctx.actions.esc(error.message)}</p><p class="section-note">Your saved work remains available. Check Recent report activity before retrying; the operation may have finished after the connection was interrupted.</p><button id="report-operation-history" class="button">Recent report activity</button>`,
        );
      ctx.actions.$('#report-operation-history')?.addEventListener?.('click', showReportActivity);
      throw error;
    } finally {
      if (operation.timer) clearTimeout(operation.timer);
      if (ownsDialog()) ctx.actions.closeModal();
      if (pending === operation) pending = null;
    }
  }

  async function showReportActivity() {
    const caseId = ctx.state.editor.currentLead?.case_id;
    try {
      const response = await ctx.actions.api(
        '/api/report-operations' + (caseId ? `?case_id=${encodeURIComponent(caseId)}` : ''),
        { timeoutMs: 10000 },
      );
      const rows = response.operations || [];
      ctx.actions.modal(
        'Recent report activity',
        `${response.warning ? `<p role="alert">${ctx.actions.esc(response.warning)}</p>` : ''}<p class="section-note">Recent preparation and certification activity for this notification. Interrupted work is never automatically retried.</p>${rows.length ? `<ul>${rows.map((row) => `<li><strong>${ctx.actions.esc(row.operation)} · ${ctx.actions.esc(row.state.replaceAll('_', ' '))}</strong><br>${ctx.actions.esc(ctx.actions.stamp?.(row.started_at) || row.started_at)} · ${Math.round(row.elapsed_seconds || 0)} seconds${row.error ? `<p>${ctx.actions.esc(row.error)}</p>` : ''}${row.cancellable ? `<p><button class="button small" data-report-cancel="${ctx.actions.esc(row.id)}">Stop preparation</button></p>` : ''}</li>`).join('')}</ul>` : '<p>No report operations have been recorded for this notification.</p>'}<div class="modal-actions"><button id="report-history-refresh" class="button">Refresh status</button></div>`,
      );
      ctx.actions.$('#report-history-refresh')?.addEventListener?.('click', showReportActivity);
      for (const button of ctx.actions.$$?.('#modal-body [data-report-cancel]') || []) {
        button.addEventListener('click', () =>
          ctx.actions.busy(button, async () => {
            await ctx.actions.api(
              `/api/report-operations/${encodeURIComponent(button.dataset.reportCancel)}/cancel`,
              { method: 'POST', body: {}, timeoutMs: 10000 },
            );
            await showReportActivity();
          }),
        );
      }
    } catch (error) {
      ctx.actions.modal(
        'Report activity unavailable',
        `<p role="alert">${ctx.actions.esc(error.message)}</p>`,
      );
    }
  }

  function showReportPDF(title, blob, notice = '') {
    if (previewURL) URL.revokeObjectURL(previewURL);
    previewURL = URL.createObjectURL(blob);
    ctx.actions.modal(
      title,
      `${notice}<p><a class="text-link" href="${previewURL}" target="_blank" rel="noopener">Open PDF in a new tab ${ctx.actions.icon('external')}</a></p><iframe class="pdf-preview" title="${ctx.actions.esc(title)}" src="${previewURL}"></iframe>`,
    );
  }

  async function previewReport() {
    return ctx.actions.reportOperation(
      'Preparing notification preview',
      async (options, isCurrent) => {
        if (ctx.state.editor.dirty) await ctx.actions.saveDraft(options);
        if (!isCurrent()) return;
        const notice = ctx.actions.historicalReportNotice();
        const blob = await ctx.actions.api(ctx.actions.leadURL('/preview.pdf'), {
          ...options,
          blob: true,
        });
        if (isCurrent()) ctx.actions.showReportPDF('Notification preview', blob, notice);
      },
    );
  }

  function disposeReportPreview() {
    sequence++;
    if (previewURL) URL.revokeObjectURL(previewURL);
    previewURL = null;
  }

  Object.assign(ctx.actions, {
    reportOperation,
    showReportActivity,
    showReportPDF,
    previewReport,
    disposeReportPreview,
  });
}
