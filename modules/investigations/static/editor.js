/** Editor feature. Dependencies and mutable state are provided by the application context. */
import { install as installEntityReview } from '../../entities/static/entity_review.js';

export function install(ctx) {
  installEntityReview(ctx);
  function checkField(name, label, help = '') {
    return `<label class="checkbox"><input type="checkbox" data-draft name="${name}" ${ctx.state.editor.draft[name] ? 'checked' : ''} ${ctx.actions.sectionLocked(['website_verified', 'sos_verified'].includes(name) ? 'attribution' : 'closing') ? 'disabled' : ''}><span>${label}${help ? `<small>${help}</small>` : ''}</span></label>`;
  }

  function editorSidebar() {
    return ctx.actions.caseSidebar();
  }

  let leadLoadSequence = 0;

  async function leadPage(id, byCase = false) {
    const sequence = ++leadLoadSequence;
    const renderId = ctx.state.navigation.renderId;
    const oldId = ctx.state.editor.currentLead?.case_id;
    const value = await ctx.actions.api(byCase ? '/api/cases/' + id : '/api/leads/' + id);
    if (sequence !== leadLoadSequence || renderId !== ctx.state.navigation.renderId) return '';
    ctx.state.editor.currentLead = value;
    ctx.state.editor.draft = structuredClone(ctx.state.editor.currentLead.draft);
    ctx.state.editor.dirty = false;
    ctx.state.workflow.workflowDirty = false;
    ctx.state.workflow.changedCaseForms.clear();
    if (oldId !== ctx.state.editor.currentLead.case_id) {
      ctx.state.editor.reportSection = 'Introduction';
      ctx.state.editor.tab =
        ctx.state.editor.currentLead.case.stage === 'in_progress'
          ? 'notification'
          : ctx.state.editor.currentLead.case.stage === 'pending_notification'
            ? 'contact'
            : 'closing';
    }
    return ctx.actions.leadMarkup();
  }

  function investigationHeaderActions() {
    const c = ctx.state.editor.currentLead.case;
    if (ctx.state.editor.tab === 'notification')
      return `${c.stage === 'in_progress' ? `<button class="button small" data-action="save">${ctx.actions.icon('save')}Save draft</button>` : c.stage === 'pending_notification' ? '<button class="button small" data-action="reopen">Revise report</button>' : ''}<button class="button small" data-action="preview">${ctx.actions.icon('external')}${c.stage === 'in_progress' ? 'Preview' : 'Open report'}</button>`;
    if (ctx.state.editor.tab === 'contact' && c.stage !== 'closed')
      return `<button class="button primary" data-action="open-contact-activity">${ctx.actions.icon('plus')}Record activity</button>`;
    return '';
  }

  function leadMarkup() {
    const l = ctx.state.editor.currentLead,
      c = l.case,
      tab = ctx.state.editor.tab,
      entries = l.entries || [],
      record = (l.reports || []).find((r) => r.id === c.certified_report_id);
    return `<section class="investigation-workbench" data-temperature="${['cool', 'warm', 'hot', 'blazing'].includes(l.intake_score?.temperature) ? l.intake_score.temperature : 'unscored'}" data-investigation-view="${ctx.actions.esc(tab)}"><header class="investigation-header"><div class="investigation-identity"><a class="investigation-back" href="#${ctx.actions.esc(ctx.state.navigation.returns.get('notifications') || 'workspace/notifications')}" aria-label="All investigations">${ctx.actions.icon('back')}</a><div><div class="investigation-kicker">Investigation <span>${ctx.actions.esc(
      String(l.case_id || '')
        .slice(0, 8)
        .toUpperCase(),
    )}</span></div><h1>${ctx.actions.esc(l.company || l.domain)}</h1><div class="investigation-meta"><a href="#entity/${encodeURIComponent(l.id)}">${ctx.actions.esc(l.domain)} ${ctx.actions.icon('external')}</a>${ctx.actions.statusBadge(c.stage)}${l.intake_score ? ctx.actions.intakeTemperatureMarkup(l.intake_score, { compact: true }) : ''}<span class="save-note ${ctx.state.editor.dirty ? 'save-dirty' : ''}" id="save-state" role="status" aria-live="polite">${ctx.state.editor.dirty ? 'Unsaved changes' : 'Saved locally'}</span></div></div></div><div class="investigation-actions">${ctx.actions.investigationHeaderActions()}</div></header><div class="investigation-navigation"><div class="editor-tabs" role="tablist" aria-label="Investigation views">${[
      ['notification', 'Report', 'file'],
      ['assets', 'Assets', 'layers', entries.length],
      ['contact', 'Contact & delivery', 'mail'],
      ['closing', 'Closing report', 'check'],
      ['activity', 'History', 'clock'],
    ]
      .map(
        ([key, label, icon, count]) =>
          `<button type="button" role="tab" id="editor-tab-${key}" aria-controls="editor-content" aria-selected="${tab === key}" tabindex="${tab === key ? 0 : -1}" class="tab ${tab === key ? 'active' : ''}" data-tab="${key}">${ctx.actions.icon(icon)}${label}${count !== undefined ? `<span class="pill-count">${count}</span>` : ''}</button>`,
      )
      .join(
        '',
      )}</div><details class="investigation-context"><summary>${ctx.actions.icon('layers')}Scope & history</summary><div class="investigation-context-body">${ctx.actions.caseProgress()}<dl class="case-facts"><dt>Reported IPs</dt><dd>${new Set(entries.map((e) => e.ip)).size}</dd><dt>Observations</dt><dd>${entries.length}</dd><dt>Root domains</dt><dd>${(l.domain_groups || []).length}</dd><dt>Opened</dt><dd>${ctx.actions.date(c.created_at)}</dd></dl>${ctx.actions.entityReviewSummary()}${l.intake_score ? ctx.actions.intakeScoreMarkup(l.intake_score) : ''}<div class="actions"><button class="button small" data-action="report-activity">Report operations</button><a class="button small" href="${ctx.actions.leadURL('/json')}">Notification JSON</a>${record?.work_log_available ? `<a class="button small" href="/api/reports/${record.id}/work-log" target="_blank" rel="noopener">Internal work log</a>` : ''}</div></div></details></div><div id="editor-content" class="investigation-content" role="tabpanel" aria-labelledby="editor-tab-${tab}" tabindex="-1">${ctx.actions.editorContent()}</div></section>`;
  }

  function editorContent() {
    const l = ctx.state.editor.currentLead;
    if (ctx.state.editor.tab === 'entity') return ctx.actions.entityMarkup();
    if (ctx.state.editor.tab === 'contact') return ctx.actions.contactMarkup();
    if (ctx.state.editor.tab === 'closing') return ctx.actions.closingMarkup();
    if (ctx.state.editor.tab === 'assets') return ctx.actions.assetsMarkup();
    if (ctx.state.editor.tab === 'attribution') return ctx.actions.attributionMarkup();
    if (ctx.state.editor.tab === 'activity')
      return (
        ctx.actions.workChronology() +
        `<section class="panel"><div class="panel-head"><h2>Notification history</h2></div><div class="panel-body">${ctx.actions.activities(l.history)}${l.reports.length ? `<h3>Completed revisions</h3>${l.reports.map((r) => `<p>Version ${r.revision} · ${ctx.actions.stamp(r.created_at)} <a class="text-link" href="/api/reports/${r.id}/pdf" target="_blank" rel="noopener">Open PDF</a></p>`).join('')}` : ''}</div></section>`
      );
    if (ctx.state.editor.tab === 'evidence') return ctx.actions.evidenceMarkup();
    return ctx.actions.reportBuilderMarkup();
  }

  ctx.constants.reportSections = [
    'Introduction',
    'Vulnerabilities',
    'Attribution',
    'Information',
    'Closing',
  ];

  function approvedText(title, body) {
    return `<div class="approved-text"><h3>${ctx.actions.esc(title)}</h3><p class="preserve-lines">${ctx.actions.esc(body || '')}</p></div>`;
  }

  function sectionReview(key) {
    return (
      (ctx.state.editor.currentLead?.section_reviews || []).find((s) => s.key === key) || {
        key,
        label: key,
        status: 'draft',
        issues: [],
        can_validate: false,
      }
    );
  }

  function sectionLocked(key) {
    return (
      ctx.state.editor.currentLead?.case?.stage !== 'in_progress' ||
      ['validated', 'stale'].includes(ctx.actions.sectionReview(key).status)
    );
  }

  function sectionStatusLabel(status) {
    return status === 'validated' ? 'Frozen' : status === 'stale' ? 'Changes need review' : 'Draft';
  }

  function sectionBanner(key) {
    const s = ctx.actions.sectionReview(key),
      frozen = ['validated', 'stale'].includes(s.status),
      issues = s.issues || [];
    return `<section class="section-validation ${ctx.actions.esc(s.status)}" aria-label="${ctx.actions.esc(s.label || ctx.state.editor.reportSection)} validation"><div class="section-validation-state"><strong>${ctx.actions.icon(frozen ? 'lock' : 'file')}${ctx.actions.sectionStatusLabel(s.status)}</strong>${frozen ? `<p>${ctx.actions.esc(s.validated_by || 'Author not recorded')} · ${ctx.actions.timeMarkup(s.validated_at)} · revision ${ctx.actions.esc(s.revision ?? '—')}</p>` : '<p>Editable section</p>'}</div>${frozen ? `<button class="button small" data-action="reopen-section" data-section="${ctx.actions.esc(key)}">Reopen section</button>` : `<button class="button primary" data-action="validate-section" data-section="${ctx.actions.esc(key)}" ${!s.can_validate && !ctx.state.editor.dirty ? 'disabled' : ''}>${ctx.actions.icon('lock')}Freeze section</button>`}${s.status === 'stale' ? '<p class="validation-warning">Related information changed after validation. The frozen content is shown below. Reopen to review the updated content.</p>' : ''}${s.status === 'stale' && (s.changed_dependencies || s.changes || []).length ? `<details class="section-changes"><summary>Changed fields and dependencies</summary><ul>${(s.changed_dependencies || s.changes).map((value) => `<li>${ctx.actions.esc(typeof value === 'string' ? value : JSON.stringify(value))}</li>`).join('')}</ul></details>` : ''}${!frozen && issues.length ? `<details class="section-issues"><summary>${issues.length} ${issues.length === 1 ? 'item' : 'items'} before freezing</summary><ul>${issues.map((issue) => `<li>${ctx.actions.esc(typeof issue === 'string' ? issue : issue.message || issue.label || 'Review this section.')}</li>`).join('')}</ul></details>` : ''}</section>`;
  }

  function reportBuilderMarkup() {
    if (ctx.state.editor.currentLead.case?.stage !== 'in_progress')
      return `<div class="certified-document-workbench"><div class="document-paper certified-paper">${ctx.actions.reportSectionContent()}</div>${ctx.actions.caseSidebar()}${ctx.actions.workChronology()}</div>`;
    const key = ctx.state.editor.reportSection.toLowerCase(),
      s = ctx.actions.sectionReview(key),
      savedDraft = ctx.state.editor.draft,
      savedLead = ctx.state.editor.currentLead;
    let body;
    try {
      if (['validated', 'stale'].includes(s.status)) {
        ctx.state.editor.draft = {
          ...ctx.state.editor.draft,
          ...Object.fromEntries(
            Object.entries(structuredClone(s.frozen_fields || {})).filter(
              ([field]) => !['include_appendix', 'appendix_revision'].includes(field),
            ),
          ),
        };
        ctx.state.editor.currentLead = {
          ...ctx.state.editor.currentLead,
          ...structuredClone(s.frozen_context || {}),
        };
        // Frozen editor projections retain only section-owned exhibits. Native
        // introduction content lives in the saved nodes rather than an exhibit.
        if (s.snapshot?.nodes)
          ctx.state.editor.currentLead.report_model = {
            ...ctx.state.editor.currentLead.report_model,
            sections: structuredClone(s.snapshot.nodes),
          };
      }
      body = ctx.actions.reportSectionContent();
    } finally {
      ctx.state.editor.draft = savedDraft;
      ctx.state.editor.currentLead = savedLead;
    }
    return `<div class="documentation-layout"><aside class="section-rail"><div class="section-rail-heading"><span>Document</span><strong>${String(ctx.constants.reportSections.indexOf(ctx.state.editor.reportSection) + 1).padStart(2, '0')} <small>/ 05</small></strong></div><nav class="report-sections" aria-label="Report sections">${ctx.constants.reportSections
      .map((name, index) => {
        const r = ctx.actions.sectionReview(name.toLowerCase()),
          active = name === ctx.state.editor.reportSection;
        return `<button type="button" class="section-nav ${active ? 'active' : ''}" data-report-section="${name}" ${active ? 'aria-current="step"' : ''}><span class="section-number">${String(index + 1).padStart(2, '0')}</span><span>${name}<small class="section-state ${ctx.actions.esc(r.status)}">${r.status === 'validated' ? 'Frozen' : r.status === 'stale' ? 'Review changes' : 'Draft'}</small></span>${ctx.actions.icon(r.status === 'validated' ? 'lock' : r.status === 'stale' ? 'refresh' : 'arrow')}</button>`;
      })
      .join(
        '',
      )}</nav>${ctx.actions.caseSidebar()}</aside><div class="section-workspace"><div class="document-toolbar"><span>${ctx.actions.esc(ctx.state.editor.reportSection)}</span><span>Draft ${ctx.actions.esc(ctx.state.editor.currentLead.draft_revision ?? 0)}<i></i>TLP:AMBER</span></div>${ctx.actions.sectionBanner(key)}<article class="document-paper section-content ${ctx.actions.sectionLocked(key) ? 'is-frozen' : ''}" aria-label="${ctx.actions.esc(ctx.state.editor.reportSection)} document content"><div class="document-paper-mast"><span>${ctx.actions.esc(ctx.state.navigation.boot?.settings?.agency || 'Shadowserver Eclipse')}</span><span>Notification report</span></div>${body}</article>${ctx.actions.workChronology(key)}</div></div>`;
  }

  function workChronology(sectionKey = '') {
    const events = (ctx.state.editor.currentLead.section_history || []).filter(
        (e) => !sectionKey || e.section_key === sectionKey,
      ),
      r = (ctx.state.editor.currentLead.reports || []).find(
        (r) => r.id === ctx.state.editor.currentLead.case?.certified_report_id,
      );
    const actionNames = {
      validated: 'Frozen',
      validate: 'Frozen',
      reopened: 'Reopened',
      reopen: 'Reopened',
      stale: 'Related content changed',
      invalidated: 'Related content changed',
      revised: 'Report revision opened',
    };
    return `<details class="work-chronology"><summary>${ctx.actions.icon('clock')}${sectionKey ? 'Section history' : 'Review history'} <span class="badge gray">${events.length}</span></summary>${events.length ? `<ol>${events.map((e) => `<li><strong>${ctx.actions.esc(ctx.constants.reportSections.find((n) => n.toLowerCase() === e.section_key) || 'Report')} · ${ctx.actions.esc(actionNames[e.action] || String(e.action || 'Updated').replaceAll('_', ' '))}${e.revision != null ? ' · revision ' + ctx.actions.esc(e.revision) : ''}</strong><p>${ctx.actions.esc(e.actor || 'Author not recorded')} · ${ctx.actions.timeMarkup(e.created_at)}</p>${e.reason ? `<p class="chronology-reason">Reason: ${ctx.actions.esc(e.reason)}</p>` : ''}</li>`).join('')}</ol>` : '<p class="section-note">Section approvals and revisions appear here with their author and date.</p>'}${r?.work_log_available ? `<div class="actions"><a class="button small" href="/api/reports/${r.id}/work-log" target="_blank" rel="noopener">${ctx.actions.icon('download')}Internal work log</a><a class="button small" href="/api/reports/${r.id}/chronology">Chronology JSON</a></div>` : ''}</details>`;
  }

  function applyLeadUpdate(value) {
    ctx.state.editor.currentLead = value;
    ctx.state.editor.draft = structuredClone(value.draft);
    ctx.state.editor.dirty = false;
    ctx.actions.$('#main').innerHTML = ctx.actions.leadMarkup();
  }

  async function validateSection(key) {
    if (
      !ctx.constants.reportSections.some((n) => n.toLowerCase() === key) ||
      ctx.actions.sectionLocked(key)
    )
      return;
    return ctx.actions.reportOperation('Freezing section', async (options, isCurrent) => {
      if (ctx.state.editor.dirty) await ctx.actions.saveDraft(options);
      if (!isCurrent()) return;
      const value = await ctx.actions.api(ctx.actions.caseURL('/sections/' + key + '/validate'), {
        ...options,
        method: 'POST',
        body: { expected_revision: ctx.state.editor.currentLead.draft_revision },
      });
      if (isCurrent() && !ctx.state.editor.dirty) {
        ctx.actions.applyLeadUpdate(value);
        ctx.actions.$(`[data-action="reopen-section"][data-section="${key}"]`)?.focus();
      }
      ctx.actions.toast('Section frozen.');
    });
  }

  function reopenFormMarkup(id, key = '') {
    const isSection = !!key;
    return `<p>${isSection ? 'The previous validation will remain in the work chronology.' : 'The certified package will be preserved as a prior revision.'} Record why the ${isSection ? 'section' : 'report'} needs to change.</p><form id="${id}" data-case="${ctx.actions.esc(ctx.state.editor.currentLead.case_id)}" data-section="${ctx.actions.esc(key)}" class="form-grid"><div class="field full"><label for="reopen-reason">Reason for ${isSection ? 'reopening' : 'revision'}</label><textarea id="reopen-reason" name="reason" rows="3" maxlength="2000" required placeholder="Describe the correction or new information…"></textarea></div><div class="modal-actions full"><button type="button" class="button" data-close-modal>Cancel</button><button type="submit" class="button primary">${isSection ? 'Reopen &amp; log reason' : 'Create revision &amp; log reason'}</button></div></form>`;
  }

  function openSectionReason(key) {
    if (!ctx.constants.reportSections.some((n) => n.toLowerCase() === key)) return;
    ctx.actions.modal(
      'Reopen ' + ctx.constants.reportSections.find((n) => n.toLowerCase() === key),
      ctx.actions.reopenFormMarkup('section-reopen-form', key),
    );
    ctx.actions.$('#reopen-reason')?.focus();
  }

  function openRevisionReason() {
    ctx.actions.modal(
      'Revise certified report',
      ctx.actions.reopenFormMarkup('report-revise-form'),
    );
    ctx.actions.$('#reopen-reason')?.focus();
  }

  function retainDraftEdits(base, working, saved) {
    const result = structuredClone(saved || {});
    for (const key of new Set([...Object.keys(base || {}), ...Object.keys(working || {})])) {
      if (JSON.stringify(base?.[key]) === JSON.stringify(working?.[key])) continue;
      if (!Object.hasOwn(working || {}, key)) delete result[key];
      else if (
        working[key] &&
        typeof working[key] === 'object' &&
        !Array.isArray(working[key]) &&
        base?.[key] &&
        typeof base[key] === 'object' &&
        !Array.isArray(base[key]) &&
        result[key] &&
        typeof result[key] === 'object' &&
        !Array.isArray(result[key])
      )
        result[key] = retainDraftEdits(base[key], working[key], result[key]);
      else result[key] = structuredClone(working[key]);
    }
    return result;
  }

  async function submitReopen(form, obj) {
    const reason = String(obj.reason || '').trim();
    if (!reason) throw new Error('Enter a reason so this change can be recorded in the work log.');
    if (form.dataset.case !== ctx.state.editor.currentLead?.case_id)
      throw new Error('The notification changed. Reopen it and try again.');
    const isSection = form.id === 'section-reopen-form',
      key = form.dataset.section;
    if (isSection && !ctx.constants.reportSections.some((n) => n.toLowerCase() === key))
      throw new Error('Unknown report section.');
    // Unlocking is independent of saving. Frozen fields may be the very reason
    // the working draft cannot yet be saved. Keep edits made during the request.
    if (!isSection && ctx.state.editor.dirty) await ctx.actions.saveDraft();
    const caseId = ctx.state.editor.currentLead.case_id,
      renderId = ctx.state.navigation.renderId,
      base = structuredClone(ctx.state.editor.currentLead.draft || {});
    const value = await ctx.actions.api(
      ctx.actions.caseURL(isSection ? '/sections/' + key + '/reopen' : '/revise'),
      {
        method: 'POST',
        body: isSection
          ? { reason, expected_revision: ctx.state.editor.currentLead.draft_revision }
          : { reason, expected_version: ctx.state.editor.currentLead.case.version },
      },
    );
    if (
      caseId !== ctx.state.editor.currentLead?.case_id ||
      renderId !== ctx.state.navigation.renderId
    )
      return;
    ctx.state.editor.tab = 'notification';
    if (isSection)
      ctx.state.editor.reportSection = ctx.constants.reportSections.find(
        (n) => n.toLowerCase() === key,
      );
    ctx.actions.closeModal();
    if (value?.draft) {
      if (isSection && ctx.state.editor.dirty) {
        const pending = retainDraftEdits(base, ctx.state.editor.draft, value.draft);
        ctx.state.editor.currentLead = value;
        ctx.state.editor.draft = pending;
        ctx.state.editor.dirty = JSON.stringify(pending) !== JSON.stringify(value.draft);
        ctx.actions.$('#main').innerHTML = ctx.actions.leadMarkup();
      } else ctx.actions.applyLeadUpdate(value);
    } else if (isSection && ctx.state.editor.dirty) {
      throw new Error(
        'Section reopened, but its updated record was unavailable. Your unsaved edits are retained.',
      );
    } else await ctx.actions.route(true);
    ctx.actions.$(`[data-report-section="${ctx.state.editor.reportSection}"]`)?.focus();
    ctx.actions.toast(
      isSection
        ? 'Section reopened. Unsaved edits retained.'
        : 'New report revision opened. Reason recorded.',
    );
  }

  function appendixOverview() {
    const model = ctx.state.editor.currentLead.report_model || {},
      appendix = model.appendix || {},
      index = appendix.index || model.appendix_index || [],
      included = ctx.state.editor.draft.include_appendix !== false,
      appendixLocked = ctx.state.editor.currentLead.case?.stage !== 'in_progress',
      edition = ctx.state.editor.draft.recipient_edition || 'full-v1',
      editionLocked =
        appendixLocked ||
        ['introduction', 'vulnerabilities', 'attribution', 'information', 'closing'].some(
          ctx.actions.sectionLocked,
        ),
      compactAvailable =
        ctx.state.editor.draft.information_revision === 'information-2026-11-10-v1';
    const partitions = [
      ['A', 'Reported assets & observations', 'introduction'],
      ['B', 'Attribution records', 'attribution'],
      ['C', 'Vulnerability & exploitation records', 'vulnerabilities'],
      ['D', 'References & supporting material', 'information'],
    ];
    return `<details class="appendix-overview"><summary>Appendix &amp; output options</summary><div class="panel-head"><div><h2>Supporting appendix</h2><p>${included ? 'Supporting records follow the closing page.' : 'The recipient report retains its source references; the full appendix is saved separately.'}</p></div><button class="button small" data-action="preview">${ctx.actions.icon('external')}Document preview</button></div><div class="panel-body"><label>Recipient edition<select data-draft name="recipient_edition" ${editionLocked ? 'disabled' : ''}><option value="full-v1" ${edition === 'full-v1' ? 'selected' : ''}>Full notification v1</option><option value="compact-v1" ${edition === 'compact-v1' ? 'selected' : ''} ${!compactAvailable ? 'disabled' : ''}>Compact recipient v1</option></select></label><p class="section-note">Compact combines next steps and resources and summarizes CVE evidence for easier scanning. The complete report and every source record remain in the internal package. ${editionLocked ? 'Reopen all reviewed sections before changing edition.' : !compactAvailable ? 'Adopt the current layouts to enable Compact recipient v1.' : 'Review all sections after changing edition.'}</p><label class="checkbox"><input type="checkbox" data-draft name="include_appendix" ${included ? 'checked' : ''} ${appendixLocked ? 'disabled' : ''}><span>Include appendix in the recipient report</span></label>${appendixLocked ? '<p class="section-note">Create a report revision to change output options.</p>' : ''}${!included ? '<p class="section-note">The closing footer will state: “The full supporting appendix is available upon request.”</p>' : ''}<div class="exhibit-list">${['Summary exhibit', 'Attribution exhibit', 'Vulnerability exhibit'].map((name) => `<span class="exhibit-chip">${ctx.actions.icon('file')}${name}</span>`).join('')}</div><div class="appendix-layout">${partitions
      .map(([code, label, owner]) => {
        const items = Array.isArray(index)
          ? index.filter((i) => String(i.id || i.entry_id || i.section || '').startsWith(code))
          : [];
        const review = ctx.actions.sectionReview(owner);
        return `<div class="appendix-part"><strong>${code} · ${label}</strong><small>${items.length ? ctx.actions.num(items.reduce((n, item) => n + (item.entry_ids?.length || 1), 0)) + ' indexed entries · ' : ''}Reviewed with ${owner[0].toUpperCase() + owner.slice(1)}</small><span class="badge ${review.status === 'validated' ? 'blue' : 'gray'}">${ctx.actions.esc(ctx.actions.sectionStatusLabel(review.status))}</span></div>`;
      })
      .join(
        '',
      )}</div><p>Preview includes the selected appendix option and saves your current edits. Complete original records remain in the evidence package.</p>${ctx.state.editor.dirty ? '<p class="save-dirty">The index above reflects the last saved draft.</p>' : ''}</div></details>`;
  }

  function senderProfileNotice() {
    if (
      !ctx.state.editor.currentLead.sender_profile_update_available ||
      ctx.state.editor.currentLead.case?.stage !== 'in_progress'
    )
      return '';
    return `<div class="notice" role="note"><strong>Sender settings have changed.</strong><p>This report keeps its saved sender identity. Adopt the current report format to use the updated sender, then review affected sections.</p><button class="button small" data-action="adopt-presentation">Review sender update</button></div>`;
  }

  function documentPresentation() {
    const policy =
        ctx.state.editor.draft.document_policy ||
        ctx.state.editor.currentLead.document_policy ||
        {},
      brand = policy.brand_profile || policy.profile_id || 'companion';
    return `<div class="panel-body"><p>Saved document branding: <strong>${ctx.actions.esc(typeof brand === 'object' ? brand.name || brand.id : brand)}</strong> · <span class="tlp-mark">TLP:AMBER</span></p><p class="section-note">Appearance changes affect the workspace only. Adopting the current format updates page layouts, narrative rules, branding, and the saved sender identity. Settings changes do not rewrite existing reports. Reopen affected validated sections first, then review them again.</p>${ctx.state.editor.currentLead.case?.stage === 'in_progress' ? '<button class="button small" data-action="adopt-presentation">Adopt current report format</button>' : ''}</div>`;
  }

  function historicalReportNotice() {
    const report = ctx.state.editor.currentLead?.historical_report;
    if (!report || report.app_version === ctx.state.navigation.boot?.version) return '';
    const version = report.app_version ? String(report.app_version).replace(/^v/, '') : null;
    return `<div class="notice historical-report" role="note"><div><strong>${version ? 'Certified in v' + ctx.actions.esc(version) + '.' : 'Certification application version not recorded.'} Viewing the preserved report revision.</strong><p>Revision ${ctx.actions.esc(report.revision ?? 'not recorded')} · Report handling recorded at certification: <strong>${ctx.actions.esc(report.handling_label || 'Not recorded')}</strong>.</p><p class="section-note">Current workspace handling is TLP:AMBER. The saved report retains its original content and markings.</p></div></div>`;
  }

  function informationPagesMarkup(locked) {
    const model = (ctx.state.editor.currentLead.report_model?.exhibits || []).find(
      (item) => item.type === 'information',
    );
    const escape = ctx.actions.esc;
    const notices = ctx.state.editor.currentLead.report_explainer_notices || [];
    const pages = (model?.pages || [])
      .map((page, index) => {
        const content = page.blocks
          .map((block) => {
            if (block.kind === 'heading') return `<h3>${escape(block.title)}</h3>`;
            if (block.kind === 'statistics_table')
              return `<div class="table-wrap"><table><thead><tr>${block.headers.map((text) => `<th>${escape(text)}</th>`).join('')}</tr></thead><tbody>${block.items.map((row) => `<tr>${row.map((text) => `<td>${escape(text)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
            if (['examples', 'routes'].includes(block.kind))
              return `<dl>${block.items.map(([label, text]) => `<dt><strong>${escape(label)}</strong></dt><dd><p>${escape(text)}</p></dd>`).join('')}</dl>`;
            return `<p>${block.kind === 'number' ? `<strong>${escape(block.number)}. </strong>` : ''}${escape(block.body || '')}</p>`;
          })
          .join('');
        return `<section class="panel"><div class="panel-head"><div><h2>${escape(page.title)}</h2><p>${index === 0 ? 'Shared business information' : 'Report explanation'} · one page</p></div></div><div class="panel-body">${page.source_report_types?.length ? `<p class="section-note">Source reports: ${page.source_report_types.map(escape).join(', ')}</p>` : ''}${content}</div></section>`;
      })
      .join('');
    return `${notices.map((notice) => `<p class="notice">${escape(notice.report_type)}: ${escape(notice.message)}</p>`).join('')}${pages || '<p>The saved report preview contains the information pages.</p>'}<p class="section-note">Each report family uses one page; IPv4 and IPv6 observations share an explanation. Existing cases retain their saved wording until you adopt the current report format.</p><details><summary>Additional optional snippets</summary>${ctx.actions.explainersMarkup(locked)}</details>`;
  }

  function technicalFindingsMarkup() {
    const model = (ctx.state.editor.currentLead.report_model?.exhibits || []).find(
      (item) => item.type === 'vulnerability',
    );
    const items = (model?.items || []).filter((item) => item.technical_explanation);
    if (!items.length) return '';
    const escape = ctx.actions.esc;
    return `<section class="panel"><div class="panel-head"><div><h2>Technical explanations</h2><p>Included with the reported lifecycle findings. Wording and references are saved with this case.</p></div></div><div class="panel-body">${items
      .map((item) => {
        const explanation = item.technical_explanation;
        return `<article><h3>${escape(explanation.title)}</h3><p class="section-note">Reported tags: ${escape(item.label)} · ${escape(item.exposure_count)} IP addresses</p>${ctx.actions.approvedText('Reported condition', explanation.body)}${ctx.actions.approvedText('Interpretation limits', explanation.limitations)}${ctx.actions.approvedText('Technical review', explanation.review)}<p class="section-note">Sources: ${(explanation.source_citations || []).map((number) => `[${escape(number)}]`).join(' ')}. Full references appear in the report.</p></article>`;
      })
      .join('')}</div></section>`;
  }

  function reportSectionContent() {
    const locked = ctx.actions.sectionLocked(ctx.state.editor.reportSection.toLowerCase()),
      opt = { disabled: locked },
      copy = ctx.state.editor.currentLead.approved_copy || {};
    const introduction = ctx.state.editor.currentLead.report_model?.sections?.find(
      (section) => section.kind === 'introduction',
    )?.model;
    const sourceSeverity =
      introduction?.severity_from_source ||
      ['source-aware-2026-11-10-v4', 'report-start-2026-11-12-v5'].includes(
        ctx.state.editor.draft.narrative_revision,
      );
    const wholeLocked = ctx.state.editor.currentLead.case?.stage !== 'in_progress';
    if (wholeLocked)
      return `${ctx.actions.historicalReportNotice()}${ctx.state.editor.currentLead.scope_warning ? `<div class="notice warn" role="status"><strong>Certified scope needs review.</strong><p>${ctx.actions.esc(ctx.state.editor.currentLead.scope_warning.message)}</p></div>` : ''}${ctx.state.editor.reportSection === 'Vulnerabilities' ? ctx.actions.observationScopeMarkup?.() || '' : ''}<section class="panel"><div class="panel-head"><h2>Certified notification</h2></div><div class="panel-body"><p>This notification retains the wording, sender and source records used at certification. Open the saved report to review its exact content.</p><button class="button primary" data-action="preview">${ctx.actions.icon('external')}Open certified report</button>${ctx.state.editor.currentLead.case?.stage === 'pending_notification' ? '<p>Use Revise report to create a new working draft with the current template.</p>' : ''}</div></section>`;
    let body = '';
    if (ctx.state.editor.reportSection === 'Introduction')
      body =
        ctx.actions.entityUpdateMarkup() +
        `<section class="panel"><div class="panel-head"><div><h2>Introduction</h2><p>Recipient and sender details for this notification.</p></div><a class="button small" href="#entity/${encodeURIComponent(ctx.state.editor.currentLead.id)}?tab=details">Edit entity</a></div><div class="panel-body"><div class="report-addresses"><div><h3>To</h3><p class="preserve-lines">${ctx.actions.esc([ctx.state.editor.draft.contact_name, ctx.state.editor.draft.company, ctx.state.editor.draft.address].filter(Boolean).join('\n'))}</p></div><div><h3>From</h3><p class="preserve-lines">${ctx.actions.esc([ctx.state.editor.draft.sender_name, ctx.state.editor.draft.sender_title, ctx.state.editor.draft.sender_profile?.agency, ctx.state.editor.draft.sender_profile?.office].filter(Boolean).join('\n') || 'Configure your sender in Settings.')}</p><a class="text-link" href="#settings">Edit sender in Settings</a></div></div>${senderProfileNotice()}<div class="form-grid">${ctx.actions.field('Notification date', 'report_date', ctx.state.editor.draft.report_date, { ...opt, type: 'date' })}${sourceSeverity ? `<div class="field"><label for="reported-severity">Reported severity</label><input id="reported-severity" value="${ctx.actions.esc(introduction?.severity || ctx.state.editor.draft.severity || 'Not specified')}" readonly aria-describedby="reported-severity-help"><small id="reported-severity-help">From the source observations; separate from internal outreach priority.</small></div>` : ctx.actions.field('Reported severity', 'severity', ctx.state.editor.draft.severity, { ...opt, choices: ['Not specified', 'Informational', 'Low', 'Medium', 'High', 'Critical'] })}</div>${ctx.actions.approvedText('Subject', ctx.state.editor.draft.subject)}${ctx.actions.approvedText('Overview', ctx.state.editor.draft.intro)}</div></section><details><summary>Report presentation</summary>${ctx.actions.templateMarkup(locked)}${ctx.actions.documentPresentation()}</details>`;
    if (ctx.state.editor.reportSection === 'Vulnerabilities')
      body =
        (ctx.actions.observationScopeMarkup?.() || '') +
        `<section class="panel"><div class="panel-head"><div><h2>Vulnerabilities</h2><p>Summary of the reported findings and their supporting sources.</p></div></div><div class="panel-body"><div class="field"><label for="outreach-template">Narrative template</label><select id="outreach-template" data-draft name="outreach_template" ${locked ? 'disabled' : ''}>${ctx.actions.optionList(
          [
            ['critical', 'Critical vulnerabilities'],
            ['targeted-v1', 'Other reported findings'],
          ],
          ctx.state.editor.draft.outreach_template || 'critical',
        )}</select><small>Choose the wording that matches the reported findings.</small></div><p id="generated-narrative" class="preserve-lines" aria-live="polite">${ctx.actions.esc(ctx.state.editor.draft.narrative)}</p><small id="narrative-refresh-status"></small><details><summary>Finding values · supply missing software or affected versions</summary><p class="section-note">Leave blank to use the source record. Business location is maintained in the entity record.</p>${(
          ctx.state.editor.currentLead.narrative_groups || []
        )
          .filter((g) => !g.excluded)
          .map(
            (g) =>
              `<fieldset class="form-grid"><legend>${ctx.actions.esc(g.hostname)} · ${ctx.actions.esc(g.protocol)} ${ctx.actions.esc(g.port)} · ${ctx.actions.esc(g.version)}</legend>${[
                ['software', 'Software'],
                ['affected_versions', 'CVE affected versions'],
              ]
                .map(
                  ([key, label]) =>
                    `<div class="field ${key === 'affected_versions' ? 'full' : ''}"><label for="finding-${g.key}-${key}">${label}</label><input id="finding-${g.key}-${key}" data-finding="${g.key}" data-finding-field="${key}" value="${ctx.actions.esc(ctx.state.editor.draft.narrative_values?.[g.key]?.[key] || '')}" placeholder="${ctx.actions.esc(g[key] || 'Not supplied in source')}" ${locked ? 'disabled' : ''}></div>`,
                )
                .join('')}</fieldset>`,
          )
          .join(
            '',
          )}</details><button class="button small" data-tab="assets">View all reported assets</button></div></section>${ctx.actions.cveMarkup()}${technicalFindingsMarkup()}`;
    if (ctx.state.editor.reportSection === 'Attribution')
      body = `<section class="panel"><div class="panel-head"><h2>Attribution</h2></div><div class="panel-body">${ctx.actions.approvedText('Open-source attribution', copy.attribution)}${ctx.actions.checkField('sos_verified', 'Secretary of State record reviewed', 'Optional additional attribution')}</div></section>${ctx.actions.attributionMarkup()}${ctx.actions.evidenceMarkup()}`;
    if (ctx.state.editor.reportSection === 'Information')
      body = `<section class="panel"><div class="panel-head"><div><h2>Information</h2><p>Security guidance included with this notification.</p></div></div><div class="panel-body">${ctx.actions.approvedText('Suggested Security Practices', copy.security_intro)}<ol>${String(
        ctx.state.editor.draft.recommendations || '',
      )
        .split('\n')
        .map((x) => `<li>${ctx.actions.esc(x)}</li>`)
        .join(
          '',
        )}</ol>${ctx.actions.approvedText('Protecting Your Business from Cyber Fraud', copy.fraud_intro)}<ul>${(copy.fraud_risks || []).map((x) => `<li>${ctx.actions.esc(x)}</li>`).join('')}</ul><p>${ctx.actions.esc(copy.fraud_stats_intro || '')}</p><ul>${(copy.fraud_stats || []).map((x) => `<li>${ctx.actions.esc(x)}</li>`).join('')}</ul>${ctx.actions.approvedText('Advisory Information & Partnership', ctx.state.editor.draft.limitations)}</div></section><details><summary>Additional optional explainers</summary>${ctx.actions.explainersMarkup(locked)}</details>`;
    if (
      ctx.state.editor.reportSection === 'Information' &&
      ctx.state.editor.currentLead.report_model?.exhibits?.some(
        (item) => item.type === 'information' && item.pages?.length,
      )
    )
      body = informationPagesMarkup(locked);
    if (ctx.state.editor.reportSection === 'Closing') {
      const closing = ctx.state.editor.currentLead.report_model?.exhibits?.find(
        (item) => item.type === 'closing',
      );
      const resources = closing?.resource_groups?.length
        ? closing.resource_groups
            .map(
              (group) =>
                `<h3>${ctx.actions.esc(group.title)}</h3><ul>${group.items.map((item) => `<li>${item.active ? `<a class="text-link" href="${ctx.actions.safeHref(item.url)}" target="_blank" rel="noopener">${ctx.actions.esc(item.label)}</a>` : ctx.actions.esc(item.label)}</li>`).join('')}</ul>`,
            )
            .join('')
        : `<h3>Recommended resources</h3><ul>${String(ctx.state.editor.draft.resources || '')
            .split('\n')
            .filter(Boolean)
            .map(
              (url) =>
                `<li><a class="text-link" href="${ctx.actions.safeHref(url)}" target="_blank" rel="noopener">${ctx.actions.esc(url)}</a></li>`,
            )
            .join('')}</ul>`;
      body = `<section class="panel"><div class="panel-head"><h2>Closing</h2></div><div class="panel-body">${resources}<p class="preserve-lines">${ctx.actions.esc(closing?.responsibility ?? copy.responsibility ?? '')}</p><p class="preserve-lines">${ctx.actions.esc(closing?.closing ?? ctx.state.editor.draft.closing)}</p><p class="preserve-lines">${ctx.actions.esc((closing?.sender_lines || [ctx.state.editor.draft.sender_name, ctx.state.editor.draft.sender_title]).filter(Boolean).join('\n'))}</p>${closing?.appendix_note ? `<p class="section-note">${ctx.actions.esc(closing.appendix_note)}</p>` : ''}</div></section><section class="panel"><div class="panel-head"><div><h2>Internal notes</h2><p>Saved in the internal evidence package; excluded from recipient reports.</p></div></div><div class="panel-body">${ctx.actions.field('Working notes', 'notes', ctx.state.editor.draft.notes, { ...opt, area: true, full: true })}</div></section>`;
    }
    return (
      body +
      (ctx.state.editor.reportSection === 'Introduction' ||
      ctx.state.editor.reportSection === 'Closing'
        ? ctx.actions.appendixOverview()
        : '')
    );
  }

  async function refreshGeneratedNarrative() {
    if (!ctx.state.editor.currentLead || ctx.actions.sectionLocked('vulnerabilities')) return;
    const requestId = ++ctx.state.editor.narrativeRefreshId,
      caseId = ctx.state.editor.currentLead.case_id;
    try {
      const result = await ctx.actions.api(ctx.actions.leadURL('/narrative'), {
        method: 'POST',
        body: structuredClone(ctx.state.editor.draft),
      });
      if (
        requestId !== ctx.state.editor.narrativeRefreshId ||
        caseId !== ctx.state.editor.currentLead.case_id ||
        ctx.actions.sectionLocked('vulnerabilities')
      )
        return;
      ctx.state.editor.draft.narrative = result.narrative;
      ctx.state.editor.currentLead.narrative_groups = result.groups;
      const node = ctx.actions.$('#generated-narrative');
      if (node) node.textContent = ctx.state.editor.draft.narrative;
      const status = ctx.actions.$('#narrative-refresh-status');
      if (status) status.textContent = '';
    } catch (error) {
      if (requestId !== ctx.state.editor.narrativeRefreshId) return;
      const status = ctx.actions.$('#narrative-refresh-status');
      if (status) status.textContent = 'Narrative preview could not refresh: ' + error.message;
    }
  }

  function scheduleNarrative() {
    clearTimeout(ctx.state.editor.narrativeRefreshTimer);
    if (ctx.actions.sectionLocked('vulnerabilities')) return;
    ctx.state.editor.narrativeRefreshId++;
    const status = ctx.actions.$('#narrative-refresh-status');
    if (status) status.textContent = 'Updating narrative…';
    ctx.state.editor.narrativeRefreshTimer = setTimeout(ctx.actions.refreshGeneratedNarrative, 250);
  }

  function explainersMarkup(disabled) {
    const pinned = new Map(
      (ctx.state.editor.draft.explainer_snapshots || []).map((b) => [b.id, b]),
    );
    const blocks = [
      ...(ctx.state.navigation.boot.explainers || []).map((b) => pinned.get(b.id) || b),
      ...[...pinned.values()].filter(
        (b) => !(ctx.state.navigation.boot.explainers || []).some((x) => x.id === b.id),
      ),
    ].filter(
      (b) => !['attribution', 'financial_crime', 'responsibility', 'eol', 'cve'].includes(b.id),
    );
    return `<section class="panel"><div class="panel-head"><div><h2>Reusable advisory text</h2><p>Saved revisions stay with this notification. Edits here do not change the library.</p></div><button class="button small" data-action="adopt-blocks" ${disabled ? 'disabled' : ''}>Adopt latest library revisions</button></div><div class="panel-body">${blocks
      .map((b) => {
        const chosen = ctx.state.editor.draft.selected_explainers.includes(b.id),
          override = ctx.state.editor.draft.explainer_overrides?.[b.id] || {};
        return `<label class="block-choice ${chosen ? 'checked' : ''}"><input type="checkbox" data-block="${ctx.actions.esc(b.id)}" ${chosen ? 'checked' : ''} ${disabled ? 'disabled' : ''}><span><strong>${ctx.actions.esc(b.title)}</strong><small>Saved revision ${ctx.actions.esc(b.revision)} · ${ctx.actions.esc(override.body ?? b.body)}</small></span></label>${chosen ? `<details><summary>Edit wording for this notification</summary><div class="form-grid"><div class="field full"><label>Heading</label><input aria-label="Notification heading for ${ctx.actions.esc(b.title)}" data-block-edit="${ctx.actions.esc(b.id)}" data-block-field="title" value="${ctx.actions.esc(override.title ?? b.title)}" ${disabled ? 'disabled' : ''}></div><div class="field full"><label>Notification wording</label><textarea aria-label="Notification wording for ${ctx.actions.esc(b.title)}" rows="5" data-block-edit="${ctx.actions.esc(b.id)}" data-block-field="body" ${disabled ? 'disabled' : ''}>${ctx.actions.esc(override.body ?? b.body)}</textarea></div></div></details>` : ''}`;
      })
      .join('')}<p><a href="#library" class="text-link">Open Library</a></p></div></section>`;
  }

  function templateMarkup(disabled) {
    const t = ctx.state.editor.draft.report_template || {
      id: 'standard',
      version: 1,
      marking: 'For Informational Purposes Only',
      font_size: 9.5,
    };
    return `<section class="panel"><div class="panel-head"><div><h2>Report presentation</h2><p>Standard notification template · version ${ctx.actions.esc(t.version)}</p></div></div><div class="panel-body form-grid"><div class="field"><label for="template-marking">Document marking</label><input id="template-marking" data-template="marking" maxlength="150" value="${ctx.actions.esc(t.marking)}" ${disabled ? 'disabled' : ''}></div><div class="field"><label for="template-size">Body text size</label><input id="template-size" data-template="font_size" type="number" min="8" max="12" step="0.5" value="${ctx.actions.esc(t.font_size)}" ${disabled ? 'disabled' : ''}></div></div></section>`;
  }

  function entityProfileMarkup() {
    const p = ctx.state.editor.currentLead.entity_profile || {};
    return `<section class="panel"><div class="panel-head"><div><h2>Entity contact & address</h2><p>Contact details support research and outreach. Reports use the organization and mailing address with the fixed addressee.</p></div><button class="button small" data-tab="contact">Discover published contacts</button></div><div class="panel-body"><form id="entity-profile-form" class="form-grid">${ctx.actions.field('Contact name', 'contact_name', p.contact_name, { draft: false })}${ctx.actions.field('Contact title', 'contact_title', p.contact_title, { draft: false })}${ctx.actions.field('Contact email', 'contact_email', p.contact_email, { draft: false, type: 'email', full: true })}${ctx.actions.entityReviewField('Mailing address', 'address', p.address, { draft: false, area: true, rows: 3, full: true })}${ctx.actions.entityReviewField('Business city', 'city', p.city, { draft: false })}${ctx.actions.entityReviewField('Business state', 'state', p.state, { draft: false })}<p class="section-note full">Use the business location; an IP geolocation is not substituted for the entity address.</p><div class="full"><button class="button primary" type="submit">Save entity details</button></div></form></div></section>`;
  }

  function entityMarkup() {
    const l = ctx.state.editor.currentLead;
    return (
      ctx.actions.entityProfileMarkup() +
      `<section class="panel"><div class="panel-head"><div><h2>Notifications for this business</h2><p>Each notification keeps its own assets, evidence and report history.</p></div>${l.cases.some((x) => ['in_progress', 'pending_notification'].includes(x.stage)) ? '' : '<button class="button primary small" data-action="new-case">New notification</button>'}</div><div class="panel-body">${l.cases.map((x) => `<div class="case-link"><a class="text-link" href="#workspace/notifications/${x.id}">${ctx.actions.esc(x.title)}</a>${ctx.actions.statusBadge(x.stage)}${x.id === l.case_id ? '<small>Current notification</small>' : ''}</div>`).join('')}</div></section><section class="panel"><div class="panel-head"><div><h2>Entity identity</h2><p>Starts with the reported hostname. Rename it when you identify the business.</p></div></div><div class="panel-body"><form id="entity-name-form" class="form-grid">${ctx.actions.entityReviewField('Entity / business name', 'name', l.company || l.domain, { full: true, draft: false, required: true })}<div class="full"><button class="button primary" type="submit">${ctx.actions.icon('save')}Save entity name</button></div></form></div></section><section class="panel"><div class="panel-head"><div><h2>Associated hostnames</h2><p>Original hostnames remain attached to their observations.</p></div><button class="button small" data-action="merge-entity">${ctx.actions.icon('layers')}Combine with entity</button></div><div class="table-wrap"><table><thead><tr><th>Reported hostname</th><th>Root domain</th></tr></thead><tbody>${(l.entity_hostnames || l.hostnames).map((h) => `<tr><td><strong>${ctx.actions.esc(h.name)}</strong></td><td>${ctx.actions.esc(h.root_domain)}</td></tr>`).join('')}</tbody></table></div></section>${l.merged_entities?.length ? `<section class="panel"><div class="panel-head"><h2>Combined entity history</h2></div><div class="panel-body">${l.merged_entities.map((e) => `<p>${ctx.actions.esc(e.company || e.domain)} · <a class="text-link" href="/api/entities/${e.id}/archived-draft.json">Prior working draft</a></p>`).join('')}<p class="section-note">Completed packages remain available in Work chronology and Certified reports.</p></div></section>` : ''}`
    );
  }

  function evidenceMarkup() {
    return `<section class="panel"><div class="panel-head"><div><h2>Website &amp; supporting images</h2></div></div><div class="panel-body">${!ctx.actions.sectionLocked('attribution') ? `<div id="website-capture-controls">${ctx.actions.captureMarkup()}</div><details class="manual-evidence"><summary>Attach an existing screenshot</summary><form id="evidence-form" class="form-grid"><div class="field"><label for="evidence-kind">Category</label><select id="evidence-kind" name="kind"><option value="website">Hostname / contact page</option><option value="sos">Secretary of State</option><option value="cve">CVE attribution</option><option value="other">Other supporting evidence</option></select></div><div class="field"><label for="evidence-date">Captured at (UTC)</label><input id="evidence-date" name="captured_at" type="datetime-local" value="${new Date().toISOString().slice(0, 16)}" required></div><div class="field full"><label for="evidence-url">Source URL</label><input id="evidence-url" name="source_url" type="url" placeholder="https://…" required></div><div class="field full"><label for="evidence-caption">Caption</label><input id="evidence-caption" name="caption" placeholder="What this screenshot establishes" required></div><div class="field full"><label for="evidence-file">Screenshot · PNG, JPEG, WebP or HEIC</label><input class="file-input" id="evidence-file" type="file" name="file" accept="image/png,image/jpeg,image/webp,.heic,.heif" required></div><div class="full"><button class="button primary" type="submit">${ctx.actions.icon('plus')}Attach screenshot</button></div></form></details>` : ''}<div class="evidence-grid">${ctx.state.editor.currentLead.evidence.map((e) => `<article class="evidence-card ${e.included ? '' : 'excluded'}"><a href="/api/evidence/${e.id}/image" target="_blank" rel="noopener"><img src="/api/evidence/${e.id}/image" alt="${ctx.actions.esc(e.caption)}" loading="lazy"></a><div><span class="badge gray">${ctx.actions.esc({ website: 'Hostname page', sos: 'Secretary of State', cve: 'CVE attribution', other: 'Supporting evidence' }[e.kind])}</span><h3>${ctx.actions.esc(e.caption || e.filename)}</h3><small>${ctx.actions.stamp(e.captured_at)}</small>${ctx.actions.captureProvenance(e)}<a class="text-link truncate" href="${ctx.actions.safeHref(e.source_url)}" target="_blank" rel="noopener">${ctx.actions.esc(e.source_url || 'No source URL')}</a><label class="checkbox"><input type="checkbox" data-evidence="${e.id}" ${e.included ? 'checked' : ''} ${ctx.actions.sectionLocked('attribution') ? 'disabled' : ''}><span>Include in notification</span></label></div></article>`).join('')}</div></div></section>`;
  }

  function notificationContext() {
    return {
      caseId: ctx.state.editor.currentLead?.case_id,
      renderId: ctx.state.navigation.renderId,
      draft: structuredClone(ctx.state.editor.draft || {}),
    };
  }

  function notificationContextCurrent(context) {
    return (
      context.caseId === ctx.state.editor.currentLead?.case_id &&
      context.renderId === ctx.state.navigation.renderId
    );
  }

  function applyNotificationMutation(value, context) {
    if (!notificationContextCurrent(context) || !value?.draft) return false;
    if (Number(value.draft_revision) < Number(ctx.state.editor.currentLead.draft_revision))
      return false;
    const draft = retainDraftEdits(context.draft, ctx.state.editor.draft, value.draft);
    ctx.state.editor.currentLead = value;
    ctx.state.editor.draft = draft;
    ctx.state.editor.dirty = JSON.stringify(draft) !== JSON.stringify(value.draft);
    const content = ctx.actions.$('#editor-content');
    if (content && !ctx.state.workflow.workflowDirty)
      content.innerHTML = ctx.actions.editorContent();
    if (ctx.state.editor.dirty) ctx.actions.markDirty();
    return true;
  }

  async function saveDraft(options = {}) {
    if (ctx.state.editor.currentLead.status === 'completed') return;
    const context = notificationContext();
    const submitted = structuredClone(ctx.state.editor.draft);
    const value = await ctx.actions.api(ctx.actions.leadURL('/draft'), {
      ...options,
      method: 'PUT',
      body: {
        expected_revision: ctx.state.editor.currentLead.draft_revision,
        fields: submitted,
      },
    });
    if (!notificationContextCurrent(context)) return value;
    ctx.state.editor.currentLead = value;
    if (JSON.stringify(ctx.state.editor.draft) !== JSON.stringify(submitted)) {
      ctx.state.editor.dirty = true;
      throw Error(
        'Earlier edits were saved; newer edits remain unsaved. Review and save them before continuing.',
      );
    }
    ctx.state.editor.draft = structuredClone(value.draft);
    ctx.state.editor.dirty = false;
    const status = ctx.actions.$('#save-state');
    if (status) {
      status.textContent = 'Saved locally';
      status.classList.remove('save-dirty');
    }
    if (ctx.state.editor.tab === 'notification')
      ctx.actions.$('#editor-content').innerHTML = ctx.actions.editorContent();
    return value;
  }

  function markDirty() {
    ctx.state.editor.dirty = true;
    ctx.actions
      .$$('[data-action="validate-section"]')
      .forEach((button) => (button.disabled = false));
    const review = ctx.actions.$('[data-draft][name="reviewed"]');
    if (review) review.checked = ctx.state.editor.draft?.reviewed === true;
    const state = ctx.actions.$('#save-state');
    if (state) {
      state.textContent = 'Unsaved changes';
      state.classList.add('save-dirty');
    }
  }
  Object.assign(ctx.actions, {
    checkField,
    editorSidebar,
    leadPage,
    leadMarkup,
    investigationHeaderActions,
    editorContent,
    approvedText,
    sectionReview,
    sectionLocked,
    sectionStatusLabel,
    sectionBanner,
    reportBuilderMarkup,
    workChronology,
    applyLeadUpdate,
    validateSection,
    reopenFormMarkup,
    openSectionReason,
    openRevisionReason,
    submitReopen,
    appendixOverview,
    documentPresentation,
    historicalReportNotice,
    reportSectionContent,
    refreshGeneratedNarrative,
    scheduleNarrative,
    explainersMarkup,
    templateMarkup,
    entityProfileMarkup,
    entityMarkup,
    evidenceMarkup,
    notificationContext,
    notificationContextCurrent,
    applyNotificationMutation,
    saveDraft,
    markDirty,
  });
}
