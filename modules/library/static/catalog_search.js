/** Submit-only local research search. Each reference type retains its own destination. */
export function createCatalogSearch(ctx) {
  let request = 0;
  const esc = (value) => ctx.actions.esc(value ?? '');
  const markup = () =>
    `<section class="catalog-research"><form id="library-search-form" class="catalog-product-search"><div class="field"><label for="library-search-query">Search Library</label><input id="library-search-query" name="query" type="search" maxlength="200" placeholder="CVE, product or explanation" required></div><button class="button" type="submit">Search references</button></form><div id="library-search-results" aria-live="polite"></div></section>`;

  function groupMarkup(name, group = {}) {
    const title = { cves: 'CVEs', products: 'Products', explainers: 'Explainers' }[name];
    const items = Array.isArray(group.items) ? group.items : [];
    return `<section class="catalog-search-group"><h3>${title} · ${ctx.actions.num(group.total || 0)}</h3>${group.error ? `<p class="catalog-error" role="status">${esc(group.error)}</p>` : ''}<ul>${items
      .map((item) => {
        const params = new URLSearchParams();
        let label, detail;
        if (name === 'cves') {
          params.set('view', 'cves');
          params.set('q', item.id);
          params.set('severity', '');
          params.set('cve', item.id);
          label = item.id;
          detail = [item.severity, item.description].filter(Boolean).join(' · ');
        } else if (name === 'products') {
          params.set('view', 'products');
          params.set('scope', 'all');
          params.set('product', item.id);
          label = [item.vendor, item.product].filter(Boolean).join(' · ');
          detail = 'Product reference; applicability requires review.';
        } else {
          params.set('item', item.id);
          label = item.title;
          detail = 'Explainer revision ' + (item.revision || 1);
        }
        return `<li><a href="${esc('#library?' + params)}">${esc(label)}</a><p>${esc(detail)}</p></li>`;
      })
      .join(
        '',
      )}</ul>${!items.length && !group.error ? '<p class="muted">No matching references.</p>' : ''}${Number(group.total) > items.length ? `<p class="catalog-basis">Showing ${items.length} of ${ctx.actions.num(group.total)} matches. Refine your search for more specific results.</p>` : ''}</section>`;
  }

  async function search(query = '') {
    const region = ctx.actions.$('#library-search-results');
    if (!region) return;
    const token = ++request;
    query = String(query).trim().slice(0, 200);
    if (!query) {
      region.innerHTML = '';
      return;
    }
    region.setAttribute('aria-busy', 'true');
    region.innerHTML = '<p role="status">Searching local references…</p>';
    try {
      const result = await ctx.actions.api(
        '/api/library/search?' + new URLSearchParams({ q: query, limit: 10 }),
      );
      if (token !== request || ctx.actions.$('#library-search-results') !== region) return;
      region.innerHTML = ['cves', 'products', 'explainers']
        .map((name) => groupMarkup(name, result.groups?.[name]))
        .join('');
    } catch (error) {
      if (
        error.name !== 'AbortError' &&
        token === request &&
        ctx.actions.$('#library-search-results') === region
      )
        region.innerHTML = `<p class="catalog-error" role="status">${esc(error.message)}</p>`;
    } finally {
      if (token === request) region.removeAttribute('aria-busy');
    }
  }
  return { markup, search };
}
