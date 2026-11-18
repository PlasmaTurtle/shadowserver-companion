/** Case-owned saved outreach text; clipboard preparation never sends a message. */
export function install(ctx) {
  const state = { session: null, generation: 0 };
  ctx.state.outreachPreparation = state;
  const fields = ['subject', 'message', 'call_outline'];
  const ids = {
    subject: 'outreach-subject',
    message: 'outreach-message',
    call_outline: 'outreach-call',
  };
  const esc = (value) => ctx.actions.esc(value);
  const endpoint = (id) => '/api/cases/' + encodeURIComponent(id);
  const current = (session) =>
    state.session === session && ctx.state.editor.currentLead?.case_id === session.caseId;
  const values = (data) => Object.fromEntries(fields.map((key) => [key, data[key] || '']));

  function capture(session = state.session) {
    if (!session || !current(session)) return;
    for (const key of fields) {
      const input = ctx.actions.$('#' + ids[key]);
      if (input) session.edits[key] = input.value;
    }
    const route = ctx.actions.$('#outreach-verification-route');
    if (route) session.verification = route.value;
    session.reviewed = ctx.actions.$('#outreach-context-reviewed')?.checked === true;
  }
  function dirty(session = state.session) {
    if (!session) return false;
    return (
      fields.some((key) => session.edits[key] !== session.baseline[key]) ||
      session.verification !== (session.data.verification_route || '')
    );
  }
  function hasUnsavedOutreach() {
    capture();
    return dirty();
  }
  function discardOutreachPreparation({ close = false } = {}) {
    if (!state.session) return;
    state.session = null;
    state.generation++;
    ctx.state.contacts.handoff = null;
    const dialog = ctx.actions.$('#modal');
    if (dialog?.dataset) delete dialog.dataset.outreachCase;
    if (close && dialog?.open) dialog.close();
  }
  function confirmDiscardOutreach() {
    if (hasUnsavedOutreach() && !confirm('Discard unsaved outreach preparation changes?'))
      return false;
    discardOutreachPreparation();
    return true;
  }
  function outreachModalCanReplace(title) {
    if (!state.session || title === 'Prepare outreach') return true;
    return confirmDiscardOutreach();
  }
  function updateStatus() {
    const session = state.session;
    if (!session) return;
    const changed = dirty(session);
    const status = ctx.actions.$('#outreach-save-state');
    if (status)
      status.textContent = session.conflict
        ? 'Saved draft changed in another window — reload before saving.'
        : changed
          ? 'Unsaved changes'
          : session.revision
            ? 'Saved locally'
            : 'Generated wording — not saved yet';
    const copy = ctx.actions.$('[data-action="copy-outreach-message"]');
    if (copy)
      copy.disabled =
        changed ||
        !session.revision ||
        session.conflict ||
        session.contextChanged ||
        !session.data.copy_allowed;
  }
  function outreachPreparationInput(event) {
    const session = state.session;
    if (
      !session ||
      !Object.values(ids)
        .concat('outreach-verification-route', 'outreach-context-reviewed')
        .includes(event.target.id)
    )
      return;
    capture(session);
    session.editSequence++;
    updateStatus();
  }

  function render(session) {
    if (!current(session)) return;
    const openDialog = ctx.actions.$('#modal');
    const active = document.activeElement;
    const retainField =
      openDialog?.open &&
      openDialog.dataset?.outreachCase === session.caseId &&
      Object.values(ids)
        .concat('outreach-verification-route', 'outreach-context-reviewed')
        .includes(active?.id)
        ? active
        : null;
    const selection =
      retainField && typeof retainField.selectionStart === 'number'
        ? [retainField.selectionStart, retainField.selectionEnd, retainField.selectionDirection]
        : null;
    const data = session.data;
    const readOnly = data.preparation_editable === false;
    const changed = session.contextChanged || data.preparation_stale;
    ctx.state.contacts.handoff = data;
    ctx.actions.modal(
      'Prepare outreach',
      `<section class="outreach-status" id="outreach-readiness" tabindex="-1" aria-label="Outreach readiness"><p><strong>${data.scope_warning ? 'Certified scope needs review' : data.ready ? 'Ready for operator review and outreach' : 'Preparation requires attention'}</strong></p>${data.blockers?.length ? `<ul class="entity-review-required">${data.blockers.map((item) => `<li>${esc(item)}</li>`).join('')}</ul>` : ''}</section>` +
        (data.scope_warning
          ? `<div class="notice warn" role="status"><strong>Retained certified report</strong><p>${esc(data.scope_warning.message)}</p><p>Copying new outreach is blocked. ${ctx.state.editor.currentLead.case?.stage === 'pending_notification' ? 'Revise the report, exclude the flagged observations in Vulnerabilities, and recertify before using it for outreach.' : 'Start a new notification and review its observation scope before further outreach.'} You can still open the historical report and record what actually happened.</p>${ctx.state.editor.currentLead.case?.stage === 'pending_notification' ? '<button class="button small" data-action="reopen">Revise report</button>' : ''}</div>`
          : '') +
        `<p>${data.contact ? `Selected route: <strong>${esc(data.contact.value)}</strong>` : 'No usable contact is selected.'}</p>` +
        (data.report
          ? `<p><a class="button" href="${esc(data.report.url)}" target="_blank" rel="noopener noreferrer">Open certified notification · revision ${esc(data.report.revision)}</a></p>`
          : '<p class="notice">Contact research only: no current certified report is available to offer or attach.</p>') +
        `<details><summary>Why this contact was selected</summary><p class="preserve-lines">${esc(data.source_explanation)}</p>${data.warnings?.length ? `<ul>${data.warnings.map((item) => `<li>${esc(item)}</li>`).join('')}</ul>` : ''}</details>` +
        (changed
          ? `<div class="notice warn" role="status"><strong>Outreach context changed.</strong><p>${esc((data.context_changes || []).join(', ') || 'Review the current report, recipient and sender details.')}</p><p>Your wording is retained. Check it against the current details before saving or copying.</p><label class="checkbox"><input type="checkbox" id="outreach-context-reviewed" ${session.reviewed ? 'checked' : ''}><span>I reviewed the current recipient, report and outreach context.</span></label></div>`
          : '') +
        `<div class="actions"><button class="button small" data-action="refresh-outreach-context">Refresh context</button>${session.conflict ? '<button class="button small" data-action="reload-outreach-preparation">Reload saved draft</button>' : ''}</div>` +
        `<details class="outreach-verification-settings" ${data.verification_route ? '' : 'open'}><summary id="outreach-verification-summary">Independent verification · ${data.verification_route ? 'configured' : 'setup needed'}</summary><form id="outreach-verification"><div class="field"><label for="outreach-verification-route">Public verification URL or office telephone route</label><input id="outreach-verification-route" name="value" maxlength="1000" value="${esc(session.verification)}"><small>Use an official route the recipient can find independently. This setting is shared by all outreach preparations on this workstation.</small></div><button class="button small" type="submit">Save verification route</button></form></details>` +
        `<div class="field"><label for="outreach-subject">Subject</label><input id="outreach-subject" maxlength="1000" value="${esc(session.edits.subject)}" ${readOnly ? 'readonly' : ''}></div>` +
        `<div class="field"><label for="outreach-message">First-contact message</label><textarea id="outreach-message" rows="12" maxlength="20000" ${readOnly ? 'readonly' : ''}>${esc(session.edits.message)}</textarea></div>` +
        `<details><summary>Call outline</summary><textarea id="outreach-call" rows="8" maxlength="10000" aria-label="Editable call outline" ${readOnly ? 'readonly' : ''}>${esc(session.edits.call_outline)}</textarea></details>` +
        `<p id="outreach-save-state" role="status"></p><div class="actions">${readOnly ? '' : '<button class="button primary" data-action="save-outreach-preparation">Save preparation</button><button class="button" data-action="reset-outreach-preparation">Reset to generated wording</button>'}<button class="button" data-action="copy-outreach-message">Copy saved subject and message</button></div>` +
        `${data.copy_blockers?.length ? `<ul class="section-note">${data.copy_blockers.map((item) => `<li>${esc(item)}</li>`).join('')}</ul>` : ''}` +
        '<p class="section-note">Preparation is saved with this case. Review the wording and recipient before use. Copying does not send, attach a report, or record delivery. Record the actual outcome separately.</p>',
    );
    const dialog = ctx.actions.$('#modal');
    if (dialog?.dataset) dialog.dataset.outreachCase = session.caseId;
    updateStatus();
    const focus = ctx.actions.$(retainField ? '#' + retainField.id : '#outreach-readiness');
    focus?.focus?.();
    if (selection) focus?.setSelectionRange?.(...selection);
  }
  function newSession(data) {
    const saved = data.preparation || { ...data, revision: 0 };
    return {
      caseId: data.case_id,
      data,
      revision: saved.revision,
      baseline: values(saved),
      edits: values(saved),
      verification: data.verification_route || '',
      contextChanged: !!data.preparation_stale,
      reviewed: false,
      conflict: false,
      editSequence: 0,
    };
  }
  async function showOutreachHandoff() {
    const lead = ctx.state.editor.currentLead;
    if (!lead?.case_id) return;
    if (ctx.state.workflow.changedCaseForms.has('case-plan'))
      throw Error('Save your contact plan edits before preparing outreach.');
    if (state.session?.caseId === lead.case_id) return refreshOutreachContext();
    if (state.session && !confirmDiscardOutreach()) return;
    const generation = ++state.generation;
    const data = await ctx.actions.api(endpoint(lead.case_id) + '/outreach-handoff', {
      timeoutMs: 15000,
    });
    if (generation !== state.generation || ctx.state.editor.currentLead?.case_id !== lead.case_id)
      return;
    state.session = newSession(data);
    render(state.session);
  }
  async function refreshOutreachContext() {
    const session = state.session;
    if (!session) return;
    capture(session);
    const request = (session.requestSequence = (session.requestSequence || 0) + 1);
    const data = await ctx.actions.api(endpoint(session.caseId) + '/outreach-handoff', {
      timeoutMs: 15000,
    });
    if (!current(session) || request !== session.requestSequence) return;
    capture(session); // Keep text entered while the read was in flight.
    if (session.verification === (session.data.verification_route || ''))
      session.verification = data.verification_route || '';
    if (data.context_hash !== session.data.context_hash) {
      const edited = fields.filter((key) => session.edits[key] !== session.baseline[key]);
      session.contextChanged = true;
      if (!session.revision && !data.preparation.revision) {
        // Untouched generated fields may follow the new context; preserve every
        // operator edit, including edits typed while the request was running.
        const generated = values(data.generated || data);
        for (const key of fields) if (!edited.includes(key)) session.edits[key] = generated[key];
        session.baseline = generated;
        session.contextChanged = edited.length > 0;
      }
      session.reviewed = false;
    }
    session.conflict = data.preparation.revision !== session.revision;
    session.data = data;
    render(session);
  }
  async function reloadOutreachPreparation() {
    const session = state.session;
    if (!session) return;
    if (
      hasUnsavedOutreach() &&
      !confirm('Replace your unsaved wording with the saved outreach draft?')
    )
      return;
    const sequence = session.editSequence;
    const request = (session.requestSequence = (session.requestSequence || 0) + 1);
    const data = await ctx.actions.api(endpoint(session.caseId) + '/outreach-handoff', {
      timeoutMs: 15000,
    });
    if (!current(session) || request !== session.requestSequence) return;
    if (sequence !== session.editSequence)
      throw Error('Newer edits were retained. Reload again if you want to replace them.');
    state.session = newSession(data);
    render(state.session);
  }
  async function saveOutreachPreparation(reset = false) {
    const session = state.session;
    if (!session || !current(session)) return;
    capture(session);
    if (session.conflict)
      throw Error('Reload the saved outreach draft before saving again. Your edits are retained.');
    if (session.contextChanged && !session.reviewed)
      throw Error('Review the current recipient, report and outreach context before saving.');
    if (reset && !confirm('Replace this preparation with current generated wording?')) return;
    const submitted = { ...session.edits },
      sequence = session.editSequence,
      contextRequest = session.requestSequence || 0;
    const body = {
      expected_revision: session.revision,
      expected_context: session.data.context_hash,
      reviewed_context: session.reviewed,
      ...(reset ? {} : submitted),
    };
    let data;
    try {
      data = await ctx.actions.api(
        endpoint(session.caseId) + '/outreach-preparation' + (reset ? '/reset' : ''),
        { method: reset ? 'POST' : 'PUT', body, timeoutMs: 15000 },
      );
    } catch (error) {
      if (current(session)) {
        try {
          await refreshOutreachContext();
        } catch {
          /* Original error explains the failed save. */
        }
      }
      throw error;
    }
    if (!current(session)) return;
    capture(session);
    const contextReadDuringSave = (session.requestSequence || 0) > contextRequest;
    const displayedContext = session.data;
    // A read started before this completed write must not restore its older
    // saved revision or create a false competing-window conflict.
    session.requestSequence = (session.requestSequence || 0) + 1;
    const verificationEdits = session.verification;
    session.data = contextReadDuringSave ? displayedContext : data;
    session.revision = data.preparation.revision;
    session.baseline = values(data.preparation);
    if (reset && sequence === session.editSequence) session.edits = { ...session.baseline };
    session.verification = verificationEdits;
    session.contextChanged = contextReadDuringSave || !!data.preparation_stale;
    session.reviewed = false;
    session.conflict = false;
    render(session);
    if (contextReadDuringSave) {
      // The save can commit before its response arrives. Preserve a newer
      // displayed context, then reconcile its blockers with the saved revision
      // instead of letting the delayed response erase a recipient/hold change.
      try {
        await refreshOutreachContext();
      } catch {
        if (current(session)) {
          session.contextChanged = true;
          render(session);
          ctx.actions.toast(
            'Preparation saved, but current context could not be refreshed. Refresh context before copying.',
            true,
          );
        }
        return;
      }
      if (!current(session)) return;
      session.contextChanged =
        !!session.data.preparation_stale ||
        session.data.context_hash !== data.preparation.context_hash;
      render(session);
    }
    ctx.actions.toast(
      dirty(session)
        ? 'Earlier preparation saved; newer edits remain unsaved.'
        : 'Outreach preparation saved locally.',
    );
  }
  async function saveOutreachVerification(values) {
    const session = state.session;
    if (!session) return;
    capture(session);
    await ctx.actions.api('/api/contact-discovery/verification-route', {
      method: 'PUT',
      body: { value: values.value, expected_value: session.data.verification_route },
      timeoutMs: 15000,
    });
    if (!current(session)) return;
    await refreshOutreachContext();
    if (!current(session)) return;
    if (session.verification === values.value)
      session.verification = session.data.verification_route;
    render(session);
    ctx.actions.$('#outreach-verification-summary')?.focus?.();
    ctx.actions.toast('Public verification route saved. Your preparation wording is retained.');
  }
  async function copyOutreachMessage() {
    const session = state.session;
    if (!session || !current(session)) return;
    capture(session);
    if (dirty(session) || !session.revision)
      throw Error('Save your outreach preparation before copying.');
    if (session.conflict || session.contextChanged || !session.data.copy_allowed)
      throw Error(
        (session.data.copy_blockers || []).join(' ') ||
          'Refresh and review the current outreach context before copying.',
      );
    const sequence = session.editSequence,
      contextHash = session.data.context_hash,
      revision = session.revision;
    let result;
    try {
      result = await ctx.actions.api(endpoint(session.caseId) + '/outreach-preparation/copy', {
        method: 'POST',
        body: { expected_revision: session.revision, expected_context: session.data.context_hash },
        timeoutMs: 15000,
      });
    } catch (error) {
      if (current(session)) {
        try {
          await refreshOutreachContext();
        } catch {
          /* Preserve original error. */
        }
      }
      throw error;
    }
    if (
      !current(session) ||
      sequence !== session.editSequence ||
      contextHash !== session.data.context_hash ||
      revision !== session.revision ||
      session.contextChanged ||
      session.conflict ||
      !session.data.copy_allowed
    )
      return;
    try {
      await navigator.clipboard.writeText(result.text);
      if (current(session))
        ctx.actions.toast(
          session.data.ready
            ? 'Saved message copied. Nothing was sent.'
            : 'Contact research message copied. Review the setup warnings; nothing was sent.',
        );
    } catch {
      if (current(session))
        ctx.actions.toast('Clipboard unavailable. Your saved preparation is retained.');
    }
  }
  Object.assign(ctx.actions, {
    showOutreachHandoff,
    refreshOutreachContext,
    reloadOutreachPreparation,
    saveOutreachPreparation,
    saveOutreachVerification,
    copyOutreachMessage,
    outreachPreparationInput,
    hasUnsavedOutreach,
    confirmDiscardOutreach,
    discardOutreachPreparation,
    outreachModalCanReplace,
  });
}
