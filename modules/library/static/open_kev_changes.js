/** Compare retained open work automatically when the Changes view is displayed. */
export function createOpenKevChanges(ctx) {
  let request = 0;
  const esc = (value) => ctx.actions.esc(value ?? '');
  async function load(offset = 0) {
    const region = ctx.actions.$('#library-open-kev');
    if (!region) return;
    const token = ++request;
    region.setAttribute('aria-busy', 'true');
    try {
      const result = await ctx.actions.api(
        '/api/library/changes/open-kev?' + new URLSearchParams({ offset, limit: 25 }),
      );
      if (token !== request || ctx.actions.$('#library-open-kev') !== region) return;
      const button = (label, page) =>
        `<button class="button" data-action="library-open-kev-page" data-offset="${page}">${label}</button>`;
      region.innerHTML = `<h4>Known-exploitation changes affecting open notifications</h4>
        ${result.notice ? `<p>${esc(result.notice)}</p>` : `<p>${ctx.actions.num(result.total)} differences across ${ctx.actions.num(result.comparable)} comparable case selections. ${result.source?.retrieved_at ? 'Local CISA catalog checked ' + esc(result.source.retrieved_at) + '.' : ''}</p>`}
        ${result.unknown ? `<p>${ctx.actions.num(result.unknown)} selections lack comparable evidence.</p>` : ''}
        ${result.unreadable_cases ? `<p>${ctx.actions.num(result.unreadable_cases)} case drafts could not be read.</p>` : ''}
        <ul>${result.items.map((row) => `<li><a href="#workspace/notifications/${encodeURIComponent(row.case_id)}">${esc(row.case_title)}</a> · ${esc(row.cve_id)} · ${row.listed ? 'Previously absent, now listed' : 'Previously listed, now absent'}${row.pinned_at ? ' · Selection checked ' + esc(row.pinned_at) : ''}</li>`).join('')}</ul>
        ${offset ? button('Previous cases', Math.max(0, offset - result.limit)) : ''}${offset + result.limit < result.total ? button('More cases', offset + result.limit) : ''}`;
    } catch (error) {
      if (
        token === request &&
        error.name !== 'AbortError' &&
        ctx.actions.$('#library-open-kev') === region
      )
        region.innerHTML = `<h4>Known-exploitation changes affecting open notifications</h4><p role="status">${esc(error.message)}</p><button class="button" data-action="library-open-kev-page">Retry comparison</button>`;
    } finally {
      if (token === request) region.removeAttribute('aria-busy');
    }
  }
  return load;
}
