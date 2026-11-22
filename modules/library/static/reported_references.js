/** Count distinct workspace observations using Observatory's retained projection. */
export function createReportedView(ctx) {
  let request = 0;
  const esc = (value) => ctx.actions.esc(value ?? '');
  const num = (value) => ctx.actions.num(value);
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
          .map(({ value, count }) => {
            const query =
              key === 'cves'
                ? { view: 'cves', q: value, severity: '', cve: value }
                : { view: 'products', scope: 'all', product_query: value };
            return `<tr><td><a href="${esc('#library?' + new URLSearchParams(query))}">${esc(value)}</a></td><td>${num(count)}</td></tr>`;
          })
          .join('');
        const button = (label, next, disabled) =>
          `<button class="button" data-action="library-reported-page" data-cve-offset="${key === 'cves' ? next : cveOffset}" data-product-offset="${key === 'products' ? next : productOffset}" ${disabled ? 'disabled' : ''}>${label}</button>`;
        return `<section><h4>${title}</h4><p>${num(group.observations_with_value)} observations with a reported value.</p>${rows ? `<table class="catalog-data-table"><thead><tr><th>${key === 'cves' ? 'CVE' : 'Product or service'}</th><th>Observations</th></tr></thead><tbody>${rows}</tbody></table>` : '<p>No values on this page.</p>'}
          ${group.total > group.limit || group.offset ? `<nav class="catalog-pagination" aria-label="${title}">${button('Previous', Math.max(0, group.offset - group.limit), group.offset === 0)}${button('Next', group.offset + group.limit, group.offset + group.limit >= group.total)}</nav>` : ''}</section>`;
      }
      region.innerHTML = `<h3>Most reported in this workspace</h3><p>Each distinct observation counts once per value. Repeated observations of the same endpoint can each count.</p><p>${num(result.observation_count)} retained observations in scope.</p>
        ${restarted ? '<p role="status">The observation ranking changed. Showing the first page of the updated counts.</p>' : ''}
        ${!result.coverage_complete ? '<p role="status">Coverage is partial. Counts apply to the available observations.</p>' : ''}
        ${(result.warnings || []).map((warning) => `<p>${esc(warning)}</p>`).join('')}
        ${ranking('cves', 'Most reported CVEs')}${ranking('products', 'Most reported products and services')}`;
    } catch (error) {
      if (
        token === request &&
        error.name !== 'AbortError' &&
        ctx.actions.$('#catalog-reported-panel') === region
      )
        region.innerHTML = `<h3>Most reported in this workspace</h3><p class="catalog-error" role="status">${esc(error.message)}</p><button class="button" data-action="library-reported-page">Retry counts</button>`;
    } finally {
      if (token === request) region.removeAttribute('aria-busy');
    }
  }
  return load;
}
