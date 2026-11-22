/** Qualified-lead association, disposition and explicit investigation-start events. */
export function createHandlers(ctx) {
  const start = async (caseId = '') => {
    const lead = ctx.state.intakeLeads.current;
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
    location.hash = 'workspace/notifications/' + encodeURIComponent(result.case_id);
    void ctx.actions.refreshNavigationCounts();
  };
  const disposition = async (status) => {
    const lead = ctx.state.intakeLeads.current;
    await ctx.actions.api(`/api/pending-leads/${encodeURIComponent(lead.id)}/disposition`, {
      method: 'POST',
      body: { expected_revision: lead.revision, status },
    });
    location.hash = ctx.state.navigation.returns.get('leads') || 'leads';
    void ctx.actions.refreshNavigationCounts();
  };
  return {
    change: [],
    click: [],
    actions: {
      'refresh-leads': () => ctx.actions.route(true),
      'ignore-queue-lead': async (button) => {
        await ctx.actions.api(
          `/api/pending-leads/${encodeURIComponent(button.dataset.lead)}/disposition`,
          {
            method: 'POST',
            body: { expected_revision: Number(button.dataset.revision), status: 'dismissed' },
          },
        );
        await ctx.actions.route(true);
        void ctx.actions.refreshNavigationCounts();
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
