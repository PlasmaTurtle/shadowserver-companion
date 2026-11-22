/** Offline publisher-cited guidance, drawn from the same bank as case selection. */
export function createReviewedGuides(ctx) {
  const esc = (value) => ctx.actions.esc(value ?? '');
  function guide(row, selected) {
    const paragraphs = (rows = []) =>
      rows.map(([title, body]) => `<dt>${esc(title)}</dt><dd>${esc(body)}</dd>`).join('');
    const sources = row.sources
      .map((source) =>
        /^https?:\/\//i.test(source.public_url)
          ? `<li><a href="${esc(source.public_url)}" target="_blank" rel="noopener noreferrer">${esc(source.title)}</a> · ${esc(source.publisher)}</li>`
          : `<li>${esc(source.title)}</li>`,
      )
      .join('');
    const rules = (row.match_rules || [])
      .map((rule) => {
        const tags = [
          ...(rule.tags || []),
          ...(rule.tag_prefixes || []).map((prefix) => prefix + '*'),
        ];
        return `<li>${esc(rule.report_types.join(', '))} · ${esc(tags.join(', '))}${Object.entries(
          rule.fields || {},
        )
          .map(([field, value]) => ' · ' + esc(field + '=' + value))
          .join(
            '',
          )}${rule.exclude_tags?.length ? ' · Excludes ' + esc(rule.exclude_tags.join(', ')) : ''}</li>`;
      })
      .join('');
    return `<details class="catalog-sources" data-guide-id="${esc(row.id)}" ${selected === row.id ? 'open' : ''}><summary>${esc(row.title)}</summary>
      <p>${esc(row.intro || row.body)}</p>
      ${row.examples?.length ? `<h5>${esc(row.examples_heading)}</h5><dl>${paragraphs(row.examples)}</dl>` : ''}
      ${row.why ? `<h5>${esc(row.why_heading)}</h5><p>${esc(row.why)}</p>` : ''}
      ${row.routes?.length ? `<h5>Organizational context</h5><dl>${paragraphs(row.routes)}</dl>` : ''}
      ${row.limitations ? `<h5>What the evidence establishes</h5><p>${esc(row.limitations)}</p>` : ''}
      ${row.review ? `<h5>Supporting evidence</h5><p>${esc(row.review)}</p>` : ''}
      ${rules ? `<h5>Report and finding criteria</h5><ul>${rules}</ul>` : ''}
      <h5>Sources</h5><ul>${sources}</ul>
      ${row.revision ? `<small>Wording revision · ${esc(row.revision)}</small>` : ''}</details>`;
  }
  async function load() {
    const region = ctx.actions.$('#library-reviewed-guides');
    if (!region) return;
    const selected = region.dataset.guide;
    try {
      const { items } = await ctx.actions.api('/api/library/guides');
      if (ctx.actions.$('#library-reviewed-guides') !== region) return;
      const headings = {
        finding: 'Finding guides',
        report: 'Report family guides',
        context: 'Report context',
      };
      region.innerHTML =
        '<h2>Reviewed explainers</h2>' +
        Object.entries(headings)
          .map(([kind, title]) => {
            const group = items.filter((row) => row.kind === kind);
            return `<details class="catalog-sources" ${group.some((row) => row.id === selected) ? 'open' : ''}><summary>${title} · ${group.length}</summary>${group.map((row) => guide(row, selected)).join('')}</details>`;
          })
          .join('');
      if (selected) {
        const target = [...region.querySelectorAll('[data-guide-id]')].find(
          (el) => el.dataset.guideId === selected,
        );
        if (target) target.scrollIntoView({ block: 'nearest' });
        else
          region.insertAdjacentHTML(
            'beforeend',
            '<p role="status">This guide is unavailable in this version.</p>',
          );
      }
    } catch (error) {
      if (error.name !== 'AbortError' && ctx.actions.$('#library-reviewed-guides') === region)
        region.innerHTML = `<h2>Reviewed explainers</h2><p role="status">${esc(error.message)}</p><button class="button" data-action="library-retry-guides">Retry guides</button>`;
    } finally {
      if (ctx.actions.$('#library-reviewed-guides') === region) region.removeAttribute('aria-busy');
    }
  }
  return load;
}
