/** Explicit company-site contact discovery; saved evidence never initiates a lookup. */
import { install as installOutreachPreparation } from './outreach_preparation.js';
export function install(ctx) {
  const state = ctx.state.contacts;
  state.selectedEntityIds ||= new Set();
  state.sourceUrls ||= new Map();
  const active = (job) => ['queued', 'running', 'cancelling'].includes(job?.state);
  const endpoint = (id) => `/api/entities/${encodeURIComponent(id)}/contacts`;
  const jobEndpoint = (id) => `/api/contact-discovery/jobs/${encodeURIComponent(id)}`;
  const esc = (value) => ctx.actions.esc(value);
  const labels = {
    relevant_found: 'Contact found',
    general_only: 'General contact channels only',
    not_found: 'Checked pages: no published contacts found',
    partial: 'Search incomplete',
    cancelled: 'Discovery stopped',
    failed: 'Discovery failed',
  };
  const purposeLabels = {
    security: 'Cybersecurity reporting',
    it: 'IT / webmaster referral',
    product_support: 'Product support',
    management: 'Management',
    general: 'General corporate contact',
    other: 'Purpose not established',
    privacy: 'Privacy office',
    hr: 'Human resources',
    media: 'Media relations',
    investor: 'Investor relations',
    compliance: 'Compliance',
    physical_emergency: 'Physical emergency',
  };
  const purposeRanks = {
    security: 0,
    it: 1,
    product_support: 2,
    management: 3,
    general: 4,
    other: 5,
    privacy: 6,
    hr: 7,
    media: 8,
    investor: 9,
    compliance: 10,
    physical_emergency: 11,
  };
  const outcomeLabels = {
    reporting_route_found: 'Published security reporting route found',
    referral_found: 'Technical referral found',
    general_only: 'General contacts found; technical route not established',
    checked_no_suitable_contact: 'Checked pages: no suitable contact found',
    incomplete: 'Some sources could not be checked completely',
    blocked: 'Website access blocked; contact availability is unknown',
    cancelled: 'Search stopped before completion',
  };
  function safeContactURL(value) {
    try {
      const url = new URL(value);
      return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password
        ? esc(url.href)
        : '';
    } catch {
      return '';
    }
  }
  function contactEntityId() {
    const route = ctx.state.navigation.currentRoute || '';
    if (route.startsWith('entity/'))
      return ctx.state.entities?.current?.id || state.contextEntityId;
    if (ctx.state.editor.tab === 'contact' && ctx.state.editor.currentLead?.id)
      return ctx.state.editor.currentLead.id;
    return state.contextEntityId;
  }
  function isVisible(entityId) {
    const route = ctx.state.navigation.currentRoute || '';
    return (
      contactEntityId() === entityId &&
      (route.startsWith('entity/') ||
        (ctx.state.editor.tab === 'contact' && ctx.state.editor.currentLead?.id === entityId))
    );
  }
  function replacePanel(selector, markup) {
    const panel = ctx.actions.$(selector);
    if (!panel) return;
    const opened = [...(panel.querySelectorAll?.('details[open][data-contact-detail]') || [])].map(
      (item) => item.dataset.contactDetail,
    );
    const focused = typeof document === 'undefined' ? null : document.activeElement;
    const restoreFocus = !!focused && !!panel.contains?.(focused);
    const keys = [
      'id',
      'data-action',
      'data-contact-review',
      'data-decision',
      'data-contact-use',
      'data-contact-route',
      'data-route-action',
      'data-contact-copy',
      'data-contact-value-copy',
      'data-contact-detail',
    ];
    const identity = restoreFocus
      ? keys.flatMap((key) =>
          focused.getAttribute?.(key) ? [[key, focused.getAttribute(key)]] : [],
        )
      : [];
    const cardId = restoreFocus ? focused.closest?.('[data-contact-id]')?.dataset.contactId : null;
    const summaryId =
      restoreFocus && focused.tagName === 'SUMMARY'
        ? focused.parentElement?.dataset.contactDetail
        : null;
    panel.outerHTML = markup;
    const current = ctx.actions.$(selector);
    for (const item of current?.querySelectorAll?.('details[data-contact-detail]') || [])
      if (opened.includes(item.dataset.contactDetail)) item.open = true;
    if (restoreFocus) {
      const controls = [
        ...(current?.querySelectorAll?.('button,input,select,summary,a,[data-contact-id]') || []),
      ];
      const summary =
        summaryId &&
        [...(current?.querySelectorAll?.('details[data-contact-detail]') || [])]
          .find((item) => item.dataset.contactDetail === summaryId)
          ?.querySelector('summary');
      const target =
        summary ||
        (identity.length &&
          controls.find(
            (item) =>
              !item.disabled && identity.every(([key, value]) => item.getAttribute(key) === value),
          )) ||
        controls.find((item) => cardId && item.dataset.contactId === cardId) ||
        current;
      target?.focus?.({ preventScroll: true });
    }
  }
  function redraw(entityId) {
    if (entityId && isVisible(entityId)) {
      replacePanel('#contact-discovery-panel', contactDiscoveryMarkup());
    }
    if (
      !entityId &&
      ['leads', 'entities'].includes(ctx.state.navigation.currentRoute.split('?')[0])
    ) {
      replacePanel('#contact-discovery-batch', contactBatchMarkup());
    }
  }
  function entityLabel(entityId) {
    const lead = ctx.state.editor.currentLead;
    return (
      (lead?.id === entityId && (lead.company || lead.domain)) ||
      state.entityNames.get(entityId) ||
      'Business entity'
    );
  }
  function progressMarkup(job, error = '', batch = false) {
    if (!job) return '';
    const watching = state.watch?.jobId === job.id;
    const title =
      {
        queued: 'Contact discovery queued',
        running: 'Finding published contacts',
        cancelling: 'Stopping contact discovery',
        completed: 'Contact discovery finished',
        cancelled: 'Contact discovery stopped',
        failed: 'Contact discovery failed',
      }[job.state] || 'Contact discovery status';
    return `<div class="contact-progress" role="status"><strong>${active(job) && watching && !error ? '<span class="spinner"></span>' : ''}${esc(title)}</strong><p>${ctx.actions.num(job.completed)} of ${ctx.actions.num(job.total)} entities processed${job.current_entity ? ` · ${esc(entityLabel(job.current_entity))}` : ''}</p>${job.error ? `<p class="entity-review-required">${esc(job.error)}</p>` : ''}${active(job) ? `<button class="button small" data-action="cancel-contact-discovery" ${job.state === 'cancelling' ? 'disabled' : ''}>Stop discovery</button>${!watching ? `<button class="button small" data-action="${batch ? 'refresh-contact-batch' : 'load-contact-discovery'}">Refresh status</button>` : ''}` : ''}${batch && job.results?.length ? `<details data-contact-detail="batch-results"><summary>Results by entity</summary><ul>${job.results.map((result) => `<li><a class="text-link" href="#entity/${encodeURIComponent(result.entity_id || '')}?tab=contacts">${esc(entityLabel(result.entity_id))}</a> · ${esc((['reporting_route_found', 'referral_found'].includes(result.outcome) ? 'Contact found' : labels[result.status]) || result.status || result.error || 'Processed')}${result.reason || result.error ? ` · ${esc(result.reason || result.error)}` : ''}</li>`).join('')}</ul></details>` : ''}</div>`;
  }
  function sourcePreview(candidate) {
    const sources = candidate.sources || [];
    const source =
      sources.find((item) => item.purpose === candidate.purpose && item.excerpt) ||
      sources.find((item) => item.excerpt) ||
      sources[0];
    if (!source) return '';
    const url = safeContactURL(source.url);
    if (!url) return '';
    const host = new URL(source.url).hostname.replace(/^www\./, '');
    return `<details class="contact-proof" data-contact-detail="source-${esc(candidate.id)}"><summary>Source · ${esc(host)}</summary><a class="text-link" href="${url}" target="_blank" rel="noopener noreferrer">${esc(source.url)}</a>${source.excerpt ? `<blockquote>${esc(source.excerpt)}</blockquote>` : ''}<p class="contact-meta">Captured ${esc(ctx.actions.stamp(source.retrieved_at || candidate.last_seen))}${source.truncated ? ' · Partial capture' : ''}</p></details>`;
  }
  function candidateMarkup(candidate, featured = false) {
    const id = esc(candidate.id);
    const url = candidate.kind === 'form' ? safeContactURL(candidate.value) : '';
    const label = candidate.fax
      ? 'Fax number'
      : candidate.kind === 'person'
        ? 'Saved person'
        : candidate.purpose === 'security'
          ? 'Security contact'
          : ['it', 'product_support'].includes(candidate.purpose)
            ? 'Technical referral found'
            : purposeLabels[candidate.purpose] || 'Saved contact';
    const canFill =
      !candidate.unusable &&
      !candidate.fax &&
      candidate.decision !== 'ignored' &&
      candidate.purpose !== 'physical_emergency' &&
      ((ctx.state.navigation.currentRoute || '').startsWith('entity/') ||
        ctx.state.editor.currentLead?.case?.stage !== 'closed') &&
      ['email', 'phone', 'person'].includes(candidate.kind);
    const identity = [candidate.name !== candidate.value ? candidate.name : '', candidate.role]
      .filter(Boolean)
      .join(' · ');
    const facts = [
      candidate.known ? 'Known contact' : '',
      candidate.preferred ? 'Preferred' : '',
      candidate.preferred && candidate.decision === 'pending' ? 'Pending confirmation' : '',
      candidate.last_successful_use && !candidate.unusable ? 'Delivery recorded' : '',
      candidate.decision === 'ignored' ? 'Hidden' : '',
      candidate.missing_from_latest
        ? 'Previously found · not in the latest search'
        : candidate.sources?.length && candidate.missing_from_latest === false
          ? 'In latest search'
          : '',
    ].filter(Boolean);
    return `<article class="contact-candidate${featured ? ' contact-featured' : ''}${candidate.unusable ? ' contact-unavailable' : ''}" data-contact-id="${id}"${featured ? ' data-primary-route="true"' : ''} tabindex="-1"><div class="contact-route-content"><h3>${url ? `<a href="${url}" target="_blank" rel="noopener noreferrer">${esc(candidate.value)}</a>` : esc(candidate.value || candidate.name)}</h3><div class="contact-purpose-line"><p class="contact-purpose">${esc(label)}${candidate.purpose === 'product_support' ? ' · Product support' : ''}</p>${identity ? `<span class="contact-identity">${esc(identity)}</span>` : ''}</div>${candidate.routing_label ? `<p class="contact-routing">${esc(candidate.routing_label)}</p>` : ''}${candidate.unusable ? `<p class="contact-unavailable-note">Unavailable · ${esc(candidate.usability_reason || 'Delivery issue recorded')}</p>` : ''}<div class="contact-route-meta">${facts.length ? `<p class="contact-facts">${facts.map((fact) => `<span>${esc(fact)}</span>`).join('')}</p>` : ''}${sourcePreview(candidate)}</div></div><div class="contact-route-actions"><button class="button small contact-copy-action" type="button" data-contact-value-copy="${id}" aria-label="Copy ${esc(candidate.value || candidate.name)}">Copy</button>${canFill ? `<button class="button small contact-fill-action" type="button" data-contact-use="${id}">Fill fields</button>` : ''}</div></article>`;
  }
  function orderedCandidates(candidates) {
    const inactive = (candidate) =>
      Number(
        candidate.decision === 'ignored' || !!candidate.unusable || !!candidate.missing_from_latest,
      );
    return [...candidates].sort(
      (a, b) =>
        inactive(a) - inactive(b) ||
        Number(!!b.preferred) - Number(!!a.preferred) ||
        (purposeRanks[a.purpose] ?? 5) - (purposeRanks[b.purpose] ?? 5) ||
        Number(!!b.known) - Number(!!a.known) ||
        ({ email: 0, phone: 1, person: 2, form: 3 }[a.kind] ?? 4) -
          ({ email: 0, phone: 1, person: 2, form: 3 }[b.kind] ?? 4) ||
        (a.value || '').localeCompare(b.value || ''),
    );
  }
  function contactDetailsMarkup(candidates, latest) {
    const stateLabels = {
      checked: 'Checked',
      checked_empty: 'No contact on this page',
      not_found: 'Page not found',
      redirected: 'Redirect followed',
      blocked: 'Blocked',
      incomplete: 'Partial capture',
      unreadable: 'Could not parse page',
      unvisited: 'Not checked',
    };
    const sources = candidates
      .map(
        (candidate) =>
          `<details class="contact-source" data-contact-detail="history-${esc(candidate.id)}"><summary>${esc(candidate.value)}<span>Source history</span></summary>${(
            candidate.sources || []
          )
            .map((source) => {
              const url = safeContactURL(source.url);
              return `<p>${url ? `<a class="text-link" href="${url}" target="_blank" rel="noopener noreferrer">${esc(source.url)}</a>` : esc(source.url || 'Saved contact')}<small>${esc(ctx.actions.stamp(source.retrieved_at || candidate.last_seen))}${source.truncated ? ' · Partial capture' : ''}</small></p>${source.excerpt ? `<blockquote>${esc(source.excerpt)}</blockquote>` : ''}`;
            })
            .join(
              '',
            )}${candidate.last_successful_use ? `<p>Last delivery ${esc(ctx.actions.stamp(candidate.last_successful_use))}</p>` : ''}${candidate.missing_from_latest ? '<p>Not present in the latest captured sources.</p>' : ''}${candidate.source_changed ? '<p>Published source context changed.</p>' : ''}${candidate.provenance_text ? `<p class="section-note">${esc(candidate.provenance_text)}</p>` : ''}${candidate.revision ? `<div class="actions">${!candidate.unusable && !candidate.preferred ? `<button class="button small" data-contact-route="${esc(candidate.id)}" data-route-action="prefer">Prefer</button>` : ''}<button class="button small" data-contact-review="${esc(candidate.id)}" data-decision="${candidate.decision === 'ignored' ? 'pending' : 'ignore'}">${candidate.decision === 'ignored' ? 'Show' : 'Hide'}</button>${candidate.unusable ? `<button class="button small" data-contact-route="${esc(candidate.id)}" data-route-action="restore">Restore availability</button>` : `<button class="button small" data-contact-route="${esc(candidate.id)}" data-route-action="unusable">Mark unavailable</button>`}</div>` : ''}</details>`,
      )
      .join('');
    const coverage = latest?.coverage?.length
      ? `<div class="table-wrap"><table><thead><tr><th>Source</th><th>Capture</th><th>Checked</th></tr></thead><tbody>${latest.coverage
          .map((row) => {
            const url = safeContactURL(row.url);
            return `<tr><td>${url ? `<a href="${url}" target="_blank" rel="noopener noreferrer">${esc(row.url)}</a>` : esc(row.url)}</td><td>${esc(stateLabels[row.state] || row.state)}${row.status_code ? ` · HTTP ${esc(row.status_code)}` : ''}${row.message ? `<p>${esc(row.message)}</p>` : ''}</td><td>${row.checked_at ? esc(ctx.actions.stamp(row.checked_at)) : '—'}</td></tr>`;
          })
          .join('')}</tbody></table></div>`
      : '';
    return (
      sources +
      coverage +
      (latest?.issues?.length
        ? `<ul>${latest.issues.map((issue) => `<li>${esc(issue.message || issue.code)}</li>`).join('')}</ul>`
        : '')
    );
  }
  function contactDiscoveryMarkup(entity) {
    if (entity) {
      state.contextEntityId = typeof entity === 'string' ? entity : entity.id;
      if (typeof entity === 'object')
        state.entityNames.set(entity.id, entity.company || entity.domain);
    }
    const entityId = contactEntityId();
    if (!entityId) return '';
    const saved = state.entities.get(entityId);
    const roots = saved?.roots || [];
    const eligible = roots.filter((root) => root.eligible);
    const selected =
      state.selectedRoots.get(entityId) ||
      saved?.default_root ||
      (eligible.length === 1 ? eligible[0].root_domain : '');
    const chosen = roots.find((root) => root.root_domain === selected);
    const job = saved?.active_job || saved?.last_job;
    const running = active(job) || state.pending?.entityId === entityId;
    const latest = saved?.latest_run;
    const candidates = orderedCandidates(saved?.contacts || saved?.candidates || []);
    const visible = candidates.filter(
      (candidate) =>
        candidate.decision !== 'ignored' &&
        !candidate.unusable &&
        !candidate.fax &&
        !candidate.purpose_conflict &&
        candidate.recommended_for_outreach !== false &&
        candidate.routine_suggestion !== false &&
        candidate.purpose !== 'physical_emergency',
    );
    // Emphasis reflects a current saved preference or a useful published role;
    // it never claims a recipient is verified or responsible for the systems.
    const present = visible.filter((candidate) => !candidate.missing_from_latest);
    const displayPool = present.length ? present : visible;
    const current = displayPool.filter(
      (candidate) =>
        !candidate.missing_from_latest && !candidate.fax && candidate.kind !== 'person',
    );
    const featured =
      current.find((candidate) => candidate.preferred) ||
      current.find((candidate) =>
        ['security', 'it', 'product_support'].includes(candidate.purpose),
      ) ||
      current[0];
    const primary = [
      ...new Set(
        [
          featured || displayPool[0],
          displayPool.find((candidate) => candidate.purpose === 'security'),
          displayPool.find((candidate) => ['it', 'product_support'].includes(candidate.purpose)),
        ].filter(Boolean),
      ),
    ];
    for (const candidate of displayPool) {
      if (primary.length >= 3) break;
      if (!primary.includes(candidate)) primary.push(candidate);
    }
    const additional = candidates.filter((candidate) => !primary.includes(candidate));
    const headline = primary.length
      ? 'Contact found'
      : running
        ? 'Finding contacts'
        : latest
          ? latest.outcome === 'blocked'
            ? 'Website unavailable'
            : latest.status === 'partial' || latest.outcome === 'incomplete'
              ? 'Search incomplete'
              : 'No contact found'
          : 'Contacts';
    const moreLabel = additional.length ? 'Sources & other contacts' : 'Sources & search details';
    return `<section class="contact-finder" id="contact-discovery-panel" data-entity-id="${esc(entityId)}" tabindex="-1" aria-label="Contacts"><header class="contact-finder-head"><h2>${headline}</h2><button class="button small contact-search-action" data-action="${latest ? 'refresh-contact-discovery' : 'start-contact-discovery'}" ${running || !chosen?.eligible ? 'disabled' : ''}>${latest ? 'Search again' : 'Find contacts'}</button></header>${roots.length > 1 ? `<div class="field contact-website"><label for="contact-root">Website</label><select id="contact-root" ${running ? 'disabled' : ''}><option value="">Select website</option>${roots.map((root) => `<option value="${esc(root.root_domain)}" ${root.root_domain === selected ? 'selected' : ''} ${!root.eligible ? 'disabled' : ''}>${esc(root.root_domain)}</option>`).join('')}</select></div>` : `<input id="contact-root" type="hidden" value="${esc(selected)}">`}${saved?.error ? `<p class="entity-review-required" role="alert">${esc(saved.error)}</p>` : ''}${saved?.roots && !eligible.length ? '<p class="contact-empty">No website is associated with this entity.</p>' : ''}${!saved ? '<p class="contact-empty">Loading saved contacts…</p>' : ''}<div class="contact-candidates contact-primary-list">${primary.map((candidate) => candidateMarkup(candidate, candidate === featured)).join('')}</div>${active(job) ? progressMarkup(job, saved?.error) : ''}<details class="contact-research-details" data-contact-detail="details"><summary>${moreLabel}${additional.length ? `<span class="contact-more-count">${additional.length} more</span>` : ''}</summary>${additional.length ? `<div class="contact-candidates contact-secondary-list">${additional.map((candidate) => candidateMarkup(candidate)).join('')}</div>` : ''}${contactDetailsMarkup(candidates, latest)}${job?.error ? `<p role="alert">${esc(job.error)}</p>` : ''}<div class="contact-evidence-tools">${latest ? `<p class="contact-meta">${esc(ctx.actions.stamp(latest.finished_at || latest.started_at))}${latest.resolved_hostname ? ` · ${esc(latest.resolved_hostname)}` : ''}</p><a class="button small" href="${endpoint(entityId)}/evidence.zip">Download evidence</a>` : ''}<button class="button small" data-action="load-contact-discovery">Reload saved contacts</button></div><div class="contact-focused-search"><div class="field"><label for="contact-source-url">Search one company page</label><input id="contact-source-url" type="url" maxlength="2048" value="${esc(state.sourceUrls.get(entityId) || '')}" placeholder="https://${esc(selected || 'company.example')}/contact" ${running ? 'disabled' : ''}></div><button class="button small" data-action="inspect-contact-source" ${running || !chosen?.eligible ? 'disabled' : ''}>Search this page</button></div></details></section>`;
  }
  function contactBatchMarkup() {
    const selected = state.batchEntityIds.filter((id) => state.selectedEntityIds.has(id));
    const count = selected.length;
    const hidden = state.selectedEntityIds.size - new Set(selected).size;
    return `<section class="panel" id="contact-discovery-batch" tabindex="-1"><div class="panel-body"><div class="contact-batch-head"><div><h2>Find contacts</h2><p class="section-note">Select up to 25 entities.</p></div><div class="actions"><button class="button" data-action="clear-contact-selection" ${!state.selectedEntityIds.size ? 'disabled' : ''}>Clear selection</button><button class="button primary" data-action="start-contact-batch" ${!count || count > 25 || active(state.batch?.job) || state.pending ? 'disabled' : ''}>Find contacts (${count})</button></div></div><p class="contact-selection-status section-note" role="status">${count ? `${ctx.actions.num(count)} selected in this view.` : 'No businesses selected in this view.'}${hidden ? ` ${ctx.actions.num(hidden)} selected outside this view will not be included.` : ''}</p>${count > 25 ? '<p class="entity-review-required">Select up to 25 entities.</p>' : ''}${count ? `<details data-contact-detail="batch-selection"><summary>Selected businesses (${count})</summary><ul>${selected.map((id) => `<li>${esc(entityLabel(id))}</li>`).join('')}</ul></details>` : ''}${state.batch?.error ? `<p class="entity-review-required" role="alert">${esc(state.batch.error)}</p>` : ''}${progressMarkup(state.batch?.job, state.batch?.error, true)}</div></section>`;
  }
  function clearContactSelection() {
    state.selectedEntityIds.clear();
    for (const checkbox of ctx.actions.$$('[data-contact-select]')) {
      checkbox.checked = false;
      checkbox.closest('tr')?.classList.remove('is-selected');
    }
    redraw(null);
  }
  function stopContactDiscoveryPolling() {
    state.generation++;
    clearTimeout(state.timer);
    state.timer = null;
    state.watch = null;
    state.pending = null;
  }
  function startWatch(job, entityId = null) {
    clearTimeout(state.timer);
    state.timer = null;
    if (!active(job)) {
      state.watch = null;
      return;
    }
    state.watch = {
      jobId: job.id,
      entityId,
      generation: state.generation,
      deadline:
        Date.now() + Math.min(1200000, Math.max(90000, Number(job.total || 1) * 45000 + 45000)),
      polls: 0,
    };
    state.timer = setTimeout(pollContactDiscovery, 1200);
  }
  async function loadContactDiscovery(entityId = contactEntityId(), { resume = true } = {}) {
    if (!entityId) return;
    const generation = state.generation;
    try {
      const saved = await ctx.actions.api(endpoint(entityId), { timeoutMs: 15000 });
      if (generation !== state.generation) return;
      const previous = state.entities.get(entityId);
      saved.last_job =
        previous?.active_job && !active(previous.active_job)
          ? previous.active_job
          : previous?.last_job;
      state.entities.set(entityId, saved);
      if (resume) startWatch(saved.active_job, entityId);
      redraw(entityId);
      return saved;
    } catch (error) {
      if (generation !== state.generation) return;
      if (state.watch?.entityId === entityId) {
        clearTimeout(state.timer);
        state.timer = null;
        state.watch = null;
      }
      state.entities.set(entityId, {
        ...(state.entities.get(entityId) || {}),
        error: error.message,
      });
      redraw(entityId);
    }
  }
  async function pollContactDiscovery() {
    const watch = state.watch;
    if (!watch || watch.generation !== state.generation) return;
    state.timer = null;
    try {
      if (Date.now() >= watch.deadline || watch.polls++ >= 1000)
        throw Error(
          'Status checks stopped at the time limit. Refresh saved status to check the final result.',
        );
      const job = await ctx.actions.api(jobEndpoint(watch.jobId), { timeoutMs: 15000 });
      if (state.watch !== watch || watch.generation !== state.generation) return;
      if (watch.entityId) {
        const saved = state.entities.get(watch.entityId) || {};
        state.entities.set(watch.entityId, { ...saved, active_job: job, error: '' });
      } else state.batch = { job, error: '' };
      if (active(job)) state.timer = setTimeout(pollContactDiscovery, 1200);
      else {
        state.watch = null;
        if (watch.entityId) await loadContactDiscovery(watch.entityId, { resume: false });
      }
      redraw(watch.entityId);
    } catch (error) {
      if (state.watch !== watch || watch.generation !== state.generation) return;
      state.watch = null;
      if (watch.entityId)
        state.entities.set(watch.entityId, {
          ...state.entities.get(watch.entityId),
          error: error.message,
        });
      else state.batch = { ...state.batch, error: error.message };
      redraw(watch.entityId);
    }
  }
  async function startContactDiscovery(refresh = false, focused = false) {
    const entityId = contactEntityId();
    const saved = state.entities.get(entityId);
    if (!entityId || state.pending || active(saved?.active_job)) return;
    const root = ctx.actions.$('#contact-root')?.value;
    if (!saved?.roots.some((item) => item.eligible && item.root_domain === root))
      throw Error('Select an entity website first.');
    const sourceUrl = focused ? (ctx.actions.$('#contact-source-url')?.value || '').trim() : '';
    if (focused) {
      if (!sourceUrl) throw Error('Enter a company source URL to inspect.');
      let url;
      try {
        url = new URL(sourceUrl);
      } catch {
        throw Error('Enter a valid HTTPS company source URL.');
      }
      const paired = root.startsWith('www.') ? root.slice(4) : `www.${root}`;
      if (
        url.protocol !== 'https:' ||
        url.username ||
        url.password ||
        ![root, paired].includes(url.hostname) ||
        (url.port && url.port !== '443')
      )
        throw Error(
          'Inspect a page on the selected hostname or its www counterpart. Open external reporting routes manually.',
        );
      state.sourceUrls.set(entityId, sourceUrl);
    }
    const generation = state.generation;
    state.pending = { entityId };
    redraw(entityId);
    try {
      const job = await ctx.actions.api(`${endpoint(entityId)}/discover`, {
        method: 'POST',
        body: {
          root_domain: root,
          include_www: true,
          refresh,
          ...(focused ? { source_url: sourceUrl } : {}),
        },
        timeoutMs: 15000,
      });
      if (generation !== state.generation) return;
      state.entities.set(entityId, { ...saved, active_job: job, error: '' });
      startWatch(job, entityId);
      if (!active(job)) await loadContactDiscovery(entityId, { resume: false });
    } catch (error) {
      if (generation !== state.generation) return;
      state.entities.set(entityId, { ...saved, error: error.message });
    } finally {
      if (generation === state.generation) {
        state.pending = null;
        redraw(entityId);
      }
    }
  }
  async function startContactBatch() {
    if (state.pending || active(state.batch?.job)) return;
    const entityIds = [...new Set(state.batchEntityIds)].filter((id) =>
      state.selectedEntityIds.has(id),
    );
    if (!entityIds.length) return;
    if (entityIds.length > 25) throw Error('Select up to 25 entities.');
    const generation = state.generation;
    state.pending = { entityId: null };
    redraw(null);
    try {
      const job = await ctx.actions.api('/api/contact-discovery/batch', {
        method: 'POST',
        body: { entity_ids: entityIds, include_www: true },
        timeoutMs: 15000,
      });
      if (generation !== state.generation) return;
      state.batch = { job, error: '' };
      startWatch(job);
    } catch (error) {
      if (generation === state.generation) state.batch = { ...state.batch, error: error.message };
    } finally {
      if (generation === state.generation) {
        state.pending = null;
        redraw(null);
      }
    }
  }
  function resumeContactBatch() {
    if (active(state.batch?.job)) {
      state.batch.error = '';
      startWatch(state.batch.job);
      redraw(null);
    }
  }
  async function cancelContactDiscovery() {
    const entityId = isVisible(contactEntityId()) ? contactEntityId() : null;
    const saved = entityId ? state.entities.get(entityId) : state.batch;
    const job = entityId ? saved?.active_job : saved?.job;
    if (!active(job)) return;
    const generation = state.generation;
    try {
      const result = await ctx.actions.api(`${jobEndpoint(job.id)}/cancel`, {
        method: 'POST',
        timeoutMs: 15000,
      });
      if (generation !== state.generation) return;
      if (entityId) state.entities.set(entityId, { ...saved, active_job: result, error: '' });
      else state.batch = { job: result, error: '' };
      startWatch(result, entityId);
      if (!active(result) && entityId) await loadContactDiscovery(entityId, { resume: false });
    } catch (error) {
      if (generation !== state.generation) return;
      clearTimeout(state.timer);
      state.timer = null;
      state.watch = null;
      if (entityId)
        state.entities.set(entityId, {
          ...saved,
          error: `Could not confirm cancellation. ${error.message}`,
        });
      else state.batch = { ...saved, error: `Could not confirm cancellation. ${error.message}` };
    }
    redraw(entityId);
  }
  function candidateById(id) {
    const saved = state.entities.get(contactEntityId());
    return (saved?.contacts || saved?.candidates || []).find((candidate) => candidate.id === id);
  }
  async function reviewContactCandidate(id, action) {
    const entityId = contactEntityId();
    const candidate = candidateById(id);
    if (!candidate || !['confirm', 'ignore', 'pending'].includes(action)) return;
    const generation = state.generation;
    const saved = await ctx.actions.api(`${endpoint(entityId)}/${encodeURIComponent(id)}/review`, {
      method: 'POST',
      body: { action, expected_revision: candidate.revision },
      timeoutMs: 15000,
    });
    if (generation !== state.generation) return;
    const previous = state.entities.get(entityId);
    const priorJob = previous?.active_job;
    if (!saved.active_job && active(priorJob)) saved.active_job = priorJob;
    saved.last_job = previous?.last_job;
    state.entities.set(entityId, saved);
    redraw(entityId);
  }
  async function useContactCandidate(id) {
    const candidate = candidateById(id);
    if (
      !candidate ||
      candidate.unusable ||
      candidate.fax ||
      candidate.decision === 'ignored' ||
      candidate.purpose === 'physical_emergency'
    )
      return;
    const entityView = (ctx.state.navigation.currentRoute || '').startsWith('entity/');
    const form = ctx.actions.$(entityView ? '#entity-contact-form' : '#case-plan');
    if (!form?.elements) {
      await copyContactValue(id);
      return;
    }
    if (!entityView && ctx.state.editor.currentLead?.case?.stage === 'closed') return;
    const mainField = { email: 'contact_email', phone: 'contact_phone', person: 'contact_name' }[
      candidate.kind
    ];
    if (!mainField) return;
    const values = { [mainField]: candidate.value };
    if (candidate.name) values.contact_name = candidate.name;
    if (candidate.role) values[entityView ? 'contact_title' : 'contact_role'] = candidate.role;
    let filled = 0;
    let firstFilled = null;
    for (const [name, value] of Object.entries(values)) {
      const input = form.elements.namedItem(name);
      if (!input || input.value.trim()) continue;
      input.value = value;
      firstFilled ||= input;
      if (typeof Event !== 'undefined' && input.dispatchEvent)
        input.dispatchEvent(new Event('input', { bubbles: true }));
      filled++;
    }
    if (filled) {
      const disclosure = form.closest?.('details');
      if (disclosure) disclosure.open = true;
      firstFilled?.focus?.({ preventScroll: true });
      firstFilled?.scrollIntoView?.({ block: 'nearest', behavior: 'auto' });
      if (entityView && ctx.state.entities) ctx.state.entities.dirty = true;
      else {
        ctx.state.workflow.workflowDirty = true;
        ctx.state.workflow.changedCaseForms.add(form.id || 'case-plan');
      }
    }
    ctx.actions.toast(
      filled ? 'Blank contact fields filled.' : 'Contact fields already contain values.',
    );
  }
  async function copyContactValue(id) {
    const candidate = candidateById(id);
    if (!candidate) return;
    const value = candidate.value || candidate.name || '';
    try {
      await navigator.clipboard.writeText(value);
      ctx.actions.toast('Contact copied.');
    } catch {
      ctx.actions.modal(
        'Contact',
        `<textarea class="contact-copy" rows="3" readonly aria-label="Contact">${esc(value)}</textarea>`,
      );
    }
  }
  async function copyContactProvenance(id) {
    const candidate = candidateById(id);
    if (!candidate?.provenance_text) return;
    try {
      await navigator.clipboard.writeText(candidate.provenance_text);
      ctx.actions.toast('Source explanation copied.');
    } catch {
      ctx.actions.modal(
        'Contact source explanation',
        `<p>Copy this retained explanation with its source references.</p><textarea class="contact-copy" rows="9" readonly aria-label="Contact source explanation">${esc(candidate.provenance_text)}</textarea>`,
      );
    }
  }
  function openContactRouteDecision(id, action) {
    const candidate = candidateById(id);
    if (!candidate || !['prefer', 'unusable', 'restore'].includes(action)) return;
    const title = {
      prefer: 'Choose preferred business contact',
      unusable: 'Mark contact route unusable',
      restore: 'Review contact usability',
    }[action];
    state.routeDecision = {
      id,
      action,
      entityId: contactEntityId(),
      revision: candidate.revision,
    };
    ctx.actions.modal(
      title,
      `<p>${esc(candidate.value)} · ${esc(candidate.purpose || 'General contact')}</p><p class="section-note">This records a new decision and preserves the original publication, review and contact history. No-answer and voicemail alone do not mean a route is unusable.</p><form id="contact-route-decision"><div class="field"><label for="contact-route-reason">Reason</label><textarea id="contact-route-reason" name="reason" rows="3" maxlength="2000" required>${action === 'prefer' ? 'Preferred route for business notification' : ''}</textarea></div><button class="button primary" type="submit">Save decision</button></form>`,
    );
    ctx.actions.$('#contact-route-reason')?.focus?.();
  }
  async function saveContactRouteDecision(values) {
    const pending = state.routeDecision;
    if (!pending) return;
    const saved = await ctx.actions.api(
      `${endpoint(pending.entityId)}/${encodeURIComponent(pending.id)}/route`,
      {
        method: 'POST',
        body: {
          action: pending.action,
          reason: values.reason,
          expected_revision: pending.revision,
        },
        timeoutMs: 15000,
      },
    );
    const previous = state.entities.get(pending.entityId);
    if (!saved.active_job && active(previous?.active_job)) saved.active_job = previous.active_job;
    saved.last_job = previous?.last_job;
    state.entities.set(pending.entityId, saved);
    state.routeDecision = null;
    ctx.actions.closeModal();
    redraw(pending.entityId);
    ctx.actions.toast('Contact route decision recorded.');
  }
  Object.assign(ctx.actions, {
    contactEntityId,
    contactDiscoveryMarkup,
    contactBatchMarkup,
    clearContactSelection,
    loadContactDiscovery,
    startContactDiscovery,
    inspectContactSource: () => startContactDiscovery(true, true),
    startContactBatch,
    resumeContactBatch,
    cancelContactDiscovery,
    reviewContactCandidate,
    useContactCandidate,
    copyContactProvenance,
    copyContactValue,
    pollContactDiscovery,
    stopContactDiscoveryPolling,
    openContactRouteDecision,
    saveContactRouteDecision,
    contactBatchSelectionChanged: () => redraw(null),
  });
  installOutreachPreparation(ctx);
}
