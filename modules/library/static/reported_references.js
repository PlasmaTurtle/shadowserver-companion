/** Show each reported value and the workspace entities counted for it. */
export function createReportedView(ctx) {
  let request = 0;
  const esc = (value) => ctx.actions.esc(value ?? '');
  const num = (value) => ctx.actions.num(value);
  const pageButton = (id, label, next) =>
    `<button class="button small" data-action="library-reported-entities" aria-controls="${esc(id)}" data-offset="${next}">${label}</button>`;
  function names(id, value, result) {
    return `<ul aria-label="${esc('Entities for ' + value)}">${result.items.map((item) => `<li><a href="#entity/${encodeURIComponent(item.id)}">${esc(item.name)}</a></li>`).join('')}</ul>
      ${result.offset ? pageButton(id, 'Previous entities', Math.max(0, result.offset - result.limit)) : ''}
      ${result.offset + result.limit < result.total ? pageButton(id, 'More entities', result.offset + result.limit) : ''}`;
  }
  function recordMembership(value, result) {
    if (!result) return '<p>Workspace entity count unavailable.</p>';
    const id = 'catalog-record-entities';
    const count = num(result.total) + (result.total === 1 ? ' entity' : ' entities');
    const coverage = result.coverage_complete
      ? ''
      : `<p>Coverage is partial. ${(result.warnings || []).map(esc).join(' ')}</p>`;
    if (!result.total) return '<p>' + count + '</p>' + coverage;
    return `<details id="${id}" class="catalog-sources" data-kind="cves" data-value="${esc(value)}" data-revision="${esc(result.revision)}"><summary>${count}</summary><div>${names(id, value, result)}</div></details>${coverage}`;
  }
  async function load(cveOffset = 0, productOffset = 0, restarted = false) {
    const region = ctx.actions.$('#catalog-reported-panel');
    if (!region) return;
    const token = ++request;
    const params = new URLSearchParams({
      limit: 10,
      cve_offset: cveOffset,
      product_offset: productOffset,
    });
    region.setAttribute('aria-busy', 'true');
    try {
      const result = await ctx.actions.api('/api/library/observed-references?' + params);
      if (token !== request || ctx.actions.$('#catalog-reported-panel') !== region) return;
      if (
        (cveOffset || productOffset) &&
        region.dataset.revision &&
        region.dataset.revision !== result.revision
      )
        return load(0, 0, true);
      region.dataset.revision = result.revision;
      function ranking(key, title) {
        const group = result[key];
        const rows = group.items
          .map(({ value, entity_count }, index) => {
            const query =
              key === 'cves'
                ? { view: 'cves', q: value, severity: '', cve: value }
                : { view: 'products', scope: 'all', product_query: value };
            const id = 'reported-entities-' + key + '-' + index;
            return `<tr><td><a href="${esc('#library?' + new URLSearchParams(query))}">${esc(value)}</a></td><td><button class="button small" data-action="library-reported-entities" aria-expanded="false" aria-controls="${id}" aria-label="${esc('Show ' + num(entity_count) + ' entities for ' + value)}">${num(entity_count)}</button></td></tr>
              <tr id="${id}" data-kind="${key}" data-value="${esc(value)}" hidden><td colspan="2"></td></tr>`;
          })
          .join('');
        const button = (label, next, disabled) =>
          `<button class="button" data-action="library-reported-page" data-cve-offset="${key === 'cves' ? next : cveOffset}" data-product-offset="${key === 'products' ? next : productOffset}" ${disabled ? 'disabled' : ''}>${label}</button>`;
        return `<section><h4>${title}</h4>${rows ? `<table class="catalog-data-table"><thead><tr><th scope="col">${key === 'cves' ? 'CVE' : 'Product or service'}</th><th scope="col">Entities</th></tr></thead><tbody>${rows}</tbody></table>` : '<p>No matching entities on this page.</p>'}
          ${group.total > group.limit || group.offset ? `<nav class="catalog-pagination" aria-label="${title}">${button('Previous', Math.max(0, group.offset - group.limit), group.offset === 0)}${button('Next', group.offset + group.limit, group.offset + group.limit >= group.total)}</nav>` : ''}</section>`;
      }
      region.innerHTML = `<h3>Ranked by entity count</h3><p>Each identified workspace entity counts once per CVE or product, across all its systems and reports. Select a count to see the entities.</p>
        ${restarted ? '<p role="status">The ranking changed. Showing the first page of the updated counts.</p>' : ''}
        ${!result.coverage_complete ? '<p role="status">Coverage is partial.</p>' : ''}
        ${(result.warnings || []).map((warning) => `<p>${esc(warning)}</p>`).join('')}
        ${ranking('cves', 'CVEs')}${ranking('products', 'Products and services')}`;
    } catch (error) {
      if (
        token === request &&
        error.name !== 'AbortError' &&
        ctx.actions.$('#catalog-reported-panel') === region
      )
        region.innerHTML = `<h3>Ranked by entity count</h3><p class="catalog-error" role="status">${esc(error.message)}</p><button class="button" data-action="library-reported-page">Retry counts</button>`;
    } finally {
      if (token === request) region.removeAttribute('aria-busy');
    }
  }
  async function showEntities(button) {
    const id = button.getAttribute('aria-controls');
    const row = ctx.actions.$('#' + id);
    if (!row) return;
    const record = row.tagName === 'DETAILS';
    const panel = record ? row.lastElementChild : row.cells[0];
    const token = (Number(row.dataset.request) || 0) + 1;
    row.dataset.request = String(token);
    const trigger = record ? null : row.previousElementSibling.querySelector('[aria-expanded]');
    if (button === trigger && !row.hidden) {
      row.hidden = true;
      trigger.setAttribute('aria-expanded', 'false');
      return;
    }
    trigger?.setAttribute('aria-expanded', 'true');
    row.hidden = false;
    const offset = Number(button.dataset.offset) || 0;
    const params = new URLSearchParams({
      kind: row.dataset.kind,
      value: row.dataset.value,
      offset,
      limit: 25,
    });
    const current = () => row.isConnected && !row.hidden && row.dataset.request === String(token);
    panel.innerHTML = '<p role="status">Loading entities…</p>';
    try {
      const result = await ctx.actions.api('/api/library/observed-references/entities?' + params);
      if (!current()) return;
      const revision = record
        ? row.dataset.revision
        : ctx.actions.$('#catalog-reported-panel')?.dataset.revision;
      if (result.revision !== revision) {
        if (record) await ctx.actions.selectCatalogRecord(row.dataset.value);
        else await load(0, 0, true);
        return;
      }
      panel.innerHTML = names(id, row.dataset.value, result);
    } catch (error) {
      if (current() && error.name !== 'AbortError')
        panel.innerHTML = `<p role="status">${esc(error.message)}</p>${pageButton(id, 'Retry entities', offset)}`;
    }
  }
  return { load, showEntities, recordMembership };
}
