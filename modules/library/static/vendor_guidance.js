/** Read retained supplier guidance; only the explicit refresh action contacts the publisher. */
export function createVendorGuidance(ctx) {
  const esc = (value) => ctx.actions.esc(value ?? '');
  const valid = (id) => /^CVE-\d{4}-\d{4,}$/.test(id);
  const shell = (id) =>
    valid(id)
      ? `<section id="catalog-vendor-guidance" data-cve="${esc(id)}" aria-label="Vendor guidance"><h4>Red Hat’s assessment</h4><p role="status">Reading the saved vendor record…</p></section>`
      : '';
  let request = 0;
  async function load(refresh = false, offset = 0) {
    const region = ctx.actions.$('#catalog-vendor-guidance');
    if (!region || !valid(region.dataset.cve)) return;
    const id = region.dataset.cve,
      token = ++request;
    const path = '/api/library/vendor-statements/redhat/' + encodeURIComponent(id);
    region.setAttribute('aria-busy', 'true');
    if (refresh)
      region.innerHTML = '<h4>Red Hat’s assessment</h4><p role="status">Checking Red Hat…</p>';
    try {
      const result = await ctx.actions.api(
        refresh ? path + '/refresh' : path + '?offset=' + offset,
        refresh ? { method: 'POST' } : {},
      );
      if (token !== request || ctx.actions.$('#catalog-vendor-guidance') !== region) return;
      const available = result.status === 'available';
      const message = result.error || result.last_attempt?.error;
      const button = (label, page) =>
        `<button class="button" data-action="library-vendor-page" data-offset="${page}">${label}</button>`;
      region.innerHTML = `<h4>Red Hat’s assessment · ${esc(id)}</h4>
        ${
          available
            ? `<p>Retrieved ${esc(result.retrieved_at)}${result.stale ? ' · Update due' : ''}</p>
          ${result.publisher_statement ? `<h5>Red Hat’s statement</h5><blockquote class="library-copy">${esc(result.publisher_statement)}</blockquote>` : '<p>Red Hat supplied no separate written statement in this record.</p>'}
          ${result.total ? `<details class="catalog-sources" ${offset ? 'open' : ''}><summary>Products and packages covered · ${ctx.actions.num(result.total)}</summary><ul>${result.statements.map((row) => `<li><strong>${esc(row.product)}</strong> · ${esc(row.status)}${row.package ? ' · ' + esc(row.package) : ''}${row.advisory ? ' · ' + esc(row.advisory) : ''}${row.release_date ? ' · ' + esc(row.release_date) : ''}${row.cpe ? `<small>${esc(row.cpe)}</small>` : ''}</li>`).join('')}</ul>${offset ? button('Previous products', Math.max(0, offset - result.limit)) : ''}${offset + result.limit < result.total ? button('More products', offset + result.limit) : ''}</details>` : ''}
          <details class="catalog-sources"><summary>Captured source</summary><dl><dt>Capture revision</dt><dd>${esc(result.revision_id)}</dd><dt>SHA-256</dt><dd><code>${esc(result.sha256)}</code></dd>${result.published_at ? `<dt>Flaw made public</dt><dd>${esc(result.published_at)}</dd>` : ''}</dl><a href="https://access.redhat.com/hydra/rest/securitydata/cve/${encodeURIComponent(id)}.json" target="_blank" rel="noopener noreferrer">Red Hat source record</a></details>
          <p><a href="https://access.redhat.com/security/cve/${encodeURIComponent(id)}" target="_blank" rel="noopener noreferrer">Red Hat Product Security</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer">CC BY 4.0</a></p>`
            : `<p>${result.status === 'not_retrieved' ? 'Fetch Red Hat’s published assessment to see which of its products it identifies for this CVE.' : 'Red Hat’s assessment is unavailable for this CVE.'}</p>`
        }
        ${message ? `<p class="catalog-error" role="status">${esc(message)}</p>` : ''}
        <button class="button" data-action="library-vendor-refresh">${available ? 'Check Red Hat for updates' : 'Fetch from Red Hat'}</button>`;
    } catch (error) {
      if (
        token === request &&
        error.name !== 'AbortError' &&
        ctx.actions.$('#catalog-vendor-guidance') === region
      )
        region.innerHTML = `<h4>Red Hat’s assessment</h4><p role="status">${esc(error.message)}</p><button class="button" data-action="library-vendor-page">Retry saved guidance</button>`;
    } finally {
      if (token === request) region.removeAttribute('aria-busy');
    }
  }
  return { shell, load };
}
