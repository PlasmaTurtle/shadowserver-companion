import { densityStats } from './eclipse_model.js';
/** Stable screen-space aggregation anchored at an actual member location. */
export function clusterLocations(nodes, camera, radius = 48) {
  const buckets = new Map(),
    clusters = [];
  // A stable order preserves membership and marker identity across equivalent
  // payloads. Keeping each representative anchor prevents centroid movement
  // from pulling otherwise separated clusters on top of one another.
  const ordered = [...nodes].sort((a, b) => String(a.id).localeCompare(String(b.id)));
  for (const node of ordered) {
    const x = node.x * camera.k + camera.x,
      y = node.y * camera.k + camera.y,
      gx = Math.floor(x / radius),
      gy = Math.floor(y / radius);
    let target = null;
    for (let dx = -1; dx <= 1 && !target; dx++)
      for (let dy = -1; dy <= 1 && !target; dy++)
        for (const candidate of buckets.get(`${gx + dx}:${gy + dy}`) || []) {
          if (Math.hypot(x - candidate.sx, y - candidate.sy) < radius) {
            target = candidate;
            break;
          }
        }
    if (!target) {
      target = {
        id: 'cluster:' + node.id,
        type: 'cluster',
        members: [],
        rows: [],
        sx: x,
        sy: y,
        x: node.x,
        y: node.y,
        label: node.label,
        observation_count: 0,
        approximate: false,
      };
      clusters.push(target);
      const key = gx + ':' + gy;
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(target);
    }
    target.members.push(node);
    target.rows.push(...(node.rows || []));
    target.observation_count += node.observation_count ?? node.rows?.length ?? 0;
    target.approximate ||= node.approximate;
  }
  for (const c of clusters) {
    c.label =
      new Set(c.members.map((n) => n.label)).size === 1
        ? c.members[0].label
        : `${c.members.length} reported locations`;
    c.location_count = c.members.length;
    if (c.members.every((n) => n.summary)) {
      // Server groups are disjoint summaries. Their exact counts must never be
      // reconstructed from the bounded example rows bundled for inspection.
      for (const key of [
        'observation_count',
        'density_count',
        'admitted_density',
        'dark_matter_density',
        'finding_count',
        'asset_count',
      ]) {
        c[key] = c.members.reduce(
          (total, n) => total + (Number(n[key]) || (key === 'asset_count' ? 1 : 0)),
          0,
        );
      }
      c.entity_ids = [
        ...new Set(c.members.flatMap((n) => n.entity_ids || [n.entity_id]).filter(Boolean)),
      ].sort();
      c.entity_count = c.entity_ids.length;
      c.entity_map = c.members.every((n) => n.type === 'entity-location');
      c.day_count = new Set(c.members.flatMap((n) => n.observed_days || [])).size;
      c.risk_changed = c.members.some((n) => n.risk_changed);
      c.summary = true;
      c.location_count = new Set(
        c.members.map((n) => `${n.latitude}|${n.longitude}|${n.location_basis || ''}`),
      ).size;
      if (c.entity_map) {
        c.label = c.entity_count === 1 ? c.members[0].label : `${c.entity_count} entities`;
        if (c.entity_count === 1) {
          c.entity_id = c.entity_ids[0];
          c.scope = c.members[0].scope || { entity_id: c.entity_id };
          c.basis = c.members[0].basis;
        } else {
          c.basis =
            'Entities grouped by nearby entity location areas. The marker uses one member’s approximate city position; entity locations are unchanged. Select an entity to inspect its location source.';
        }
      } else if (c.members.length === 1) c.scope = c.members[0].scope;
      else {
        const locationKeys = new Set(
          c.members.map((n) => n.location_scope?.location_key).filter(Boolean),
        );
        if (locationKeys.size === 1 && c.members.every((n) => n.location_scope?.location_key))
          c.scope = { location_key: [...locationKeys][0] };
        const cities = new Set(
          c.members.map((n) => [n.city, n.region].filter(Boolean).join(', ')).filter(Boolean),
        );
        c.label =
          cities.size === 1
            ? `${[...cities][0]} · ${c.members.length} assets`
            : `${c.members.length} assets · ${c.location_count} reported areas`;
      }
      const rank = { cool: 0, warm: 1, hot: 2, blazing: 3 };
      c.temperature =
        c.members
          .map((n) => n.temperature)
          .filter((t) => t in rank)
          .sort((a, b) => rank[b] - rank[a])[0] || '';
    } else Object.assign(c, densityStats(c.rows));
  }
  return clusters;
}
export function semanticLevel(ratio) {
  return ratio >= 2.65 ? 'sources' : ratio >= 1.35 ? 'endpoints' : 'overview';
}
export function membershipForObservation(model, id) {
  const selected =
    model.selectedRow?.id === id || model.selectedRow?.observation_id === id
      ? model.selectedRow
      : null;
  return (model.nodes || []).filter(
    (n) =>
      n.rows?.some((row) => row.id === id) ||
      (n.observation_ids || []).includes(id) ||
      (selected?.asset_id && n.asset_id === selected.asset_id) ||
      (n.type === 'entity-location' &&
        selected?.entity_id &&
        (n.entity_id === selected.entity_id || n.entity_ids?.includes(selected.entity_id))),
  );
}
export function sharedSupport(graph) {
  return (graph.nodes || [])
    .filter((n) => n.type !== 'asset')
    .map((n) => ({
      id: n.id,
      shared: n.asset_count > 1,
      recurring: n.day_count > 1,
      rows: n.observation_count || 0,
      assets: n.asset_count || 0,
      entities: n.entity_count || 0,
      days: n.day_count || 0,
    }));
}

/** Scene-local cache. Pan and hover translate summaries; they never reread history. */
export function createLocationClusterer(nodes) {
  const cache = new Map();
  return (camera, radius = 48) => {
    const key = camera.k + ':' + radius;
    let clusters = cache.get(key);
    if (!clusters) {
      clusters = clusterLocations(nodes, { k: camera.k, x: 0, y: 0 }, radius);
      cache.set(key, clusters);
      if (cache.size > 3) cache.delete(cache.keys().next().value);
    }
    for (const c of clusters) {
      c.sx = c.x * camera.k + camera.x;
      c.sy = c.y * camera.k + camera.y;
    }
    return clusters;
  };
}
