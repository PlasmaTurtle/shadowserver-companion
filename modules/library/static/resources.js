import { createReviewedGuides } from './reviewed_guides.js';

/** Reference explainer editing owned by Library. No startup requests or event listeners are installed here. */
export function install(ctx) {
  const loadReviewedGuides = createReviewedGuides(ctx);
  async function resourcesPage(params = new URLSearchParams()) {
    if (params.get('item')) ctx.state.resources.resourceId = params.get('item');
    return (
      ctx.actions.heading(
        'Library',
        '',
        `<button id="library-new-explainer" class="button primary" data-action="new-block" disabled>${ctx.actions.icon('plus')}New explainer</button>`,
      ) +
      (await ctx.actions.catalogSection(params, { defer: true })) +
      `<section id="library-reviewed-guides" data-guide="${ctx.actions.esc(params.get('guide') || '')}" aria-busy="true"><h2>Reviewed explainers</h2><p role="status">Loading guides…</p></section>` +
      `<section id="library-explainers" aria-busy="true"><h2 class="catalog-explainers-heading">Explainers</h2><p role="status">Loading explanations…</p></section>`
    );
  }

  async function loadLibraryExplainers() {
    const region = ctx.actions.$('#library-explainers');
    if (!region) return;
    region.setAttribute('aria-busy', 'true');
    try {
      const resources = await ctx.actions.api('/api/explainers?include_archived=true');
      if (ctx.actions.$('#library-explainers') !== region) return;
      ctx.state.resources.resources = resources;
      ctx.state.navigation.boot.explainers = resources.filter((item) => !item.archived_at);
      if (!resources.some((item) => item.id === ctx.state.resources.resourceId))
        ctx.state.resources.resourceId =
          resources.find((item) => !item.archived_at)?.id || resources[0]?.id;
      region.innerHTML = ctx.actions.resourceList();
      const button = ctx.actions.$('#library-new-explainer');
      if (button) button.disabled = false;
    } catch (error) {
      if (error.name !== 'AbortError' && ctx.actions.$('#library-explainers') === region)
        region.innerHTML = `<h2 class="catalog-explainers-heading">Explainers</h2><p class="catalog-error" role="status">${ctx.actions.esc(error.message)}</p><button class="button" data-action="library-retry-explainers">Retry explanations</button>`;
    } finally {
      if (ctx.actions.$('#library-explainers') === region) region.removeAttribute('aria-busy');
    }
  }

  async function mountLibraryPage() {
    await Promise.allSettled([
      ctx.actions.mountCatalog(),
      loadLibraryExplainers(),
      loadReviewedGuides(),
    ]);
  }

  function resourceCitationFields(sources, metadata = []) {
    const details = new Map(metadata.map((item) => [item.url, item]));
    const urls = [
      ...new Set(
        String(sources || '')
          .split('\n')
          .map((x) => x.trim())
          .filter(Boolean),
      ),
    ];
    return (
      urls
        .map((url, index) => {
          const row = details.get(url) || {};
          return `<fieldset class="form-grid" data-citation-row data-citation-url="${ctx.actions.esc(url)}"><legend>${ctx.actions.esc(url)}</legend>${[
            ['publisher', 'Publisher'],
            ['title', 'Source title'],
            ['retrieved_at', 'Retrieval date'],
            ['date_published', 'Published date'],
            ['date_updated', 'Updated date'],
          ]
            .map(
              ([key, label]) =>
                `<div class="field ${key === 'title' ? 'full' : ''}"><label for="citation-${index}-${key}">${label}</label><input id="citation-${index}-${key}" data-citation-key="${key}" value="${ctx.actions.esc(row[key] || '')}" ${key.includes('date') || key === 'retrieved_at' ? 'placeholder="YYYY-MM-DD or ISO timestamp"' : ''}></div>`,
            )
            .join('')}</fieldset>`;
        })
        .join('') || '<p class="section-note">Add source URLs above to record citation details.</p>'
    );
  }

  function readResourceCitations(form) {
    return [...form.querySelectorAll('[data-citation-row]')].map((row) => ({
      url: row.dataset.citationUrl,
      ...Object.fromEntries(
        [...row.querySelectorAll('[data-citation-key]')].map((input) => [
          input.dataset.citationKey,
          input.value.trim(),
        ]),
      ),
    }));
  }

  function resourceOrigin(block) {
    return (
      {
        bundled: 'Bundled starting text',
        bundled_edited: 'Bundled starting text · edited locally',
        analyst: 'Analyst-created',
      }[block.origin] || 'Origin not recorded'
    );
  }

  function resourceForm() {
    const b = ctx.state.resources.resources.find(
      (r) => r.id === ctx.state.resources.resourceId,
    ) || { title: '', body: '', sources: '' };
    const sourceLinks = String(b.sources || '')
      .split('\n')
      .map((url) => url.trim())
      .filter(Boolean)
      .map((url) =>
        /^https?:\/\//i.test(url)
          ? `<li><a href="${ctx.actions.esc(url)}" target="_blank" rel="noopener noreferrer">${ctx.actions.esc(url)}</a></li>`
          : `<li>${ctx.actions.esc(url)}</li>`,
      )
      .join('');
    const actions = b.id
      ? `<div class="actions"><button class="button" data-action="resource-history">Revision history</button><button class="button" data-action="resource-usage">Used by</button><button class="button" data-action="resource-archive" data-archived="${b.archived_at ? 'false' : 'true'}">${b.archived_at ? 'Make active' : 'Archive explainer'}</button></div>`
      : '';
    const editor = b.archived_at
      ? '<p class="notice">Archived explanations are unavailable for new selections. Existing cases and reports keep their copies. Make this explanation active to edit it.</p>'
      : `<details class="dm-library-edit" ${b.id ? '' : 'open'}><summary>${b.id ? 'Edit explanation' : 'New explanation'}</summary><p class="section-note">Certified reports retain their original wording.</p><form id="resource-form" class="form-grid" data-block-id="${ctx.actions.esc(b.id || '')}" data-expected-revision="${b.revision || ''}">${ctx.actions.field('Title', 'title', b.title, { full: true, draft: false, required: true })}${ctx.actions.field('Explanation', 'body', b.body, { area: true, rows: 10, full: true, draft: false })}${ctx.actions.field('Sources · one URL per line', 'sources', b.sources, { area: true, rows: 4, full: true, draft: false })}<details class="full"><summary>Source citations · publisher, title and dates</summary><p class="section-note">Record dates from the source and your actual retrieval. Leave unavailable details blank. Adding or changing a URL updates these fields when you leave the URL box.</p><div id="resource-citations">${ctx.actions.resourceCitationFields(b.sources, b.source_metadata || [])}</div></details><div id="resource-status" class="full" role="status"></div><div class="full"><button class="button primary" type="submit">${ctx.actions.icon('save')}Save explainer</button></div></form></details>`;
    return `${b.id ? `<article class="dm-library-sheet"><span class="dm-overline">${resourceOrigin(b)} · Revision ${ctx.actions.num(b.revision)}${b.archived_at ? ' · Archived' : ''}</span><h2>${ctx.actions.esc(b.title)}</h2><div class="library-copy">${ctx.actions.esc(b.body)}</div>${sourceLinks ? `<footer><span class="dm-overline">Sources</span><ol>${sourceLinks}</ol></footer>` : ''}</article>` : ''}${actions}${editor}<div id="resource-lifecycle-status" role="status"></div><section id="resource-history"></section><section id="resource-comparison"></section><section id="resource-usage"></section>`;
  }

  function resourceList() {
    const items = [...ctx.state.resources.resources].sort(
      (a, b) => Number(Boolean(a.archived_at)) - Number(Boolean(b.archived_at)),
    );
    return `<h2 class="catalog-explainers-heading">Explainers</h2><div class="resource-layout"><section class="panel resource-list">${items.map((b) => `<button class="resource-item ${b.id === ctx.state.resources.resourceId ? 'active' : ''}" data-resource="${ctx.actions.esc(b.id)}">${ctx.actions.icon('book')}<span><strong>${ctx.actions.esc(b.title)}</strong><small>${resourceOrigin(b)} · Revision ${ctx.actions.num(b.revision)}${b.archived_at ? ' · Archived' : ''}</small></span>${ctx.actions.icon('arrow')}</button>`).join('') || '<p>No explanations yet.</p>'}</section><section id="resource-editor">${resourceForm()}</section></div>`;
  }

  function rememberResource(saved) {
    const rows = ctx.state.resources.resources;
    const index = rows.findIndex((item) => item.id === saved.id);
    if (index >= 0) rows[index] = saved;
    else rows.push(saved);
    ctx.state.navigation.boot.explainers = rows.filter((item) => !item.archived_at);
  }

  function renderResourceList() {
    const region = ctx.actions.$('#library-explainers');
    if (region) region.innerHTML = resourceList();
  }

  function revisionContent(block, label) {
    return `<article class="panel"><h4>${ctx.actions.esc(label)}</h4><h5>${ctx.actions.esc(block.title)}</h5><div class="library-copy">${ctx.actions.esc(block.body)}</div><h5>Sources and citations</h5><div class="library-copy">${ctx.actions.esc(block.sources || 'No sources')}</div>${(
      block.source_metadata || []
    )
      .map(
        (item) =>
          `<dl>${Object.entries(item)
            .filter(([, value]) => value)
            .map(
              ([key, value]) =>
                `<dt>${ctx.actions.esc(key.replaceAll('_', ' '))}</dt><dd>${ctx.actions.esc(value)}</dd>`,
            )
            .join('')}</dl>`,
      )
      .join('')}</article>`;
  }

  function showResourceConflict(form, error) {
    if (error.status !== 409 || !error.detail?.current) return false;
    if (ctx.actions.$('#resource-form') !== form) return true;
    form.dataset.dirty = 'true';
    form.resourceConflict = error.detail.current;
    const status = ctx.actions.$('#resource-status');
    if (status)
      status.innerHTML = `<p class="notice warn">${ctx.actions.esc(error.message)}</p>${revisionContent(error.detail.current, `Current saved revision ${error.detail.current.revision}`)}${error.detail.current.archived_at ? '<p>This explanation was archived. Copy your draft before making it active again.</p>' : '<button type="button" class="button" data-action="resource-rebase">Keep my draft and edit from this revision</button>'}`;
    return true;
  }

  function rebaseResourceDraft() {
    const form = ctx.actions.$('#resource-form');
    const current = form?.resourceConflict;
    if (!current || current.archived_at) return;
    // Explicit analyst choice after comparison; never automatically overwrite a conflict.
    form.dataset.expectedRevision = String(current.revision);
    form.resourceConflict = null;
    const status = ctx.actions.$('#resource-status');
    if (status)
      status.textContent = `Your draft is unchanged. Review it, then save a new revision after revision ${current.revision}.`;
  }

  async function resourceHistory(before) {
    const id = ctx.state.resources.resourceId;
    const region = ctx.actions.$('#resource-history');
    if (!id || !region) return;
    region.innerHTML = '<p role="status">Loading revision history…</p>';
    try {
      const result = await ctx.actions.api(
        `/api/explainers/${encodeURIComponent(id)}/history${before ? '?before=' + Number(before) : ''}`,
      );
      if (ctx.actions.$('#resource-history') !== region || ctx.state.resources.resourceId !== id)
        return;
      region.innerHTML = `<h3>Revision history</h3>${result.earliest_revision > 1 ? `<p>Retained history starts at revision ${ctx.actions.num(result.earliest_revision)}. Earlier Library wording was not retained by older versions; existing case/report copies are unchanged.</p>` : ''}<ul>${result.items.map((row) => `<li>Revision ${ctx.actions.num(row.revision)} · ${ctx.actions.esc(row.action.replaceAll('_', ' '))} · ${ctx.actions.esc(row.updated_at)}${row.actor ? ' · ' + ctx.actions.esc(row.actor) : ''}<div class="actions"><button class="button small" data-action="resource-compare" data-revision="${row.revision}">Inspect and compare</button><button class="button small" data-action="resource-restore" data-revision="${row.revision}">Restore as new revision</button></div></li>`).join('')}</ul>${result.next_before ? `<button class="button" data-action="resource-history" data-before="${result.next_before}">Older revisions</button>` : ''}${before ? '<button class="button" data-action="resource-history">Newest revisions</button>' : ''}`;
    } catch (error) {
      if (ctx.actions.$('#resource-history') === region)
        region.innerHTML = `<p role="status">${ctx.actions.esc(error.message)}</p>`;
    }
  }

  async function compareResource(revision) {
    const id = ctx.state.resources.resourceId;
    const region = ctx.actions.$('#resource-comparison');
    if (!id || !region) return;
    region.innerHTML = '<p role="status">Loading comparison…</p>';
    try {
      const base = `/api/explainers/${encodeURIComponent(id)}`;
      const [old, current] = await Promise.all([
        ctx.actions.api(`${base}/revisions/${Number(revision)}`),
        ctx.actions.api(base),
      ]);
      if (ctx.actions.$('#resource-comparison') !== region || ctx.state.resources.resourceId !== id)
        return;
      const changed = ['title', 'body', 'sources', 'source_metadata'].filter(
        (key) => JSON.stringify(old[key] || []) !== JSON.stringify(current[key] || []),
      );
      region.innerHTML = `<h3>Revision comparison</h3><p>${changed.length ? 'Changed: ' + ctx.actions.esc(changed.map((key) => key.replaceAll('_', ' ')).join(', ')) : 'Wording and citations are identical.'}</p><div class="resource-comparison">${revisionContent(old, `Revision ${old.revision}`)}${revisionContent(current, `Current revision ${current.revision}`)}</div>`;
    } catch (error) {
      if (ctx.actions.$('#resource-comparison') === region)
        region.innerHTML = `<p role="status">${ctx.actions.esc(error.message)}</p>`;
    }
  }

  async function resourceUsage(offset = 0) {
    const id = ctx.state.resources.resourceId;
    const region = ctx.actions.$('#resource-usage');
    if (!id || !region) return;
    region.innerHTML = '<p role="status">Loading usage…</p>';
    try {
      const result = await ctx.actions.api(
        `/api/explainers/${encodeURIComponent(id)}/usage?offset=${Number(offset)}`,
      );
      if (ctx.actions.$('#resource-usage') !== region || ctx.state.resources.resourceId !== id)
        return;
      region.innerHTML = `<h3>Used by · ${ctx.actions.num(result.total)} case selections</h3><p>${ctx.actions.esc(result.scope)}</p><ul>${result.items.map((row) => `<li><a href="#workspace/notifications/${encodeURIComponent(row.id)}">${ctx.actions.esc(row.title || row.id)}</a> · ${ctx.actions.esc(row.stage.replaceAll('_', ' '))} · ${row.explainer_revision ? 'explainer revision ' + ctx.actions.num(row.explainer_revision) : 'legacy unpinned selection'}${row.has_case_wording ? ' · case-specific wording' : ''}</li>`).join('') || '<li>No current case selects this explanation.</li>'}</ul>${offset > 0 ? `<button class="button" data-action="resource-usage" data-offset="${Math.max(0, offset - result.limit)}">Previous</button>` : ''}${offset + result.items.length < result.total ? `<button class="button" data-action="resource-usage" data-offset="${offset + result.limit}">Next</button>` : ''}`;
    } catch (error) {
      if (ctx.actions.$('#resource-usage') === region)
        region.innerHTML = `<p role="status">${ctx.actions.esc(error.message)}</p>`;
    }
  }

  async function resourceLifecycle(operation, revision) {
    if (hasUnsavedLibrary() && !confirm('Continue without saving your current changes?')) return;
    const id = ctx.state.resources.resourceId;
    const current = ctx.state.resources.resources.find((item) => item.id === id);
    if (!current) return;
    if (
      operation === 'restore' &&
      !confirm(
        `Restore revision ${revision} as a new active revision? Existing cases and reports keep their saved wording.`,
      )
    )
      return;
    const editor = ctx.actions.$('#resource-editor');
    const form = ctx.actions.$('#resource-form');
    const editRevision = form?.dataset.editRevision;
    const body = { expected_revision: current.revision };
    if (operation !== 'restore') body.archived = operation === 'archive';
    try {
      const saved = await ctx.actions.api(
        `/api/explainers/${encodeURIComponent(id)}/${operation === 'restore' ? 'restore/' + Number(revision) : 'archive'}`,
        { method: 'POST', body },
      );
      rememberResource(saved);
      if (ctx.actions.$('#resource-editor') !== editor || ctx.state.resources.resourceId !== id)
        return;
      if (form && form.dataset.editRevision !== editRevision) {
        form.dataset.expectedRevision = String(saved.revision);
        ctx.actions.toast('The Library revision changed. Your newer edits remain unsaved.');
        return;
      }
      if (form) form.dataset.dirty = 'false';
      renderResourceList();
      ctx.actions.toast('Explainer revision saved. Existing case and report wording is unchanged.');
    } catch (error) {
      if (form && showResourceConflict(form, error)) return;
      const status = ctx.actions.$('#resource-lifecycle-status');
      if (status && ctx.actions.$('#resource-editor') === editor)
        status.innerHTML = `<p>${ctx.actions.esc(error.message)}</p><button class="button" data-action="resource-reload">Reload saved explanation</button>`;
      else throw error;
    }
  }

  function hasUnsavedLibrary() {
    return ctx.actions.$('#resource-form')?.dataset.dirty === 'true';
  }
  const actions = {
    resourcesPage,
    mountLibraryPage,
    loadLibraryExplainers,
    loadReviewedGuides,
    resourceCitationFields,
    readResourceCitations,
    resourceForm,
    resourceList,
    rememberResource,
    renderResourceList,
    showResourceConflict,
    rebaseResourceDraft,
    resourceHistory,
    compareResource,
    resourceUsage,
    resourceLifecycle,
    hasUnsavedLibrary,
  };
  Object.assign(ctx.actions, actions);
  return actions;
}
