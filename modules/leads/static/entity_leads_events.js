/** Qualified-lead association, disposition and explicit investigation-start events. */
export function createHandlers(ctx) {
  const advance = async (id, view, created = '') => {
    void ctx.actions.refreshNavigationCounts();
    if (ctx.state.navigation.renderId !== view) return;
    const next = await ctx.actions.nextLeadRoute(id, created);
    if (ctx.state.navigation.renderId !== view) return;
    if (next === location.hash.replace(/^#/, '')) await ctx.actions.route(true);
    else location.hash = next;
    if (created && next !== created) ctx.actions.toast('Findings assigned to notification.');
  };
  const start = async (caseId = '') => {
    const lead = ctx.state.intakeLeads.current;
    const view = ctx.state.navigation.renderId;
    const target = (lead.active_cases || []).find((c) => c.id === caseId);
    const result = await ctx.actions.api(
      `/api/pending-leads/${encodeURIComponent(lead.id)}/start`,
      {
        method: 'POST',
        body: {
          expected_revision: lead.revision,
          ...(target ? { case_id: target.id, expected_case_version: target.version } : {}),
        },
      },
    );
    const created = 'workspace/notifications/' + encodeURIComponent(result.case_id);
    await advance(lead.id, view, created);
  };
  const disposition = async (status) => {
    const lead = ctx.state.intakeLeads.current;
    const view = ctx.state.navigation.renderId;
    await ctx.actions.api(`/api/pending-leads/${encodeURIComponent(lead.id)}/disposition`, {
      method: 'POST',
      body: { expected_revision: lead.revision, status },
    });
    await advance(lead.id, view);
  };
  return {
    change: [],
    click: [],
    actions: {
      'refresh-leads': () => ctx.actions.route(true),
      'ignore-queue-lead': async (button) => {
        const view = ctx.state.navigation.renderId;
        await ctx.actions.api(
          `/api/pending-leads/${encodeURIComponent(button.dataset.lead)}/disposition`,
          {
            method: 'POST',
            body: { expected_revision: Number(button.dataset.revision), status: 'dismissed' },
          },
        );
        await advance(button.dataset.lead, view);
      },
      'start-lead': () => start(),
      'defer-lead': () => disposition('deferred'),
      'dismiss-lead': () => disposition('dismissed'),
      'restore-lead': () => disposition('pending'),
    },
    forms: {
      'pending-lead-search': async (form, obj) => {
        location.hash = 'leads?' + new URLSearchParams(obj);
      },
      'lead-start-form': async (form, obj) => start(obj.case_id),
      'lead-associate-form': async (form, obj) => {
        const lead = ctx.state.intakeLeads.current;
        await ctx.actions.api(`/api/pending-leads/${encodeURIComponent(lead.id)}/associate`, {
          method: 'POST',
          body: { expected_revision: lead.revision, entity_id: obj.entity_id },
        });
        await ctx.actions.route(true);
      },
    },
  };
}
