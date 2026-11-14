import { installLibrary } from './catalog_library.js';

/** Local CVE browsing. Network synchronization is owned by the catalog service. */
export function install(ctx) {
  const state = (ctx.state.resources.catalog = {
    status: null,
    result: { items: [], total: 0, limit: 25, offset: 0 },
    query: '',
    severity: 'CRITICAL',
    selected: null,
    detail: null,
    generation: 0,
    searchRequest: 0,
    detailRequest: 0,
    timer: null,
  });
  const esc = (value) => ctx.actions.esc(value ?? '');
  const num = (value) => ctx.actions.num(Number(value) || 0);
  const date = (value) => (value ? ctx.actions.stamp(value) : 'Not yet synced');
  const busy = (status = state.status) =>
    Boolean(status?.running || status?.job?.status === 'running');
  const array = (value) => (Array.isArray(value) ? value : []);
  const safeLink = (url) => /^https?:\/\/[^\s<>"']+$/i.test(String(url || ''));

  function catalogRiskStatusMarkup(risk) {
    if (!risk) return '';
    return `<details class="catalog-risk-status"><summary>Local intelligence · CVSS, EPSS &amp; KEV</summary><div class="catalog-risk-feeds"><div><strong>CVSS</strong><span>All published assessments are retained with the CVE records.</span></div>${[
      'epss',
      'kev',
    ]
      .map((name) => {
        const feed = risk[name] || {};
        return `<div><strong>${name.toUpperCase()} · ${num(feed.count)} records</strong><span>${feed.last_success_at ? `Updated ${date(feed.last_success_at)}${feed.stale ? ' · Update due' : ''}` : 'Not yet downloaded'}${feed.score_date ? ` · Scores ${esc(feed.score_date)}` : ''}</span>${feed.last_error ? `<small class="catalog-error">${esc(feed.last_error)}</small>` : ''}</div>`;
      })
      .join(
        '',
      )}</div><div class="catalog-actions">${risk.running ? `<span role="status">${esc(risk.job?.message || 'Updating local intelligence…')}</span><button class="button" data-action="catalog-risk-cancel">Cancel intelligence sync</button>` : '<button class="button" data-action="catalog-risk-sync">Sync EPSS &amp; KEV</button>'}</div></details>`;
  }

  function catalogIndexMarkup(status) {
    const index = status.index_status;
    if (!index || index.ready || !status.total) return '';
    return `<div class="catalog-index-note" role="status"><span>${esc(status.index_job?.message || 'Preparing product index')} · ${num(index.indexed)} of ${num(index.total)} CVEs</span>${status.index_running ? '' : '<button class="button" data-action="catalog-index">Build product index</button>'}</div>`;
  }

  function catalogStatusMarkup(status = state.status) {
    if (!status)
      return '<p class="muted">Catalog status is unavailable. <button class="button" data-action="catalog-refresh">Try again</button></p>';
    const running = busy(status);
    const job = status.job || {};
    const complete = Boolean(status.bootstrap_complete);
    const phase = job.message || (running ? 'Updating catalog…' : '');
    const loadedYears = Array.isArray(status.years_complete)
      ? status.years_complete.length
      : Number(status.years_complete) || 0;
    const requiredYears = Array.isArray(status.required_years)
      ? status.required_years.length
      : Number(status.required_years) || 0;
    const error = status.last_error || job.error;
    const needsKey = status.api_access && !status.api_access.configured;
    const partial = loadedYears || status.api_bootstrap?.start_index;
    const access = needsKey
      ? '<div class="notice warn"><span>Connect NVD to download the full CVE catalog and keep it updated.</span><a class="button" href="#settings">Add NVD API key</a></div>'
      : '';
    return `${access}<div class="catalog-status-heading"><div><span class="dm-overline">Local reference</span><h2 id="catalog-heading">Products &amp; vulnerabilities</h2></div><div class="catalog-actions">${running ? `<button class="button" data-action="catalog-cancel">${complete ? 'Cancel sync' : 'Pause download'}</button>` : `<button class="button ${complete ? '' : 'primary'}" data-action="catalog-sync" ${needsKey ? 'disabled' : ''}>${complete ? 'Sync now' : partial ? 'Resume download' : 'Download catalog'}</button>`}</div></div><div class="catalog-summary"><div><strong>${num(status.total)}</strong><span>CVEs stored locally</span></div><div><strong>${complete ? (status.stale ? 'Update due' : 'Ready') : running ? 'Downloading' : partial ? 'Partially downloaded' : 'Not downloaded'}</strong><span>${complete ? `Last sync ${date(status.last_success_at)}` : 'Complete compressed annual feeds · API updates after seeding; allow 10 GiB free'}</span></div></div>${running ? `<div class="catalog-progress" role="status" aria-live="polite"><span class="catalog-pulse" aria-hidden="true"></span><div><strong>${esc(phase)}</strong>${job.total_records ? `<small>${num(job.records)} of ${num(job.total_records)} CVEs</small>` : requiredYears && status.download_method === 'feeds' ? `<small>${num(loadedYears)} of ${num(requiredYears)} yearly feeds saved</small>` : ''}</div></div>` : ''}${error ? `<p class="catalog-error" role="status">${esc(error)}</p>` : ''}<div class="catalog-sync-preference"><label class="checkbox"><input id="catalog-enabled" type="checkbox" ${status.enabled ? 'checked' : ''} ${running || (!complete && !loadedYears && !status.enabled) ? 'disabled' : ''}><span>Update daily</span></label><span>${status.enabled ? `While the backend is open, or through an enabled closed-app schedule; catches up when reopened.${status.next_check_at ? ` Next check ${date(status.next_check_at)}.` : ''}` : complete || loadedYears ? 'Daily updates paused.' : 'Daily updates start with the first download.'}</span></div>${
      Object.keys(job.timings || status.timings || {}).length
        ? `<details><summary>Sync timings</summary><p>${Object.entries(
            job.timings || status.timings,
          )
            .map(
              ([key, value]) =>
                `${esc(key.replace(/_seconds$/, '').replaceAll('_', ' '))}: ${Number(value).toFixed(1)}s`,
            )
            .join(' · ')}</p></details>`
        : ''
    }${catalogRiskStatusMarkup(status.risk)}${catalogIndexMarkup(status)}`;
  }

  function catalogResultsMarkup() {
    const result = state.result || {};
    const items = result.items || [];
    const offset = Number(result.offset) || 0;
    const limit = Number(result.limit) || 25;
    const total = Number(result.total) || 0;
    const rows = items
      .map((item) => {
        const id = item.id || item.cve_id;
        const severity = String(item.severity || 'UNKNOWN').toUpperCase();
        return `<button class="catalog-result ${state.selected === id ? 'active' : ''}" data-catalog-cve="${esc(id)}" aria-pressed="${state.selected === id}"><span class="catalog-result-title"><strong>${esc(id)}</strong><span class="catalog-severity" data-severity="${esc(severity)}">${esc(severity)}</span></span><span class="catalog-result-copy">${esc(item.description || 'No description available')}</span><small>${esc(item.status || '')}${item.modified || item.last_modified ? ` · ${date(item.modified || item.last_modified)}` : ''}</small></button>`;
      })
      .join('');
    return `<div class="catalog-result-count" role="status">${total ? `${num(offset + 1)}–${num(Math.min(offset + items.length, total))} of ${num(total)}` : 'No matching records'}</div><div class="catalog-result-list">${rows || `<p class="catalog-empty">${state.status?.total ? 'Try another CVE ID, product or description.' : 'Download the catalog to search CVEs offline.'}</p>`}</div>${total > limit ? `<nav class="catalog-pagination" aria-label="CVE search results"><button class="button" data-action="catalog-page" data-offset="${Math.max(0, offset - limit)}" ${offset === 0 ? 'disabled' : ''}>Previous</button><button class="button" data-action="catalog-page" data-offset="${offset + limit}" ${offset + limit >= total ? 'disabled' : ''}>Next</button></nav>` : ''}`;
  }

  function catalogDetailMarkup(record = state.detail) {
    if (!record)
      return '<div class="catalog-detail-empty"><span class="dm-overline">Reference record</span><p>Select a CVE to read its description, severity and sources.</p></div>';
    const cve = record.cve || {};
    const descriptions = array(cve.descriptions).filter((item) => item && typeof item === 'object');
    const description =
      descriptions.find((item) => item.lang === 'en')?.value ||
      descriptions[0]?.value ||
      'No description available.';
    const metrics = cve.metrics || {};
    const metricRows = ['cvssMetricV40', 'cvssMetricV31', 'cvssMetricV30', 'cvssMetricV2'].flatMap(
      (key) => array(metrics[key]).filter((item) => item && typeof item === 'object'),
    );
    const preferred =
      ['cvssMetricV40', 'cvssMetricV31', 'cvssMetricV30', 'cvssMetricV2']
        .map((key) => array(metrics[key]).filter((item) => item && typeof item === 'object'))
        .find((items) => items.length) || [];
    const primary = preferred.find((item) => item.type === 'Primary') || preferred[0];
    const metric = primary?.cvssData || {};
    const severity = String(
      metric.baseSeverity || primary?.baseSeverity || 'UNKNOWN',
    ).toUpperCase();
    const score = Number.isFinite(metric.baseScore) ? metric.baseScore.toFixed(1) : '—';
    const refs = array(cve.references).filter((item) => item && safeLink(item.url));
    const source = record.source || {};
    const risk = record.risk || {},
      kev = risk.kev,
      epss = risk.epss;
    const riskMarkup = `<section class="catalog-record-risk"><div><span>Known exploitation</span><strong>${kev?.listed ? 'CISA KEV' : kev ? 'Not listed in the local KEV feed' : 'KEV data unavailable'}</strong>${kev?.entry?.dateAdded ? `<small>Added ${esc(kev.entry.dateAdded)}</small>` : ''}${kev?.source?.retrieved_at ? `<small>Checked ${date(kev.source.retrieved_at)}${kev.stale ? ' · Update due' : ''}</small>` : ''}${kev?.entry?.knownRansomwareCampaignUse ? `<small>Ransomware use: ${esc(kev.entry.knownRansomwareCampaignUse)}</small>` : ''}</div><div><span>EPSS</span><strong>${Number.isFinite(epss?.score) ? `${(epss.score * 100).toFixed(2)}% probability` : 'No local score'}</strong>${Number.isFinite(epss?.percentile) ? `<small>${(epss.percentile * 100).toFixed(1)}th percentile</small>` : ''}${epss?.score_date ? `<small>${esc(epss.score_date)}${epss.stale ? ' · Update due' : ''}${epss.model_version ? ` · ${esc(epss.model_version)}` : ''}</small>` : ''}</div>${kev?.entry?.requiredAction ? `<p>${esc(kev.entry.requiredAction)}</p>` : ''}</section>`;
    const assessmentMarkup = metricRows.length
      ? `<details class="catalog-sources"><summary>CVSS assessments · ${num(metricRows.length)}</summary><div class="catalog-table-wrap"><table class="catalog-data-table"><thead><tr><th>Version / source</th><th>Score</th><th>Vector</th></tr></thead><tbody>${metricRows.map((item) => `<tr><td>CVSS ${esc(item.cvssData?.version || '')}<small>${esc(item.source || 'Source not specified')} · ${esc(item.type || '')}</small></td><td>${Number.isFinite(item.cvssData?.baseScore) ? item.cvssData.baseScore.toFixed(1) : '—'}<small>${esc(item.cvssData?.baseSeverity || item.baseSeverity || '')}</small></td><td><code>${esc(item.cvssData?.vectorString || 'Not supplied')}</code></td></tr>`).join('')}</tbody></table></div></details>`
      : '';
    return `<article class="catalog-record"><div class="catalog-record-heading"><div><span class="dm-overline">${esc(cve.vulnStatus || 'NVD record')}</span><h3>${esc(cve.id)}</h3></div><div class="catalog-score" data-severity="${esc(severity)}"><strong>${esc(score)}</strong><span>${esc(severity)}</span></div></div><p class="catalog-description">${esc(description)}</p>${riskMarkup}${ctx.actions.catalogObservedMarkup?.(record.observations) || ''}<dl class="catalog-record-dates"><div><dt>Published</dt><dd>${date(cve.published)}</dd></div><div><dt>Modified</dt><dd>${date(cve.lastModified || record.last_modified)}</dd></div></dl>${metric.version ? `<p class="catalog-metric">CVSS ${esc(metric.version)}${primary.source ? ` · ${esc(primary.source)}` : ''}${metric.vectorString ? `<code>${esc(metric.vectorString)}</code>` : ''}</p>` : ''}${assessmentMarkup}<a class="text-link catalog-observatory-link" href="#eclipse?cve=${encodeURIComponent(cve.id || '')}">See observed connections</a><a class="text-link" href="https://nvd.nist.gov/vuln/detail/${encodeURIComponent(cve.id || '')}" target="_blank" rel="noopener noreferrer">Open NVD record ${ctx.actions.icon('external')}</a><details class="catalog-sources"><summary>References · ${num(refs.length)}</summary><ul>${refs.map((ref) => `<li><a href="${esc(ref.url)}" target="_blank" rel="noopener noreferrer">${esc(ref.url)}</a>${array(ref.tags).length ? `<small>${esc(ref.tags.join(' · '))}</small>` : ''}</li>`).join('') || '<li>No published references.</li>'}</ul></details><details class="catalog-sources"><summary>Source record</summary><dl><dt>Retrieved</dt><dd>${date(source.retrieved_at)}</dd>${source.url ? `<dt>Source</dt><dd>${safeLink(source.url) ? `<a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.url)}</a>` : esc(source.url)}</dd>` : ''}${source.record_sha256 ? `<dt>Record SHA-256</dt><dd><code>${esc(source.record_sha256)}</code></dd>` : ''}</dl><pre>${esc(JSON.stringify(cve, null, 2))}</pre></details></article>`;
  }

  function catalogMarkup() {
    const cveMarkup = `<form id="catalog-search-form" class="catalog-search"><div class="field"><label for="catalog-query">Search CVEs</label><input id="catalog-query" name="query" type="search" value="${esc(state.query)}" placeholder="CVE ID, product or description" maxlength="200"></div><div class="field"><label for="catalog-severity">Severity</label><select id="catalog-severity" name="severity">${ctx.actions.optionList(
      [
        ['', 'All severities'],
        ['CRITICAL', 'Critical'],
        ['HIGH', 'High'],
        ['MEDIUM', 'Medium'],
        ['LOW', 'Low'],
        ['NONE', 'None'],
        ['UNKNOWN', 'Unknown'],
      ],
      state.severity,
    )}</select></div><button class="button" type="submit">Search</button></form><div class="catalog-browse"><section id="cve-catalog-results" aria-label="CVE search results">${catalogResultsMarkup()}</section><section id="cve-catalog-detail" aria-label="Selected CVE">${catalogDetailMarkup()}</section></div>`;
    return `<section id="cve-catalog" class="catalog-panel panel" aria-labelledby="catalog-heading"><div id="cve-catalog-status">${catalogStatusMarkup()}</div>${ctx.actions.catalogLibraryMarkup(cveMarkup)}<p class="catalog-attribution">This product uses data from the NVD API but is not endorsed or certified by the NVD.</p></section>`;
  }

  function stopCatalogPolling() {
    if (state.timer) clearTimeout(state.timer);
    state.timer = null;
  }

  function scheduleCatalogPolling(generation = state.generation, delay = 1500) {
    stopCatalogPolling();
    state.timer = setTimeout(() => {
      if (generation === state.generation && ctx.actions.$('#cve-catalog'))
        void refreshCatalogStatus(generation);
    }, delay);
  }

  async function catalogSection(params = new URLSearchParams()) {
    stopCatalogPolling();
    const generation = ++state.generation;
    if (params.has('q')) state.query = params.get('q').slice(0, 200);
    const requestedSeverity = params.get('severity');
    if (['', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NONE', 'UNKNOWN'].includes(requestedSeverity))
      state.severity = requestedSeverity;
    try {
      const status = await ctx.actions.api('/api/cve-catalog/status');
      if (generation !== state.generation) return '';
      state.status = status;
      const search = new URLSearchParams({ q: state.query, limit: '25', offset: '0' });
      if (state.severity) search.set('severity', state.severity);
      const result = await ctx.actions.api('/api/cve-catalog/search?' + search);
      if (generation !== state.generation) return '';
      state.result = result;
      await ctx.actions.loadCatalogLibrary(params);
      if (generation !== state.generation) return '';
      const requested = params.get('cve');
      if (requested && /^CVE-\d{4}-\d{4,}$/i.test(requested))
        state.selected = requested.toUpperCase();
      if (state.selected) {
        try {
          const path = '/api/cve-catalog/records/' + encodeURIComponent(state.selected);
          const [detail, observations] = await Promise.all([
            ctx.actions.api(path),
            ctx.actions.api(path + '/observations').catch(() => null),
          ]);
          if (generation !== state.generation) return '';
          state.detail = { ...detail, observations: observations || detail.observations };
        } catch (error) {
          if (error.name === 'AbortError' || generation !== state.generation) return '';
          state.detail = null;
        }
      }
    } catch (error) {
      if (error.name === 'AbortError' || generation !== state.generation) return '';
      state.status = null;
      state.detail = null;
      state.result = { items: [], total: 0, limit: 25, offset: 0 };
    }
    scheduleCatalogPolling(generation);
    return catalogMarkup();
  }

  async function refreshCatalogStatus(generation = state.generation) {
    const region = ctx.actions.$('#cve-catalog-status');
    if (!region || generation !== state.generation) return;
    const wasRunning = busy();
    const wasIndexing = state.status?.index_running;
    const wasRiskSyncing = state.status?.risk?.running;
    try {
      const status = await ctx.actions.api('/api/cve-catalog/status');
      if (generation !== state.generation || ctx.actions.$('#cve-catalog-status') !== region)
        return;
      state.status = status;
      region.innerHTML = catalogStatusMarkup();
      if (wasRunning && !busy()) await searchCatalog(state.query, state.severity, 0);
      if ((wasIndexing && !status.index_running) || (wasRiskSyncing && !status.risk?.running)) {
        await ctx.actions.searchCatalogProducts();
        if (state.selected && state.library.view === 'cves')
          await selectCatalogRecord(state.selected);
      }
    } catch (error) {
      if (ctx.actions.$('#cve-catalog-status') === region)
        region.innerHTML = `<p class="catalog-error" role="status">Catalog status unavailable: ${esc(error.message)}</p><button class="button" data-action="catalog-refresh">Try again</button>`;
    }
    if (generation === state.generation && ctx.actions.$('#cve-catalog'))
      scheduleCatalogPolling(
        generation,
        busy() || state.status?.risk?.running || state.status?.index_running ? 1500 : 30000,
      );
  }

  async function searchCatalog(query = '', severity = '', offset = 0) {
    const region = ctx.actions.$('#cve-catalog-results');
    if (!region) return;
    const request = ++state.searchRequest;
    state.query = String(query).trim();
    state.severity = severity;
    ctx.actions.refreshCatalogSelection?.();
    const params = new URLSearchParams({ q: state.query, limit: '25', offset: String(offset) });
    if (severity) params.set('severity', severity);
    region.setAttribute?.('aria-busy', 'true');
    try {
      const result = await ctx.actions.api('/api/cve-catalog/search?' + params);
      if (request !== state.searchRequest || ctx.actions.$('#cve-catalog-results') !== region)
        return;
      state.result = result;
      region.innerHTML = catalogResultsMarkup();
    } catch (error) {
      if (request === state.searchRequest && ctx.actions.$('#cve-catalog-results') === region)
        region.innerHTML = `<p class="catalog-error" role="status">${esc(error.message)}</p>`;
    } finally {
      if (request === state.searchRequest) region.removeAttribute?.('aria-busy');
    }
  }

  async function selectCatalogRecord(id) {
    if (ctx.actions.$('#catalog-library')) await ctx.actions.showCatalogView('cves');
    const region = ctx.actions.$('#cve-catalog-detail');
    if (!region) return;
    const request = ++state.detailRequest;
    state.selected = id;
    ctx.actions.refreshCatalogSelection?.();
    ctx.actions.$$('[data-catalog-cve]').forEach((button) => {
      const selected = button.dataset.catalogCve === id;
      button.classList.toggle('active', selected);
      button.setAttribute?.('aria-pressed', String(selected));
    });
    region.setAttribute?.('aria-busy', 'true');
    try {
      const [result, observations] = await Promise.all([
        ctx.actions.api('/api/cve-catalog/records/' + encodeURIComponent(id)),
        ctx.actions.$('#catalog-library')
          ? ctx.actions
              .api('/api/cve-catalog/records/' + encodeURIComponent(id) + '/observations')
              .catch(() => null)
          : Promise.resolve(null),
      ]);
      if (request !== state.detailRequest || ctx.actions.$('#cve-catalog-detail') !== region)
        return;
      state.detail = { ...result, observations: observations || result.observations };
      region.innerHTML = catalogDetailMarkup();
    } catch (error) {
      if (request === state.detailRequest && ctx.actions.$('#cve-catalog-detail') === region)
        region.innerHTML = `<p class="catalog-error" role="status">${esc(error.message)}</p>`;
    } finally {
      if (request === state.detailRequest) region.removeAttribute?.('aria-busy');
    }
  }

  async function catalogCommand(command, enabled) {
    const region = ctx.actions.$('#cve-catalog-status');
    const result = await ctx.actions.api('/api/cve-catalog/' + command, {
      method: 'POST',
      ...(command === 'settings' ? { body: { enabled } } : {}),
    });
    if (ctx.actions.$('#cve-catalog-status') !== region) return;
    if (result && 'total' in result) state.status = result;
    await refreshCatalogStatus();
  }

  Object.assign(ctx.actions, {
    catalogSection,
    catalogStatusMarkup,
    catalogResultsMarkup,
    catalogDetailMarkup,
    searchCatalog,
    selectCatalogRecord,
    refreshCatalogStatus,
    catalogCommand,
    stopCatalogPolling,
  });
  installLibrary(ctx);
}
