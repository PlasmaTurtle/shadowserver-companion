/** Observatory navigation: persistent preferences, explicit scopes, reversible descent. */
export const VIEW_NAMES = ['field', 'atlas', 'pulse', 'records'];
export const SCOPE_KEYS = [
  'search',
  'cve',
  'condition',
  'product',
  'productName',
  'locationKey',
  'version',
  'entity',
  'asset',
  'ip',
  'service',
  'city',
  'region',
  'country',
  'network',
  'intelligence',
  'status',
  'intake',
  'unplaced',
  'cutoff',
];
const scopeQueryKeys = {
  q: 'search',
  cve: 'cve',
  condition: 'condition',
  product_id: 'product',
  product_name: 'productName',
  location_key: 'locationKey',
  version: 'version',
  entity_id: 'entity',
  asset_id: 'asset',
  ip: 'ip',
  service: 'service',
  city: 'city',
  region: 'region',
  country: 'country',
  network: 'network',
  intelligence: 'intelligence',
  status: 'status',
  intake: 'intake',
  unplaced: 'unplaced',
  date_to: 'cutoff',
};
const blankScope = () =>
  Object.fromEntries(
    SCOPE_KEYS.map((k) => [k, k === 'intelligence' ? 'all' : k === 'unplaced' ? false : '']),
  );
