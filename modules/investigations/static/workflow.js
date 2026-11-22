/** Workflow feature. Dependencies and mutable state are provided by the application context. */
export function install(ctx) {
  ctx.constants.caseStages = [
    ['scan_validation', 'Scan Validation', 'Review reported assets and their attribution', 'leads'],
    [
      'in_progress',
      'Work in Progress',
      'Build, validate and certify the report',
      'workspace/notifications?stage=in_progress',
    ],
    [
      'pending_notification',
      'Completed & Pending Notification',
      'Arrange contact and record delivery',
      'workspace/notifications?stage=pending_notification',
    ],
    [
      'notification_completed',
      'Notification Completed',
      'Document the outcome and conclude the work',
      'workspace/notifications?stage=notification_completed',
    ],
    [
      'closed',
      'Closing Report Completed',
      'Retain the documented outcome',
      'workspace/notifications?stage=closed',
    ],
  ];

  const caseURL = (suffix) => '/api/cases/' + ctx.state.editor.currentLead.case_id + (suffix || '');

  const leadURL = (suffix) =>
    '/api/leads/' +
    ctx.state.editor.currentLead.id +
    (suffix || '') +
    '?case_id=' +
    ctx.state.editor.currentLead.case_id;

  const localDateTime = () => {
    const d = new Date();
    return new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  };

  const localDay = () => ctx.actions.localDateTime().slice(0, 10);

  const optionList = (values, selected) =>
    values
      .map(
        ([v, label]) =>
          `<option value="${v}" ${v === selected ? 'selected' : ''}>${ctx.actions.esc(label)}</option>`,
      )
      .join('');

  function stageCards(w) {
    return `<div class="cards workflow-metrics">${ctx.constants.caseStages.map(([key, label, help, href], i) => `<a class="metric" href="#${href}"><div class="metric-top"><span>${i + 1}. ${label}</span></div><div class="metric-value">${ctx.actions.num(w[key])}</div><small>${key === 'scan_validation' ? `hostname group${w[key] === 1 ? '' : 's'}` : `notification case${w[key] === 1 ? '' : 's'}`}</small><div class="metric-foot">${help} ${ctx.actions.icon('arrow')}</div></a>`).join('')}</div><div class="mini-metrics workflow-summary"><a class="text-link" href="#workspace/notifications?stage=closed"><strong>${ctx.actions.num(w.closed)}</strong> Completed archive</a><span><strong>${ctx.actions.num(w.delivered_total)}</strong> successfully notified</span><span><strong>${ctx.actions.num(w.closed_without_delivery)}</strong> closed without delivery</span><a class="text-link" href="#workspace/notifications?due_before=${ctx.actions.localDay()}"><strong>${ctx.actions.num(w.due)}</strong> follow-ups due</a></div>`;
  }

  function caseTable(rows, filtered = false) {
    if (!rows.length)
      return ctx.actions.empty(
        'No notifications in this view',
        filtered
          ? 'Change the filter to see other notifications.'
          : 'Start a notification from Leads.',
        filtered
          ? ctx.actions.linkButton('#workspace/notifications', 'Clear filters', '', 'search')
          : ctx.actions.linkButton('#leads', 'Open Leads'),
      );
    return `<div class="table-wrap"><table><thead><tr><th scope="col">Business / notification</th><th scope="col">Stage</th><th scope="col">Assets</th><th scope="col">Next action</th><th scope="col">Follow-up</th></tr></thead><tbody>${rows.map((r) => `<tr class="intake-priority-row" data-temperature="${['cool', 'warm', 'hot', 'blazing'].includes(r.intake_score?.temperature) ? r.intake_score.temperature : 'unscored'}"><td><a class="text-link" href="#workspace/notifications/${r.id}"><strong>${ctx.actions.esc(r.company || r.domain)}</strong></a><small>${ctx.actions.esc(r.title)}</small>${r.intake_score ? ctx.actions.intakeTemperatureMarkup(r.intake_score, { compact: true }) : ''}</td><td>${ctx.actions.statusBadge(r.stage)}</td><td><strong>${ctx.actions.num(r.assets)}</strong><small>${ctx.actions.num(r.observations)} observations</small></td><td>${ctx.actions.esc(r.next_action || '—')}</td><td>${r.follow_up_date ? `<span class="${r.stage !== 'closed' && r.follow_up_date <= ctx.actions.localDay() ? 'due-date' : ''}">${ctx.actions.date(r.follow_up_date)}</span>` : '—'}</td></tr>`).join('')}</tbody></table></div>`;
  }

  async function casesPage(params) {
    const stage = params.get('stage') || '',
      q = params.get('q') || '',
      due = params.get('due_before') || '',
      signal = params.get('signal') || 'all';
    const allRows = await ctx.actions.api(
      '/api/cases?' + new URLSearchParams({ stage, q, ...(due ? { due_before: due } : {}) }),
    );
    const rows = allRows.filter((r) =>
      signal === 'kev'
        ? r.kev === true
        : signal === 'ransomware'
          ? ctx.actions.hasKnownRansomware(r)
          : true,
    );
    return (
      ctx.actions.heading(
        'Investigations',
        '',
        ctx.actions.linkButton('#entities', 'Entities', '', 'layers'),
      ) +
      `<section class="panel"><div class="filter-bar"><nav class="tabs case-filter-tabs" aria-label="Notification stage filters">${[['', 'All notifications'], ...ctx.constants.caseStages.slice(1).map((x) => [x[0], x[1]])].map(([v, n]) => `<a class="tab ${v === stage ? 'active' : ''}" href="#workspace/notifications${v ? '?stage=' + v : ''}" ${v === stage ? 'aria-current="page"' : ''}>${n}</a>`).join('')}</nav><form id="case-search" class="input-search">${ctx.actions.icon('search')}<input aria-label="Search notifications" name="q" placeholder="Business, hostname or notification…" value="${ctx.actions.esc(q)}"><input type="hidden" name="stage" value="${ctx.actions.esc(stage)}">${due ? `<input type="hidden" name="due_before" value="${ctx.actions.esc(due)}">` : ''}<select name="signal" aria-label="Filter notification intelligence" data-submit-filter>${ctx.actions.signalOptions(signal)}</select><button class="button small" type="submit">Apply</button></form></div><div class="count-text">${ctx.actions.num(rows.length)} notifications ${due ? `· follow-up due by ${ctx.actions.date(due)} · <a href="#workspace/notifications" class="text-link">Clear filter</a>` : ''}</div>${ctx.actions.caseTable(rows, !!stage || !!q || !!due || signal !== 'all')}</section>`
    );
  }

  function caseProgress() {
    const c = ctx.state.editor.currentLead.case,
      completed = c.stage === 'closed',
      at = ctx.constants.caseStages.findIndex((x) => x[0] === c.stage);
    return `<ol class="case-progress" aria-label="Shadowserver Notification workflow">${ctx.constants.caseStages
      .map(([key, label], i) => {
        const skipped = key === 'notification_completed' && completed && !c.delivered_at;
        return `<li class="${i === at ? 'current' : i < at && !skipped ? 'passed' : ''}" ${i === at ? 'aria-current="step"' : ''}><span>${i < at && !skipped ? ctx.actions.icon('check') : i + 1}</span>${skipped ? 'Delivery not recorded' : label}</li>`;
      })
      .join('')}</ol>`;
  }

  function caseSidebar() {
    const l = ctx.state.editor.currentLead,
      c = l.case,
      ready = l.readiness || [],
      blockers = ready.filter((r) => !r.ok && !r.key?.startsWith('section_')),
      frozen = (l.section_reviews || []).filter((r) => r.status === 'validated').length,
      canCertify = frozen === 5 && ready.every((r) => r.ok),
      r = (l.reports || []).find((r) => r.id === c.certified_report_id);
    if (ctx.state.editor.tab !== 'notification') return '';
    if (c.stage !== 'in_progress')
      return `<section class="report-certification certified-summary"><span class="investigation-kicker">Certified revision</span><h3>${r ? 'Revision ' + r.revision : 'Preserved report'}</h3>${r ? `<p>${r.certification_source === 'analyst' ? 'Certified by ' + ctx.actions.esc(r.certified_by || 'Author not recorded') : 'Imported finalized report'}<br>${ctx.actions.stamp(r.certified_at || r.created_at)}</p>` : ''}${c.delivered_at ? `<p>Delivered ${ctx.actions.stamp(c.delivered_at)}</p>` : ''}<button class="button" data-tab="${c.stage === 'pending_notification' ? 'contact' : 'closing'}">${c.stage === 'pending_notification' ? 'Contact & delivery' : 'Closing report'}${ctx.actions.icon('arrow')}</button></section>`;
    return `<section class="report-certification"><span class="investigation-kicker">Report certification</span><div class="certification-count"><strong>${frozen}<small>/ 5</small></strong><span>sections frozen</span></div><div class="progress"><span style="width:${frozen * 20}%"></span></div>${blockers.length ? `<details class="certification-blockers"><summary>${blockers.length} ${blockers.length === 1 ? 'check' : 'checks'} remaining</summary><ul>${blockers.map((r) => `<li>${ctx.actions.esc(r.label)}</li>`).join('')}</ul></details>` : ''}<p class="save-note">${canCertify ? 'Ready to certify.' : 'Freeze all five sections to certify.'}</p><button class="button ${canCertify ? 'primary' : ''} full-width" data-action="finalize" ${canCertify ? '' : 'disabled'}>${ctx.actions.icon('check')}Certify report</button></section>`;
  }

  function outreachPolicyMarkup(policy = {}) {
    return `<section class="panel"><div class="panel-head"><div><h2>Outreach decision</h2><p>A hold remains in effect until you change it. Review dates create reminders, not contact or reopening.</p></div></div><div class="panel-body"><form id="case-outreach-policy" class="form-grid"><div class="field"><label for="outreach-state">Decision</label><select id="outreach-state" name="state">${ctx.actions.optionList(
      [
        ['active', 'Active'],
        ['deferred', 'Defer outreach'],
        ['do_not_contact', 'Do not contact'],
      ],
      policy.state || 'active',
    )}</select></div><div class="field"><label for="outreach-review-on">Reconsider on</label><input id="outreach-review-on" name="review_on" type="date" value="${ctx.actions.esc(policy.review_on || '')}" aria-describedby="outreach-date-help" ${policy.state === 'deferred' ? 'required' : ''}><small id="outreach-date-help">${policy.state === 'deferred' ? 'Required for deferred outreach.' : 'Optional. Set a date to bring this decision back to Workspace.'}</small></div>${ctx.actions.field('Reason for decision', 'reason', policy.reason || '', { area: true, draft: false, full: true, required: true })}<div class="actions full"><button type="submit" class="button">Save outreach decision</button>${policy.changed_at ? `<span class="muted">${ctx.actions.esc(policy.changed_by || '')} · ${ctx.actions.stamp(policy.changed_at)}</span>` : ''}</div></form></div></section>`;
  }

  function findingHistoryMarkup(history) {
    if (!history?.items?.length) return '';
    const labels = {
      new: 'New finding',
      seen_again: 'Seen again',
      changed: 'Changed version',
      covered: 'Covered by notification',
      not_seen: 'Not seen in latest retained observations',
      qualification_unknown: 'Legacy qualification unavailable',
    };
    return `<section class="panel"><div class="panel-head"><div><h2>Finding history</h2><p>${ctx.actions.esc(history.basis)}</p></div><span class="badge gray">${ctx.actions.num(history.total)} distinct findings</span></div><div class="panel-body"><div class="inline-stats">${Object.entries(
      history.counts,
    )
      .map(([key, n]) => `<span>${ctx.actions.num(n)} ${ctx.actions.esc(labels[key])}</span>`)
      .join(
        '',
      )}</div><details><summary>Compare observations and prior notifications</summary><div class="table-wrap"><table><thead><tr><th scope="col">Finding / asset</th><th scope="col">Change</th><th scope="col">First / last approved observation</th><th scope="col">Prior notification</th></tr></thead><tbody>${history.items.map((item) => `<tr><td>${ctx.actions.esc(item.finding)}<small>${ctx.actions.esc(item.hostname)} · ${ctx.actions.esc(item.ip)}${item.port ? ':' + ctx.actions.esc(item.port) : ''}</small></td><td>${ctx.actions.esc(labels[item.state])}<small>${ctx.actions.num(item.reported_observation_count ?? item.observations)} reported · ${ctx.actions.num(item.approved_observation_count ?? item.observations)} approved${item.legacy_unknown_observation_count ? ` · ${ctx.actions.num(item.legacy_unknown_observation_count)} legacy qualification unavailable` : ''} · versions ${ctx.actions.esc(item.versions.filter(Boolean).join(', ') || 'not recorded')}</small></td><td>${ctx.actions.date(item.first_observed)}<small>${ctx.actions.date(item.last_observed)}</small></td><td>${item.notifications.map((n) => `<a class="text-link" href="#workspace/notifications/${encodeURIComponent(n.case_id)}">Revision ${ctx.actions.num(n.revision)} · ${ctx.actions.date(n.sent_at)}</a>`).join('<br>') || 'No delivery recorded'}</td></tr>`).join('')}</tbody></table></div>${history.truncated ? '<p>Showing the first 250 findings; totals include all retained findings.</p>' : ''}</details></div></section>`;
  }

  function contactMarkup() {
    const l = ctx.state.editor.currentLead,
      c = l.case,
      locked = c.stage === 'closed',
      opt = { draft: false, disabled: locked },
      profile = l.current_entity?.entity_profile || l.entity_profile || {},
      name = c.contact_name || profile.contact_name,
      route = c.contact_email || c.contact_phone || profile.contact_email || profile.contact_phone,
      attempts = l.attempts || [];
    return `${l.outreach_policy?.state && l.outreach_policy.state !== 'active' ? `<div class="notice warn outreach-hold-notice"><div><strong>${l.outreach_policy.state === 'deferred' ? 'Outreach deferred' : 'Do not contact'}</strong><p>${ctx.actions.esc(l.outreach_policy.reason)}</p>${l.outreach_policy.review_on ? `<small>Reconsider ${ctx.actions.date(l.outreach_policy.review_on)}</small>` : ''}</div><button class="button small" data-action="review-outreach-decision">Review decision</button></div>` : ''}<div class="outreach-workbench"><div class="outreach-findings">${ctx.actions.contactDiscoveryMarkup()}</div><aside class="outreach-plan"><div class="outreach-plan-heading"><span class="investigation-kicker">Contact plan</span>${c.delivered_at ? '<span class="badge blue">Delivered</span>' : ''}</div><h2>${ctx.actions.esc(name || 'No contact selected')}</h2><p class="contact-plan-route">${ctx.actions.esc(route || 'No destination saved')}</p>${c.next_action ? `<p class="contact-plan-next">${ctx.actions.esc(c.next_action)}</p>` : ''}${c.follow_up_date ? `<p class="contact-plan-date">${ctx.actions.icon('clock')}Follow-up ${ctx.actions.date(c.follow_up_date)}</p>` : ''}${c.delivered_at ? `<p class="section-note">Delivered ${ctx.actions.stamp(c.delivered_at)}</p>` : ''}<button class="button small" data-action="outreach-handoff">Prepare outreach${ctx.actions.icon('arrow')}</button><details class="saved-plan-editor"><summary>${locked ? 'Contact details' : 'Edit contact plan'}</summary><form id="case-plan" class="form-grid">${ctx.actions.field('Contact name / team', 'contact_name', c.contact_name || (l.current_entity?.entity_profile || l.entity_profile)?.contact_name, opt)}${ctx.actions.field('Role', 'contact_role', c.contact_role || (l.current_entity?.entity_profile || l.entity_profile)?.contact_title, opt)}${ctx.actions.field('Email', 'contact_email', c.contact_email || (l.current_entity?.entity_profile || l.entity_profile)?.contact_email, { ...opt, type: 'email' })}${ctx.actions.field('Phone', 'contact_phone', c.contact_phone || (l.current_entity?.entity_profile || l.entity_profile)?.contact_phone, opt)}${ctx.actions.field('Next action', 'next_action', c.next_action, { ...opt, full: true })}${ctx.actions.field('Follow-up date', 'follow_up_date', c.follow_up_date, { ...opt, type: 'date' })}${locked ? '' : `<div class="full"><button class="button" type="submit">${ctx.actions.icon('save')}Save contact plan</button></div>`}</form></details></aside><section class="outreach-timeline"><div class="outreach-section-heading"><div><span class="investigation-kicker">Recorded work</span><h2>Recent activity</h2></div><span>${attempts.length} ${attempts.length === 1 ? 'record' : 'records'}</span></div>${ctx.actions.attemptMarkup(attempts.slice(0, 3))}${attempts.length > 3 ? `<details class="contact-earlier"><summary>Earlier activity · ${attempts.length - 3}</summary>${ctx.actions.attemptMarkup(attempts.slice(3))}</details>` : ''}${
      locked
        ? ''
        : `<details id="contact-activity-compose" class="contact-activity-compose"><summary>${ctx.actions.icon('plus')}Record contact activity</summary><p class="section-note">Email sent stays pending until successful delivery is recorded.</p><form id="case-attempt" class="form-grid">${ctx.actions.field('When · local time', 'occurred_at', ctx.actions.localDateTime(), { type: 'datetime-local', draft: false, required: true })}<div class="field"><label for="attempt-channel">Channel</label><select id="attempt-channel" name="channel">${ctx.actions.optionList(
            [
              ['phone', 'Phone'],
              ['email', 'Email'],
              ['mail', 'Mail'],
              ['in_person', 'In person'],
              ['other', 'Other'],
            ],
            'phone',
          )}</select></div><div class="field"><label for="attempt-outcome">Outcome</label><select id="attempt-outcome" name="outcome">${ctx.actions.optionList(
            [
              ['contact_research', 'Contact research'],
              ['no_answer', 'No answer'],
              ['voicemail', 'Voicemail left'],
              ['callback_requested', 'Callback requested'],
              ['email_sent', 'Email sent'],
              ['bounced', 'Email bounced'],
              ...(['pending_notification', 'notification_completed'].includes(c.stage)
                ? [
                    ['delivered', 'Report delivered'],
                    ['acknowledged', 'Receipt acknowledged'],
                  ]
                : []),
              ['recipient_update', 'Recipient update'],
              ['other', 'Other'],
            ],
            'contact_research',
          )}</select></div><div class="field"><label for="attempt-report">Report revision</label><select id="attempt-report" name="report_id"><option value="">No report involved</option>${l.reports.map((r) => `<option value="${r.id}" ${r.id === c.certified_report_id ? 'selected' : ''}>Revision ${r.revision}${r.id === c.certified_report_id ? ' · current certified report' : ' · prior report'}</option>`).join('')}</select></div>${ctx.actions.field('Recipient / team', 'recipient', c.contact_name || (l.current_entity?.entity_profile || l.entity_profile)?.contact_name, { draft: false })}${ctx.actions.field('Destination · email, phone or address', 'destination', c.contact_email || c.contact_phone || (l.current_entity?.entity_profile || l.entity_profile)?.contact_email, { draft: false })}<div class="field full"><label for="attempt-source">Basis of information</label><select id="attempt-source" name="information_source">${ctx.actions.optionList(
            [
              ['administrative', 'Contact / administrative record'],
              ['recipient_reported', 'Reported by the recipient'],
              ['analyst_verified', 'Independently verified by analyst'],
            ],
            'administrative',
          )}</select></div>${ctx.actions.field('Notes / recipient response', 'notes', '', { area: true, full: true, draft: false, help: 'Describe what happened and any action reported by the recipient.' })}${ctx.actions.field('Recorded by', 'recorded_by', ctx.state.navigation.boot.settings.analyst_name, { draft: false, required: true, full: true })}<div class="full"><button class="button primary" type="submit">${ctx.actions.icon('plus')}Add activity</button></div></form></details>`
    }</section><details class="outreach-tools"><summary>Outreach decision & finding history</summary>${ctx.actions.outreachPolicyMarkup(l.outreach_policy)}${ctx.actions.findingHistoryMarkup(l.finding_history)}</details></div>`;
  }

  function attemptMarkup(rows) {
    return rows.length
      ? rows
          .map(
            (a) =>
              `<article class="contact-event"><div><strong>${ctx.actions.esc(a.outcome.replaceAll('_', ' '))}</strong><span class="badge ${a.information_source === 'recipient_reported' ? 'amber' : 'gray'}">${ctx.actions.esc(a.information_source.replaceAll('_', ' '))}</span></div><small>${ctx.actions.stamp(a.occurred_at)} · ${ctx.actions.esc(a.channel.replaceAll('_', ' '))} · ${ctx.actions.esc(a.recipient || 'Recipient not recorded')}${a.destination ? ' · ' + ctx.actions.esc(a.destination) : ''}</small><p>${ctx.actions.esc(a.notes)}</p><small>Recorded by ${ctx.actions.esc(a.recorded_by)}${a.report_id ? ' · ' + ctx.actions.esc('revision ' + (ctx.state.editor.currentLead.reports.find((r) => r.id === a.report_id)?.revision ?? 'unavailable')) : ''}</small></article>`,
          )
          .join('')
      : '<p class="section-note">Calls, emails, delivery and recipient updates appear here.</p>';
  }

  function closingMarkup() {
    const l = ctx.state.editor.currentLead,
      c = l.case;
    if (l.closure)
      return `<div class="closing-workbench"><section class="closing-record"><div class="closing-record-mark">${ctx.actions.icon('check')}</div><span class="investigation-kicker">Investigation closed</span><h2>${ctx.actions.esc(l.closure.disposition.replaceAll('_', ' '))}</h2><p class="closing-byline">${ctx.actions.stamp(l.closure.created_at)} · ${ctx.actions.esc(l.closure.closed_by)}</p>${l.closure.files_available === false ? '<div class="notice warn">Closing files are missing or changed. Restore the original package from backup.</div>' : ''}<p class="preserve-lines closing-conclusion">${ctx.actions.esc(l.closure.conclusion)}</p><div class="actions">${['pdf', 'docx', 'json'].map((f) => `<a class="button ${f === 'pdf' ? 'primary' : ''}" href="${ctx.actions.caseURL('/closing/' + f)}" ${f === 'pdf' ? 'target="_blank" rel="noopener"' : ''}>${f === 'pdf' ? 'Open closing PDF' : f.toUpperCase()}</a>`).join('')}</div></section><details class="closing-history"><summary>Recorded chronology · ${(l.attempts || []).length} ${(l.attempts || []).length === 1 ? 'record' : 'records'}</summary>${ctx.actions.attemptMarkup(l.attempts || [])}</details></div>`;
    return `<div class="closing-workbench"><header class="closing-heading"><span class="investigation-kicker">Close the investigation</span><h2>Record the outcome.</h2><p>Certified revisions and contact history accompany this conclusion.</p></header>${!c.delivered_at ? '<div class="notice warn">No successful delivery is recorded. Closing this notification will not count it as a completed notification.</div>' : `<div class="closing-delivered">${ctx.actions.icon('check')}Report delivered ${ctx.actions.stamp(c.delivered_at)}</div>`}<form id="case-close" class="form-grid closing-form"><div class="field full"><label for="closing-disposition">Disposition</label><select id="closing-disposition" name="disposition">${ctx.actions.optionList(
      c.delivered_at
        ? [['notified', 'Successfully notified']]
        : [
            ['unable_to_contact', 'Unable to contact'],
            ['out_of_scope', 'Out of scope'],
            ['duplicate', 'Duplicate notification'],
            ['other', 'Other'],
          ],
      'notified',
    )}</select></div>${ctx.actions.field('Conclusion', 'conclusion', '', { area: true, rows: 7, draft: false, full: true, required: true, help: 'Record the response and outcome. Identify recipient-reported remediation.' })}${ctx.actions.field('Closed by', 'closed_by', ctx.state.navigation.boot.settings.analyst_name, { draft: false, full: true, required: true })}<label class="checkbox full"><input type="checkbox" name="reviewed"><span>I reviewed the closing report and its chronology.</span></label><div class="actions full closing-actions"><button type="submit" name="intent" value="preview" class="button">${ctx.actions.icon('external')}Preview closing report</button><button type="submit" name="intent" value="close" class="button primary">${ctx.actions.icon('check')}Finalize closing report</button></div></form><details class="closing-history"><summary>Review recorded chronology · ${(l.attempts || []).length} ${(l.attempts || []).length === 1 ? 'record' : 'records'}</summary>${ctx.actions.attemptMarkup(l.attempts || [])}</details></div>`;
  }

  async function caseSubmit(form, obj, data, intent) {
    if (form.id === 'case-search') {
      location.hash = 'workspace/notifications?' + new URLSearchParams(obj);
      return;
    }
    if (ctx.state.editor.dirty) await ctx.actions.saveDraft();
    const expected_version = ctx.state.editor.currentLead.case.version;
    let updated;
    if (form.id === 'case-outreach-policy')
      updated = await ctx.actions.api(ctx.actions.caseURL('/outreach-policy'), {
        method: 'PUT',
        body: { ...obj, expected_version, review_on: obj.review_on || null },
      });
    if (form.id === 'case-plan')
      updated = await ctx.actions.api(ctx.actions.caseURL('/plan'), {
        method: 'PUT',
        body: { ...obj, expected_version, follow_up_date: obj.follow_up_date || null },
      });
    if (form.id === 'case-attempt')
      updated = await ctx.actions.api(ctx.actions.caseURL('/attempts'), {
        method: 'POST',
        body: {
          ...obj,
          expected_version,
          report_id: obj.report_id || null,
          occurred_at: new Date(obj.occurred_at).toISOString(),
        },
      });
    if (form.id === 'case-close') {
      const body = {
        disposition: obj.disposition,
        conclusion: obj.conclusion,
        closed_by: obj.closed_by,
        reviewed: data.has('reviewed'),
        expected_version,
      };
      if (intent === 'preview') {
        await ctx.actions.reportOperation(
          'Preparing closing report preview',
          async (options, isCurrent) => {
            const blob = await ctx.actions.api(ctx.actions.caseURL('/closing-preview'), {
              ...options,
              method: 'POST',
              body,
              blob: true,
            });
            if (isCurrent()) ctx.actions.showReportPDF('Closing report preview', blob);
          },
        );
        return;
      }
      await ctx.actions.api(ctx.actions.caseURL('/close'), { method: 'POST', body });
    }
    ctx.state.workflow.changedCaseForms.delete(form.id);
    if (updated) {
      // Saving one contact form must not discard text entered in the other.
      const pending = [...ctx.state.workflow.changedCaseForms]
        .filter((id) => ctx.actions.$('#' + id))
        .map((id) => [id, [...new FormData(ctx.actions.$('#' + id))]]);
      ctx.state.editor.currentLead = updated;
      ctx.state.editor.draft = structuredClone(updated.draft);
      ctx.actions.$('#main').innerHTML = ctx.actions.leadMarkup();
      for (const [id, fields] of pending)
        for (const [name, value] of fields) {
          const control = ctx.actions.$(`#${id} [name="${name}"]`);
          if (control) {
            control.value = value;
            for (
              let parent = control.closest?.('details');
              parent;
              parent = parent.parentElement?.closest?.('details')
            )
              parent.open = true;
          }
        }
      ctx.state.workflow.workflowDirty = ctx.state.workflow.changedCaseForms.size > 0;
      if (ctx.state.editor.tab === 'contact')
        await ctx.actions.loadContactDiscovery?.(updated.id, { resume: false });
    } else {
      ctx.state.workflow.workflowDirty = false;
      await ctx.actions.route(true);
    }
    ctx.actions.toast(
      form.id === 'case-close'
        ? 'Closing report finalized.'
        : form.id === 'case-outreach-policy'
          ? 'Outreach decision saved.'
          : form.id === 'case-plan'
            ? 'Contact plan saved.'
            : 'Contact activity recorded.',
    );
  }
  async function reportsPage() {
    const rows = await ctx.actions.api('/api/reports');
    return (
      ctx.actions.heading(
        'Packages',
        '',
        `<span class="dm-overline">${ctx.actions.num(rows.length)} certified revisions</span>`,
      ) +
      `<section class="dm-packages">${rows.length ? rows.map((r) => `<article class="dm-package-row"><div class="dm-package-identity"><span class="dm-overline">Revision ${ctx.actions.num(r.revision)} · ${ctx.actions.date(r.created_at)}</span><h2><a href="#workspace/notifications/${encodeURIComponent(r.case_id)}">${ctx.actions.esc(r.company || r.domain)}</a></h2><p>${ctx.actions.esc(r.domain)}</p>${r.sent_at ? `<span class="badge green">Delivery recorded · ${ctx.actions.date(r.sent_at)}</span>` : '<span class="badge gray">Delivery not recorded</span>'}</div>${r.files_available ? `<div class="dm-package-download"><span class="dm-overline">Recipient</span><a class="button primary" href="/api/reports/${r.id}/recipient-zip">${ctx.actions.icon('download')}Recipient package</a><div><a class="text-link" href="/api/reports/${r.id}/pdf" target="_blank" rel="noopener">PDF</a><a class="text-link" href="/api/reports/${r.id}/docx">DOCX</a></div>${r.supporting_appendix_available ? `<details><summary>Separate appendix</summary><a class="text-link" href="/api/reports/${r.id}/appendix-pdf" target="_blank" rel="noopener">PDF</a><a class="text-link" href="/api/reports/${r.id}/appendix-docx">DOCX</a></details>` : ''}</div><div class="dm-package-download"><span class="dm-overline">Internal record</span><a class="button" href="/api/reports/${r.id}/zip">${ctx.actions.icon('download')}Evidence &amp; records</a><p>Searchable reader, source records and chronology.</p></div>` : '<div class="notice warn">Package files missing. Restore from backup.</div>'}</article>`).join('') : ctx.actions.empty('No certified reports yet', 'Certify a reviewed draft to save its PDF, DOCX, evidence and source snapshot.', ctx.actions.linkButton('#investigations', 'Open investigations'))}</section>`
    );
  }

  Object.assign(ctx.actions, {
    reportsPage,
    caseURL,
    leadURL,
    localDateTime,
    localDay,
    optionList,
    stageCards,
    caseTable,
    casesPage,
    caseProgress,
    caseSidebar,
    contactMarkup,
    attemptMarkup,
    closingMarkup,
    caseSubmit,
    outreachPolicyMarkup,
    findingHistoryMarkup,
  });
}
