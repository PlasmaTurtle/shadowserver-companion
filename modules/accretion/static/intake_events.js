/** Intake controls and upload handlers; teardown releases the owned dropzone. */
export function createHandlers(ctx) {
  return {
    change: [
      {
        matches: (el, e) => el.id === 'report-files',
        run: async (el, e) => {
          return ctx.actions.upload(el.files);
        },
      },
    ],
    click: [
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
    forms: {},
    dispose: () => ctx.actions.disposeIntakeDropzone?.(),
  };
}
