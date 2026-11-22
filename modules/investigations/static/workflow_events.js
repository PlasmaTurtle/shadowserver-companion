/** Workflow interactions. No browser listeners or startup side effects. */
export function createHandlers(ctx) {
  return {
    input(e) {
      const form = e.target.closest(
        '#case-plan,#case-attempt,#case-close,#case-outreach-policy,#entity-profile-form',
      );
      if (form) {
        ctx.state.workflow.workflowDirty = true;
        ctx.state.workflow.changedCaseForms.add(form.id);
      }
    },
    change: [
      {
        matches: (el) => el.id === 'outreach-state',
        run: (el) => {
          const form = el.closest('form');
          const date = form.querySelector('[name="review_on"]');
          date.required = el.value === 'deferred';
          form.querySelector('#outreach-date-help').textContent = date.required
            ? 'Required for deferred outreach.'
            : 'Optional. Set a date to bring this decision back to Workspace.';
        },
      },
    ],
    click: [],
    actions: {
      'review-outreach-decision': () => {
        let form = ctx.actions.$('#case-outreach-policy');
        if (!form) {
          ctx.actions.$('#editor-tab-contact')?.click();
          form = ctx.actions.$('#case-outreach-policy');
        }
        if (!form) return;
        for (
          let parent = form.closest?.('details');
          parent;
          parent = parent.parentElement?.closest?.('details')
        )
          parent.open = true;
        form.scrollIntoView({
          behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
            ? 'auto'
            : 'smooth',
          block: 'start',
        });
        form?.querySelector('[name="state"]')?.focus({ preventScroll: true });
      },
      reopen: async (el) => {
        ctx.actions.openRevisionReason();
      },
      'new-case': async (el) => {
        if (ctx.state.editor.dirty) await ctx.actions.saveDraft();
        const value = await ctx.actions.api('/api/cases', {
          method: 'POST',
          body: { entity_id: ctx.state.editor.currentLead.id },
        });
        location.hash = 'workspace/notifications/' + value.case_id;
      },
      'merge-entity': async (el) => {
        if (ctx.state.editor.dirty) await ctx.actions.saveDraft();
        const choices = (await ctx.actions.api('/api/leads')).filter(
          (x) => x.id !== ctx.state.editor.currentLead.id,
        );
        if (!choices.length) {
          ctx.actions.toast('There are no other entities to combine yet.');
          return;
        }
        ctx.actions.modal(
          'Combine entities',
          `<p>Move all hostnames and observations from <strong>${ctx.actions.esc(ctx.state.editor.currentLead.company || ctx.state.editor.currentLead.domain)}</strong> to the selected entity. Untouched lead groups combine into one notification. Notifications with analyst work stay separate when both have history. Existing report packages retain their content.</p><form id="entity-merge-form" class="form-grid"><div class="field full"><label for="merge-target">Keep this entity</label><select id="merge-target" name="target_id">${choices.map((c) => `<option value="${c.id}" data-revision="${c.draft_revision}">${ctx.actions.esc(c.company || c.domain)} · ${ctx.actions.num(c.assets)} IPs</option>`).join('')}</select></div><div class="modal-actions full"><button class="button primary" type="submit">Combine and review notification</button></div></form>`,
        );
      },
    },
    forms: {
      'section-reopen-form': async (form, obj, data, reviewDecision) => {
        await ctx.actions.submitReopen(form, obj);
        return;
      },
      'report-revise-form': async (form, obj, data, reviewDecision) => {
        await ctx.actions.submitReopen(form, obj);
        return;
      },
      'presentation-adopt-form': async (form, obj, data, reviewDecision) => {
        await ctx.actions.submitReopen(form, obj);
        return;
      },
      'case-search': async (form, obj, data, reviewDecision) => {
        await ctx.actions.caseSubmit(form, obj, data, reviewDecision);
        return;
      },
      'case-outreach-policy': async (form, obj, data, reviewDecision) => {
        await ctx.actions.caseSubmit(form, obj, data, reviewDecision);
      },
      'case-plan': async (form, obj, data, reviewDecision) => {
        await ctx.actions.caseSubmit(form, obj, data, reviewDecision);
        return;
      },
      'case-attempt': async (form, obj, data, reviewDecision) => {
        await ctx.actions.caseSubmit(form, obj, data, reviewDecision);
        return;
      },
      'case-close': async (form, obj, data, reviewDecision) => {
        await ctx.actions.caseSubmit(form, obj, data, reviewDecision);
        return;
      },
      'entity-name-form': async (form, obj, data, reviewDecision) => {
        if (ctx.state.editor.dirty) await ctx.actions.saveDraft();
        ctx.state.editor.currentLead = await ctx.actions.api(
          '/api/entities/' + ctx.state.editor.currentLead.id + '/name',
          {
            method: 'PUT',
            body: {
              name: obj.name,
              expected_revision: ctx.state.editor.currentLead.entity_revision,
            },
          },
        );
        await ctx.actions.route(true);
        ctx.actions.toast('Entity name saved.');
        return;
      },
      'entity-merge-form': async (form, obj, data, reviewDecision) => {
        const option = ctx.actions.$('#merge-target').selectedOptions[0];
        const result = await ctx.actions.api(
          '/api/entities/' + ctx.state.editor.currentLead.id + '/merge',
          {
            method: 'POST',
            body: {
              target_id: obj.target_id,
              source_revision: ctx.state.editor.currentLead.entity_revision,
              target_revision: Number(option.dataset.revision),
            },
          },
        );
        ctx.state.editor.dirty = false;
        ctx.actions.closeModal();
        location.hash = 'entity/' + result.id;
        ctx.actions.toast('Entities combined. Review the retained draft and full asset list.');
        return;
      },
      'entity-profile-form': async (form, obj, data, reviewDecision) => {
        if (ctx.state.editor.dirty) await ctx.actions.saveDraft();
        await ctx.actions.api('/api/entities/' + ctx.state.editor.currentLead.id + '/profile', {
          method: 'PUT',
          body: { ...obj, expected_revision: ctx.state.editor.currentLead.entity_revision },
        });
        ctx.state.workflow.workflowDirty = false;
        ctx.state.workflow.changedCaseForms.delete(form.id);
        await ctx.actions.route(true);
        ctx.actions.toast('Entity details saved.');
        return;
      },
    },
  };
}
