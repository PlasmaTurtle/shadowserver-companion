/** Pure read-model helpers for Eclipse. Spatial layout is never evidence. */
export const LENSES = {
  vulnerability: {
    label: 'Finding',
    plural: 'findings',
    color: '#b5a2ff',
    types: ['cve', 'finding'],
  },
  ip: { label: 'Shared IP', plural: 'IP addresses', color: '#80e5ef', types: ['ip'] },
  organization: {
    label: 'Organization',
    plural: 'organizations',
    color: '#8ce2bf',
    types: ['entity'],
  },
  service: { label: 'Service', plural: 'services', color: '#efc381', types: ['service'] },
  version: { label: 'Version', plural: 'versions', color: '#e4afd4', types: ['version'] },
};
export { escapeHTML as esc, formatCount as num } from '../../ui/static/format.js';
import { hasKnownRansomware as knownRansomware } from '../../library/static/risk.js';
export { knownRansomware };
export const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
export function priorityMark(value) {
  const labels = { cool: 'Cool', warm: 'Warm', hot: 'Hot', blazing: 'Blazing' };
  return Object.hasOwn(labels, value)
    ? `<span class="ec-priority" data-temperature="${value}" title="Internal outreach priority"><i aria-hidden="true"></i>${labels[value]}</span>`
    : '';
}
export function densityBand(value) {
  const count = Math.max(0, Number(value) || 0);
  return count > 1000
    ? { id: 'purple', label: 'Extreme observation density', color: '#b26cff' }
    : count > 200
      ? { id: 'red', label: 'High observation density', color: '#f07891' }
      : count > 50
        ? { id: 'yellow', label: 'Elevated observation density', color: '#eccb6b' }
        : { id: 'normal', label: 'Observation density', color: '#7cffff' };
}
export function findingCount(rows) {
  return new Set(
    rows.flatMap(
      (r) => r.finding_ids || (r.finding_id ? [r.finding_id] : r.asset_id ? [] : [r.id]),
    ),
  ).size;
}
export function densityStats(rows) {
  const events = new Map(rows.map((r) => [r.observation_id || r.id, r]));
  const values = [...events.values()];
  return {
    observation_count: values.length,
    density_count: values.length,
    admitted_density: values.filter(
      (r) =>
        r.admitted === true ||
        (!('admitted' in r) && ['qualified', 'delivered'].includes(r.status)),
    ).length,
    dark_matter_density: values.filter(
      (r) => r.dark_matter === true && r.admission_state !== 'legacy_unknown',
    ).length,
    legacy_unknown_density: values.filter(
      (r) => r.admission_state === 'legacy_unknown' || r.status === 'qualification_unknown',
    ).length,
    day_count: new Set(values.map((r) => r.observed_day).filter(Boolean)).size,
    finding_count: findingCount(values),
    asset_count: new Set(values.map((r) => r.asset_id || endpointKey(r))).size,
    entity_count: unique(values, 'entity_id'),
    risk_changed: values.some((r) => r.risk_changed === true),
  };
}
export function findingRows(rows, representatives = []) {
  const definitions = new Map(representatives.map((r) => [r.finding_id || r.id, r]));
  const records = new Map();
  for (const row of rows) {
    const unadmittedRepeat =
      row.admitted === false &&
      (row.finding_ids || []).some((id) => definitions.get(id)?.admitted === true);
    const ids = unadmittedRepeat
      ? [row.id]
      : row.finding_ids?.length
        ? row.finding_ids
        : [row.finding_id || row.id];
    for (const id of ids) {
      const prior = records.get(id),
        definition = definitions.get(id);
      const observation = row.observation_id || row.id;
      const seen = prior?._events || new Set(),
        days = prior?._days || new Set();
      seen.add(observation);
      if (row.observed_day) days.add(row.observed_day);
      const latest =
        !prior || String(row.observed_at || '') >= String(prior.observed_at || '') ? row : prior;
      records.set(id, {
        ...(definition || {}),
        ...latest,
        // The chosen observation owns endpoint, location and time. Definitions
        // supply condition identity/current workflow, never a newer observation.
        observation_id: latest.observation_id || latest.id,
        id,
        finding_id:
          definition?.finding_id || row.finding_id || (row.finding_ids?.includes(id) ? id : null),
        finding_ids: row.finding_ids?.includes(id) ? [id] : row.finding_ids,
        admitted_finding_ids: definition
          ? definition.admitted
            ? [id]
            : []
          : latest.admitted_finding_ids,
        unadmitted_finding_ids: definition
          ? definition.admitted
            ? []
            : [id]
          : latest.unadmitted_finding_ids,
        tag: definition?.tag || latest.tag,
        catalog_findings: definition?.catalog_findings || latest.catalog_findings,
        kev: definition?.kev ?? latest.kev,
        risk_changed: definition?.risk_changed ?? latest.risk_changed,
        risk_change_reasons: definition?.risk_change_reasons || latest.risk_change_reasons,
        risk_updated_at: definition?.risk_updated_at || latest.risk_updated_at,
        record_kind: definition ? 'finding' : latest.record_kind,
        admitted: unadmittedRepeat ? false : (definition?.admitted ?? latest.admitted),
        dark_matter: unadmittedRepeat
          ? true
          : (definition?.dark_matter ?? (definition ? !definition.admitted : latest.dark_matter)),
        status: definition?.admitted === false ? 'excluded' : definition?.status || latest.status,
        case_id: definition ? definition.case_id : latest.case_id,
        case_ids: definition ? definition.case_ids : latest.case_ids,
        case_stage: definition ? definition.case_stage : latest.case_stage,
        delivered_at: definition ? definition.delivered_at : latest.delivered_at,
        lead_id: definition ? definition.lead_id : latest.lead_id,
        intake_disposition: definition
          ? definition.admitted
            ? 'lead'
            : 'dark_matter'
          : latest.intake_disposition,
        fresh_at: definition?.fresh_at || latest.fresh_at,
        observation_count: seen.size,
        sightings: days.size,
        _events: seen,
        _days: days,
      });
    }
  }
  return [...records.values()].map(({ _events, _days, ...row }) => row);
}
export const point = (row) =>
  Number.isFinite(row.latitude) &&
  Number.isFinite(row.longitude) &&
  Math.abs(row.latitude) <= 90 &&
  Math.abs(row.longitude) <= 180;
