/** Queues interactions. No browser listeners or startup side effects. */
export function createHandlers(ctx) {
  return {
    change: [
      {
        matches: (el) => el.hasAttribute?.('data-contact-select'),
        run: (el) => {
          ctx.state.contacts.selectedEntityIds ||= new Set();
          if (el.checked) ctx.state.contacts.selectedEntityIds.add(el.dataset.contactSelect);
          else ctx.state.contacts.selectedEntityIds.delete(el.dataset.contactSelect);
          el.closest('tr')?.classList.toggle('is-selected', el.checked);
          ctx.actions.contactBatchSelectionChanged?.();
        },
      },
      {
        matches: (el, e) => el.hasAttribute?.('data-submit-filter'),
        run: async (el, e) => {
          el.closest('form')?.requestSubmit();
          return;
        },
      },
      {
        matches: (el, e) => el.id === 'report-files',
        run: async (el, e) => {
          return ctx.actions.upload(el.files);
        },
      },
    ],
    click: [
      {
        matches: (el) => el.dataset.attributionDecision,
        run: (el) =>
          ctx.actions.busy(el, async () => {
            const row = el.closest('[data-attribution-review-row]');
            if (!row || row.dataset.pending === 'true') return;
            row.dataset.pending = 'true';
            const controls = [...row.querySelectorAll('button')].map((button) => [
              button,
              button === el ? false : button.disabled,
            ]);
            controls.forEach(([button]) => {
              button.disabled = true;
            });
            try {
              await ctx.actions.api(
                '/api/groups/' + encodeURIComponent(el.dataset.attributionGroup) + '/review',
                {
                  method: 'POST',
                  body: {
                    result_id: el.dataset.result,
                    evidence_index:
                      el.dataset.attributionDecision === 'accept'
                        ? Number(el.dataset.evidenceIndex)
                        : null,
                    decision: el.dataset.attributionDecision,
                    note:
                      el.dataset.attributionDecision === 'accept'
                        ? 'Accepted the displayed registration match from the attribution list.'
                        : 'Rejected from the attribution list.',
                  },
                },
              );
              row.remove();
              const total = ctx.actions.$('[data-review-total]');
              if (total) {
                const remaining = Math.max(
                  0,
                  Number(String(total.textContent).replaceAll(',', '')) - 1,
                );
                total.textContent = ctx.actions.num(remaining);
                if (!remaining) await ctx.actions.route(true);
              }
              void ctx.actions.refreshNavigationCounts();
            } finally {
              delete row.dataset.pending;
              controls.forEach(([button, disabled]) => {
                button.disabled = disabled;
              });
            }
          }),
      },
      {
        matches: (el) => el.dataset.reevaluateImport,
        run: (el) =>
          ctx.actions.busy(el, async () => {
            const result = await ctx.actions.api(
              '/api/imports/' + el.dataset.reevaluateImport + '/reevaluate',
              { method: 'POST' },
            );
            ctx.actions.toast(
              result.duplicate
                ? 'This file and policy have already been evaluated.'
                : 'Original file queued under the current policy; prior results retained.',
            );
            await ctx.actions.showImport(result.id);
          }),
      },
      {
        matches: (el, e) => el.dataset.group,
        run: async (el, e) => {
          return ctx.actions.busy(null, () => ctx.actions.showGroup(el.dataset.group));
        },
      },
      {
        matches: (el, e) => el.dataset.retryGroup,
        run: async (el, e) => {
          return ctx.actions.busy(el, async () => {
            await ctx.actions.api('/api/groups/' + el.dataset.retryGroup + '/retry', {
              method: 'POST',
              body: { result_id: el.dataset.result || null },
            });
            ctx.actions.closeModal();
            await ctx.actions.route(true);
            ctx.actions.toast('Attribution retry queued.');
          });
        },
      },
      {
        matches: (el, e) => el.dataset.import,
        run: async (el, e) => {
          return ctx.actions.busy(null, () => ctx.actions.showImport(el.dataset.import));
        },
      },
      {
        matches: (el, e) => el.dataset.pause || el.dataset.retry,
        run: async (el, e) => {
          return ctx.actions.busy(el, async () => {
            const id = el.dataset.pause || el.dataset.retry;
            await ctx.actions.api(`/api/imports/${id}/${el.dataset.pause ? 'pause' : 'retry'}`, {
              method: 'POST',
            });
            await ctx.actions.showImport(id);
            await ctx.actions.route(true);
          });
        },
      },
    ],
    actions: {
      scan: async (el) => {
        const result = await ctx.actions.api('/api/inbox/scan', { method: 'POST' });
        ctx.actions.toast(`${result.added} reports added from inbox.`);
        await ctx.actions.route(true);
      },
    },
    forms: {
      'attribution-review-form': async (form, obj, data, reviewDecision) => {
        const result = await ctx.actions.api('/api/groups/' + form.dataset.group + '/review', {
          method: 'POST',
          body: {
            result_id: form.dataset.result,
            evidence_index: reviewDecision === 'accept' ? Number(obj.evidence_index) : null,
            decision: reviewDecision,
            note: obj.note || '',
          },
        });
        ctx.actions.closeModal();
        if (result.lead_id) location.hash = 'entity/' + result.lead_id;
        else await ctx.actions.route(true);
        ctx.actions.toast(
          result.lead_id
            ? 'Attribution accepted. All group observations retained.'
            : 'Match dismissed. Evidence and decision retained.',
        );
        return;
      },
      'lead-search': async (form, obj, data, reviewDecision) => {
        location.hash = 'entities?' + new URLSearchParams(obj);
        return;
      },
      'global-search-form': async (form, obj, data, reviewDecision) => {
        ctx.actions.closeModal();
        location.hash = 'entities?q=' + encodeURIComponent(obj.q);
        return;
      },
    },
  };
}
