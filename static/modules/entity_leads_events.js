/** Entity and pending-lead actions are independent of the notification editor. */
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
  let locationTimer,
    locationRequest = 0;
  let entityAdoption = null;
  let lifecycleReview = null;
  const entityRevision = (entity) => entity?.entity_revision ?? entity?.draft_revision;
  const entityCurrent = (entity, revision) =>
    ctx.state.entities.current === entity &&
    entityRevision(ctx.state.entities.current) === revision;
  const reasonField =
    '<div class="field"><label for="lifecycle-reason">Reason for this correction</label><textarea id="lifecycle-reason" name="reason" required maxlength="5000"></textarea></div>';
  const lifecycleActions = (label) =>
    `<div class="modal-actions"><button class="button" type="button" data-close-modal>Cancel</button><button class="button primary" type="submit">${label}</button></div>`;
  return {
    input(event) {
      const form = event.target.closest?.(
        '#entity-details-form,#entity-contact-form,#entity-ip-form,#entity-asset-form',
      );
      if (!form) return;
      if (form.id === 'entity-details-form' && ['city', 'state'].includes(event.target.name)) {
        clearTimeout(locationTimer);
        const request = ++locationRequest,
          renderId = ctx.state.navigation.renderId;
        locationTimer = setTimeout(async () => {
          if (renderId !== ctx.state.navigation.renderId) return;
          const city = form.elements.city.value,
            state = form.elements.state.value;
          try {
            const result = await ctx.actions.api(
              '/api/entity-locations?state=' +
                encodeURIComponent(state) +
                '&q=' +
                encodeURIComponent(city),
            );
            if (
              request !== locationRequest ||
              renderId !== ctx.state.navigation.renderId ||
              !form.isConnected
            )
              return;
            const options = ctx.actions.$('#entity-city-options');
            if (options)
              options.innerHTML = result.cities
                .map(
                  (r) =>
                    `<option value="${ctx.actions.esc(r.city)}">${ctx.actions.esc(r.state)}</option>`,
                )
                .join('');
          } catch (error) {
            if (error.name !== 'AbortError' && request === locationRequest) {
              const options = ctx.actions.$('#entity-city-options');
              if (options) options.innerHTML = '';
            }
          }
        }, 180);
      }
      ctx.state.entities.dirty = true;
      ctx.state.entities.changedForms.add(form.id);
      const status = ctx.actions.$('#entity-save-state');
      if (status) status.textContent = 'Unsaved changes';
    },
    change: [],
    click: [],
    actions: {
      'transfer-entity-asset': async (button) => {
        if (ctx.state.entities.dirty)
          throw Error('Save entity changes before transferring ownership.');
        const entity = ctx.state.entities.current,
          revision = entityRevision(entity),
          modalRevision = ctx.actions.currentModalRevision();
        const rows = await ctx.actions.api('/api/entities');
        if (
          !entityCurrent(entity, revision) ||
          modalRevision !== ctx.actions.currentModalRevision()
        )
          return;
        const esc = ctx.actions.esc;
        lifecycleReview = null;
        ctx.actions.modal(
          'Transfer asset ownership',
          `<form id="transfer-asset-select-form" data-entity="${esc(entity.id)}" data-revision="${esc(revision)}" data-hostname="${esc(button.dataset.hostname)}"><p>Transfer <strong>${esc(button.dataset.hostname)}</strong> from ${esc(entity.company || entity.domain)} to another business.</p><div class="field"><label for="transfer-target">New owner</label><select id="transfer-target" name="target_entity_id" required><option value="">Select business</option>${rows
            .filter((r) => r.id !== entity.id)
            .map((r) => `<option value="${esc(r.id)}">${esc(r.company || r.domain)}</option>`)
            .join('')}</select></div>${lifecycleActions('Review affected records')}</form>`,
        );
      },
      'reactivate-entity-finding': async (button) => {
        if (ctx.state.entities.dirty)
          throw Error('Save entity changes before restoring a finding.');
        const entity = ctx.state.entities.current,
          revision = entityRevision(entity),
          modalRevision = ctx.actions.currentModalRevision();
        const endpoint = `/api/entities/${encodeURIComponent(entity.id)}/findings/${encodeURIComponent(button.dataset.finding)}/reactivation`;
        const plan = await ctx.actions.api(endpoint);
        if (
          !entityCurrent(entity, revision) ||
          modalRevision !== ctx.actions.currentModalRevision()
        )
          return;
        lifecycleReview = { entity, revision, plan, endpoint, type: 'reactivation' };
        const esc = ctx.actions.esc;
        ctx.actions.modal(
          'Review finding restoration',
          `<form id="entity-lifecycle-confirm-form" data-entity="${esc(entity.id)}"><p>Restore <strong>${esc(plan.finding.condition)}</strong> for ${esc(plan.finding.hostname)} to Leads using ${esc(plan.restored_observations)} retained approved observations.</p><p>The source evidence and its admission decisions remain unchanged. No notification or report is modified.</p><ul>${plan.sources.map((r) => `<li>${esc(r.observed_at || 'Observation time unknown')} · ${esc(r.ip)} · ${esc(r.sheet)} row ${esc(r.row_number)}</li>`).join('')}</ul>${reasonField}${lifecycleActions('Restore finding')}</form>`,
        );
      },
      'entity-dns-refresh': () => ctx.actions.refreshEntityDns(true),
      'combine-entity': async () => {
        if (ctx.state.entities.dirty) throw Error('Save entity changes before combining records.');
        const entity = ctx.state.entities.current;
        const rows = (await ctx.actions.api('/api/entities')).filter((row) => row.id !== entity.id);
        const esc = ctx.actions.esc;
        ctx.actions.modal(
          'Combine entities',
          `<form id="combine-entity-form" data-source="${esc(entity.id)}" class="form-grid"><div class="field full"><label for="combine-target">Keep this entity</label><select id="combine-target" name="target_id" required><option value="">Select entity</option>${rows.map((row) => `<option value="${esc(row.id)}" data-revision="${esc(row.entity_revision ?? row.draft_revision)}">${esc(row.company || row.domain)}</option>`).join('')}</select></div><p class="section-note">Hostnames, contacts, observations and history are retained under the selected entity. Existing report packages stay unchanged.</p><div class="modal-actions full"><button class="button" type="button" data-close-modal>Cancel</button><button class="button primary" type="submit">Combine</button></div></form>`,
        );
      },
      'use-entity-details': async () => {
        const modalRevision = ctx.actions.currentModalRevision();
        const context = ctx.actions.notificationContext();
        if (ctx.state.editor.dirty) await ctx.actions.saveDraft();
        if (!ctx.actions.notificationContextCurrent(context)) return;
        const saved = ctx.actions.notificationContext();
        const lead = ctx.state.editor.currentLead;
        const plan = await ctx.actions.api(
          '/api/cases/' + encodeURIComponent(lead.case_id) + '/entity-details',
        );
        if (
          !ctx.actions.notificationContextCurrent(saved) ||
          modalRevision !== ctx.actions.currentModalRevision()
        )
          return;
        if (!plan.changed) {
          ctx.actions.toast('This report already uses the current entity details.');
          return;
        }
        entityAdoption = { context: saved, plan };
        const esc = ctx.actions.esc;
        const reopen = plan.reopen_sections || [];
        ctx.actions.modal(
          'Review entity update',
          `<form id="adopt-entity-details-form" data-case="${esc(lead.case_id)}"><p>The report will use the following current business details. Earlier certified reports remain unchanged.</p><div class="table-wrap"><table><thead><tr><th scope="col">Detail</th><th scope="col">In this report</th><th scope="col">Current entity</th></tr></thead><tbody>${plan.changes.map((item) => `<tr><th scope="row">${esc(item.label)}</th><td>${esc(item.before || 'Not recorded')}</td><td>${esc(item.after || 'Not recorded')}</td></tr>`).join('')}</tbody></table></div><p>${reopen.length ? `This update will reopen ${esc(reopen.map((key) => key[0].toUpperCase() + key.slice(1)).join(', '))} for review. Other validated sections stay frozen.` : 'No validated sections need reopening.'}</p><div class="field"><label for="entity-adoption-reason">${reopen.length ? 'Reason for reopening these sections' : 'Review note (optional)'}</label><textarea id="entity-adoption-reason" name="reason" maxlength="5000" ${reopen.length ? 'required' : ''}></textarea></div><div class="modal-actions"><button class="button" type="button" data-close-modal>Cancel</button><button class="button primary" type="submit">${reopen.length ? 'Reopen affected sections and update' : 'Use updated details'}</button></div></form>`,
        );
      },
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
      'transfer-asset-select-form': async (form, obj) => {
        const entity = ctx.state.entities.current,
          revision = Number(form.dataset.revision),
          modalRevision = ctx.actions.currentModalRevision();
        if (form.dataset.entity !== entity?.id || !entityCurrent(entity, revision))
          throw Error('This business changed. Review the transfer again.');
        const endpoint = `/api/entities/${encodeURIComponent(entity.id)}/ownership-transfer`;
        const plan = await ctx.actions.api(
          endpoint +
            '?hostname=' +
            encodeURIComponent(form.dataset.hostname) +
            '&target_entity_id=' +
            encodeURIComponent(obj.target_entity_id),
        );
        if (
          !form.isConnected ||
          !entityCurrent(entity, revision) ||
          modalRevision !== ctx.actions.currentModalRevision()
        )
          return;
        lifecycleReview = { entity, revision, plan, endpoint, type: 'transfer' };
        const esc = ctx.actions.esc;
        ctx.actions.modal(
          'Review ownership transfer',
          `<form id="entity-lifecycle-confirm-form" data-entity="${esc(entity.id)}"><p><strong>${esc(plan.hostname)}</strong>: ${esc(plan.source_name)} → ${esc(plan.target_name)}. Effective on confirmation.</p><h3>Current associations that move</h3><ul>${plan.assets.map((a) => `<li>${esc(a.hostname)}</li>`).join('') || `<li>${esc(plan.hostname)}</li>`}</ul><h3>Pending leads that change</h3>${plan.pending_leads.length ? `<ul>${plan.pending_leads.map((q) => `<li>${esc(q.root_domain)}: ${esc(q.affected_observations)} observations leave current work; ${esc(q.remaining_observations)} remain.</li>`).join('')}</ul>` : '<p>No pending leads affected.</p>'}<h3>Notifications retained by the original business</h3>${plan.retained_cases.length ? `<ul>${plan.retained_cases.map((c) => `<li>${esc(c.title || c.id)} · ${esc(c.stage)}${c.certified_report_id ? ' · certified report retained' : ''}</li>`).join('')}</ul>` : '<p>No notifications affected.</p>'}<p>${esc(plan.historical_evidence)}</p>${reasonField}${lifecycleActions('Confirm ownership transfer')}</form>`,
        );
      },
      'entity-lifecycle-confirm-form': async (form, obj) => {
        const review = lifecycleReview;
        if (
          !review ||
          !form.isConnected ||
          form.dataset.entity !== review.entity.id ||
          !entityCurrent(review.entity, review.revision)
        )
          throw Error('This review is no longer current. Open it again.');
        const modalRevision = ctx.actions.currentModalRevision(),
          plan = review.plan;
        const body =
          review.type === 'transfer'
            ? {
                hostname: plan.hostname,
                target_entity_id: plan.target_entity_id,
                source_revision: plan.source_revision,
                target_revision: plan.target_revision,
                review_token: plan.review_token,
                reason: obj.reason,
              }
            : {
                expected_revision: plan.entity_revision,
                review_token: plan.review_token,
                reason: obj.reason,
              };
        await ctx.actions.api(review.endpoint, { method: 'POST', body });
        if (
          lifecycleReview !== review ||
          !form.isConnected ||
          !entityCurrent(review.entity, review.revision) ||
          modalRevision !== ctx.actions.currentModalRevision()
        )
          return;
        lifecycleReview = null;
        ctx.actions.closeModal();
        await ctx.actions.route(true);
        void ctx.actions.refreshNavigationCounts();
        ctx.actions.toast(
          review.type === 'transfer'
            ? 'Ownership transferred. Earlier evidence remains with its recorded business.'
            : 'Finding restored to Leads.',
        );
      },
      'adopt-entity-details-form': async (form, obj) => {
        const adoption = entityAdoption;
        if (
          !adoption ||
          form.dataset.case !== adoption.plan.case_id ||
          !ctx.actions.notificationContextCurrent(adoption.context)
        )
          throw Error('This notification changed. Review the entity update again.');
        const plan = adoption.plan;
        const updated = await ctx.actions.api(
          '/api/cases/' + encodeURIComponent(plan.case_id) + '/entity-details',
          {
            method: 'POST',
            body: {
              expected_version: plan.expected_version,
              expected_entity_revision: plan.expected_entity_revision,
              reopen_affected: plan.reopen_sections.length > 0,
              reason: obj.reason || '',
            },
          },
        );
        if (ctx.actions.applyNotificationMutation(updated, adoption.context)) {
          if (entityAdoption === adoption) {
            if (form.isConnected) ctx.actions.closeModal();
            entityAdoption = null;
          }
          ctx.actions.toast('Report entity details updated. Review the reopened sections.');
        }
      },
      'combine-entity-form': async (form, obj) => {
        const entity = ctx.state.entities.current;
        if (form.dataset.source !== entity?.id)
          throw Error('This entity changed. Reopen its details.');
        const option = ctx.actions.$('#combine-target').selectedOptions[0];
        const result = await ctx.actions.api(
          '/api/entities/' + encodeURIComponent(entity.id) + '/merge',
          {
            method: 'POST',
            body: {
              target_id: obj.target_id,
              source_revision: entity.entity_revision ?? entity.draft_revision,
              target_revision: Number(option.dataset.revision),
            },
          },
        );
        ctx.actions.closeModal();
        location.hash = 'entity/' + encodeURIComponent(result.id);
        ctx.actions.toast('Entities combined.');
      },
      'entity-asset-form': async (form, obj) => {
        const entity = ctx.state.entities.current;
        if (form.dataset.entity !== entity?.id)
          throw Error('This entity changed. Reopen its assets.');
        if ([...ctx.state.entities.changedForms].some((name) => name !== form.id))
          throw Error('Save the other entity changes before associating an asset.');
        await ctx.actions.api('/api/entities/' + encodeURIComponent(entity.id) + '/assets', {
          method: 'POST',
          body: {
            hostname: obj.hostname,
            expected_revision: entity.entity_revision ?? entity.draft_revision,
          },
        });
        if (ctx.state.entities.current?.id !== entity.id) return;
        ctx.state.entities.dirty = false;
        ctx.state.entities.changedForms.clear();
        await ctx.actions.route(true);
        ctx.actions.toast('Asset associated.');
      },
      'entity-ip-form': async (form, obj) => {
        const entity = ctx.state.entities.current;
        if (form.dataset.entity !== entity?.id)
          throw Error('This entity changed. Reopen its details.');
        await ctx.actions.api(
          '/api/entities/' + encodeURIComponent(entity.id) + '/ip-associations',
          {
            method: 'POST',
            body: {
              ip: obj.ip,
              expected_revision: entity.entity_revision ?? entity.draft_revision,
            },
          },
        );
        ctx.state.entities.dirty = false;
        ctx.state.entities.changedForms.clear();
        await ctx.actions.route(true);
        ctx.actions.toast('IP association saved.');
      },
      'entity-contact-form': async (form, obj) => {
        const entity = ctx.state.entities.current;
        if (form.dataset.entity !== entity?.id)
          throw Error('This entity changed. Reopen its contacts.');
        const profile = entity.entity_profile || {};
        await ctx.actions.api('/api/entities/' + encodeURIComponent(entity.id) + '/profile', {
          method: 'PUT',
          body: {
            contact_name: obj.contact_name || '',
            contact_title: obj.contact_title || '',
            contact_email: obj.contact_email || '',
            contact_phone: obj.contact_phone || '',
            address: profile.address || '',
            city: profile.city || '',
            state: profile.state || '',
            notes: profile.notes || '',
            expected_revision: entity.entity_revision ?? entity.draft_revision,
          },
        });
        ctx.state.entities.dirty = false;
        ctx.state.entities.changedForms.clear();
        await ctx.actions.route(true);
        ctx.actions.toast('Contact saved.');
      },
      'entity-search': async (form, obj) => {
        location.hash = 'entities?' + new URLSearchParams(obj);
      },
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
      'entity-details-form': async (form, obj) => {
        let entity = ctx.state.entities.current;
        if (form.dataset.entity !== entity?.id)
          throw Error('This entity changed. Reopen its details.');
        const endpoint = '/api/entities/' + encodeURIComponent(entity.id);
        if (obj.name !== (entity.company || entity.domain)) {
          entity = await ctx.actions.api(endpoint + '/name', {
            method: 'PUT',
            body: {
              name: obj.name,
              expected_revision: entity.entity_revision ?? entity.draft_revision,
            },
          });
          ctx.state.entities.current = entity;
        }
        const profile = entity.entity_profile || {};
        await ctx.actions.api(endpoint + '/profile', {
          method: 'PUT',
          body: {
            contact_name: profile.contact_name || '',
            contact_title: profile.contact_title || '',
            contact_email: profile.contact_email || '',
            contact_phone: profile.contact_phone || '',
            address: obj.address || '',
            city: obj.city || '',
            state: obj.state || '',
            notes: obj.notes || '',
            expected_revision: entity.entity_revision ?? entity.draft_revision,
          },
        });
        ctx.state.entities.dirty = false;
        ctx.state.entities.changedForms.clear();
        await ctx.actions.route(true);
        ctx.actions.toast('Entity saved.');
      },
    },
  };
}