export function initialState(saved = {}, params = new URLSearchParams(), snapshot = {}) {
  if (!saved || typeof saved !== 'object' || Array.isArray(saved)) saved = {};
  if (!snapshot || typeof snapshot !== 'object') snapshot = {};
  const explicit = [...params.keys()].some((k) => k !== 'view');
  const scope = blankScope();
  if (!explicit) for (const k of SCOPE_KEYS) if (saved[k] !== undefined) scope[k] = saved[k];
  const urlKeys = {
    search: 'search',
    q: 'search',
    cve: 'cve',
    condition: 'condition',
    product: 'product',
    product_name: 'productName',
    location_key: 'locationKey',
    version: 'version',
    entity: 'entity',
    asset: 'asset',
    ip: 'ip',
    service: 'service',
    city: 'city',
    region: 'region',
    country: 'country',
    network: 'network',
    scope: 'intelligence',
    status: 'status',
    intake: 'intake',
    date_to: 'cutoff',
  };
  for (const [query, key] of Object.entries(urlKeys))
    if (params.has(query)) scope[key] = params.get(query) || '';
  if (params.has('unplaced')) scope.unplaced = params.get('unplaced') === 'true';
  if (!scope.product) scope.product = snapshot.catalog_selection?.product_id || '';
  if (!['all', 'critical', 'critical_kev', 'kev', 'ransomware'].includes(scope.intelligence))
    scope.intelligence = 'all';
  if (!['', 'lead', 'dark_matter', 'unclassified'].includes(scope.intake)) scope.intake = '';
  scope.unplaced = scope.unplaced === true;
  for (const key of SCOPE_KEYS)
    if (key !== 'unplaced')
      scope[key] =
        typeof scope[key] === 'string'
          ? scope[key].slice(0, 300)
          : key === 'intelligence'
            ? 'all'
            : '';
  if (scope.cutoff && !/^\d{4}-\d{2}-\d{2}$/.test(scope.cutoff)) scope.cutoff = '';
  return {
    ...scope,
    view: VIEW_NAMES.includes(params.get('view'))
      ? params.get('view')
      : VIEW_NAMES.includes(saved.defaultView)
        ? saved.defaultView
        : 'field',
    defaultView: VIEW_NAMES.includes(saved.defaultView) ? saved.defaultView : 'field',
    lens: ['organization', 'ip', 'service', 'vulnerability', 'version'].includes(saved.lens)
      ? saved.lens
      : 'organization',
    recordsMode: 'findings',
    day: 0,
    page: 0,
    selected: null,
    graphFocus: '',
    listOpen: false,
    inspectorOpen: false,
  };
}
export function selectionScope(node = {}, rows = []) {
  const source = node.scope || {};
  const scope = {};
  for (const [query, key] of Object.entries(scopeQueryKeys))
    if (source[query] !== undefined && source[query] !== '') scope[key] = source[query];
  if (Object.keys(scope).length) return scope;
  const row = rows[0];
  if (node.entity_id || (node.type === 'entity' && node.id?.startsWith('entity:')))
    scope.entity = node.entity_id || node.id.slice(7);
  else if (node.asset_id || node.type === 'asset') {
    if (node.asset_id || row?.asset_id) scope.asset = node.asset_id || row.asset_id;
  } else if (node.type === 'cve' && /^CVE-\d{4}-\d{4,}$/i.test(node.label || ''))
    scope.cve = node.label.toUpperCase();
  else if (node.type === 'ip' && node.label) scope.ip = node.label;
  else if (node.type === 'location' || node.type === 'cluster') {
    const cities = new Set(rows.map((r) => r.city).filter(Boolean)),
      regions = new Set(rows.map((r) => r.region).filter(Boolean));
    if (cities.size === 1 && regions.size === 1) {
      scope.city = [...cities][0];
      scope.region = [...regions][0];
    }
  }
  return scope;
}
export function drillOptions(node, rows = []) {
  const scope = selectionScope(node, rows);
  if (!Object.keys(scope).length) return [];
  return [
    { id: 'locations', label: 'Locations', view: 'atlas' },
    { id: 'products', label: 'Products', view: 'records', recordsMode: 'products' },
    { id: 'organizations', label: 'Organizations', view: 'field', lens: 'organization' },
    { id: 'assets', label: 'Assets & findings', view: 'records' },
    { id: 'history', label: 'History', view: 'pulse' },
  ];
}
export function scopeLabels(state, entities = [], catalog = null) {
  const labels = [];
  if (state.search) labels.push('Search: ' + state.search);
  if (state.cve) labels.push(state.cve);
  if (state.condition)
    labels.push(
      'Finding: ' + state.condition.replace(/^eol[-:]/i, 'End of life · ').replace(/:/g, ' · '),
    );
  if (state.product) labels.push('Product: ' + (catalog?.label || state.product));
  if (state.productName) labels.push('Product: ' + state.productName);
  if (state.version) labels.push('Version: ' + state.version);
  if (state.locationKey && !state.city && !state.region) labels.push('Selected location');
  if (state.entity) {
    const entity = entities.find((e) => e.id === state.entity);
    labels.push('Organization: ' + (entity?.name || entity?.domain || state.entity));
  }
  if (state.asset) labels.push('Selected asset');
  if (state.ip) labels.push('IP: ' + state.ip);
  if (state.service) labels.push('Service: ' + state.service);
  if (state.city || state.region || state.country)
    labels.push([state.city, state.region, state.country].filter(Boolean).join(', '));
  if (state.network)
    labels.push(state.network === '__unknown' ? 'No reported ASN' : 'AS' + state.network);
  if (state.intelligence !== 'all')
    labels.push(
      {
        critical: 'Critical',
        critical_kev: 'Critical + KEV',
        kev: 'KEV',
        ransomware: 'Ransomware',
      }[state.intelligence],
    );
  if (state.status) labels.push('Status: ' + state.status);
  if (state.intake)
    labels.push(
      { lead: 'Admitted', dark_matter: 'Dark matter', unclassified: 'Unclassified' }[state.intake],
    );
  if (state.unplaced) labels.push('Unplaced');
  if (state.cutoff) labels.push('Through ' + state.cutoff);
  return labels;
}
export function queryFor(state, pageSize = 20) {
  const params = new URLSearchParams({
    lens: state.lens,
    max_nodes: '180',
    max_edges: '300',
    include_undated: 'true',
    limit: String(pageSize),
    offset: String(state.page * pageSize),
  });
  const cve =
    state.cve ||
    (/^CVE-\d{4}-\d{4,}$/i.test(state.search.trim()) ? state.search.trim().toUpperCase() : '');
  const values = {
    ...Object.fromEntries(
      Object.entries(scopeQueryKeys).map(([query, key]) => [query, state[key]]),
    ),
    q: cve ? '' : state.search,
    cve,
    focus: state.graphFocus,
    unplaced: state.unplaced ? 'true' : '',
  };
  for (const [key, value] of Object.entries(values))
    if (value !== '' && value !== false && value != null) params.set(key, String(value));
  return params;
}
export function scopedURL(state) {
  const params = new URLSearchParams();
  const keys = {
    search: 'q',
    cve: 'cve',
    condition: 'condition',
    product: 'product',
    productName: 'product_name',
    locationKey: 'location_key',
    version: 'version',
    entity: 'entity',
    asset: 'asset',
    ip: 'ip',
    service: 'service',
    city: 'city',
    region: 'region',
    country: 'country',
    network: 'network',
    intelligence: 'scope',
    status: 'status',
    intake: 'intake',
    cutoff: 'date_to',
  };
  for (const [key, name] of Object.entries(keys))
    if (state[key] && !(key === 'intelligence' && state[key] === 'all'))
      params.set(name, state[key]);
  if (state.unplaced) params.set('unplaced', 'true');
  return '#eclipse' + (params.size ? '?' + params : '');
}
export function persistentState(state) {
  return {
    ...Object.fromEntries(SCOPE_KEYS.map((k) => [k, state[k]])),
    defaultView: state.defaultView,
    lens: state.lens,
  };
}