export const adverse = (row) =>
  row.kev === true ||
  knownRansomware(row) ||
  ['critical', 'high'].includes(String(row.catalog_severity || row.severity || '').toLowerCase());
export const statusName = (value) =>
  ({
    qualified: 'Qualified',
    delivered: 'Delivered',
    review: 'Attribution review',
    pending: 'Pending',
    excluded: 'Excluded',
    unqualified: 'Unqualified',
    qualification_unknown: 'Legacy qualification unavailable',
  })[value] || 'Unqualified';
export const dayLabel = (value) => (value ? String(value).slice(0, 10) : 'Undated');
export function hash(text) {
  let h = 2166136261;
  for (const c of String(text)) {
    h ^= c.charCodeAt(0);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
export const seeded = (key) => hash(key) / 4294967296;
export const unique = (rows, key) => new Set(rows.map((row) => row[key]).filter(Boolean)).size;
export function cves(row) {
  const values = row.reported_cves || row.cves || row.cve_ids || [];
  const explicit = Array.isArray(values)
    ? values
        .map((value) => (typeof value === 'string' ? value : value.id || value.cve || ''))
        .filter(Boolean)
    : String(values).match(/CVE-\d{4}-\d+/gi) || [];
  return [
    ...new Set(
      [...explicit, ...(String(row.tag || '').match(/CVE-\d{4}-\d{4,}/gi) || [])].map((v) =>
        v.toUpperCase(),
      ),
    ),
  ];
}
export function filterRows(rows, filters) {
  const query = String(filters.search || '')
    .trim()
    .toLowerCase();
  const exactCVE = /^cve-\d{4}-\d{4,}$/.test(query) ? query.toUpperCase() : '';
  const relevantFindings = (row) =>
    (row.catalog_findings || []).filter(
      (item) =>
        (!filters.product || (row.catalog_product_cves || []).includes(item.id)) &&
        (!exactCVE || item.id === exactCVE),
    );
  return rows.filter(
    (row) =>
      (!filters.entity || row.entity_id === filters.entity) &&
      (!filters.product || row.catalog_product_id === filters.product) &&
      (!filters.network ||
        (filters.network === '__unknown'
          ? !row.asn
          : String(row.asn).replace(/^AS/i, '') === filters.network)) &&
      (!filters.status ||
        row.status === filters.status ||
        (filters.status === 'excluded' && row.unadmitted_finding_ids?.length)) &&
      (!filters.intake ||
        (row.intake_disposition || 'unclassified') === filters.intake ||
        (filters.intake === 'dark_matter' && row.unadmitted_finding_ids?.length)) &&
      (!filters.unplaced || !point(row)) &&
      (filters.intelligence === 'kev'
        ? filters.product || exactCVE
          ? relevantFindings(row).some((item) => item.kev === true)
          : row.kev === true
        : filters.intelligence === 'critical'
          ? relevantFindings(row).some((item) => item.severity === 'CRITICAL')
          : filters.intelligence === 'critical_kev'
            ? relevantFindings(row).some(
                (item) => item.severity === 'CRITICAL' && item.kev === true,
              )
            : filters.intelligence === 'ransomware'
              ? filters.product || exactCVE
                ? relevantFindings(row).some(
                    (item) => item.risk?.kev?.entry?.knownRansomwareCampaignUse === 'Known',
                  )
                : knownRansomware(row)
              : true) &&
      (!filters.cutoff || !row.observed_day || row.observed_day <= filters.cutoff) &&
      (!query ||
        (exactCVE
          ? cves(row).includes(exactCVE)
          : [
              row.hostname,
              row.ip,
              row.domain,
              row.entity_name,
              row.tag,
              row.product,
              row.version,
              row.protocol,
              row.port,
              row.city,
              row.region,
              row.asn,
              ...cves(row),
            ].some((value) =>
              String(value || '')
                .toLowerCase()
                .includes(query),
            ))),
  );
}
export function observationKeys(row, lens) {
  if (lens === 'organization')
    return row.entity_id
      ? [{ key: row.entity_id, label: row.entity_name || row.domain || 'Saved entity' }]
      : [];
  if (lens === 'ip')
    return row.ip && row.ip_valid !== false ? [{ key: row.ip, label: row.ip }] : [];
  if (lens === 'service' || lens === 'version') {
    const parts = [
      String(row.protocol || '')
        .trim()
        .toUpperCase(),
      /^\d{1,7}$/.test(String(row.port || ''))
        ? String(Number(row.port))
        : String(row.port || '').trim(),
      String(row.product || row.service || '')
        .trim()
        .toLowerCase(),
    ];
    const label = parts.filter(Boolean).join(' / ');
    if (lens === 'version') {
      if (!row.version || !String(row.product || row.service || '').trim()) return [];
      return [
        {
          key: JSON.stringify([
            label ? parts : ['unknown product', row.hostname, row.ip],
            String(row.version).trim(),
          ]),
          label: (label || row.hostname || row.ip || 'Unknown product') + ' · ' + row.version,
        },
      ];
    }
    return label ? [{ key: JSON.stringify(parts), label }] : [];
  }
  const values = cves(row).map((key) => ({ key, label: key }));
  for (const label of String(row.tag || '')
    .split(/[;,|]/)
    .map((v) => v.trim())
    .filter(Boolean)) {
    if (!/^CVE-\d{4}-\d{4,}$/i.test(label))
      values.push({ key: 'finding:' + label.toLowerCase(), label });
  }
  return values;
}
export function timeline(rows) {
  const bins = new Map();
  let undated = 0;
  for (const row of rows) {
    if (!row.observed_day) {
      undated++;
      continue;
    }
    const bin = bins.get(row.observed_day) || { day: row.observed_day, rows: [], count: 0 };
    bin.rows.push(row);
    bin.count++;
    bins.set(bin.day, bin);
  }
  return { bins: [...bins.values()].sort((a, b) => a.day.localeCompare(b.day)), undated };
}
export function sourceLinks(rows) {
  const links = new Map();
  for (const row of rows) {
    for (const [type, id, label, route] of [
      ['entity', row.entity_id, 'Open entity', '#entity/'],
      ['lead', row.lead_id, 'Open lead', '#leads/'],
      ['case', row.case_id, 'Open notification', '#workspace/notifications/'],
    ]) {
      if (id && !links.has(type + id))
        links.set(type + id, {
          type,
          id,
          label,
          href: route + encodeURIComponent(id),
          name: row.entity_name || row.hostname || row.ip,
        });
    }
  }
  return [...links.values()];
}
/** Visual approach scale only. This never changes density or quantitative map marks. */
export function fieldBodyScale(ratio) {
  const safe = Number.isFinite(ratio) && ratio > 0 ? ratio : 1;
  return clamp(safe ** 0.6, 0.75, 2.6);
}
export function graphLayout(graph, lens, options = {}, legacyHeight = 760) {
  const width = typeof options === 'number' ? options : options.width || 1200,
    height = typeof options === 'number' ? legacyHeight : options.height || 760,
    focused = typeof options === 'object' && options.focused === true;
  // The server owns bounded field pages. A second client-side slice silently
  // drops objects, edges and page totals, so every returned node stays reachable.
  const nodes = (graph?.nodes || []).map((n) => ({
    ...n,
    x: 0,
    y: 0,
    r: n.type === 'asset' && n.field_object !== true ? 6 : 18,
  }));
  const map = new Map(nodes.map((n) => [n.id, n]));
  const links = (graph?.edges || [])
    .filter((e) => map.has(e.source) && map.has(e.target))
    .map((e) => ({ ...e, from: map.get(e.source), to: map.get(e.target) }));
  const neighbors = new Map();
  for (const edge of links) {
    for (const [a, b] of [
      [edge.source, edge.to],
      [edge.target, edge.from],
    ]) {
      if (!neighbors.has(a)) neighbors.set(a, []);
      neighbors.get(a).push(b);
    }
  }
  const stamp = (value) => {
    const parsed = typeof value === 'string' && value ? Date.parse(value) : NaN;
    return Number.isFinite(parsed) ? parsed : -Infinity;
  };
  const dates = new Map(
    nodes.map((n) => {
      const fresh = stamp(n.fresh_at),
        seen = stamp(n.last_seen),
        value = Number.isFinite(fresh) ? fresh : seen;
      n.recency_at = Number.isFinite(fresh) ? n.fresh_at : Number.isFinite(seen) ? n.last_seen : '';
      return [n.id, { value }];
    }),
  );
  const recentFirst = (a, b) =>
    dates.get(b.id).value - dates.get(a.id).value || a.id.localeCompare(b.id);
  // Unresolved endpoints are first-class pageable bodies, not satellites merely
  // because their source type is "asset". The server marks that distinction.
  const isBody = (node) => node.field_object === true || node.type !== 'asset';
  const hubs = nodes.filter(isBody).sort(recentFirst);
  const assets = nodes.filter((node) => !isBody(node)),
    groups = new Map();
  const dated = [...dates.values()].map((d) => d.value).filter(Number.isFinite),
    rangeNew = stamp(graph?.recency_range?.newest),
    rangeOld = stamp(graph?.recency_range?.oldest),
    newest = Number.isFinite(rangeNew) ? rangeNew : Math.max(...dated),
    oldest = Number.isFinite(rangeOld) ? rangeOld : Math.min(...dated);
  for (const node of nodes) {
    const value = dates.get(node.id).value;
    // Depth encodes meaningful recency, never density, severity or entity size.
    // The full filtered index supplies a shared range across field pages.
    node.depth = !Number.isFinite(value)
      ? 0
      : newest > oldest
        ? clamp((value - oldest) / (newest - oldest), 0, 1)
        : 1;
  }
  for (const asset of assets) {
    const parents = (neighbors.get(asset.id) || []).filter(isBody);
    const primary = parents.sort(recentFirst)[0];
    asset.group = primary?.id || 'unlinked';
    if (!groups.has(asset.group)) groups.set(asset.group, []);
    groups.get(asset.group).push(asset);
  }
  // Stable recency/identity ordering keeps density updates from rearranging the
  // field. Newer bodies occupy the near center; older ones extend into the field.
  const golden = Math.PI * (3 - Math.sqrt(5));
  const largestGroup = Math.max(1, ...[...groups.values()].map((group) => group.length));
  const maximumFootprintScale = 1.65;
  const orbitAt = (index) => (focused ? 110 : 74) + Math.sqrt(index) * (focused ? 55 : 30);
  // Reserve the bounded maximum footprint, rather than moving body centers when
  // breadth metadata changes. Matching elliptical coordinates keep adjacent
  // constellations separate even at the largest supported overview footprint.
  const maximumFootprint = orbitAt(largestGroup - 1) * (focused ? 1 : maximumFootprintScale);
  const spacing = Math.max(380, maximumFootprint * 2 + 96);
  let revealRank = 0;
  hubs.forEach((hub, i) => {
    const angle = i * golden - Math.PI / 3;
    const radius = i === 0 ? 0 : spacing * Math.sqrt(i);
    hub.x = width / 2 + Math.cos(angle) * radius;
    hub.y = height / 2 + Math.sin(angle) * radius * 0.72;
    hub.rank = Number.isFinite(hub.field_rank) ? hub.field_rank : i + 1;
    hub.revealRank = revealRank++;
    const group = (groups.get(hub.id) || []).sort(recentFirst);
    const breadth =
      [hub.total_assets, hub.asset_count, group.length]
        .filter((value) => value != null && value !== '')
        .map(Number)
        .find((value) => Number.isFinite(value) && value >= 0) ?? 0;
    hub.footprintScale = focused
      ? 1
      : 1 + clamp(Math.log2(Math.max(1, breadth)) / 12, 0, 1) * (maximumFootprintScale - 1);
    hub.footprintRadius = group.length ? orbitAt(group.length - 1) * hub.footprintScale : 0;
    group.forEach((n, j) => {
      const orbit = orbitAt(j) * hub.footprintScale,
        angle = j * golden - Math.PI / 2;
      n.x = hub.x + Math.cos(angle) * orbit;
      n.y = hub.y + Math.sin(angle) * orbit * (focused ? 0.88 : 0.72);
      n.revealRank = revealRank++;
    });
  });
  const unlinked = groups.get('unlinked') || [];
  const outer = spacing * Math.sqrt(hubs.length + 1);
  unlinked.sort(recentFirst);
  unlinked.forEach((n, i) => {
    const angle = i * golden,
      radius = outer + Math.sqrt(i) * 110;
    n.x = width / 2 + Math.cos(angle) * radius;
    n.y = height / 2 + Math.sin(angle) * radius * 0.72;
    n.revealRank = revealRank++;
  });
  return {
    nodes,
    edges: links,
    neighbors,
    hubs,
    bounds: bounds(nodes, width, height),
    lens,
    hubCount: hubs.length,
    focused,
  };
}
export function endpointKey(row) {
  if (row.asset_id) return row.asset_id;
  const hostname = String(row.hostname || '')
    .trim()
    .toLowerCase()
    .replace(/\.$/, '');
  const ip = row.ip_valid === false ? '' : String(row.ip || '').trim();
  if (!hostname && !ip) return JSON.stringify(['unidentified', row.id]);
  return JSON.stringify([
    hostname,
    ip,
    String(row.protocol || '')
      .trim()
      .toUpperCase(),
    /^\d{1,7}$/.test(String(row.port || ''))
      ? String(Number(row.port))
      : String(row.port || '').trim(),
    String(row.product || row.service || '')
      .trim()
      .toLowerCase(),
  ]);
}
export function attachSources(model, rows) {
  const byId = new Map(rows.map((r) => [r.id, r])),
    byEndpoint = new Map();
  for (const row of rows) {
    const key = endpointKey(row);
    if (!byEndpoint.has(key)) byEndpoint.set(key, []);
    byEndpoint.get(key).push(row);
  }
  for (const node of model.nodes) {
    if (node.type !== 'asset') continue;
    const example = (node.observation_ids || []).map((id) => byId.get(id)).find(Boolean);
    node.rows = node.asset_id
      ? byEndpoint.get(node.asset_id) || []
      : example
        ? byEndpoint.get(endpointKey(example)) || []
        : [];
    node.displayLabel = example?.hostname || example?.ip || node.label;
    node.days =
      node.observed_days ||
      [...new Set(node.rows.map((r) => r.observed_day).filter(Boolean))].sort();
    const temperatures = { cool: 0, warm: 1, hot: 2, blazing: 3 };
    if (!node.temperature)
      node.temperature =
        node.rows
          .map((r) => r.temperature)
          .filter((v) => v in temperatures)
          .sort((a, b) => temperatures[b] - temperatures[a])[0] || '';
  }
  return model;
}
export function bounds(nodes, width = 1000, height = 620) {
  if (!nodes.length) return { minX: 0, minY: 0, maxX: width, maxY: height };
  return {
    minX: Math.min(...nodes.map((n) => n.x)) - 70,
    minY: Math.min(...nodes.map((n) => n.y)) - 60,
    maxX: Math.max(...nodes.map((n) => n.x)) + 70,
    maxY: Math.max(...nodes.map((n) => n.y)) + 60,
  };
}
export function atlasLayout(rows) {
  if (!Array.isArray(rows)) return atlasSummaryLayout(rows);
  const groups = new Map();
  for (const row of rows) {
    const key = row.entity_id
      ? 'entity:' + row.entity_id
      : row.asset_id
        ? 'asset:' + row.asset_id
        : `${row.latitude}|${row.longitude}|${row.location_basis || ''}`;
    let n = groups.get(key);
    if (!n) {
      n = { id: 'location:' + key, type: 'location', rows: [], latest: null };
      groups.set(key, n);
    }
    n.rows.push(row);
    if (
      point(row) &&
      (!n.latest || String(row.observed_at || '') >= String(n.latest.observed_at || ''))
    )
      n.latest = row;
  }
  const placedGroups = [...groups.values()].filter((n) => n.latest);
  const nodes = placedGroups
    .sort((a, b) => b.rows.length - a.rows.length || a.id.localeCompare(b.id))
    .slice(0, 1800)
    .map((n) => {
      const stats = densityStats(n.rows),
        row = n.latest;
      return {
        ...n,
        ...stats,
        ...mercatorPoint(row.longitude, row.latitude),
        label: row.entity_name || row.hostname || row.ip || row.city || 'Reported coordinates',
        approximate: row.location_basis === 'city_area',
        r: 4 + Math.min(10, Math.log2(1 + stats.finding_count) * 2),
        basis:
          'One entity or unresolved asset, positioned at its latest selected reported location. Halo shows distinct observation density; the number shows unique findings.',
      };
    });
  return {
    nodes,
    edges: [],
    bounds: bounds(nodes, 1000, 620),
    unplaced: rows.filter((r) => !point(r)).length,
    omittedLocations: Math.max(0, placedGroups.length - nodes.length),
    polarRows: rows.filter((r) => point(r) && Math.abs(r.latitude) > 85).length,
  };
}
/** Aggregate DTOs carry exact counts; rows are bounded evidence examples only. */
export function atlasSummaryLayout(payload = {}) {
  const nodes = (payload.nodes || []).filter(point).map((n) => ({
    ...n,
    type: n.type || (payload.unit === 'entities' ? 'entity-location' : 'location'),
    rows: n.rows || [],
    summary: true,
    ...mercatorPoint(n.longitude, n.latitude),
    approximate:
      n.approximate ??
      ['city_area', 'entity_city_area', 'reported_asset_city_area'].includes(n.location_basis),
    basis:
      n.basis ||
      (payload.unit === 'entities'
        ? n.location_basis === 'reported_asset_city_area'
          ? 'Approximate city area from the entity’s latest selected IP or hostname report. This is not a verified entity address.'
          : 'Approximate area of the entity’s current saved city and state. This is not an exact business address or historical location.'
        : 'Latest selected reported location for this asset. Counts include its selected supporting observations; geography is not verified ownership.'),
  }));
  return {
    unit: payload.unit || 'locations',
    nodes,
    edges: [],
    bounds: bounds(nodes),
    unplaced: payload.unplaced_entities ?? payload.unplaced_count ?? 0,
    unplacedEntities: payload.unplaced_entities_list || [],
    omittedUnplacedEntities: payload.omitted_unplaced_entities || 0,
    totalEntities: payload.total_entities || 0,
    mappedEntities: payload.mapped_entities || 0,
    unresolvedAssetCount: payload.unresolved_asset_count || 0,
    omittedLocations: payload.omitted_nodes || 0,
    polarRows: (payload.nodes || []).filter((n) => point(n) && Math.abs(n.latitude) > 85).length,
    summary: true,
  };
}
export function pulseSummaryLayout(payload = {}) {
  const lanes = (payload.lanes || []).map((n) => ({ ...n, rows: n.rows || [] }));
  const days = [...new Set(payload.days || lanes.flatMap((n) => (n.bins || []).map((b) => b.day)))]
    .filter(Boolean)
    .sort();
  const start = days.length ? Date.parse(days[0]) : 0,
    end = days.length ? Date.parse(days.at(-1)) : 0,
    span = Math.max(86400000, end - start);
  const nodes = lanes.flatMap((lane, index) =>
    (lane.bins || []).map((bin) => ({
      ...bin,
      id: 'pulse:' + (lane.id || lane.key) + ':' + bin.day,
      type: 'pulse',
      label: lane.label,
      rows: bin.rows || [],
      scope: { ...(lane.scope || {}), date_from: bin.day, date_to: bin.day },
      x: 300 + (days.length === 1 ? 0.5 : (Date.parse(bin.day) - start) / span) * 700,
      y: 105 + index * 62,
      summary: true,
    })),
  );
  return {
    nodes,
    edges: [],
    lanes,
    days,
    start,
    end,
    summary: true,
    bounds: { minX: 0, minY: 0, maxX: 1090, maxY: Math.max(360, lanes.length * 62 + 155) },
    omittedLanes: payload.omitted_lanes || 0,
    undated: payload.undated || 0,
  };
}
export function mercatorPoint(longitude, latitude) {
  // A Pacific seam keeps Alaska's Aleutian islands together without geographic insets.
  const wrappedLongitude = longitude > 100 ? longitude - 360 : longitude;
  return {
    x: (wrappedLongitude + 80.5) * 100,
    y:
      ((-Math.log(Math.tan(Math.PI / 4 + (clamp(latitude, -85, 85) * Math.PI) / 360)) * 180) /
        Math.PI) *
        100 +
      3700,
  };
}
export function geographicStates(geo) {
  return (geo?.states || [])
    .map((state) => {
      const polygons =
        state.geometry?.type === 'Polygon'
          ? [state.geometry.coordinates]
          : state.geometry?.type === 'MultiPolygon'
            ? state.geometry.coordinates
            : [];
      const bounds = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
      for (const polygon of polygons)
        for (const ring of polygon)
          for (const [lon, lat] of ring) {
            const point = mercatorPoint(lon, lat);
            bounds.minX = Math.min(bounds.minX, point.x);
            bounds.maxX = Math.max(bounds.maxX, point.x);
            bounds.minY = Math.min(bounds.minY, point.y);
            bounds.maxY = Math.max(bounds.maxY, point.y);
          }
      return { ...state, bounds };
    })
    .filter((state) => Number.isFinite(state.bounds.minX));
}
export function jurisdictionBounds(states, codes) {
  const selected = states.filter((state) => codes.includes(state.properties?.postal));
  if (!selected.length) return null;
  return selected.reduce(
    (bounds, state) => ({
      minX: Math.min(bounds.minX, state.bounds.minX),
      minY: Math.min(bounds.minY, state.bounds.minY),
      maxX: Math.max(bounds.maxX, state.bounds.maxX),
      maxY: Math.max(bounds.maxY, state.bounds.maxY),
    }),
    { ...selected[0].bounds },
  );
}
export function histogramBins(bins, limit = 120) {
  const size = Math.max(1, Math.ceil(bins.length / limit)),
    result = [];
  for (let i = 0; i < bins.length; i += size) {
    const items = bins.slice(i, i + size);
    result.push({
      first: items[0].day,
      last: items.at(-1).day,
      count: items.reduce((sum, b) => sum + b.count, 0),
    });
  }
  return result;
}
export function pulseLayout(rows, lens, selectedRow = null) {
  if (!Array.isArray(rows)) return pulseSummaryLayout(rows);
  const days = [...new Set(rows.map((r) => r.observed_day).filter(Boolean))].sort();
  const groups = new Map();
  for (const row of rows) {
    for (const key of observationKeys(row, lens)) {
      const group = groups.get(key.key) || { ...key, rows: [] };
      group.rows.push(row);
      groups.set(key.key, group);
    }
  }
  const focusKeys = new Set(
    selectedRow ? observationKeys(selectedRow, lens).map((k) => k.key) : [],
  );
  const lanes = [...groups.values()]
    .sort(
      (a, b) =>
        Number(focusKeys.has(b.key)) - Number(focusKeys.has(a.key)) ||
        b.rows.length - a.rows.length ||
        a.key.localeCompare(b.key),
    )
    .slice(0, 12);
  const start = days.length ? Date.parse(days[0]) : 0,
    end = days.length ? Date.parse(days.at(-1)) : 0;
  const span = Math.max(86400000, end - start);
  const nodes = [];
  lanes.forEach((lane, index) => {
    const byDay = new Map();
    for (const row of lane.rows) {
      if (!row.observed_day) continue;
      const bin = byDay.get(row.observed_day) || [];
      bin.push(row);
      byDay.set(row.observed_day, bin);
    }
    for (const [day, items] of byDay) {
      nodes.push({
        id: 'pulse:' + lane.key + ':' + day,
        type: 'pulse',
        label: lane.label,
        day,
        rows: items,
        x: 300 + (days.length === 1 ? 0.5 : (Date.parse(day) - start) / span) * 700,
        y: 105 + index * 62,
        r: 5 + Math.min(14, Math.sqrt(items.length) * 2),
        observation_count: items.length,
      });
    }
  });
  return {
    nodes,
    edges: [],
    lanes,
    days,
    start,
    end,
    bounds: { minX: 0, minY: 0, maxX: 1090, maxY: Math.max(360, lanes.length * 62 + 155) },
    omittedLanes: Math.max(0, groups.size - lanes.length),
    undated: rows.filter((r) => !r.observed_day).length,
  };
}
export function safeLocalURL(value, prefix) {
  return typeof value === 'string' && value.startsWith(prefix) && !value.includes('\\')
    ? value
    : '';
}
