/** Complete source-record browser. Storage and field semantics belong to Accretion. */
export function createDarkMatterBrowser(ctx, { onChange = () => {} } = {}) {
  const selection = { query: '', field: '', operator: 'eq', value: '', source: 'normalized' };
  let result = null,
    catalog = null,
    error = '',
    request = 0;
  const esc = (value) => ctx.actions.esc(value ?? '');
  const valueText = (value) =>
    value === undefined
      ? 'Missing'
      : value === null
        ? 'Null'
        : typeof value === 'object'
          ? JSON.stringify(value)
          : String(value);
  const panel = () => ctx.actions.$('#catalog-dark-matter-panel');
  const operators = [
    ['eq', 'equals'],
    ['ne', 'does not equal'],
    ['contains', 'contains'],
    ['gt', 'greater than'],
    ['gte', 'at least'],
    ['lt', 'less than'],
    ['lte', 'at most'],
    ['exists', 'is present'],
    ['missing', 'is missing'],
    ['invalid', 'is malformed'],
  ];

  function select(values = {}) {
    for (const key of Object.keys(selection)) {
      if (values[key] !== undefined)
        selection[key] = String(values[key]).slice(0, key === 'value' ? 2000 : 200);
    }
    if (!operators.some(([key]) => key === selection.operator)) selection.operator = 'eq';
    if (!['raw', 'normalized'].includes(selection.source)) selection.source = 'normalized';
  }

  function predicates() {
    if (!selection.field) return [];
    const predicate = { field: selection.field, op: selection.operator, source: selection.source };
    if (!['exists', 'missing', 'invalid'].includes(selection.operator)) {
      const type = catalog?.fields?.find((item) => item.name === selection.field)?.type;
      let value = selection.value;
      if (
        selection.source !== 'raw' &&
        ['integer', 'number', 'float', 'port', 'asn'].includes(type) &&
        value.trim() !== '' &&
        Number.isFinite(Number(value))
      )
        value = Number(value);
      if (selection.source !== 'raw' && type === 'boolean' && ['true', 'false'].includes(value))
        value = value === 'true';
      predicate.value = value;
    }
    return [predicate];
  }

  function fieldRows(record) {
    const raw = record.raw_fields || {},
      normalized = record.normalized_fields || {},
      errors = record.errors || {};
    return Object.keys(raw)
      .sort()
      .map(
        (name) =>
          `<tr><th scope="row">${esc(name)}</th><td>${esc(valueText(raw[name]))}</td><td>${esc(valueText(normalized[name]))}${errors[name] ? `<small>${esc(valueText(errors[name]))}</small>` : ''}</td></tr>`,
      )
      .join('');
  }

  function render() {
    const items = result?.items || [],
      total = Number(result?.total) || 0,
      offset = Number(result?.offset) || 0,
      limit = Number(result?.limit) || 25;
    const names = [
      ...new Set([
        'stage',
        'outcome',
        'reason',
        'report_type',
        'import_id',
        ...(catalog?.fields || []).map((field) => field.name),
      ]),
    ];
    const active = selection.query || selection.field;
    return `<div class="catalog-subheading"><div><span class="dm-overline">Source archive</span><h3>Dark Matter</h3><p>Complete report rows and their funnel outcomes, including malformed and out-of-scope evidence.</p></div><a class="text-link" href="#eclipse?intake=dark_matter">Explore in Observatory</a></div>
<form id="catalog-dark-matter-form" class="catalog-product-search">
<div class="field"><label for="catalog-dark-matter-query">Search source values</label><input id="catalog-dark-matter-query" type="search" name="query" maxlength="200" value="${esc(selection.query)}"></div>
<div class="field"><label for="dark-matter-field">Field</label><input id="dark-matter-field" name="field" list="dark-matter-field-catalog" value="${esc(selection.field)}" placeholder="Any report field"><datalist id="dark-matter-field-catalog">${names.map((name) => `<option value="${esc(name)}"></option>`).join('')}</datalist></div>
<div class="field"><label for="dark-matter-operator">Comparison</label><select id="dark-matter-operator" name="operator">${operators.map(([name, label]) => `<option value="${name}"${name === selection.operator ? ' selected' : ''}>${label}</option>`).join('')}</select></div>
<div class="field"><label for="dark-matter-value">Value</label><input id="dark-matter-value" name="value" value="${esc(selection.value)}" maxlength="2000" placeholder="Unused for present, missing or malformed"></div>
<div class="field"><label for="dark-matter-source">Values</label><select id="dark-matter-source" name="source"><option value="normalized"${selection.source === 'normalized' ? ' selected' : ''}>Normalized</option><option value="raw"${selection.source === 'raw' ? ' selected' : ''}>Original</option></select></div>
<button class="button" type="submit">Filter records</button>${active ? '<button class="button" type="button" data-action="catalog-dark-matter-clear">Clear filters</button>' : ''}</form>
${error ? `<p class="catalog-error" role="alert">${esc(error)}</p>` : ''}<p class="catalog-basis">${total.toLocaleString()} matching source records. Each source row is retained once; later decisions remain linked to it.</p>
<div class="catalog-table-wrap"><table class="catalog-data-table"><thead><tr><th>Endpoint</th><th>Finding / report</th><th>Funnel outcome</th><th>Source / fields</th></tr></thead><tbody>${
      items
        .map((record) => {
          const raw = record.raw_fields || {},
            source = record.source || {};
          return `<tr data-record-id="${esc(record.record_id)}"><td><strong>${esc(record.hostname || raw.hostname || 'Hostname missing')}</strong><small>${esc(record.ip || raw.ip || 'IP missing')}</small><small>${esc(raw.region || '')}</small></td><td>${esc(raw.tag || 'Finding not supplied')}<small>${esc(record.report_type)}</small></td><td><strong>${esc(record.stage)} · ${esc(record.outcome)}</strong><small>${esc(record.reason)}</small></td><td>${record.import_id ? `<a href="/api/imports/${encodeURIComponent(record.import_id)}/original">${esc(source.name || 'Original report')}</a>` : esc(source.name || 'Source')}<small>${esc(source.sheet || 'Source')} · row ${esc(source.row)}</small></td></tr><tr><td colspan="4"><details><summary>All ${Object.keys(raw).length} source fields</summary><table class="catalog-data-table"><thead><tr><th>Field</th><th>Original value</th><th>Normalized value</th></tr></thead><tbody>${fieldRows(record)}</tbody></table></details></td></tr>`;
        })
        .join('') ||
      `<tr><td colspan="4">${active ? 'No observations match these filters.' : 'No observations match this view.'}</td></tr>`
    }</tbody></table></div>
${total > limit ? `<nav class="catalog-pagination" aria-label="Source records"><button class="button" data-action="catalog-dark-matter-page" data-offset="${Math.max(0, offset - limit)}" ${offset ? '' : 'disabled'}>Previous</button><span>${offset + 1}–${Math.min(total, offset + limit)} of ${total}</span><button class="button" data-action="catalog-dark-matter-page" data-offset="${offset + limit}" ${offset + limit < total ? '' : 'disabled'}>Next</button></nav>` : ''}`;
  }

  async function load(values, offset = 0) {
    select(values);
    const token = ++request,
      region = panel();
    result = null;
    error = '';
    region?.setAttribute('aria-busy', 'true');
    try {
      if (!catalog) catalog = await ctx.actions.api('/api/dark-matter/fields');
      if (token !== request) return;
      const data = await ctx.actions.api(
        '/api/dark-matter?' +
          new URLSearchParams({
            q: selection.query,
            filters: JSON.stringify(predicates()),
            limit: 25,
            offset,
          }),
      );
      if (token === request) result = data;
    } catch (failure) {
      if (token === request) error = failure.message || 'Dark Matter is unavailable.';
    } finally {
      if (token === request) {
        if (region && panel() === region) {
          region.innerHTML = render();
          region.removeAttribute('aria-busy');
        }
        onChange();
      }
    }
  }
  return {
    render,
    load,
    select,
    selection,
    clear: () => load({ query: '', field: '', operator: 'eq', value: '', source: 'normalized' }),
  };
}
