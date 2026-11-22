import { hasKnownRansomware } from '../../library/static/risk.js';

/** Intelligence feature. Dependencies and mutable state are provided by the application context. */
export function install(ctx) {
  let catalogSearchSequence = 0;
  function reportCveIds() {
    return [
      ...new Set(
        ctx.state.editor.currentLead.entries.flatMap(
          (e) =>
            String(
              e.normalized?.case_condition_scope
                ? (e.normalized.active_conditions || []).join(';')
                : e.source.fields.tag || '',
            )
              .toUpperCase()
              .match(/CVE-\d{4}-\d{4,}/g) || [],
        ),
      ),
    ].sort();
  }

  function signalOptions(selected = 'all') {
    return ctx.actions.optionList(
      [
        ['all', 'All findings'],
        ['kev', 'Known exploited · KEV'],
        ['ransomware', 'Known ransomware use'],
      ],
      selected,
    );
  }

  function intelligenceMarkup(c, locked = false) {
    const assessments = c.ssvc_assessments || [],
      chosen =
        ctx.state.editor.draft?.selected_ssvc_assessments?.[c.id] || c.selected_ssvc_assessment_id,
      assessment = assessments.find((a) => a.id === chosen) || null;
    const ransomware = c.ransomware || {},
      known = ctx.actions.hasKnownRansomware(c),
      rsLabel =
        ransomware.label || (known ? 'Known ransomware use' : 'No CISA assessment in this catalog');
    const signal = (name, value, detail, adverse = false) =>
      `<div class="intel-signal ${adverse ? 'adverse' : ''}"><span>${ctx.actions.esc(name)}</span><strong>${ctx.actions.esc(value)}</strong>${detail ? `<small>${ctx.actions.esc(detail)}</small>` : ''}</div>`;
    const kev =
      c.kev === true
        ? 'Known exploited · CISA KEV'
        : c.kev === false
          ? 'Not listed in retrieved catalog'
          : 'Assessment unavailable';
    const ssLabel =
      assessment?.label ||
      {
        active: 'Active exploitation reported',
        poc: 'Public PoC / known exploitation method',
        none: 'No exploitation evidence reported in this assessment',
      }[assessment?.exploitation] ||
      'No selected assessment';
    return `<section class="intel-panel" aria-label="Exploitation and impact for ${ctx.actions.esc(c.id)}"><h4>Exploitation &amp; impact</h4><div class="intel-grid">${signal('Known exploitation', kev, c.kev_details?.dateAdded ? 'Included ' + c.kev_details.dateAdded : c.kev_date ? 'Catalog ' + c.kev_date : 'Catalog date unavailable', c.kev === true)}${signal('Ransomware', rsLabel, ransomware.status === 'unrecognized' ? 'Unrecognized source value: ' + ransomware.raw : 'CISA catalog assessment', known)}${signal('SSVC exploitation', ssLabel, assessment ? [assessment.publisher, assessment.assessed_at ? 'Assessed ' + ctx.actions.stamp(assessment.assessed_at) : 'Assessment time not supplied'].filter(Boolean).join(' · ') : 'No inference from missing information', ['active', 'poc'].includes(assessment?.exploitation))}${signal('EPSS probability', c.epss != null ? (Number(c.epss) * 100).toFixed(2) + '% probability' : 'Not supplied', c.epss != null ? [c.epss_date ? 'Score date ' + c.epss_date : 'Score date not supplied', c.epss_percentile != null ? (Number(c.epss_percentile) * 100).toFixed(2) + ' percentile' : 'Percentile not supplied'].join(' · ') : '', false)}</div>${assessments.length ? `<div class="intel-assessment field"><label for="ssvc-${ctx.actions.esc(c.id)}">Selected exploitation assessment for this notification</label><select id="ssvc-${ctx.actions.esc(c.id)}" data-ssvc-id="${ctx.actions.esc(c.id)}" ${locked ? 'disabled' : ''}><option value="">Use preferred source assessment</option>${assessments.map((a) => `<option value="${ctx.actions.esc(a.id)}" ${ctx.state.editor.draft?.selected_ssvc_assessments?.[c.id] === a.id ? 'selected' : ''}>${ctx.actions.esc(a.publisher || 'Source')} · ${ctx.actions.esc(a.label || a.exploitation || 'Unrecognized value')} · ${ctx.actions.esc(a.assessed_at || 'Undated')}</option>`).join('')}</select></div>` : ''}${(c.impacts || []).length ? `<details open><summary>Source-supported potential impacts</summary>${c.impacts.map((i) => `<div class="intel-assessment"><strong>${ctx.actions.esc(i.label)}</strong><p>${ctx.actions.esc(i.source_text)}</p>${i.conditions ? `<p><strong>Conditions:</strong> ${ctx.actions.esc(typeof i.conditions === 'string' ? i.conditions : JSON.stringify(i.conditions))}</p>` : ''}<small>${ctx.actions.esc(i.publisher || 'Source')} · ${ctx.actions.esc((i.basis || '').replaceAll('_', ' '))}</small></div>`).join('')}</details>` : ''}<p>These indicators describe the vulnerability. They do not establish compromise of this business or confirm that a reported version is exploitable.</p><details><summary>Assessment history &amp; acquisition status</summary><pre>${ctx.actions.esc(JSON.stringify({ intelligence_revision_id: c.intelligence_revision_id || null, assessments, acquisition: c.acquisition || [], ransomware: c.ransomware || null, reference_records: c.reference_records || [] }, null, 2))}</pre></details></section>`;
  }

  function sourceDetailsMarkup(c) {
    const attempts = [...(c.acquisition || []), ...(c.refresh_acquisition || [])];
    return (c.sources || [])
      .map((source) => {
        const publisher = source.publisher || 'Source not supplied';
        const latest = attempts
          .filter((a) => a.publisher === publisher)
          .sort((a, b) =>
            String(b.completed_at || '').localeCompare(String(a.completed_at || '')),
          )[0];
        const details = [
          source.record_path && (source.sha256 || source.body_sha256)
            ? source.network_request === false
              ? 'Preserved local extract'
              : 'Preserved response'
            : 'Source reference',
          'Retrieved ' + ctx.actions.stamp(source.retrieved_at),
        ];
        if (publisher.includes('FIRST') && c.epss_date) details.push('Score date ' + c.epss_date);
        if (publisher.includes('CISA') && c.kev_date) details.push('Catalog date ' + c.kev_date);
        if (latest?.outcome && latest.outcome !== 'success') {
          details.push('Latest attempt: ' + String(latest.outcome).replaceAll('_', ' '));
        }
        return `<p><a class="text-link" href="${ctx.actions.safeHref(source.public_url || source.url)}" target="_blank" rel="noopener">${ctx.actions.esc(publisher)}</a><br><small>${details.map(ctx.actions.esc).join(' · ')}</small></p>`;
      })
      .join('');
  }

  async function openReportCatalog() {
    const initial = ctx.actions.reportCveIds()[0] || '';
    ctx.actions.modal(
      'Search local CVE catalog',
      `<form id="report-catalog-search-form"><div class="field"><label for="report-catalog-query">CVE ID, product or description</label><input id="report-catalog-query" name="query" type="search" maxlength="200" value="${ctx.actions.esc(initial)}"></div><button class="button" type="submit">Search</button></form><div id="report-catalog-results" aria-live="polite"></div>`,
    );
    await searchReportCatalog(initial);
  }

  async function searchReportCatalog(query = '') {
    const sequence = ++catalogSearchSequence,
      caseId = ctx.state.editor.currentLead?.case_id,
      current = () =>
        sequence === catalogSearchSequence &&
        caseId === ctx.state.editor.currentLead?.case_id &&
        ctx.actions.$('#modal').open &&
        ctx.actions.$('#modal-title').textContent === 'Search local CVE catalog';
    if (!current()) return;
    ctx.actions.$('#report-catalog-results').innerHTML =
      '<p role="status">Searching local records…</p>';
    try {
      const result = await ctx.actions.api(
        '/api/cve-catalog/search?' + new URLSearchParams({ q: query.trim(), limit: '25' }),
      );
      if (!current()) return;
      const reported = new Set(ctx.actions.reportCveIds()),
        locked = ctx.actions.sectionLocked('vulnerabilities');
      ctx.actions.$('#report-catalog-results').innerHTML = result.items.length
        ? `<p class="section-note">${ctx.actions.num(result.total)} local matches${result.total > result.items.length ? ' · showing the first 25' : ''}</p><ul class="source-refresh-list">${result.items
            .map(
              (record) =>
                `<li><strong>${ctx.actions.esc(record.id)} · ${ctx.actions.esc(record.severity || 'Unscored')}</strong><p>${ctx.actions.esc(record.description || 'Description unavailable')}</p>${reported.has(record.id) ? `<button type="button" class="button small" data-action="retrieve-catalog-cve" data-cve-id="${ctx.actions.esc(record.id)}" ${locked ? 'disabled' : ''}>Retrieve for this notification</button>` : '<small>Reference only · not reported in this notification</small>'}</li>`,
            )
            .join('')}</ul>`
        : '<p>No matching local records. Download or update the catalog in Library.</p>';
    } catch (error) {
      if (current())
        ctx.actions.$('#report-catalog-results').innerHTML =
          `<p role="alert">${ctx.actions.esc(error.message)}</p>`;
    }
  }

  async function retrieveCveSources({ refresh = false, cveIds = null } = {}) {
    if (ctx.state.editor.pendingCveRefresh?.running)
      throw Error('A source retrieval is already running.');
    const reported = ctx.actions.reportCveIds(),
      ids = cveIds || reported,
      request = {
        caseId: ctx.state.editor.currentLead.case_id,
        revision: ctx.state.editor.currentLead.draft_revision,
        records: [],
        failures: [],
        running: true,
        cancelled: false,
      };
    if (!ids.length || ids.some((id) => !reported.includes(id)))
      throw Error('Select a CVE reported in this notification.');
    ctx.state.editor.pendingCveRefresh = request;
    const progress = () => {
      const body = `<p>Retrieved ${request.records.length + request.failures.length} of ${ids.length} CVEs. Reading the local catalog and saved feeds. No external requests.</p><div class="progress"><span style="width:${ids.length ? ((request.records.length + request.failures.length) / ids.length) * 100 : 0}%"></span></div><div class="modal-actions"><button class="button" data-action="cancel-cve-refresh">Stop after current request</button></div>`;
      if (!request.progressOpened) {
        ctx.actions.modal('Retrieve published sources', body);
        request.progressOpened = true;
      } else if (
        ctx.actions.$('#modal').open &&
        ctx.actions.$('#modal-title').textContent === 'Retrieve published sources'
      )
        ctx.actions.$('#modal-body').innerHTML = body;
    };
    progress();
    try {
      const job = await ctx.actions.api('/api/source-jobs', {
        method: 'POST',
        body: { cve_ids: ids, refresh, local_only: true },
      });
      if (request.detached) return;
      request.jobId = job.id || job.job_id;
      if (!request.jobId) throw Error('The source retrieval did not return a job identifier.');
      if (request.cancelled)
        await ctx.actions.api('/api/source-jobs/' + request.jobId + '/cancel', { method: 'POST' });
      let state = job;
      while (['queued', 'running'].includes(state.status)) {
        await new Promise((resolve) => setTimeout(resolve, 750));
        if (request.detached) return;
        state = await ctx.actions.api('/api/source-jobs/' + request.jobId);
        if (request.detached) return;
        request.records = state.results || [];
        request.failures = (state.errors || []).map((error) => ({
          id: error.cve_id || error.id || 'Source request',
          message: error.error || error.message || String(error),
        }));
        if (ctx.state.editor.currentLead?.case_id === request.caseId && !request.cancelled)
          progress();
      }
      request.records = state.results || [];
      request.failures = (state.errors || []).map((error) => ({
        id: error.cve_id || error.id || 'Source request',
        message: error.error || error.message || String(error),
      }));
      request.cancelled = request.cancelled || state.status === 'cancelled';
    } catch (error) {
      request.failures.push({ id: 'Retrieval job', message: error.message });
    }
    request.running = false;
    if (request.detached) return;
    if (
      ctx.state.editor.currentLead?.case_id === request.caseId &&
      ctx.actions.$('#modal').open &&
      ctx.actions.$('#modal-title').textContent === 'Retrieve published sources'
    )
      if (
        !ctx.actions.sectionLocked('vulnerabilities') &&
        ctx.state.editor.currentLead.draft_revision === request.revision
      ) {
        ctx.actions.adoptCveSources();
      } else ctx.actions.showCveRefreshReview(request);
    else {
      ctx.actions.toast('Source retrieval finished. Open Vulnerabilities to review the results.');
      if (
        ctx.state.editor.currentLead?.case_id === request.caseId &&
        ctx.actions.$('#editor-content')
      )
        ctx.actions.$('#editor-content').innerHTML = ctx.actions.editorContent();
    }
  }

  function showCveRefreshReview(request = ctx.state.editor.pendingCveRefresh) {
    if (!request || request.running || ctx.state.editor.currentLead?.case_id !== request.caseId)
      return;
    const updated = request.records.filter(
      (c) =>
        JSON.stringify(c) !==
        JSON.stringify((ctx.state.editor.draft.cve_records || []).find((old) => old.id === c.id)),
    );
    ctx.actions.modal(
      'Review retrieved sources',
      `<p>Source retrieval is complete${request.cancelled ? ' for the requested subset' : ''}. Review the result before adopting it into this notification.</p><ul class="source-refresh-list">${request.records
        .map((c) => {
          const old = (ctx.state.editor.draft.cve_records || []).find((r) => r.id === c.id),
            fields = [
              'description',
              'verification_status',
              'cvss_assessments',
              'kev',
              'ransomware',
              'ssvc_assessments',
              'impacts',
              'epss',
              'epss_date',
            ].filter((key) => JSON.stringify(old?.[key]) !== JSON.stringify(c[key]));
          const local =
            c.local_only ||
            c.from_catalog ||
            (c.sources || []).some((s) => s.network_request === false);
          return `<li><strong>${ctx.actions.esc(c.id)} · ${ctx.actions.esc(c.verification_status || 'Source unresolved')}</strong><small>${fields.length ? 'Changed: ' + fields.map(ctx.actions.esc).join(', ') : 'No displayed values changed'}</small><small>${local ? 'Local catalog / saved feed' : c.from_cache ? 'Saved source record' : 'Publisher retrieval'} · ${ctx.actions.esc(ctx.actions.stamp(c.retrieved_at))}</small>${(c.errors || []).length ? `<small>${c.errors.map(ctx.actions.esc).join('; ')}</small>` : ''}</li>`;
        })
        .join(
          '',
        )}${request.failures.map((f) => `<li><strong>${ctx.actions.esc(f.id)} · Retrieval failed</strong><small>${ctx.actions.esc(f.message)}. The existing selection remains available.</small></li>`).join('')}</ul><div class="source-refresh-actions"><p class="section-note">Adoption changes this draft only. Save and renew affected section validations before certification. ${updated.length} returned record(s) differ from the draft.</p><button class="button" data-close-modal>Keep current selections</button><button class="button primary" data-action="adopt-cves" ${!request.records.length || ctx.actions.sectionLocked('vulnerabilities') ? 'disabled' : ''}>Adopt retrieved records</button></div>`,
    );
  }

  function adoptCveSources() {
    if (!ctx.state.editor.pendingCveRefresh || ctx.state.editor.pendingCveRefresh.running) return;
    if (
      ctx.state.editor.currentLead.case_id !== ctx.state.editor.pendingCveRefresh.caseId ||
      ctx.state.editor.currentLead.draft_revision !== ctx.state.editor.pendingCveRefresh.revision
    )
      throw Error(
        'The notification changed while retrieving sources. Retrieve again before adoption.',
      );
    if (ctx.actions.sectionLocked('vulnerabilities'))
      throw Error('Reopen the Vulnerabilities section before adopting sources.');
    ctx.state.editor.draft.cve_records ??= [];
    const missing = ctx.state.editor.pendingCveRefresh.records.filter(
      (r) => r.local_catalog_missing,
    ).length;
    for (const result of ctx.state.editor.pendingCveRefresh.records) {
      const existing = ctx.state.editor.draft.cve_records.find((x) => x.id === result.id);
      // Missing reference data cannot erase an already selected source snapshot.
      if (result.local_catalog_missing && existing?.verification_status === 'published') continue;
      ctx.state.editor.draft.cve_records = ctx.state.editor.draft.cve_records
        .filter((x) => x.id !== result.id)
        .concat(result);
    }
    ctx.state.editor.pendingCveRefresh = null;
    ctx.state.editor.draft.reviewed = false;
    ctx.actions.markDirty();
    ctx.actions.closeModal();
    ctx.actions.$('#editor-content').innerHTML = ctx.actions.editorContent();
    ctx.actions.scheduleNarrative();
    ctx.actions.toast(
      missing
        ? `${missing} CVE record(s) missing from the local catalog. Available records added; existing sources retained.`
        : 'Local CVE records added to this draft.',
    );
  }

  function cveMarkup() {
    const ids = ctx.actions.reportCveIds(),
      locked = ctx.actions.sectionLocked('vulnerabilities');
    if (!ids.length) return '';
    const visibleIds = ids.filter((id) => {
      const c = (ctx.state.editor.draft.cve_records || []).find((x) => x.id === id) || {};
      return ctx.state.editor.cveSignalFilter === 'kev'
        ? c.kev === true
        : ctx.state.editor.cveSignalFilter === 'ransomware'
          ? ctx.actions.hasKnownRansomware(c)
          : true;
    });
    return `<section class="panel"><div class="panel-head"><div><h2>Published CVE sources</h2><p>Reported CVEs are populated from the local catalog. Missing records stay visible; update the catalog in Library. Recipient IT personnel determine applicability.</p></div><div class="actions">${ctx.state.editor.pendingCveRefresh?.caseId === ctx.state.editor.currentLead.case_id && !ctx.state.editor.pendingCveRefresh.running ? '<button class="button small" data-action="review-cves">Review retrieved sources</button>' : ''}<button class="button small" data-action="search-report-catalog">Search catalog</button><button class="button small" data-action="cves" ${ctx.state.editor.pendingCveRefresh?.running ? 'disabled' : ''}>${ctx.actions.icon('search')}${ctx.state.editor.pendingCveRefresh?.running ? 'Retrieving sources…' : 'Load local CVEs'}</button></div></div><div class="panel-body"><details><summary>Refresh sources</summary><p>Use the current local catalog and saved risk feeds. Existing frozen sections stay unchanged.</p><button class="button small" data-action="refresh-cves" ${ctx.state.editor.pendingCveRefresh?.running ? 'disabled' : ''}>Refresh local records</button></details><div class="queue-filters"><label for="cve-signal-filter">Show</label><select id="cve-signal-filter">${ctx.actions.signalOptions(ctx.state.editor.cveSignalFilter)}</select><span class="section-note">${visibleIds.length} of ${ids.length} CVEs · display filter only</span></div>${visibleIds.length ? '' : '<p class="section-note">No selected records match this indicator. Unknown values remain unknown.</p>'}${visibleIds
      .map((id) => {
        const c = ctx.state.editor.draft.cve_records.find((x) => x.id === id) || { id },
          choice = ctx.state.editor.draft.cve_dispositions?.[id] || {},
          action = choice.action || 'source';
        const cvss = c.cvss_assessments?.length
          ? c.cvss_assessments
          : c.cvss != null
            ? [{ score: c.cvss, version: c.cvss_version, source: c.cvss_source }]
            : [];
        const input = (label, key, area = false) =>
          `<div class="field full"><label>${label}</label>${area ? `<textarea aria-label="${label} for ${id}" rows="4" data-cve-field="${key}" data-cve-id="${id}" ${locked ? 'disabled' : ''}>${ctx.actions.esc(choice[key] || '')}</textarea>` : `<input aria-label="${label} for ${id}" data-cve-field="${key}" data-cve-id="${id}" value="${ctx.actions.esc(choice[key] || '')}" ${locked ? 'disabled' : ''}>`}</div>`;
        return `<article class="cve-card"><div class="cve-heading"><a class="text-link" href="${ctx.actions.safeHref(c.public_url || 'https://nvd.nist.gov/vuln/detail/' + id)}" target="_blank" rel="noopener">${ctx.actions.esc(id)} ${ctx.actions.icon('external')}</a><span class="badge ${c.verification_status === 'published' ? 'blue' : ['rejected', 'invalid'].includes(c.verification_status) ? 'red' : 'gray'}">${ctx.actions.esc(c.local_catalog_missing ? 'Missing from local catalog' : (c.verification_status || 'Unresolved').replaceAll('_', ' '))}</span></div><small>${ctx.actions.esc(c.publisher || c.source || 'Published record')} ${c.description_source ? ' · ' + ctx.actions.esc(c.description_source) : ''}</small><p class="preserve-lines">${ctx.actions.esc(c.description || 'No usable published description is available locally. Update the catalog in Library, document an official-text fallback, or exclude this CVE with a reason.')}</p><div class="cve-scores">${cvss.length ? cvss.map((v) => `<span class="${Number(v.score ?? v.baseScore) >= 9 ? 'severity-critical' : Number(v.score ?? v.baseScore) >= 7 ? 'severity-high' : ''}">CVSS ${ctx.actions.esc(v.version || '')} <b>${ctx.actions.esc(v.score ?? v.baseScore)}</b> ${ctx.actions.esc(v.severity || '')} · ${ctx.actions.esc(v.source || v.publisher || 'Source unspecified')}</span>`).join('') : '<span>CVSS unavailable</span>'}</div>${ctx.actions.intelligenceMarkup(c, locked)}<small>Retrieved ${ctx.actions.stamp(c.retrieved_at)}${c.from_cache ? ' · saved response' : ''}</small>${c.errors?.length ? `<div class="notice warn">${c.errors.map(ctx.actions.esc).join('<br>')}</div>` : ''}<details><summary>Source details and references</summary>${sourceDetailsMarkup(c)}<details><summary>Preserved response metadata</summary><pre>${ctx.actions.esc(JSON.stringify(c.sources || [], null, 2))}</pre></details>${(c.references || []).map((url) => `<p><a class="text-link" href="${ctx.actions.safeHref(url)}" target="_blank" rel="noopener">${ctx.actions.esc(url)}</a></p>`).join('')}</details><div class="field"><label for="disposition-${id}">Use in this notification</label><select id="disposition-${id}" data-cve-disposition="${id}" ${locked ? 'disabled' : ''}><option value="source" ${action === 'source' ? 'selected' : ''}>Use selected published source</option><option value="fallback" ${action === 'fallback' ? 'selected' : ''} ${['reserved', 'rejected'].includes(c.verification_status) ? 'disabled' : ''}>Document an official-text fallback</option><option value="exclude" ${action === 'exclude' ? 'selected' : ''}>Exclude with a recorded reason</option></select></div>${action !== 'source' ? `<div class="form-grid">${input(action === 'exclude' ? 'Reason for exclusion' : 'Reason for using this official source', 'reason', true)}${action === 'fallback' ? input('Official publisher / contributor', 'publisher') + input('Public source URL', 'source_url') + input('Retrieved at · ISO timestamp with timezone', 'retrieved_at') + input('Published description · paste exact official text', 'description', true) : ''}</div><p class="section-note">${action === 'exclude' ? 'The original observation remains in notification history.' : 'This text is retained as captured source evidence; no screenshot is required.'}</p>` : ''}</article>`;
      })
      .join('')}</div></section>`;
  }
  Object.assign(ctx.actions, {
    reportCveIds,
    hasKnownRansomware,
    signalOptions,
    intelligenceMarkup,
    retrieveCveSources,
    openReportCatalog,
    searchReportCatalog,
    showCveRefreshReview,
    adoptCveSources,
    cveMarkup,
  });
}
