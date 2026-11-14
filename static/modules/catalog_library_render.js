/** Product and outreach reference views. All published text stays escaped. */
export function createLibraryRender(ctx, state) {
  const esc = (v) => ctx.actions.esc(v ?? '');
  const num = (v) => ctx.actions.num(Number(v) || 0);
  const array = (v) => (Array.isArray(v) ? v : []);
  const stamp = (v) =>
    /^\d{4}-\d{2}-\d{2}$/.test(String(v || ''))
      ? esc(v)
      : v
        ? ctx.actions.stamp(v)
        : 'Not yet synced';
  const scopeName = (v) =>
    ({
      critical: 'Critical',
      critical_kev: 'Critical + KEV',
      kev: 'All KEVs',
      all: 'All severities',
    })[v] || 'Critical';
  const label = (p) => [p?.vendor, p?.product].filter(Boolean).join(' · ') || 'Product';
  const page = (result, action) => {
    const offset = Number(result?.offset) || 0,
      limit = Number(result?.limit) || 25,
      total = Number(result?.total) || 0;
    return total > limit
      ? `<nav class="catalog-pagination" aria-label="${esc(action === 'catalog-products-page' ? 'Products' : 'Records')}"><button class="button" data-action="${action}" data-offset="${Math.max(0, offset - limit)}" ${offset ? '' : 'disabled'}>Previous</button><span>${num(offset + 1)}–${num(Math.min(offset + limit, total))} of ${num(total)}</span><button class="button" data-action="${action}" data-offset="${offset + limit}" ${offset + limit < total ? '' : 'disabled'}>Next</button></nav>`
      : '';
  };
  const unit = (n, plural) =>
    Number(n) === 1
      ? {
          entities: 'entity',
          products: 'product',
          CVEs: 'CVE',
          KEVs: 'KEV',
          observations: 'observation',
          findings: 'finding',
          endpoints: 'endpoint',
        }[plural] || plural
      : plural;
  const count = (n, plural) => `${num(n)} ${unit(n, plural)}`;
  const conditions = (value) => {
    if (typeof value === 'string') return value;
    if (Array.isArray(value))
      return value.map((v) => (typeof v === 'string' ? v : JSON.stringify(v))).join(' · ');
    return value && Object.keys(value).length ? JSON.stringify(value) : '';
  };
  const matchMarkup = (match) => {
    if (!match) return '';
    const value = typeof match === 'string' ? match : match.state;
    const reason = typeof match === 'object' ? match.reason : '';
    return `<span class="catalog-match" data-match="${esc(value)}">${esc(String(value || 'unresolved').replaceAll('_', ' '))}</span>${reason ? `<small>${esc(reason)}</small>` : ''}`;
  };
  const indexNotice = (index) =>
    index && !index.ready
      ? `<p class="catalog-index-note" role="status">Product index ${num(index.indexed)} of ${num(index.total)} CVEs. Results will expand as indexing finishes.</p>`
      : '';
  const error = (message) =>
    message ? `<p class="catalog-error" role="status">${esc(message)}</p>` : '';
  const scopes = () =>
    `<div class="field"><label for="catalog-product-scope">Outreach scope</label><select id="catalog-product-scope" name="scope">${ctx.actions.optionList(
      [
        ['critical', 'Critical'],
        ['critical_kev', 'Critical + KEV'],
        ['kev', 'All KEVs'],
        ['all', 'All severities'],
      ],
      state.scope,
    )}</select></div>`;

  function observedMarkup(observed, { product = false } = {}) {
    if (!observed)
      return '<section class="catalog-observed"><h4>Observed here</h4><p class="muted">Local observations are unavailable.</p></section>';
    const counts = observed.counts || {},
      items = array(observed.items),
      versions = array(observed.versions),
      entities = array(observed.entities);
    const localLink = (url, text) =>
      /^#(?:entity|entities|investigations|leads|workspace)(?:[/?]|$)/.test(String(url || ''))
        ? `<a href="${esc(url)}">${esc(text)}</a>`
        : esc(text);
    return `<section class="catalog-observed"><div class="catalog-subheading"><h4>Observed here</h4><span>${count(counts.findings ?? counts.observations, 'findings')} · ${count(counts.observations, 'observations')} · ${count(counts.entities, 'entities')}</span></div>${product ? '<p class="catalog-basis">Product matches need confirmation against the reported version and configuration. They are separate from CVEs identified in the report.</p>' : ''}${
      items.length
        ? `<div class="catalog-local-counts">${product && ('reported' in counts || 'product_candidates' in counts) ? `<span><strong>${num(counts.reported)}</strong> reported CVE observations</span><span><strong>${num(counts.product_candidates)}</strong> product candidates</span>` : ''}<span><strong>${num(counts.endpoints)}</strong> ${unit(counts.endpoints, 'endpoints')}</span><span><strong>${num(counts.pending_entities)}</strong> ${unit(counts.pending_entities, 'entities')} with pending work</span><span><strong>${num(counts.notified_entities)}</strong> ${unit(counts.notified_entities, 'entities')} notified</span>${counts.dark_matter ? `<span><strong>${num(counts.dark_matter)}</strong> Dark Matter observations</span>` : ''}${counts.unassociated ? `<span><strong>${num(counts.unassociated)}</strong> unassociated observations</span>` : ''}</div>${product && versions.length ? `<div class="catalog-version-chips" aria-label="Reported versions">${versions.map((v) => `<button class="button" data-catalog-observed-version="${esc(v.version || '')}" ${v.version ? '' : 'disabled'}>${esc(v.version || 'Version not reported')} <small>${num(v.count)}</small></button>`).join('')}</div>` : ''}<details class="catalog-sources catalog-observation-details"><summary>Findings · ${num(counts.findings ?? counts.observations)}</summary><div class="catalog-table-wrap"><table class="catalog-data-table"><thead><tr><th>Entity / endpoint</th><th>Reported version</th><th>Finding basis</th><th>Work</th></tr></thead><tbody>${items
            .slice(0, 25)
            .map(
              (item) =>
                `<tr><td>${localLink(item.entity_url, item.entity_name || item.hostname || item.ip || 'Unassociated')}<small>${esc([item.hostname, item.ip].filter(Boolean).join(' · '))}</small></td><td>${esc(item.version || 'Not reported')}<small>${item.observed_day ? stamp(item.observed_day) : ''}</small></td><td>${esc(item.basis || 'Reported observation')}${array(item.matched_cves).length ? `<small>${esc(item.matched_cves.join(', '))}</small>` : ''}</td><td>${item.case_url ? localLink(item.case_url, item.case_stage || item.status || 'Open investigation') : esc(item.status || 'Not started')}${item.dark_matter ? '<small>Dark Matter</small>' : ''}</td></tr>`,
            )
            .join(
              '',
            )}</tbody></table></div>${Number(observed.total) > 25 ? `<p class="catalog-basis">Showing 25 of ${num(observed.total)} findings. Counts include all matches.</p>` : ''}</details>${entities.length ? `<details class="catalog-sources"><summary>Associated entities · ${num(entities.length)}</summary><ul>${entities.map((entity) => `<li><a href="#entity/${encodeURIComponent(entity.id)}">${esc(entity.name || entity.domain || entity.id)}</a> · ${count(entity.observations, 'observations')}</li>`).join('')}</ul></details>` : ''}`
        : '<p class="catalog-empty">No matching observations in the imported reports.</p>'
    }${array(observed.warnings)
      .map((warning) => `<p class="catalog-basis">${esc(warning)}</p>`)
      .join('')}</section>`;
  }

  function productRows() {
    const result = state.products || {},
      items = array(result.items);
    return `<div class="catalog-result-count" role="status">${count(result.total, 'products')} · ${esc(scopeName(state.scope))}</div>${indexNotice(result.index)}<div class="catalog-product-list">${items.map((item) => `<button class="catalog-product-item ${state.productId === item.id ? 'active' : ''}" data-catalog-product="${esc(item.id)}" aria-pressed="${state.productId === item.id}"><span class="catalog-product-vendor">${esc(item.vendor || 'Vendor not specified')}</span><strong>${esc(item.product || item.name || 'Product')}</strong><span class="catalog-product-counts"><span>${count(item.cve_count, 'CVEs')}</span><span>${count(item.critical_count, 'critical')}</span><span class="catalog-kev-count">${count(item.kev_count, 'KEVs')}</span></span><small>${esc(array(item.sources).join(' · '))}</small></button>`).join('') || `<p class="catalog-empty">${ctx.state.resources.catalog.status?.total ? 'No products match this scope. Try another product or scope.' : 'Download the catalog to explore affected products and versions.'}</p>`}</div>${page(result, 'catalog-products-page')}`;
  }

  function productDetail() {
    const detail = state.product;
    if (!detail)
      return `<div class="catalog-product-empty"><span class="dm-overline">Products &amp; versions</span><h3>Explore affected products</h3><p>Select a product to compare affected versions, critical CVEs and known exploitation with your imported reports.</p></div>`;
    const product = detail.product || {},
      items = array(detail.items);
    return `<article class="catalog-product-dossier"><div class="catalog-subheading"><div><span class="dm-overline">${esc(product.vendor || 'Affected product')}</span><h3>${esc(product.product || product.name || 'Product')}</h3></div><span>${esc(array(product.sources).join(' · '))}</span></div><a class="text-link" href="#eclipse?product=${encodeURIComponent(state.productId)}&amp;scope=${encodeURIComponent(state.scope)}">See observed connections</a> <button class="button" data-action="catalog-clear-product">All products</button>${observedMarkup(state.observed, { product: true })}<section class="catalog-applicability"><h4>Affected versions</h4><form id="catalog-version-form" class="catalog-version-form"><div class="field"><label for="catalog-version">Compare a reported version</label><input id="catalog-version" name="version" value="${esc(state.version)}" maxlength="160" placeholder="Version or build as reported"></div><button class="button" type="submit">Compare</button>${state.version ? '<button class="button" type="button" data-action="catalog-version-clear">Clear</button>' : ''}</form><p class="catalog-basis">${state.version ? `Comparing ${esc(state.version)}. ` : ''}A catalog match may still require confirmation of the platform or configuration.</p><div class="catalog-result-count">${count(detail.total, 'CVEs')} · ${esc(scopeName(state.scope))}</div>${indexNotice(detail.index)}<div class="catalog-product-cves">${items.map((item) => `<section class="catalog-product-cve"><div class="catalog-subheading"><button class="catalog-cve-link" data-catalog-cve="${esc(item.id)}">${esc(item.id)}</button><div class="catalog-inline-labels"><span class="catalog-severity" data-severity="${esc(item.severity || 'UNKNOWN')}">${esc(item.severity || 'UNKNOWN')}${Number.isFinite(item.score) ? ` ${item.score.toFixed(1)}` : ''}</span>${item.kev === true || item.kev?.listed ? '<span class="catalog-kev-badge">KEV</span>' : ''}</div></div><p>${esc(item.description || '')}</p>${array(item.versions).length ? `<ul class="catalog-version-ranges">${item.versions.map((v) => `<li><div><strong>${esc(v.range || v.version || 'Version range not specified')}</strong><span>${esc(v.source || '')}${v.status ? ` · ${esc(v.status)}` : ''}</span></div>${matchMarkup(v.match)}${conditions(v.conditions) ? `<small>${esc(conditions(v.conditions))}</small>` : ''}</li>`).join('')}</ul>` : '<p class="catalog-basis">No usable version range is available for this record.</p>'}${item.versions_truncated ? `<p class="catalog-basis">Showing selected ranges from ${num(item.version_count)} source entries. Open the CVE for the complete source record.</p>` : ''}</section>`).join('') || '<p class="catalog-empty">No CVEs match this product and scope.</p>'}</div>${page(detail, 'catalog-product-cves-page')}</section></article>`;
  }

  function productsPanel() {
    return `<form id="catalog-product-form" class="catalog-product-search"><div class="field"><label for="catalog-product-query">Find a product</label><input id="catalog-product-query" name="query" type="search" value="${esc(state.query)}" maxlength="200" placeholder="Exchange, PHP, Apache, Roundcube…"></div>${scopes()}<button class="button" type="submit">Search products</button></form>${error(state.error)}<div class="catalog-product-layout"><section id="catalog-products-results" aria-label="Affected products">${productRows()}</section><section id="catalog-product-detail" aria-label="Selected product">${productDetail()}</section></div>`;
  }

  function fieldsPanel() {
    const data = state.fields || {},
      fields = array(data.available_fields),
      items = array(data.items),
      population = Number(data.population) || 0;
    return `<div class="catalog-field-heading"><div><h3>Field explorer</h3><p>${esc(scopeName(state.scope))}${state.productId && state.product ? ` · ${esc(label(state.product.product))}` : ' · All products'}</p>${state.productId ? '<button class="button" data-action="catalog-clear-product">All products</button>' : ''}</div><form id="catalog-field-form"><div class="field"><label for="catalog-field">Field</label><select id="catalog-field" name="field">${ctx.actions.optionList(fields.length ? fields.map((f) => [f.id, f.label]) : [['weakness', 'Weakness']], state.field)}</select></div><button class="button" type="submit">Explore</button></form></div>${error(state.error)}${indexNotice(data.index)}<div class="catalog-field-coverage"><span><strong>${num(population)}</strong> distinct CVEs</span><span><strong>${num(data.covered)}</strong> with usable values</span><span><strong>${num(data.missing)}</strong> missing or unclassified</span></div><div class="catalog-field-values">${items.map((item) => `<button class="catalog-field-value" data-catalog-field-value="${esc(item.value)}"><span>${esc(item.value || 'Unknown')}</span><span class="catalog-field-bar" aria-hidden="true"><i style="width:${population ? Math.min(100, Math.max(0, (Number(item.count) / population) * 100)) : 0}%"></i></span><strong>${num(item.count)}</strong><small>${population ? ((Number(item.count) / population) * 100).toFixed(1) : '0'}%</small></button>`).join('') || '<p class="catalog-empty">No indexed values in this selection.</p>'}</div><p class="catalog-basis">Each value counts a CVE once. A CVE can have several values, so categories can overlap.</p>`;
  }

  function darkMatterPanel() {
    const result = state.darkMatter || {};
    return `<div class="catalog-subheading"><div><span class="dm-overline">Intake history</span><h3>Dark Matter</h3><p>Retained observations without exact approved findings, including unavailable historical qualification.</p></div><a class="text-link" href="#eclipse?intake=dark_matter">Explore the field</a></div><form id="catalog-dark-matter-form" class="catalog-product-search"><div class="field"><label for="catalog-dark-matter-query">Find an observation</label><input id="catalog-dark-matter-query" type="search" name="query" maxlength="200" value="${esc(state.darkMatterQuery)}" placeholder="Domain, IP, finding or city"></div><button class="button" type="submit">Search</button>${state.darkMatterQuery ? '<button class="button" type="button" data-action="catalog-dark-matter-clear">Clear search</button>' : ''}</form>${error(state.error)}<div class="catalog-field-coverage"><span><strong>${num(result.total)}</strong> matching source observations</span><span><strong>${num(result.counts?.dark_matter)}</strong> known observed-only</span><span><strong>${num(result.counts?.lead)}</strong> with exact approved findings</span>${result.counts?.qualification_unknown ? `<span><strong>${num(result.counts.qualification_unknown)}</strong> qualification unavailable</span>` : ''}</div><p class="catalog-basis">Each physical observation counts once. Historical ownership is retained separately from the current asset association. Unavailable qualification is neither approval nor rejection.</p>${array(result.reasons).length ? `<details class="catalog-sources"><summary>Qualification context</summary><ul>${result.reasons.map((item) => `<li>${esc(item.label)} · ${num(item.total)}</li>`).join('')}</ul></details>` : ''}<div class="catalog-table-wrap"><table class="catalog-data-table"><thead><tr><th>Endpoint / entity</th><th>Finding</th><th>Intake decision</th><th>Source</th></tr></thead><tbody>${
      array(result.items)
        .map(
          (item) =>
            `<tr><td><strong>${esc(item.hostname)}</strong><small>${esc(item.ip)}</small>${item.entity_id ? `<a href="#entity/${encodeURIComponent(item.entity_id)}">${esc(item.entity_name || item.root_domain)}</a><small>Recorded business association</small>` : ''}</td><td>${esc(item.tag)}<small>${esc(item.version || 'Version not reported')}</small>${array(item.clipped_fields).length ? '<small>Summary shortened; original retains complete fields.</small>' : ''}</td><td><span class="catalog-match">${item.disposition === 'qualification_unknown' ? 'Qualification unavailable' : 'Dark Matter'}</span>${item.known_aggregate_admitted ? '<small>Earlier qualification is recorded; exact condition approval is unavailable.</small>' : ''}<small>${esc(item.reason_label)}</small><small>${esc([item.city, item.region].filter(Boolean).join(', '))}</small></td><td><a href="/api/imports/${encodeURIComponent(item.import_id)}/original">${esc(item.import_name)}</a><small>${esc(item.sheet || 'Source')} · row ${num(item.row)}</small><small>${esc(item.observed_at || 'Undated')}</small></td></tr>`,
        )
        .join('') ||
      `<tr><td colspan="4">${state.darkMatterQuery ? 'No observations match this search.' : 'No observations match this view.'}</td></tr>`
    }</tbody></table></div>${page(result, 'catalog-dark-matter-page')}`;
  }

  function changesPanel() {
    const result = state.changes || {};
    const value = (v) =>
      v === null || v === undefined || v === ''
        ? 'Not supplied'
        : typeof v === 'string'
          ? v
          : JSON.stringify(v);
    return `<div class="catalog-subheading"><div><h3>Catalog changes</h3><p>Only changes recorded during catalog updates appear here.</p></div><button class="button" data-action="catalog-refresh-changes">Refresh</button></div>${error(state.error)}<div class="catalog-changes">${
      array(result.items)
        .map(
          (item) =>
            `<article class="catalog-change"><div class="catalog-subheading"><button class="catalog-cve-link" data-catalog-cve="${esc(item.cve_id)}">${esc(item.cve_id)}</button><time>${stamp(item.changed_at)}</time></div><dl>${array(
              item.fields,
            )
              .map(
                (field) =>
                  `<div><dt>${esc(String(field.field || '').replaceAll('_', ' '))}</dt><dd><span class="catalog-change-before">${esc(value(field.before))}</span><span class="catalog-change-after">${esc(value(field.after))}</span></dd></div>`,
              )
              .join('')}</dl></article>`,
        )
        .join('') ||
      '<p class="catalog-empty">No material changes have been recorded. Changes appear here when catalog updates are applied.</p>'
    }</div>${page(result, 'catalog-changes-page')}`;
  }

  return {
    productsPanel,
    productRows,
    productDetail,
    fieldsPanel,
    changesPanel,
    darkMatterPanel,
    observedMarkup,
  };
}
