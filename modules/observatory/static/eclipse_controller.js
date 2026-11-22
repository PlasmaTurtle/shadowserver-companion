import { requestJSON } from '../../ui/static/request.js';

/** Observatory interaction owner. No mutations, remote tiles, or background lookups. */
import {
  LENSES,
  esc,
  num,
  point,
  knownRansomware,
  statusName,
  unique,
  filterRows,
  timeline,
  graphLayout,
  attachSources,
  endpointKey,
  atlasLayout,
  pulseLayout,
  sourceLinks,
  safeLocalURL,
  adverse,
  histogramBins,
  findingCount,
  findingRows,
  densityStats,
  densityBand,
  priorityMark,
} from './eclipse_model.js';
import { createScene } from './eclipse_scene.js';
import { membershipForObservation, clusterLocations } from './eclipse_space.js';
import {
  initialState,
  selectionScope,
  drillOptions,
  scopeLabels,
  queryFor,
  scopedURL,
  persistentState,
} from './eclipse_navigation_state.js';
const PAGE_SIZE = 20;
const FIELD_PAGE_SIZE = 24;
const FIELD_ASSET_PAGE_SIZE = 120;
const VIEW_TIMEOUT_MS = 120000;
const viewTitles = {
  field: ['DARK MATTER FIELD', 'Your observed internet', ''],
  atlas: ['ENTITY GEOGRAPHY', 'Entity map', ''],
  pulse: ['OBSERVATION HISTORY', 'Observation history', ''],
  records: ['OBSERVED FINDINGS', 'Findings', ''],
};
const patternLabel = (type) =>
  ({
    shared_ip: 'Shared infrastructure',
    shared_cve: 'Common vulnerability',
    shared_service: 'Service connection',
    shared_version: 'Shared version',
    recurrent_asset: 'Recurring observation',
    first_seen_finding: 'First locally observed',
  })[type] || 'Observed connection';
function readState() {
  try {
    const value = JSON.parse(localStorage.getItem('companion.eclipse.view.0995') || '{}');
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  } catch {
    return {};
  }
}
export function mount(root, snapshot) {
  const $ = (selector) => root.querySelector(selector),
    saved = readState(),
    urlSelection = new URLSearchParams(location.hash.split('?')[1] || '');
  const state = initialState(saved, urlSelection, snapshot);
  Object.assign(state, { fieldOffset: 0, fieldAssetOffset: 0, fieldRevision: '' });
  let all = [],
    representatives = [],
    byId = new Map(),
    fullTime = { bins: [], undated: 0 },
    days = [],
    records = { items: [], total: 0, offset: 0, limit: PAGE_SIZE },
    counts = {},
    envelope = null,
    fieldReturn = null,
    recordsReturn = null,
    geographyFailed = false,
    restoreCamera = null,
    revision = '',
    activeJourney = null,
    journeySerial = 0,
    alive = true,
    filtered = [],
    filteredRecords = [],
    intelligence = null,
    graph = null,
    selection = null,
    sourceDetail = null,
    request = null,
    requestId = 0,
    detailRequest = null,
    detailId = 0,
    replay = null,
    searchTimer = null,
    slowTimer = null;
  const aborter = new AbortController(),
    signal = aborter.signal,
    on = (target, event, fn) => target?.addEventListener(event, fn, { signal });
  function cancelDetail() {
    detailId++;
    detailRequest?.abort();
    detailRequest = null;
  }
  function entityAtlas() {
    return intelligence?.atlas?.unit === 'entities';
  }
  function atlasEntities() {
    if (!entityAtlas()) return [];
    const payload = intelligence?.atlas || {};
    return [
      ...atlasLayout(payload).nodes,
      ...(payload.unplaced_entities_list || []).map((node) => ({ ...node, unplaced: true })),
    ];
  }
  function entityDirectory(nodes, title = 'Entities in this map') {
    return `<section class="ec-object-directory"><div class="ec-section-heading"><h3>${esc(title)}</h3><span>${num(nodes.length)}</span></div>${nodes.map((node) => `<button type="button" class="ec-source-row" data-ec-map-entity="${esc(node.id)}"><strong>${esc(node.label || node.entity_id)}</strong><small>${num(node.asset_count || 0)} assets · ${num(node.finding_count || 0)} findings${node.unplaced ? ' · location unavailable' : ''}</small></button>`).join('')}</section>`;
  }
  function mapLocationLabel(node) {
    const bases = new Set((node.members || [node]).map((item) => item.location_basis));
    return bases.has('reported_asset_city_area')
      ? bases.size > 1
        ? 'Saved and latest reported city areas'
        : 'Latest associated reported city area'
      : 'Current saved entity city area';
  }
  function restoreSelection(id) {
    if (state.view !== 'atlas') return graph.nodes.find((node) => node.id === id) || null;
    const nodes = atlasEntities();
    const found = nodes.find((node) => node.id === id);
    if (found) return found;
    if (selection?.type !== 'cluster' || !selection.members?.length) return null;
    const membersKey = (cluster) =>
      cluster.members
        .map((member) => member.id)
        .sort()
        .join('|');
    const previousMembers = membersKey(selection);
    const camera = scene.captureView?.()?.camera || { x: 0, y: 0, k: 1 };
    return (
      clusterLocations(
        nodes.filter((node) => !node.unplaced),
        camera,
        56,
      ).find((cluster) => membersKey(cluster) === previousMembers) || null
    );
  }
  function hydrate(result) {
    envelope = result;
    snapshot = result.snapshot || {};
    scene.jurisdiction?.(snapshot.jurisdiction);
    intelligence = result.intelligence || {};
    graph = intelligence.graph || { nodes: [], edges: [] };
    if (intelligence.field) {
      state.fieldOffset = intelligence.field.offset || 0;
      state.fieldAssetOffset = intelligence.field.asset_page?.offset || 0;
      state.fieldRevision = intelligence.field.revision || result.revision || '';
    }
    revision = String(result.revision || '');
    root.dataset.revision = revision;
    const revisionLabel = $('#ec-revision');
    if (revisionLabel) {
      const updated = new Date(result.generated_at || snapshot.generated_at || '');
      revisionLabel.textContent = Number.isNaN(updated.getTime())
        ? ''
        : 'Updated ' + updated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    all = Array.isArray(snapshot.observations) ? snapshot.observations : [];
    representatives = snapshot.findings || [];
    records = result.records || {
      items: representatives,
      total: representatives.length,
      offset: 0,
      limit: PAGE_SIZE,
    };
    filtered = all;
    filteredRecords = records.items || [];
    counts = snapshot.counts || intelligence.counts || {};
    byId = new Map([...all, ...representatives, ...filteredRecords].map((r) => [r.id, r]));
    for (const row of [...all, ...filteredRecords])
      if (row.observation_id) byId.set(row.observation_id, row);
    fullTime = snapshot.timeline || intelligence.timeline || timeline(all);
    if (Array.isArray(fullTime)) fullTime = { bins: fullTime, undated: 0 };
    fullTime.bins ||= [];
    days = fullTime.bins.map((bin) => bin.day);
    state.day = state.cutoff
      ? Math.max(
          0,
          days.findLastIndex((day) => day <= state.cutoff),
        )
      : Math.max(0, days.length - 1);
    const entities = snapshot.entities || [];
    $('#ec-entity').innerHTML =
      '<option value="">All organizations</option>' +
      entities
        .map((e) => `<option value="${esc(e.id)}">${esc(e.name || e.domain)}</option>`)
        .join('');
    if (state.entity && !entities.some((e) => e.id === state.entity))
      $('#ec-entity').insertAdjacentHTML(
        'beforeend',
        `<option value="${esc(state.entity)}">Selected organization</option>`,
      );
    const networks = snapshot.networks || [
      ...new Set(
        all
          .map((r) => r.asn)
          .filter(Boolean)
          .map(String),
      ),
    ];
    $('#ec-network').innerHTML =
      '<option value="">All ASNs</option><option value="__unknown">No ASN reported</option>' +
      networks.map((asn) => `<option value="${esc(asn)}">AS${esc(asn)}</option>`).join('');
  }
  const scene = createScene($('#ec-canvas'), {
    select: selectNode,
    clear: clearSelection,
    hover: showTooltip,
    camera: (percent) => {
      $('#ec-zoom-level').textContent = percent + '%';
    },
    level: (level) => {
      for (const button of root.querySelectorAll('[data-ec-level]'))
        button.setAttribute('aria-pressed', String(button.dataset.ecLevel === level));
      $('#ec-scene-coordinate').textContent =
        state.view.toUpperCase() + ' / ' + level.toUpperCase();
    },
    motion: (enabled, reduced) => {
      $('#ec-motion').textContent = reduced
        ? 'Reduced motion'
        : enabled
          ? 'Motion on'
          : 'Motion off';
      $('#ec-motion').setAttribute('aria-pressed', String(enabled));
      $('#ec-motion').disabled = reduced;
    },
  });
  // Exposed only as diagnostic numbers; no mutable controller/state is placed on window.
  root.dataset.ready = 'false';
  root.dataset.view = state.view;
  function openInspector(value = true, { focus = false } = {}) {
    state.inspectorOpen = value;
    root.dataset.inspectorOpen = String(value);
    $('#ec-inspect-toggle').setAttribute('aria-expanded', String(value));
    const mobile = window.matchMedia('(max-width:1050px)').matches;
    if (mobile) {
      $('#ec-inspector').setAttribute('role', 'dialog');
      $('#ec-inspector').setAttribute('aria-modal', 'false');
    } else {
      $('#ec-inspector').removeAttribute('role');
      $('#ec-inspector').removeAttribute('aria-modal');
    }
    if (value && focus && mobile) $('#ec-drawer-close').focus({ preventScroll: true });
  }
  function syncSelection() {
    const item = sourceDetail || selection;
    root.dataset.hasSelection = String(!!item);
    $('#ec-selection').hidden = !item;
    syncDrill();
    $('#ec-drawer-title').textContent = sourceDetail
      ? 'Source observation'
      : selection
        ? {
            entity: 'Organization',
            'entity-location': 'Entity',
            product: 'Product',
            asset: 'Asset',
            cve: 'Vulnerability',
            location: 'Location',
            cluster: 'Location',
          }[selection.type] || 'Selected object'
        : 'Explore';
    if (!item) return;
    $('#ec-selection-kind').textContent = sourceDetail
      ? 'Source observation'
      : item.type === 'asset'
        ? 'Observed endpoint'
        : item.type === 'cluster'
          ? 'Reported location cluster'
          : {
              entity: 'Organization',
              'entity-location': 'Entity',
              product: 'Product',
              cve: 'Reported vulnerability',
              ip: 'Reported IP',
              service: 'Product or service',
              version: 'Product version',
            }[item.type] || 'Selected connection';
    $('#ec-selection-name').textContent = sourceDetail
      ? item.hostname || item.ip || 'Original row'
      : item.label || item.title || 'Observation';
    $('#ec-selection-support').textContent = sourceDetail
      ? (item.observed_day || 'Undated') +
        ' · ' +
        (item.source?.sheet || 'Source') +
        ' ' +
        (item.source?.row ?? '')
      : state.view === 'atlas' && entityAtlas()
        ? `${num(item.entity_count || 1)} entities · ${num(item.asset_count || 0)} assets · ${num(item.finding_count || 0)} findings`
        : num(item.finding_count || 0) +
          ' findings · ' +
          num(item.observation_count || item.rows?.length || 0) +
          ' observations';
  }
  function announce(message) {
    $('#ec-announcement').textContent = message;
  }
  function persist() {
    try {
      const source = fieldReturn ? { ...fieldReturn.state, defaultView: state.defaultView } : state;
      localStorage.setItem('companion.eclipse.view.0995', JSON.stringify(persistentState(source)));
    } catch {}
  }
  function syncControls() {
    for (const [id, key] of [
      ['ec-search', 'search'],
      ['ec-entity', 'entity'],
      ['ec-network', 'network'],
      ['ec-intelligence', 'intelligence'],
      ['ec-status', 'status'],
      ['ec-intake', 'intake'],
    ])
      $('#' + id).value = state[key];
    for (const button of root.querySelectorAll('[data-ec-view]'))
      button.setAttribute('aria-pressed', String(button.dataset.ecView === state.view));
    for (const button of root.querySelectorAll('[data-ec-lens]'))
      button.setAttribute('aria-pressed', String(button.dataset.ecLens === state.lens));
    $('#ec-unplaced').setAttribute(
      'aria-pressed',
      String(state.view === 'atlas' && entityAtlas() ? false : state.unplaced),
    );
    $('#ec-unplaced').setAttribute(
      'aria-label',
      state.view === 'atlas' && entityAtlas()
        ? 'List entities without a usable city area'
        : 'Filter observations without reported locations',
    );
    $('#ec-time').max = Math.max(0, days.length - 1);
    $('#ec-time').value = state.day;
    $('#ec-time').setAttribute(
      'aria-valuetext',
      state.cutoff ? 'Through ' + state.cutoff : 'All dates',
    );
    $('#ec-time').disabled = days.length < 2;
    $('#ec-replay').disabled = days.length < 2;
    const labels = scopeLabels(state, snapshot.entities || [], snapshot.catalog_selection).map(
      (label) => {
        if (label === 'Unplaced') return 'Source observations without location';
        if (label === 'Selected location') return 'Selected source location';
        const location = [state.city, state.region, state.country].filter(Boolean).join(', ');
        return location && label === location ? 'Source location: ' + label : label;
      },
    );
    $('#ec-filter-count').textContent = labels.length || '';
    $('#ec-scope-caption').textContent = fieldReturn
      ? fieldReturn.label
      : labels[0] || 'Your observed internet';
    const chips = $('#ec-scope-chips');
    if (chips) {
      chips.hidden = !labels.length;
      chips.innerHTML = labels
        .map((label) => `<span class="ec-scope-chip">${esc(label)}</span>`)
        .join('');
    }
    const back = $('#ec-back-field');
    if (back) {
      back.hidden = !fieldReturn;
      back.textContent =
        '← Back to ' +
        (fieldReturn?.state.view === 'atlas'
          ? 'Atlas'
          : fieldReturn?.state.view === 'pulse'
            ? 'Pulse'
            : fieldReturn?.state.view === 'records'
              ? 'Records'
              : 'Field');
    }
    const [kicker, title, subtitle] = viewTitles[state.view];
    $('#ec-scene-kicker').textContent = 'LOCAL INTELLIGENCE / ' + kicker;
    $('#ec-scene-title').textContent = title;
    $('#ec-scene-subtitle').textContent = subtitle;
    $('#ec-scene-coordinate').textContent = {
      field: '01 / FIELD',
      atlas: '02 / ATLAS',
      pulse: '03 / PULSE',
      records: '04 / RECORDS',
    }[state.view];
    $('#ec-region').hidden = state.view !== 'atlas';
    $('#ec-region').disabled = !snapshot.jurisdiction?.states?.length || geographyFailed;
    $('#ec-region').title = snapshot.jurisdiction?.label
      ? `Fit configured jurisdiction: ${snapshot.jurisdiction.label}. Geographic outlines do not define legal jurisdiction.`
      : 'Choose jurisdiction in Settings to enable this map context.';
    $('#ec-fit').textContent = state.view === 'atlas' ? 'Fit entities' : 'Fit';
    root.dataset.view = state.view;
    const historyPanel = root.querySelector('.ec-history-panel');
    if (historyPanel && (state.view === 'pulse' || state.cutoff)) historyPanel.open = true;
    $('#ec-records').hidden = state.view !== 'records';
    $('#ec-list-toggle').setAttribute('aria-expanded', String(state.view === 'records'));
    $('#ec-canvas').setAttribute(
      'aria-label',
      {
        field: 'Relationship field',
        atlas: 'Entity map using approximate entity city areas',
        pulse: 'Observation timeline',
        records: 'Finding records',
      }[state.view] +
        '. Drag to pan; plus and minus zoom. Brackets select objects; Enter focuses. Use Explore for the entity directory or Records for findings.',
    );
    $('#ec-density-legend').hidden = state.view === 'atlas';
    $('#ec-unplaced-count').textContent = num(
      state.view === 'atlas' && entityAtlas()
        ? intelligence.atlas.unplaced_entities
        : (counts.unplaced ?? counts.unplaced_count ?? 0),
    );
    $('#ec-entities').textContent = num(
      state.view === 'atlas' && entityAtlas()
        ? intelligence.atlas.total_entities
        : (counts.entities ?? counts.entity_count ?? 0),
    );
  }
  function refreshFiltered() {
    // This response owns the complete filtered cohort. Sample rows are never totals.
    const count = (name, fallback = 0) => Number(counts[name] ?? fallback);
    $('#ec-rows').textContent = num(count('findings', count('finding_count', records.total)));
    $('#ec-hosts').textContent = num(count('assets', count('asset_count')));
    $('#ec-observations').textContent = num(count('observations', count('observation_count')));
    $('#ec-entities').textContent = num(count('entities', count('entity_count')));
    $('#ec-dark-matter').textContent = num(
      count(
        'dark_matter_observations',
        count('dark_matter_rows', count('dark_matter', count('dark_matter_count'))),
      ),
    );
    $('#ec-unplaced-count').textContent = num(
      state.view === 'atlas' && entityAtlas()
        ? intelligence.atlas.unplaced_entities
        : count('unplaced', count('unplaced_count')),
    );
    $('#ec-list-total').textContent = num(records.total);
    $('#ec-cutoff').textContent = state.cutoff ? 'Through ' + state.cutoff : 'All dates';
    $('#ec-first-day').textContent = days[0] || 'No observation dates';
    $('#ec-last-day').textContent = days.at(-1) || '';
    const undated = intelligence?.counts?.undated_rows ?? fullTime.undated;
    $('#ec-unknown-dates').textContent = undated ? num(undated) + ' undated included' : '';
    const bars = histogramBins(fullTime.bins),
      max = Math.max(1, ...bars.map((b) => b.count));
    $('#ec-histogram').innerHTML = bars
      .map(
        (bin) =>
          `<span class="${state.cutoff && bin.first > state.cutoff ? 'ec-future' : ''}" style="height:${Math.max(3, (bin.count / max) * 100)}%" title="${esc(bin.first === bin.last ? bin.first : bin.first + ' – ' + bin.last)}: ${num(bin.count)} observations"></span>`,
      )
      .join('');
    if (state.view === 'records') renderList();
    syncControls();
    persist();
  }
  function renderScene({ reset = false, reveal = false } = {}) {
    syncFieldNavigation();
    if (state.view === 'records') {
      renderList();
      return;
    }
    let model;
    if (state.view === 'field') {
      model = attachSources(
        graphLayout(graph || { nodes: [], edges: [] }, state.lens, { focused: !!state.graphFocus }),
        filtered,
      );
      if (
        sourceDetail &&
        !model.nodes.some(
          (node) =>
            node.type === 'asset' &&
            sourceDetail.asset_id &&
            node.asset_id === sourceDetail.asset_id,
        ) &&
        !membershipForObservation(model, sourceDetail.observation_id || sourceDetail.id).some(
          (n) => n.type === 'asset',
        )
      ) {
        const rows = filtered.filter((r) => endpointKey(r) === endpointKey(sourceDetail));
        const days = new Set(rows.map((r) => r.observed_day).filter(Boolean));
        model.nodes.push({
          id: 'selected-source:' + (sourceDetail.observation_id || sourceDetail.id),
          type: 'asset',
          label: sourceDetail.hostname || sourceDetail.ip || 'Source endpoint',
          displayLabel: sourceDetail.hostname || sourceDetail.ip || 'Source endpoint',
          x: (model.bounds.minX + model.bounds.maxX) / 2,
          y: (model.bounds.minY + model.bounds.maxY) / 2,
          rows,
          observation_count: rows.length,
          observation_ids: rows.map((r) => r.id),
          day_count: days.size,
          basis:
            'This endpoint is outside the displayed connections. No additional relationship is implied.',
          supplement: true,
        });
        model.selectedSupplement = true;
      }
      for (const node of model.nodes) {
        node.risk_changed =
          node.risk_changed === true || (node.rows || []).some((row) => row.risk_changed === true);
        node.adverse =
          node.adverse === true ||
          adverse(node) ||
          (node.rows || (node.observation_ids || []).map((id) => byId.get(id))).some((row) =>
            adverse(row || {}),
          );
      }
    } else if (state.view === 'atlas') {
      model = atlasLayout(entityAtlas() ? intelligence.atlas : { unit: 'entities', nodes: [] });
      const entityId = selection?.entity_id || selection?.scope?.entity_id;
      if (entityId && selection?.type !== 'entity-location' && entityAtlas()) {
        const entityNode = atlasEntities().find((node) => node.entity_id === entityId);
        if (entityNode) {
          selection = entityNode;
          state.selected = entityNode.id;
        }
      }
    } else
      model = pulseLayout(
        intelligence?.pulse || filtered,
        state.lens,
        sourceDetail || (selection?.rows || [])[0] || byId.get(selection?.observation_ids?.[0]),
      );
    model.selectedRow = sourceDetail;
    scene.set(model, state.view, state.lens, { reset, reveal });
    scene.select(selection?.id || null);
    if (sourceDetail) scene.selectObservation(sourceDetail.observation_id || sourceDetail.id);
    $('#ec-scene-title').textContent =
      state.view === 'field'
        ? state.graphFocus && selection
          ? selection.label || 'Constellation'
          : 'Dark Matter Field'
        : viewTitles[state.view][1];
    $('#ec-scene-subtitle').textContent =
      state.view === 'field'
        ? state.graphFocus
          ? `${num(model.nodes.filter((n) => n.type === 'asset').length)} assets in view`
          : `${LENSES[state.lens].label} · newest changes nearest`
        : state.view === 'atlas'
          ? entityAtlas()
            ? `${num(model.nodes.length)} of ${num(intelligence.atlas.total_entities)} entities shown`
            : `${num(model.nodes.length)} assets with reported locations`
          : `${num(model.lanes.length)} lanes · ${num(model.days.length)} scan dates`;
    $('#ec-space-key').textContent =
      state.view === 'field'
        ? 'Corona: density · spread: distinct assets · shadow: dark matter'
        : state.view === 'atlas'
          ? entityAtlas()
            ? 'Number = entities · dashed outline = approximate city area'
            : 'Number = unique findings · halo = observation density · dashed = approximate area'
          : 'Cell intensity and number = observations';
    root.dataset.nodeCount = String(model.nodes.length);
    root.dataset.edgeCount = String(model.edges?.length || 0);
    const noData = !envelope,
      noMatch =
        state.view === 'field'
          ? !model.nodes.length
          : state.view === 'atlas'
            ? entityAtlas()
              ? !Number(intelligence.atlas.total_entities || 0)
              : !model.nodes.length &&
                !Number(counts.observations ?? counts.observation_count ?? records.total)
            : Number(records.total || 0) === 0,
      noGeometry = state.view === 'atlas' && !model.nodes.length,
      emptyPulse = state.view === 'pulse' && !model.nodes.length,
      noGraph = state.view === 'field' && !model.nodes.length;
    $('#ec-map-empty').hidden = !(noData || noMatch || noGeometry || emptyPulse || noGraph);
    if (noData)
      $('#ec-map-empty').innerHTML =
        '<div class="ec-empty-orbit" aria-hidden="true"></div><h2>A quiet field.</h2><p>Import a report to see your observed internet take shape.</p><a class="ec-btn ec-btn-primary" href="#data">Import observations <svg class="ec-arrow" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 13 13 3M4 3h9v9"/></svg></a>';
    else if (noMatch)
      $('#ec-map-empty').innerHTML =
        state.view === 'atlas' && entityAtlas()
          ? '<h2>No entities in this scope.</h2><p>Assets without an associated entity remain in Records. Reset filters to include other entities.</p><button class="ec-btn" data-ec-action="reset">Reset filters</button>'
          : '<div class="ec-empty-orbit" aria-hidden="true"></div><h2>No findings match.</h2><p>Reset the filters to return to your full local field.</p><button class="ec-btn" data-ec-action="reset">Reset filters</button>';
    else if (noGeometry)
      $('#ec-map-empty').innerHTML = entityAtlas()
        ? '<h2>Entities need a usable city area.</h2><p>No entities in this scope have a usable saved or latest reported city area. Open the entity list to review their profiles.</p><button class="ec-btn" data-ec-action="unplaced-entities">List unplaced entities</button>'
        : '<h2>Beyond the map.</h2><p>These observations have no usable location. They remain available in Field, Pulse, and Records.</p><button class="ec-btn" data-ec-view="field">Open Field</button>';
    else if (emptyPulse)
      $('#ec-map-empty').innerHTML =
        '<h2>No dated observations match this view.</h2><p>Undated observations remain in Records. Choose another connection type.</p>';
    else if (noGraph)
      $('#ec-map-empty').innerHTML =
        '<h2>No connections match this view.</h2><p>Source observations remain in Records. Choose another connection type.</p>';
    const limits = intelligence?.graph?.limits;
    $('#ec-map-caption').textContent =
      state.view === 'field'
        ? state.graphFocus
          ? 'Selected constellation · lines show reported associations.'
          : 'Depth shows recency · halos show observation density.'
        : state.view === 'atlas'
          ? (geographyFailed
              ? 'Local geography could not load. Entity profiles and Records remain available. '
              : '') +
            (entityAtlas()
              ? `Saved entity city first; otherwise latest associated reported city. Approximate areas, not street addresses.${state.cutoff ? ' Evidence through ' + state.cutoff + '; saved profiles are current, reported cities follow selected evidence.' : ''}`
              : `${num(model.unplaced)} unplaced observations remain in Records. Dashed outlines mark approximate city areas.`) +
            (snapshot.jurisdiction?.label
              ? ` Context: ${snapshot.jurisdiction.label}. Fit entities includes locations outside this area.`
              : '')
          : `${num(model.undated)} undated observations remain in Records. Cells count observations; gaps do not establish remediation.`;
    $('#ec-coverage').textContent =
      state.view === 'field' && limits?.nodes_truncated
        ? `Showing ${num(model.nodes.length)} of ${num(limits.total_nodes)} nodes · ${num(limits.edges_truncated)} connections outside this view. Use the page controls or select an object.`
        : state.view === 'atlas' && entityAtlas()
          ? `${num(intelligence.atlas.unplaced_entities)} entities without usable city areas · ${num(intelligence.atlas.unresolved_asset_count)} assets without an associated entity.${intelligence.atlas.omitted_nodes ? ' ' + num(intelligence.atlas.omitted_nodes) + ' mapped entities omitted; narrow the filters.' : ''}`
          : state.view === 'atlas' && (model.omittedLocations || model.polarRows)
            ? `${num(model.omittedLocations)} additional assets remain in Records. ${model.polarRows ? num(model.polarRows) + ' polar rows projected at ±85° latitude.' : ''}`
            : state.view === 'pulse' && model.omittedLanes
              ? `${num(model.omittedLanes)} additional lanes available by search.`
              : model.selectedSupplement
                ? 'This endpoint is shown separately from the displayed connections; no additional relationship is implied.'
                : 'All interactive marks represent source records.';
    if (model.selectedSupplement && limits?.nodes_truncated)
      $('#ec-coverage').textContent +=
        ' This endpoint is shown separately from the displayed connections; no additional relationship is implied.';
  }
  function syncFieldNavigation() {
    const nav = $('#ec-field-navigation'),
      field = intelligence?.field;
    if (!nav) return;
    nav.hidden = state.view !== 'field' || !field;
    if (nav.hidden) return;
    const focused = !!state.graphFocus,
      page = focused ? field.asset_page : field;
    // A standalone endpoint is a focused object, not an empty asset collection.
    if (focused && !page) {
      nav.hidden = true;
      return;
    }
    const total = Number(focused ? page?.total_assets : page?.total_objects) || 0;
    const offset = Number(page?.offset) || 0,
      limit = Number(page?.limit) || (focused ? FIELD_ASSET_PAGE_SIZE : FIELD_PAGE_SIZE);
    const busy = root.dataset.ready === 'loading';
    $('#ec-field-range').textContent = total
      ? `${num(offset + 1)}–${num(Math.min(offset + limit, total))} of ${num(total)} ${focused ? 'assets' : 'objects'}`
      : `No ${focused ? 'assets' : 'objects'}`;
    $('#ec-field-prev').textContent = focused ? '← Previous assets' : '← Newer';
    $('#ec-field-next').textContent = focused ? 'More assets →' : 'Older →';
    $('#ec-field-prev').disabled = busy || offset <= 0;
    $('#ec-field-next').disabled = busy || !page?.has_more;
  }
  function query(value = state) {
    const params = queryFor(value, PAGE_SIZE);
    if (value.view === 'field') {
      params.set('field_only', 'true');
      params.set('field_limit', FIELD_PAGE_SIZE);
      params.set('field_offset', value.fieldOffset || 0);
      params.set('field_asset_limit', FIELD_ASSET_PAGE_SIZE);
      params.set('field_asset_offset', value.fieldAssetOffset || 0);
      if (value.fieldRevision) params.set('field_revision', value.fieldRevision);
    }
    return params;
  }
  async function loadIntelligence({
    reset = false,
    selectId = '',
    queryState = null,
    beforeCommit = null,
    journeyToken = null,
  } = {}) {
    if (journeyToken === null) cancelJourney();
    request?.abort();
    request = new AbortController();
    const currentRequest = request;
    const current = ++requestId;
    clearTimeout(slowTimer);
    slowTimer = setTimeout(() => {
      if (!alive || current !== requestId) return;
      $('#ec-loading').innerHTML =
        '<span class="ec-loading-orbit"></span>Still preparing this view…';
      $('#ec-data-status').textContent =
        'Still preparing this view. You can continue using the app.';
    }, 10000);
    root.dataset.ready = 'loading';
    syncFieldNavigation();
    syncDrill();
    if (!beforeCommit)
      for (const id of ['ec-rows', 'ec-hosts', 'ec-entities', 'ec-dark-matter', 'ec-observations'])
        $('#' + id).textContent = '—';
    $('#ec-data-status').textContent = 'Updating selection…';
    if (!beforeCommit && state.view === 'records')
      $('#ec-record-list').innerHTML = '<p role="status">Loading matching records…</p>';
    $('#ec-canvas').setAttribute('aria-busy', 'true');
    $('#ec-loading').hidden = !!beforeCommit;
    $('#ec-loading').setAttribute('role', 'status');
    $('#ec-loading').innerHTML = '<span class="ec-loading-orbit"></span>Resolving the field…';
    try {
      const result = await requestJSON('/api/eclipse/view?' + query(queryState || state), {
        signal: currentRequest.signal,
        timeoutMs: VIEW_TIMEOUT_MS,
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      if (beforeCommit) {
        const arrival = await beforeCommit;
        if (arrival?.completed === false) return;
      }
      if (
        !alive ||
        current !== requestId ||
        (journeyToken !== null && activeJourney?.id !== journeyToken)
      )
        return;
      if (queryState) {
        Object.assign(state, queryState);
        history.replaceState(null, '', scopedURL(state));
      }
      if (journeyToken !== null) {
        activeJourney = null;
        root.dataset.journey = 'resolved';
      }
      hydrate(result);
      refreshFiltered();
      $('#ec-loading').hidden = true;
      root.dataset.ready = 'true';
      syncDrill();
      $('#ec-data-status').textContent =
        num(counts.findings ?? counts.finding_count ?? records.total) +
        ' findings · ' +
        num(counts.observations ?? counts.observation_count ?? 0) +
        ' observations';
      if (selectId) {
        const node = restoreSelection(selectId);
        selection = node || null;
        state.selected = node?.id || null;
      }
      renderScene({ reset, reveal: state.view === 'field' });
      if (state.view === 'field' && state.graphFocus && selection) scene.focus(selection.id);
      if (restoreCamera) {
        scene.restoreView?.(restoreCamera);
        restoreCamera = null;
      }
      renderInspector();
      announce(`${num(counts.findings ?? records.total)} findings. ${state.view} view.`);
    } catch (error) {
      if (!alive || current !== requestId) return;
      if (
        error.status === 409 &&
        error.detail?.code === 'field_revision_changed' &&
        (queryState || state).view === 'field'
      ) {
        const next = {
          ...(queryState || state),
          fieldOffset: 0,
          fieldAssetOffset: 0,
          fieldRevision: '',
        };
        announce('The field changed. Returning to its newest page.');
        return loadIntelligence({
          reset: true,
          selectId,
          queryState: next,
          beforeCommit,
          journeyToken,
        });
      }
      $('#ec-loading').hidden = true;
      if (beforeCommit) {
        const failed = activeJourney;
        activeJourney = null;
        fieldReturn = failed?.returnBefore || null;
        scene.cancelApproach?.();
        root.dataset.journey = fieldReturn ? 'resolved' : '';
        root.dataset.ready = 'error';
        refreshFiltered();
        syncSelection();
        $('#ec-data-status').textContent = 'Could not open the selected object';
        openInspector(true);
        $('#ec-inspector-content').innerHTML =
          `<h2>Could not open this selection.</h2><p role="alert">${esc(error.code === 'REQUEST_TIMEOUT' ? 'The request timed out.' : error.message)}</p>${failed?.action ? `<button type="button" class="ec-btn" data-ec-drill="${esc(failed.action)}">Try again</button>` : failed?.focusId ? '<button type="button" class="ec-btn" data-ec-action="retry-focus">Try again</button>' : ''}`;
        return;
      }
      graph = { nodes: [], edges: [] };
      intelligence = null;
      envelope = null;
      filtered = [];
      filteredRecords = [];
      records = { items: [], total: 0, offset: 0, limit: PAGE_SIZE };
      counts = {};
      refreshFiltered();
      root.dataset.ready = 'error';
      renderScene({ reset });
      $('#ec-map-empty').hidden = false;
      $('#ec-map-empty').innerHTML =
        `<h2>Could not open this selection.</h2><p role="alert">${esc(error.code === 'REQUEST_TIMEOUT' ? 'The request timed out.' : error.message)}</p><button class="ec-btn" data-ec-action="retry">Try again</button>`;
      if (state.view === 'records') $('#ec-record-list').innerHTML = $('#ec-map-empty').innerHTML;
      $('#ec-data-status').textContent = 'Selection unavailable';
      $('#ec-inspector-content').innerHTML =
        `<span class="ec-eyebrow">OBSERVATORY</span><h2>Could not resolve this field.</h2><p role="alert">${esc(error.code === 'REQUEST_TIMEOUT' ? 'The connection request timed out.' : error.message)}</p><div class="ec-inspector-links"><button class="ec-btn" data-ec-action="retry">Try again</button><button class="ec-btn" data-ec-view="atlas">Open Atlas</button><button class="ec-btn" data-ec-action="records">Browse records</button></div>`;
    } finally {
      if (current === requestId) {
        clearTimeout(slowTimer);
        $('#ec-canvas').setAttribute('aria-busy', 'false');
        syncFieldNavigation();
      }
    }
  }
  async function loadRecords() {
    cancelJourney();
    cancelDetail();
    if (sourceDetail) {
      sourceDetail = null;
      state.selected = selection?.id || null;
      syncSelection();
      renderInspector();
    }
    request?.abort();
    const currentRequest = new AbortController();
    request = currentRequest;
    const current = ++requestId,
      requestedPage = state.page;
    const params = query();
    params.set('records_only', 'true');
    root.dataset.ready = 'loading';
    syncDrill();
    $('#ec-records').setAttribute('aria-busy', 'true');
    $('#ec-prev').disabled = true;
    $('#ec-next').disabled = true;
    $('#ec-record-list').innerHTML = '<p role="status">Loading findings…</p>';
    clearTimeout(slowTimer);
    slowTimer = setTimeout(() => {
      if (!alive || current !== requestId) return;
      $('#ec-record-list').innerHTML =
        '<p role="status">Still preparing these findings. You can continue using the app.</p>';
    }, 10000);
    try {
      const result = await requestJSON('/api/eclipse/view?' + params, {
        signal: currentRequest.signal,
        timeoutMs: VIEW_TIMEOUT_MS,
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      if (!alive || current !== requestId) return;
      if (String(result.revision || '') !== revision) {
        // Intake changed underneath this page: replace every view together.
        await loadIntelligence({ reset: false, selectId: selection?.id || '' });
        return;
      }
      records = result.records;
      filteredRecords = records.items || [];
      snapshot = { ...snapshot, findings: filteredRecords };
      envelope = { ...envelope, snapshot, records };
      representatives = filteredRecords;
      byId = new Map([...all, ...filteredRecords].map((row) => [row.id, row]));
      for (const row of filteredRecords) if (row.observation_id) byId.set(row.observation_id, row);
      root.dataset.ready = 'true';
      syncDrill();
      renderList();
      announce('Findings ' + $('#ec-page').textContent);
    } catch (error) {
      if (!alive || current !== requestId) return;
      state.page = Math.floor((records.offset || 0) / PAGE_SIZE);
      root.dataset.ready = 'error';
      syncDrill();
      renderList();
      $('#ec-record-list').insertAdjacentHTML(
        'afterbegin',
        `<p role="alert">${esc(error.code === 'REQUEST_TIMEOUT' ? 'The findings request timed out.' : error.message)} <button type="button" class="ec-text-btn" data-ec-page="${requestedPage}">Try again</button></p>`,
      );
    } finally {
      if (current === requestId) {
        clearTimeout(slowTimer);
        $('#ec-records').setAttribute('aria-busy', 'false');
      }
    }
  }
  function cancelJourney() {
    if (!activeJourney) return;
    const previous = activeJourney;
    activeJourney = null;
    journeySerial++;
    requestId++;
    request?.abort();
    clearTimeout(slowTimer);
    scene.cancelApproach?.();
    fieldReturn = previous.returnBefore;
    root.dataset.journey = fieldReturn ? 'resolved' : '';
    root.dataset.ready = envelope ? 'true' : 'false';
    syncDrill();
    $('#ec-loading').hidden = true;
    $('#ec-canvas').setAttribute('aria-busy', 'false');
    $('#ec-data-status').textContent =
      num(counts.findings ?? counts.finding_count ?? records.total) +
      ' findings · ' +
      num(counts.observations ?? counts.observation_count ?? 0) +
      ' observations';
    syncControls();
  }
  function update({ reset = false, keepSelection = false, keepPage = false } = {}) {
    if (recordsReturn && !keepSelection)
      recordsReturn = {
        view: recordsReturn.view,
        camera: null,
        selection: null,
        sourceDetail: null,
      };
    cancelJourney();
    fieldReturn = null;
    window.CosmicBackground?.resetApproach?.();
    state.graphFocus = '';
    state.fieldOffset = 0;
    state.fieldAssetOffset = 0;
    state.fieldRevision = '';
    if (!keepPage) state.page = 0;
    if (!keepSelection) {
      selection = null;
      state.selected = null;
      sourceDetail = null;
    }
    cancelDetail();
    syncSelection();
    syncControls();
    history.replaceState(null, '', scopedURL(state));
    return loadIntelligence({ reset });
  }
  function setView(view, { remember = true } = {}) {
    if (!viewTitles[view]) return;
    if (view === 'records' && state.view !== 'records')
      recordsReturn = { view: state.view, camera: scene.captureView?.(), selection, sourceDetail };
    cancelJourney();
    const replacingPending = root.dataset.ready === 'loading';
    state.view = view;
    state.recordsMode = 'findings';
    scene.cancelApproach?.();
    state.listOpen = view === 'records';
    if (remember) state.defaultView = view;
    syncControls();
    persist();
    if (intelligence?.field && view !== 'field') {
      if (selection) Object.assign(state, selectionScope(selection, rowsForSelection()));
      state.graphFocus = '';
      state.page = 0;
      loadIntelligence({ reset: true });
      return;
    }
    if (view === 'field' && !intelligence?.field) {
      state.fieldRevision = '';
      loadIntelligence({ reset: true });
      return;
    }
    // The retained envelope may already match this view while an opposite
    // payload is in flight (Field → Atlas → Field). Supersede that request
    // before it can replace the current view with incompatible aggregates.
    if (replacingPending) {
      loadIntelligence({ reset: true });
      return;
    }
    renderScene({ reset: false });
    renderInspector();
    if (sourceDetail && view !== 'records')
      scene.selectObservation(sourceDetail.observation_id || sourceDetail.id, { focus: true });
    announce(view + ' view. ' + num(records.total) + ' findings.');
  }
  function setLens(lens) {
    if (!LENSES[lens]) return;
    state.lens = lens;
    return update({ reset: true });
  }
  function rowsForSelection(node = selection) {
    return node?.rows || (node?.observation_ids || []).map((id) => byId.get(id)).filter(Boolean);
  }
  function syncDrill() {
    const context = $('#ec-drill-context'),
      actions = $('#ec-drill-actions');
    if (context)
      context.textContent = selection
        ? 'Explore ' + (selection.label || selection.title || 'selection')
        : '';
    if (actions)
      actions.innerHTML = selection
        ? (state.view === 'atlas' &&
          entityAtlas() &&
          selection.type === 'cluster' &&
          !selection.entity_id
            ? []
            : drillOptions(selection, rowsForSelection())
          )
            .map(
              (option) =>
                `<button type="button" class="ec-btn" data-ec-drill="${option.id}" ${root.dataset.ready === 'loading' ? 'disabled' : ''}>${option.label}</button>`,
            )
            .join('')
        : '';
  }
  async function descend(id, extraScope = {}) {
    if (!selection) return;
    cancelJourney();
    const target = drillOptions(selection, rowsForSelection()).find((option) => option.id === id);
    if (!target) return;
    const returnBefore = fieldReturn;
    if (!fieldReturn)
      fieldReturn = {
        state: { ...state },
        snapshot,
        envelope,
        selection,
        sourceDetail,
        camera: scene.captureView?.(),
        label: selection.label || selection.title || 'Selected object',
      };
    const journeyToken = ++journeySerial;
    activeJourney = { id: journeyToken, returnBefore, action: id };
    root.dataset.journey = 'approaching';
    const arrival = Promise.resolve(scene.approach?.(selection.id) || { completed: true });
    window.CosmicBackground?.approach?.({ depth: 1, ...(scene.position?.(selection.id) || {}) });
    const destination = {
      ...state,
      ...selectionScope(selection, rowsForSelection()),
      ...extraScope,
      view: target.view,
      recordsMode: target.recordsMode || 'findings',
      page: 0,
      graphFocus: '',
      fieldOffset: 0,
      fieldAssetOffset: 0,
      fieldRevision: '',
      listOpen: target.view === 'records',
    };
    if (target.lens) destination.lens = target.lens;
    sourceDetail = null;
    cancelDetail();
    syncControls();
    const loading = loadIntelligence({
      reset: true,
      queryState: destination,
      beforeCommit: arrival,
      journeyToken,
    });
    arrival.then((result) => {
      if (!alive || activeJourney?.id !== journeyToken) return;
      if (result?.completed === false) cancelJourney();
      else if (root.dataset.ready === 'loading') $('#ec-loading').hidden = false;
    });
    await loading;
  }
  function backToField() {
    if (!fieldReturn) return setView('field');
    const previous = fieldReturn;
    cancelJourney();
    requestId++;
    request?.abort();
    cancelDetail();
    clearTimeout(slowTimer);
    stopReplay();
    scene.cancelApproach?.();
    fieldReturn = null;
    const preference = state.defaultView;
    Object.assign(state, previous.state, { defaultView: preference });
    state.listOpen = state.view === 'records';
    root.dataset.journey = '';
    selection = previous.selection;
    sourceDetail = previous.sourceDetail;
    if (previous.envelope) hydrate(previous.envelope);
    $('#ec-loading').hidden = true;
    $('#ec-canvas').setAttribute('aria-busy', 'false');
    root.dataset.ready = 'true';
    refreshFiltered();
    renderScene();
    scene.restoreView?.(previous.camera);
    window.CosmicBackground?.resetApproach?.();
    renderInspector();
    history.replaceState(null, '', scopedURL(state));
    persist();
    announce('Returned to ' + state.view + ' and the previous selection.');
  }
  function stats(items) {
    return `<div class="ec-stat-row"><div><strong>${num(items[0][0])}</strong><span>${items[0][1]}</span></div><div><strong>${num(items[1][0])}</strong><span>${items[1][1]}</span></div><div><strong>${num(items[2][0])}</strong><span>${items[2][1]}</span></div></div>`;
  }
  function rowsMarkup(rows, { examples = false } = {}) {
    return (
      rows
        .slice(0, 5)
        .map(
          (row) =>
            `<button type="button" class="ec-source-row" data-ec-row="${esc(row.id || row.observation_id)}"><strong>${esc(row.hostname || row.ip || row.source?.workbook || 'Source observation')}</strong><small>${esc(row.observed_day || 'Undated')} · ${esc(row.source?.sheet || 'Source')} ${esc(row.source?.row ?? '')}</small></button>`,
        )
        .join('') +
      (examples
        ? '<p class="ec-truth-note">A sample of supporting observations is shown. Counts include all matching observations.</p>'
        : '')
    );
  }
  function linksMarkup(rows) {
    const links = sourceLinks(rows);
    return links.length
      ? `<div class="ec-inspector-links">${links
          .slice(0, 12)
          .map(
            (link) =>
              `<a class="ec-btn ${link.type === 'entity' ? 'ec-btn-primary' : ''}" href="${esc(link.href)}" title="${esc(link.name || link.label)}">${esc((link.type === 'case' ? 'Notification · ' : link.type === 'lead' ? 'Lead · ' : '') + (link.name || link.label))} <svg class="ec-arrow" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 13 13 3M4 3h9v9"/></svg></a>`,
          )
          .join(
            '',
          )}${links.length > 12 ? `<span class="ec-truth-note">${num(links.length - 12)} more destinations. Open scoped Records to inspect them.</span>` : ''}</div>`
      : '';
  }
  function organizationMarkup(node, rows) {
    const candidates = node.organizations || node.entities || [];
    const organizations = new Map();
    for (const e of candidates)
      if (e.id || e.entity_id)
        organizations.set(e.id || e.entity_id, { ...e, id: e.id || e.entity_id });
    for (const row of rows)
      if (row.entity_id && !organizations.has(row.entity_id))
        organizations.set(row.entity_id, {
          id: row.entity_id,
          name: row.entity_name || row.hostname || row.entity_id,
          temperature: row.temperature,
        });
    if (!organizations.size) return '';
    return `<section id="ec-organizations"><div class="ec-section-heading"><h3>Affected organizations</h3><span>${num(node.entity_count ?? organizations.size)}</span></div>${[
      ...organizations.values(),
    ]
      .slice(0, 12)
      .map(
        (e) =>
          `<a class="ec-organization" href="#entity/${encodeURIComponent(e.id)}"><strong>${esc(e.name || e.company || e.domain || e.id)}</strong>${priorityMark(e.temperature)}${e.finding_count != null ? `<small>${num(e.finding_count)} findings</small>` : ''}</a>`,
      )
      .join(
        '',
      )}${Number(node.entity_count || organizations.size) > Math.min(12, organizations.size) ? '<button type="button" class="ec-text-btn" data-ec-drill="organizations">Explore all affected organizations</button>' : ''}</section>`;
  }
  function darkMatterMarkup(node) {
    const count = Number(node.dark_matter_density ?? node.dark_matter_observations ?? 0);
    if (!count) return '';
    const reasons = Array.isArray(node.dark_matter_reasons) ? node.dark_matter_reasons : [];
    return `<section class="ec-dark-evidence" aria-label="Dark matter evidence"><h3>Dark matter <span>${num(count)}</span></h3><p>Retained observations outside admission.</p>${node.first_dark_observed_at || node.last_dark_observed_at ? `<dl class="ec-detail-grid"><dt>First observed</dt><dd>${esc(String(node.first_dark_observed_at || 'Undated').slice(0, 10))}</dd><dt>Last observed</dt><dd>${esc(String(node.last_dark_observed_at || 'Undated').slice(0, 10))}</dd></dl>` : ''}${reasons.length ? `<dl class="ec-dark-reasons">${reasons.map((item) => `<dt>${esc(item.reason)}</dt><dd>${num(item.count)}</dd>`).join('')}</dl>` : '<p>Open an evidence example for its recorded disposition.</p>'}${Object.keys(selectionScope(node, rowsForSelection(node))).length ? '<button type="button" class="ec-text-btn" data-ec-action="dark-records">Explore these observations →</button>' : ''}</section>`;
  }
  function openUnplacedEntities() {
    if (!entityAtlas()) return;
    const nodes = atlasEntities().filter((node) => node.unplaced);
    $('#ec-inspector-content').innerHTML =
      `${entityDirectory(nodes, 'Entities without a usable city area')}<p>Open an entity to review or edit its city and state. When no complete location is saved, the latest associated reported city is used if it can be placed.</p>${intelligence.atlas.omitted_unplaced_entities ? `<p>${num(intelligence.atlas.omitted_unplaced_entities)} additional unplaced entities. Narrow the entity or search filter to inspect them.</p>` : ''}${!nodes.length ? '<p>All entities in this scope have usable city areas.</p>' : ''}`;
    $('#ec-drawer-title').textContent = 'Unplaced entities';
    openInspector(true, { focus: true });
    announce(`${num(intelligence.atlas.unplaced_entities)} entities without usable city areas.`);
  }
  function renderEntityInspector(node) {
    const members = node.type === 'cluster' ? node.members || [] : [node];
    const entity = members.length === 1 ? members[0] : null;
    const workflow = entity?.workflow_summary || {};
    const workflowItems = [
      ...Object.entries(workflow.findings_by_status || {}).map(([status, count]) => [
        statusName(status) + ' findings',
        count,
      ]),
      ...Object.entries(workflow.cases_by_stage || {}).map(([stage, count]) => [
        stage.replace(/_/g, ' ') + ' notifications',
        count,
      ]),
    ];
    const rows = entity?.rows || [];
    const profile = entity ? '#entity/' + encodeURIComponent(entity.entity_id) : '';
    const locationSource = entity?.location_source_locator || {};
    const locationProvenance =
      entity?.location_basis === 'reported_asset_city_area'
        ? `<div class="ec-section-heading"><h3>Reported city fallback</h3></div><p>No complete entity location is saved. Using the latest associated report in the selected evidence.</p><dl class="ec-detail-grid"><dt>Reported city</dt><dd>${esc([entity.city, entity.region].filter(Boolean).join(', ') || 'Not reported')}</dd><dt>Hostname / IP</dt><dd>${esc(entity.location_hostname || locationSource.hostname || 'Hostname not reported')} · ${esc(entity.location_ip || locationSource.ip || 'IP not reported')}</dd><dt>Observed</dt><dd>${esc(entity.location_observed_at || entity.location_observed_day || locationSource.observed_at || locationSource.observed_day || 'Undated')}</dd><dt>Source</dt><dd>${esc([locationSource.source?.workbook, locationSource.source?.sheet, locationSource.source?.row != null ? 'row ' + locationSource.source.row : ''].filter(Boolean).join(' · ') || 'Preserved source observation')}</dd></dl><button type="button" class="ec-btn" data-ec-location-source="${esc(entity.id)}">Inspect location source</button>`
        : '';
    $('#ec-inspector-content').innerHTML =
      `<div class="ec-inspector-top"><span class="ec-eyebrow">${entity ? 'ENTITY' : 'ENTITIES IN THIS AREA'}</span><button class="ec-btn" type="button" data-ec-action="clear">Close ×</button></div><h2>${esc(entity?.label || node.label || 'Entities')}</h2>${stats(
        entity
          ? [
              [entity.asset_count || 0, 'assets'],
              [entity.finding_count || 0, 'findings'],
              [workflow.case_count || 0, 'notifications'],
            ]
          : [
              [node.entity_count || members.length, 'entities'],
              [node.asset_count || 0, 'assets'],
              [node.finding_count || 0, 'findings'],
            ],
      )}<p>${esc(entity?.basis || node.basis || 'Saved entity city areas, or the latest associated reported city when none is saved. Positions are approximate.')}</p>${entity?.unplaced ? `<p>${esc(entity.unplaced_reason || 'No usable saved or latest reported city area is available for this entity.')}</p>` : ''}${state.cutoff ? `<p>Evidence through ${esc(state.cutoff)}. Saved profile locations are current; reported fallback cities follow the selected evidence.</p>` : ''}${locationProvenance}${entity ? `<div class="ec-inspector-links"><a class="ec-btn" href="${esc(profile)}">Open entity</a><a class="ec-btn" href="${esc(profile)}?tab=assets">Entity assets</a><a class="ec-btn" href="${esc(profile)}?tab=history">Workflow history</a><a class="ec-btn" href="${esc(profile)}?tab=details">Edit saved location</a></div><div class="ec-section-heading"><h3>Current workflow</h3></div>${workflowItems.length ? `<dl class="ec-detail-grid">${workflowItems.map(([label, count]) => `<dt>${esc(label)}</dt><dd>${num(count)}</dd>`).join('')}</dl>` : '<p>No finding or notification workflow is recorded in this scope.</p>'}<details><summary>Supporting source evidence · ${num(entity.observation_count || 0)} observations</summary><p>Observations support this entity’s assets and findings. A reported city is used only when no complete entity location is saved.</p>${rowsMarkup(rows, { examples: true })}${!rows.length ? '<p>Open Assets & findings or the entity profile for supporting records.</p>' : ''}</details>` : `<p>Select an entity to inspect its assets, findings and workflow.</p>${entityDirectory(members, 'Choose an entity')}`}`;
  }
  function renderInspector() {
    if (!alive) return;
    syncSelection();
    if (sourceDetail) {
      renderSource(sourceDetail);
      return;
    }
    const panel = $('#ec-inspector-content');
    if (state.view === 'atlas' && entityAtlas()) {
      if (selection && (selection.type === 'entity-location' || selection.type === 'cluster'))
        renderEntityInspector(selection);
      else {
        const nodes = atlasEntities();
        $('#ec-pattern-count').textContent = num(intelligence.atlas.total_entities);
        panel.innerHTML = `${entityDirectory(nodes)}<p>Map positions prefer the saved entity city and state. Otherwise they use the latest associated reported city area; this is not a verified entity address.</p>${intelligence.atlas.omitted_nodes || intelligence.atlas.omitted_unplaced_entities ? '<p>The directory is bounded. Narrow the entity or search filter to inspect additional entities.</p>' : ''}${!nodes.length ? '<p>No entities match the current scope.</p>' : ''}<button type="button" class="ec-btn" data-ec-action="unplaced-entities">Unplaced entities · ${num(intelligence.atlas.unplaced_entities)}</button>`;
      }
      return;
    }
    if (selection) {
      const n = selection,
        rows = n.rows || (n.observation_ids || []).map((id) => byId.get(id)).filter(Boolean);
      const label =
        n.type === 'entity'
          ? 'Organization'
          : n.type === 'product'
            ? 'Product'
            : ['location', 'cluster', 'map-endpoint'].includes(n.type)
              ? 'Reported location'
              : n.type === 'pulse'
                ? 'Observed recurrence'
                : n.type === 'asset'
                  ? 'Observed endpoint'
                  : n.type === 'pattern'
                    ? patternLabel(n.patternType)
                    : 'Shared ' +
                      ({
                        entity: 'organization',
                        cve: 'CVE',
                        finding: 'finding',
                        ip: 'IP',
                        service: 'service',
                        version: 'version',
                      }[n.type] || 'value');
      panel.innerHTML = `<div class="ec-inspector-top"><span class="ec-eyebrow">${esc(label.toUpperCase())}</span><button class="ec-btn" type="button" data-ec-action="clear">Close ×</button></div><h2>${esc(n.label || n.title)}</h2><p>${esc(n.basis || (['location', 'cluster', 'map-endpoint'].includes(n.type) ? (n.approximate ? 'Reported city area; the point is approximate.' : 'Coordinates supplied by the source report.') : 'Observations recorded at this scan date.'))}</p>${stats(
        [
          [n.finding_count ?? 0, 'findings'],
          [n.observation_count ?? rows.length, 'observations'],
          [n.entity_count ?? unique(rows, 'entity_id'), 'organizations'],
        ],
      )}<dl class="ec-detail-grid"><dt>First observed</dt><dd>${esc(
        n.first_seen ||
          rows
            .map((r) => r.observed_day)
            .filter(Boolean)
            .sort()[0] ||
          'Undated',
      )}</dd><dt>Last observed</dt><dd>${esc(
        n.last_seen ||
          rows
            .map((r) => r.observed_day)
            .filter(Boolean)
            .sort()
            .at(-1) ||
          'Undated',
      )}</dd>${n.total_assets != null ? `<dt>Distinct assets</dt><dd>${num(n.total_assets)}</dd>` : ''}${n.day_count ? `<dt>Scan days</dt><dd>${num(n.day_count)}</dd>` : ''}<dt>Admitted observations</dt><dd>${num(n.admitted_density ?? densityStats(rows).admitted_density)}</dd><dt>Dark matter observations</dt><dd>${num(n.dark_matter_density ?? densityStats(rows).dark_matter_density)}</dd></dl>${
        n.recency_basis
          ? `<details><summary>Data chronology</summary><p>${esc(n.recency_basis)}</p><dl class="ec-detail-grid">${[
              ['First indexed locally', n.first_indexed_at],
              ['Latest addition locally', n.latest_indexed_at],
              ['Changed locally', n.local_changed_at],
              ['KEV added by CISA', n.kev_added_at],
            ]
              .filter(([, value]) => value)
              .map(
                ([label, value]) =>
                  `<dt>${esc(label)}</dt><dd>${esc(String(value).slice(0, 10))}</dd>`,
              )
              .join('')}</dl></details>`
          : ''
      }${darkMatterMarkup(n)}${organizationMarkup(n, rows)}${linksMarkup(rows)}${n.id && !['location', 'cluster', 'map-endpoint', 'pulse', 'pattern'].includes(n.type) ? '<button class="ec-btn" data-ec-action="focus">Focus this connection</button>' : ''}<div class="ec-section-heading"><h3>Evidence examples</h3><span>${num(Math.min(5, rows.length))} shown</span></div>${rowsMarkup(rows, { examples: true })}${!rows.length ? '<p>Open Records to inspect available observations.</p>' : ''}<p class="ec-truth-note">Shared infrastructure or identifiers do not establish common ownership. Workflow status describes current saved work.</p>`;
      return;
    }
    const priorityRank = (item) => {
      const temperature = item.temperature;
      const name =
        typeof temperature === 'object' ? temperature?.id || temperature?.label : temperature;
      return (
        { blazing: 4, hot: 3, warm: 2, cool: 1, cold: 0 }[String(name || '').toLowerCase()] || 0
      );
    };
    const byAttention = (a, b) =>
      priorityRank(b) - priorityRank(a) ||
      Number(b.risk_changed === true) - Number(a.risk_changed === true) ||
      String(b.fresh_at || '').localeCompare(String(a.fresh_at || '')) ||
      String(a.label || a.id).localeCompare(String(b.label || b.id));
    const patterns = [...(intelligence?.patterns || [])].sort(byAttention);
    $('#ec-pattern-count').textContent = num(patterns.length);
    const objects = (graph?.nodes || []).filter((n) => n.field_object || n.type !== 'asset');
    if (!intelligence?.field) objects.sort(byAttention);
    const objectDirectory = objects.length
      ? `<section class="ec-object-directory"><div class="ec-section-heading"><h3>Objects in this field</h3><span>${num(objects.length)}</span></div>${objects
          .slice(0, 6)
          .map(
            (n) =>
              `<button type="button" class="ec-source-row" data-ec-node="${esc(n.id)}"><strong>${esc(n.label || n.title || 'Observed object')}</strong><small>${num(n.finding_count || 0)} findings · ${num(n.observation_count || 0)} observations</small></button>`,
          )
          .join('')}${
          objects.length > 6
            ? `<details><summary>All ${num(objects.length)} objects in view</summary>${objects
                .slice(6)
                .map(
                  (n) =>
                    `<button type="button" class="ec-source-row" data-ec-node="${esc(n.id)}"><strong>${esc(n.label || n.title || 'Observed object')}</strong><small>${num(n.finding_count || 0)} findings</small></button>`,
                )
                .join('')}</details>`
            : ''
        }</section>`
      : '';
    if (intelligence?.field) {
      panel.innerHTML = `${objectDirectory || '<p>No objects match this selection.</p>'}<details><summary>Field legend</summary><p>New or materially changed findings appear nearest. Older objects recede; undated objects sit at the far edge. Coronas show observation density; constellation spread reflects distinct assets. Shadow envelopes show retained, unadmitted observations. None of these represents outreach priority.</p><p>Lines connect identifiers reported together. Shared infrastructure does not establish ownership.</p></details>${intelligence.coverage?.warnings?.length ? `<details><summary>Source coverage</summary><p>${intelligence.coverage.warnings.map(esc).join('<br>')}</p></details>` : ''}`;
      return;
    }
    panel.innerHTML = `${objectDirectory}<div class="ec-section-heading"><h3>Observed connections</h3><span>${num(patterns.length)}</span></div>${
      patterns
        .slice(0, 4)
        .map(
          (pattern) =>
            `<button class="ec-pattern" data-ec-pattern="${esc(pattern.id)}"><span class="ec-pattern-type">${esc(patternLabel(pattern.type))}<span class="ec-pattern-arrow" aria-hidden="true"><svg class="ec-arrow" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 13 13 3M4 3h9v9"/></svg></span></span><strong>${esc(pattern.label || pattern.title)}</strong><small>${num(pattern.entity_count)} entities · ${num(pattern.asset_count)} endpoints<br>${num(pattern.observation_count)} observations${pattern.day_count > 1 ? ' across ' + num(pattern.day_count) + ' scan days' : ''}</small></button>`,
        )
        .join('') ||
      `<p>${all.length ? 'No shared or recurrent identifiers in this selection.' : 'Import observations to populate this field.'}</p>`
    }${patterns.length > 4 ? `<button class="ec-text-btn" data-ec-action="patterns">All ${num(patterns.length)} connections <svg class="ec-arrow" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 13 13 3M4 3h9v9"/></svg></button>` : ''}<details><summary>Relationship basis</summary><p>${esc(intelligence?.semantics?.graph || 'Only co-occurrence in preserved source observations creates a connection. Shared identifiers do not establish ownership or compromise.')}</p></details>${intelligence?.coverage?.warnings?.length ? `<details><summary>Source coverage</summary><p>${intelligence.coverage.warnings.map(esc).join('<br>')}</p></details>` : ''}`;
  }
  function clearSelection() {
    cancelJourney();
    window.CosmicBackground?.resetApproach?.();
    if (state.graphFocus && fieldReturn) {
      backToField();
      return;
    }
    selection = null;
    state.selected = null;
    sourceDetail = null;
    detailRequest?.abort();
    detailId++;
    scene.select(null);
    syncSelection();
    if (state.graphFocus) {
      state.graphFocus = '';
      loadIntelligence({ reset: true });
      return;
    }
    renderInspector();
  }
  function selectNode(node) {
    if (root.dataset.ready === 'loading' && !activeJourney) return;
    if (
      state.view === 'atlas' &&
      entityAtlas() &&
      node.type === 'cluster' &&
      node.members?.length === 1
    )
      node = node.members[0];
    cancelJourney();
    if (node.type === 'source') {
      loadSource(node.row.id);
      return;
    }
    selection = node;
    sourceDetail = null;
    state.selected = node.id;
    detailRequest?.abort();
    detailId++;
    scene.select(node.id);
    renderInspector();
    openInspector(true, { focus: true });
    if (state.view === 'field') {
      window.CosmicBackground?.approach?.({ depth: 1, ...(scene.position?.(node.id) || {}) });
      if (
        intelligence?.field &&
        node.type !== 'asset' &&
        graph.nodes.some((n) => n.id === node.id) &&
        state.graphFocus !== node.id
      ) {
        openConstellation(node);
      } else scene.focus?.(node.id);
    } else if (state.view !== 'records' && !node.unplaced) scene.focus?.(node.id, 1.5);
    announce(
      (node.label || 'Observation') + ' selected. Details available in Selection and connections.',
    );
  }
  function openConstellation(node) {
    const returnBefore = fieldReturn;
    if (!fieldReturn)
      fieldReturn = {
        state: { ...state },
        snapshot,
        envelope,
        selection,
        sourceDetail,
        camera: scene.captureView?.(),
        label: node.label || 'Field',
      };
    const journeyToken = ++journeySerial;
    activeJourney = { id: journeyToken, returnBefore, focusId: node.id };
    root.dataset.journey = 'approaching';
    const arrival = Promise.resolve(scene.approach?.(node.id) || { completed: true });
    const destination = { ...state, graphFocus: node.id, fieldOffset: 0, fieldAssetOffset: 0 };
    loadIntelligence({
      reset: true,
      selectId: node.id,
      queryState: destination,
      beforeCommit: arrival,
      journeyToken,
    });
    arrival.then((result) => {
      if (!alive || activeJourney?.id !== journeyToken) return;
      if (result?.completed === false) cancelJourney();
      else if (root.dataset.ready === 'loading') $('#ec-loading').hidden = false;
    });
  }
  function pageField(direction) {
    const field = intelligence?.field;
    if (!field || root.dataset.ready === 'loading') return;
    const focused = !!state.graphFocus,
      page = focused ? field.asset_page : field;
    if (!page || (direction > 0 && !page.has_more)) return;
    const key = focused ? 'fieldAssetOffset' : 'fieldOffset';
    const limit = Number(page.limit) || (focused ? FIELD_ASSET_PAGE_SIZE : FIELD_PAGE_SIZE);
    const next = {
      ...state,
      [key]: direction > 0 ? page.next_offset : Math.max(0, page.offset - limit),
      fieldRevision: field.revision || revision,
    };
    if (!focused) {
      selection = null;
      sourceDetail = null;
      state.selected = null;
      next.selected = null;
      fieldReturn = null;
      window.CosmicBackground?.resetApproach?.();
    }
    cancelDetail();
    loadIntelligence({ reset: true, queryState: next, selectId: focused ? state.graphFocus : '' });
  }
  async function selectPattern(id) {
    const pattern = (intelligence?.patterns || []).find((p) => p.id === id);
    if (!pattern) return;
    const type = pattern.type;
    const lens =
      type === 'shared_ip'
        ? 'ip'
        : type === 'shared_service'
          ? 'service'
          : type === 'shared_version'
            ? 'version'
            : ['shared_cve', 'first_seen_finding'].includes(type)
              ? 'vulnerability'
              : state.lens;
    openInspector(true);
    if (type === 'recurrent_asset') {
      selection = {
        ...pattern,
        id: pattern.node_id,
        type: 'asset',
        label: pattern.label || pattern.title,
      };
      state.view = 'pulse';
      syncControls();
      renderScene({ reset: true });
      renderInspector();
      return;
    }
    state.view = 'field';
    state.lens = LENSES[lens] ? lens : 'service';
    state.graphFocus = pattern.node_id;
    selection = {
      ...pattern,
      id: pattern.node_id,
      type: pattern.node_id?.split(':')[0] || type.replace('shared_', ''),
      label: pattern.label || pattern.title,
    };
    syncControls();
    persist();
    await loadIntelligence({ reset: true, selectId: pattern.node_id });
  }
  async function loadSource(id, suppliedRow = null) {
    cancelJourney();
    const row = suppliedRow ||
      byId.get(id) ||
      filteredRecords.find((r) => r.id === id) ||
      (entityAtlas()
        ? atlasEntities()
            .flatMap((node) => node.rows || [])
            .find((item) => item.id === id || item.observation_id === id)
        : null) || { id, hostname: 'Source observation' };
    detailRequest?.abort();
    detailRequest = new AbortController();
    const sourceRequest = detailRequest;
    const token = ++detailId;
    selection = null;
    sourceDetail = null;
    state.selected = id;
    sourceDetail = row;
    syncSelection();
    openInspector(true, { focus: true });
    renderScene();
    scene.selectObservation(row.observation_id || id, { focus: true });
    $('#ec-inspector-content').innerHTML =
      '<span class="ec-eyebrow">SOURCE OBSERVATION</span><h2>Opening the source.</h2><p role="status">Reading the preserved observation…</p>';
    try {
      const detailURL =
        safeLocalURL(row.detail_url, '/api/eclipse/observations/') ||
        '/api/eclipse/observations/' + encodeURIComponent(row.observation_id || id);
      const result = await requestJSON(detailURL, {
        signal: sourceRequest.signal,
        timeoutMs: 20000,
        credentials: 'same-origin',
      });
      if (!alive || token !== detailId) return;
      sourceDetail = result;
      renderSource(result);
      syncSelection();
      renderScene();
      scene.selectObservation(result.observation_id || result.id || id, { focus: true });
      announce('Source observation opened: ' + (result.hostname || result.ip || 'original row'));
    } catch (error) {
      if (!alive || token !== detailId) return;
      $('#ec-inspector-content').innerHTML =
        `<div class="ec-inspector-top"><span class="ec-eyebrow">SOURCE OBSERVATION</span><button class="ec-btn" data-ec-action="clear">Close ×</button></div><h2>Could not open this source.</h2><p role="alert">${esc(error.code === 'REQUEST_TIMEOUT' ? 'The source request timed out.' : error.message)}</p><button class="ec-btn" data-ec-row="${esc(id)}">Try again</button>`;
    }
    if (state.listOpen) renderList();
  }
  function renderSource(row) {
    const source = row.source || {},
      original = safeLocalURL(
        row.original_url ||
          '/api/imports/' + encodeURIComponent(source.import_id || '') + '/original',
        '/api/imports/',
      ),
      fields = Object.entries(row.fields || {}),
      findings = (row.catalog_findings || []).slice(0, 12),
      referenceMarkup = findings.length
        ? `<section class="ec-reference-findings"><div class="ec-section-heading"><h3>Current Library findings</h3></div>${findings
            .map((finding) => {
              const epss = finding.epss,
                probability = Number.isFinite(epss?.score)
                  ? `${(epss.score * 100).toFixed(2)}%`
                  : null;
              return `<p><a class="ec-text-btn" href="#library?view=cves&amp;cve=${encodeURIComponent(finding.id)}">${esc(finding.id)}</a><br>${esc(finding.severity || 'UNKNOWN')}${Number.isFinite(finding.score) ? ` · CVSS ${esc(finding.score)}` : ''}${finding.kev === true ? ' · KEV' : ''}${probability ? `<br>EPSS ${esc(probability)} · ${esc(epss.score_date || 'Date unavailable')}${epss.stale ? ' · stale' : ''}` : ''}</p>`;
            })
            .join(
              '',
            )}${(row.catalog_findings || []).length > findings.length ? `<p>Showing ${findings.length} of ${row.catalog_findings.length} local findings.</p>` : ''}<p class="ec-truth-note">Current references for the CVEs explicitly reported here. Preserved source values and frozen reports are unchanged.</p></section>`
        : '';
    $('#ec-inspector-content').innerHTML =
      `<div class="ec-inspector-top"><span class="ec-eyebrow">SOURCE OBSERVATION</span><button class="ec-btn" type="button" data-ec-action="clear">Close ×</button></div><h2>${esc(row.hostname || row.ip || 'Original row')}</h2><span class="ec-tag">${esc(statusName(row.status))}</span>${priorityMark(row.temperature)}${row.risk_changed ? `<span class="ec-tag ec-risk" title="${esc((row.risk_change_reasons || []).join(' '))}">Risk changed</span>` : ''}${row.admission_state === 'legacy_unknown' || row.status === 'qualification_unknown' ? '<span class="ec-tag">Legacy qualification unavailable</span>' : row.dark_matter ? '<span class="ec-tag">Dark Matter</span>' : row.intake_disposition === 'lead' ? '<span class="ec-tag">Admitted</span>' : ''}${row.kev ? '<span class="ec-tag ec-risk">Known exploited · KEV</span>' : ''}${knownRansomware(row) ? '<span class="ec-tag ec-risk">Known ransomware use</span>' : ''}<dl class="ec-detail-grid"><dt>Address</dt><dd>${esc(row.ip || 'Not reported')}</dd><dt>Finding</dt><dd>${esc(row.tag || 'Not reported')}</dd><dt>Service</dt><dd>${esc([row.protocol, row.port, row.product].filter(Boolean).join(' / ') || 'Not reported')}</dd><dt>Version</dt><dd>${esc(row.version || 'Not reported')}</dd><dt>Observed</dt><dd>${esc(row.observed_at || 'Undated')}</dd><dt>Location</dt><dd>${esc([row.city, row.region].filter(Boolean).join(', ') || 'Unplaced')}</dd></dl><p>${esc(row.location_basis === 'city_area' ? 'Approximate city-area location, not an asset position.' : row.location_basis === 'reported_coordinates' ? 'Coordinates supplied in the source report.' : 'No usable reported location.')}</p>${row.disposition_reason ? `<p class="ec-truth-note">${esc(row.disposition_reason)}</p>` : ''}${linksMarkup([row])}${referenceMarkup}<div class="ec-section-heading"><h3>Preserved source</h3></div><p>${esc(source.workbook || 'Source file')}<br>${esc(source.sheet || 'Sheet')} · row ${esc(source.row ?? '')}</p>${row.source_available !== false && source.import_id ? `<div class="ec-inspector-links"><a class="ec-btn" href="${esc(original)}">Download original <svg class="ec-arrow" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 13 13 3M4 3h9v9"/></svg></a></div>` : '<p>Original source file unavailable.</p>'}<details><summary>Source fields · ${fields.length}</summary><p class="ec-truth-note">Some displayed values may be shortened. Download the original report for complete fields.</p>${row.fields_error ? `<p role="alert">${esc(row.fields_error)}</p>` : ''}<dl class="ec-source-fields">${fields.map(([key, value]) => `<dt>${esc(key)}</dt><dd>${esc(typeof value === 'object' ? JSON.stringify(value) : value)}</dd>`).join('')}</dl></details>${row.attribution ? `<details><summary>Saved attribution evidence</summary><pre>${esc(JSON.stringify(row.attribution, null, 2))}</pre></details>` : ''}<details><summary>Source fingerprint & dates</summary><pre>${esc(JSON.stringify({ sha256: source.sha256, observed_at: row.observed_at, imported_at: row.imported_at, attribution_validated_at: row.attribution_validated_at, delivered_at: row.delivered_at }, null, 2))}</pre></details><p class="ec-truth-note">Source values are preserved as reported. ${row.individually_attributed ? 'This row is the supporting attribution entry.' : 'Qualification of a hostname group does not independently attribute every observation.'}</p>`;
  }
  function showTooltip(node, x, y) {
    const tip = $('#ec-tooltip');
    tip.hidden = !node;
    if (!node) return;
    const counts =
      node.finding_count != null || node.summary
        ? node
        : node.rows
          ? densityStats(node.rows)
          : node;
    const density = node.density_count ?? counts.observation_count ?? 0;
    tip.innerHTML =
      state.view === 'atlas' && entityAtlas()
        ? `${esc(node.label || 'Entity')}<small>${num(node.entity_count || 1)} entities · ${num(node.asset_count || 0)} assets · ${num(node.finding_count || 0)} findings<br>${esc(mapLocationLabel(node))} · approximate${node.risk_changed ? '<br>Material local risk change since intake' : ''}</small>`
        : `${esc(node.label || 'Observation')}<small>${num(counts.finding_count || 0)} findings · ${num(density)} observations<br>${num(node.admitted_density ?? counts.admitted_density ?? 0)} admitted · ${num(node.dark_matter_density ?? counts.dark_matter_density ?? 0)} dark matter${(node.legacy_unknown_density ?? counts.legacy_unknown_density ?? 0) ? ` · ${num(node.legacy_unknown_density ?? counts.legacy_unknown_density)} legacy qualification unavailable` : ''}<br>${esc(densityBand(density).label)} · independent of outreach priority${node.temperature ? '<br>' + priorityMark(node.temperature) : ''}${node.risk_changed || counts.risk_changed ? '<br>Material local risk change since intake' : ''}</small>`;
    tip.style.left = Math.min(x + 14, Math.max(0, $('#ec-viewport').clientWidth - 290)) + 'px';
    tip.style.top = Math.max(8, y - 60) + 'px';
  }
  function renderList() {
    const title = $('#ec-record-title'),
      returnFindings = $('#ec-record-findings');
    if (title)
      title.textContent =
        state.recordsMode === 'products'
          ? 'Products'
          : records.kind === 'observations'
            ? 'Dark matter observations'
            : 'Findings';
    if (returnFindings) returnFindings.hidden = state.recordsMode !== 'products';
    if (state.recordsMode === 'products') {
      renderProducts();
      return;
    }
    const start = records.offset ?? state.page * PAGE_SIZE,
      rows = records.items || [];
    $('#ec-record-count').textContent = num(records.total);
    $('#ec-record-list').innerHTML = rows.length
      ? `<div class="ec-table-wrap" tabindex="0" role="region" aria-label="Scrollable findings table"><table><thead><tr><th scope="col">Observed endpoint</th><th scope="col">Finding / service</th><th scope="col">Last observed / history</th><th scope="col">Current status</th><th scope="col">Source row</th></tr></thead><tbody>${rows.map((row) => `<tr aria-selected="${state.selected === row.id || state.selected === row.observation_id}"><td><button type="button" data-ec-row="${esc(row.id)}">${esc(row.hostname || row.ip || 'Original row')}</button><small>${esc(row.ip || 'IP not reported')}</small></td><td>${esc(row.tag || row.product || 'Not reported')}<small>${esc([row.protocol, row.port, row.version].filter(Boolean).join(' / '))}</small></td><td>${esc(row.observed_day || 'Undated')}<small>${records.kind === 'observations' ? 'Source observation' : `${num(row.reported_observation_count ?? row.observation_count ?? 1)} reported · ${num(row.approved_observation_count ?? row.observation_count ?? 0)} approved${row.legacy_unknown_observation_count ? ` · ${num(row.legacy_unknown_observation_count)} legacy qualification unavailable` : ''} · ${num(row.sightings || 0)} days`}</small>${row.fresh_at ? `<small>Changed ${esc(String(row.fresh_at).slice(0, 10))}</small>` : ''}</td><td>${esc(statusName(row.status))}${priorityMark(row.temperature)}${row.risk_changed ? `<span class="ec-tag ec-risk" title="${esc((row.risk_change_reasons || []).join(' '))}">Risk changed</span>` : ''}${row.admission_state === 'legacy_unknown' || row.status === 'qualification_unknown' ? '<small>Legacy qualification unavailable</small>' : row.dark_matter ? `<small>Dark matter${row.disposition_reason ? ' · ' + esc(row.disposition_reason) : ''}</small>` : row.intake_disposition === 'lead' ? '<small>Admitted finding</small>' : ''}</td><td>${esc(row.source?.sheet || 'Source')} ${esc(row.source?.row ?? '')}<small>${esc(row.source?.workbook || '')}</small></td></tr>`).join('')}</tbody></table></div>`
      : '<p>No observations match the current filters.</p>';
    $('#ec-page').textContent = records.total
      ? `${num(start + 1)}–${num(Math.min(records.total, start + rows.length))} of ${num(records.total)}`
      : records.kind === 'observations'
        ? '0 observations'
        : '0 findings';
    $('#ec-prev').disabled = state.page === 0;
    $('#ec-next').disabled = start + rows.length >= records.total;
  }
  function renderProducts() {
    const products = intelligence?.products || [],
      start = state.page * PAGE_SIZE,
      items = products.slice(start, start + PAGE_SIZE),
      total = intelligence?.product_total ?? products.length;
    $('#ec-record-count').textContent = num(total);
    $('#ec-record-list').innerHTML = items.length
      ? `<div class="ec-table-wrap" tabindex="0" role="region" aria-label="Scrollable products table"><table><thead><tr><th scope="col">Product</th><th scope="col">Organizations</th><th scope="col">Assets</th><th scope="col">Findings</th><th scope="col">Observations</th></tr></thead><tbody>${items.map((p) => `<tr><td><button type="button" data-ec-product="${esc(p.id)}">${esc(p.label)}</button></td><td>${num(p.entity_count)}</td><td>${num(p.asset_count)}</td><td>${num(p.finding_count)}</td><td>${num(p.observation_count)}</td></tr>`).join('')}</tbody></table></div>${total > products.length ? `<p class="ec-truth-note">Showing ${num(products.length)} of ${num(total)} products. Search within this selection to narrow the breakdown.</p>` : ''}`
      : '<p>No named products were reported in this selection. All findings remain available.</p>';
    $('#ec-page').textContent = items.length
      ? `${num(start + 1)}–${num(start + items.length)} of ${num(products.length)} displayed products`
      : '0 products';
    $('#ec-prev').disabled = state.page === 0;
    $('#ec-next').disabled = start + items.length >= products.length;
  }
  function showList(value = true) {
    if (value) {
      setView('records', { remember: false });
      $('#ec-records-close').focus({ preventScroll: true });
      return;
    }
    if (recordsReturn) {
      const previous = recordsReturn;
      recordsReturn = null;
      selection = previous.selection;
      sourceDetail = previous.sourceDetail;
      state.selected = selection?.id || null;
      setView(previous.view, { remember: false });
      if (previous.view === 'atlas' && previous.selection) {
        selection = restoreSelection(previous.selection.id);
        state.selected = selection?.id || null;
        renderScene();
      }
      if (root.dataset.ready === 'loading') restoreCamera = previous.camera;
      else if (previous.camera) scene.restoreView?.(previous.camera);
      else scene.fit();
      renderInspector();
    } else if (fieldReturn) backToField();
    else setView('field', { remember: false });
  }
  function stopReplay() {
    clearInterval(replay);
    replay = null;
    $('#ec-replay').textContent = 'Play history';
  }
  function reset() {
    cancelJourney();
    stopReplay();
    fieldReturn = null;
    root.dataset.journey = '';
    scene.cancelApproach?.();
    Object.assign(state, {
      search: '',
      cve: '',
      condition: '',
      asset: '',
      ip: '',
      service: '',
      city: '',
      region: '',
      country: '',
      productName: '',
      locationKey: '',
      version: '',
      recordsMode: 'findings',
      product: '',
      entity: '',
      network: '',
      intelligence: 'all',
      status: '',
      intake: '',
      unplaced: false,
      cutoff: '',
      day: Math.max(0, days.length - 1),
      graphFocus: '',
      selected: null,
    });
    history.replaceState(null, '', '#eclipse');
    update({ reset: true });
  }
  on(root, 'click', (event) => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.id === 'ec-back-field') {
      backToField();
      return;
    }
    if (button.dataset.ecPage !== undefined) {
      state.page = Math.max(0, Number(button.dataset.ecPage) || 0);
      loadRecords();
      return;
    }
    if (button.dataset.ecNode) {
      const node = (graph?.nodes || []).find((n) => n.id === button.dataset.ecNode);
      if (node) selectNode(node);
      return;
    }
    if (button.dataset.ecMapEntity) {
      const node = atlasEntities().find((item) => item.id === button.dataset.ecMapEntity);
      if (node) selectNode(node);
      return;
    }
    if (button.dataset.ecLocationSource) {
      const node = atlasEntities().find((item) => item.id === button.dataset.ecLocationSource);
      const row = node?.location_source_locator || node?.rows?.[0];
      const id = node?.location_observation_id || row?.observation_id || row?.id;
      if (id && row) loadSource(id, row);
      return;
    }
    if (button.dataset.ecProduct) {
      if (root.dataset.ready === 'loading' && !activeJourney) return;
      const product = (intelligence?.products || []).find((p) => p.id === button.dataset.ecProduct);
      if (product) selectNode({ ...product, type: 'product', rows: [] });
      return;
    }
    if (button.dataset.ecDrill) {
      if (root.dataset.ready !== 'loading') descend(button.dataset.ecDrill);
      return;
    }
    if (button.dataset.ecLevel) {
      if (window.matchMedia('(max-width:760px)').matches) {
        const details = root.querySelector('.ec-instrument-options');
        if (details) details.open = false;
      }
      scene.level(button.dataset.ecLevel);
      return;
    }
    if (['ec-inspect-toggle', 'ec-drawer-close'].includes(button.id)) {
      const closing = state.inspectorOpen;
      openInspector(!closing);
      if (closing && button.id === 'ec-drawer-close')
        $('#ec-inspect-toggle').focus({ preventScroll: true });
      return;
    }
    if (['ec-mobile-inspect', 'ec-selection-inspect'].includes(button.id)) {
      openInspector(true, { focus: true });
      return;
    }
    if (button.id === 'ec-locate') {
      if (sourceDetail)
        scene.selectObservation(sourceDetail.observation_id || sourceDetail.id, { focus: true });
      else if (selection) {
        scene.focus(selection.id);
        window.CosmicBackground?.approach?.({ depth: 1 });
      }
      return;
    }
    if (button.dataset.ecView) {
      setView(button.dataset.ecView);
      return;
    }
    if (button.dataset.ecLens) {
      if (window.matchMedia('(max-width:760px)').matches) {
        const details = root.querySelector('.ec-instrument-options');
        if (details) details.open = false;
      }
      setLens(button.dataset.ecLens);
      return;
    }
    if (button.dataset.ecRow) {
      if (root.dataset.ready === 'loading' && !activeJourney) return;
      loadSource(button.dataset.ecRow);
      return;
    }
    if (button.dataset.ecPattern) {
      if (root.dataset.ready === 'loading') return;
      selectPattern(button.dataset.ecPattern);
      return;
    }
    const action = button.dataset.ecAction;
    if (action === 'unplaced-entities') {
      openUnplacedEntities();
      return;
    }
    if (action === 'dark-records') {
      descend('assets', { intake: 'dark_matter' });
      return;
    }
    if (action === 'record-findings') {
      state.recordsMode = 'findings';
      state.page = 0;
      update({ keepSelection: true });
      return;
    }
    if (action === 'clear') {
      clearSelection();
      return;
    }
    if (action === 'reset') {
      reset();
      return;
    }
    if (action === 'records') {
      showList();
      return;
    }
    if (action === 'retry-focus' && selection) {
      openConstellation(selection);
      return;
    }
    if (action === 'retry') {
      loadIntelligence();
      return;
    }
    if (action === 'focus' && selection) {
      if (state.view === 'field' && intelligence?.field) {
        openConstellation(selection);
        return;
      }
      state.view = 'field';
      state.graphFocus = selection.id;
      state.fieldOffset = 0;
      state.fieldAssetOffset = 0;
      state.fieldRevision = '';
      syncControls();
      loadIntelligence({ reset: true, selectId: selection.id });
      return;
    }
    if (action === 'patterns') {
      const patterns = intelligence?.patterns || [];
      $('#ec-inspector-content').innerHTML =
        `<div class="ec-inspector-top"><span class="ec-eyebrow">OBSERVED CONNECTIONS</span><button class="ec-btn" data-ec-action="clear">Back</button></div><h2>${num(patterns.length)} connections.</h2>${patterns.map((p) => `<button class="ec-pattern" data-ec-pattern="${esc(p.id)}"><span class="ec-pattern-type">${esc(patternLabel(p.type))}</span><strong>${esc(p.label || p.title)}</strong><small>${num(p.asset_count)} endpoints · ${num(p.entity_count)} entities · ${num(p.observation_count)} observations</small></button>`).join('')}`;
      return;
    }
    if (button.id === 'ec-filter-toggle') {
      const open = $('#ec-filters').hidden;
      $('#ec-filters').hidden = !open;
      button.setAttribute('aria-expanded', String(open));
    } else if (button.id === 'ec-reset') reset();
    else if (button.id === 'ec-refresh') {
      stopReplay();
      cancelDetail();
      sourceDetail = null;
      loadIntelligence({ reset: false, selectId: selection?.id || '' });
    } else if (button.id === 'ec-unplaced') {
      if (state.view === 'atlas' && entityAtlas()) {
        openUnplacedEntities();
        return;
      }
      state.unplaced = !state.unplaced;
      update({ reset: true });
    } else if (button.id === 'ec-zoom-in') scene.zoom(1.25);
    else if (button.id === 'ec-zoom-out') scene.zoom(0.8);
    else if (button.id === 'ec-fit') {
      scene.fit();
      window.CosmicBackground?.resetApproach?.();
    } else if (button.id === 'ec-field-prev') pageField(-1);
    else if (button.id === 'ec-field-next') pageField(1);
    else if (button.id === 'ec-region') scene.fit(true);
    else if (button.id === 'ec-list-toggle') showList(!state.listOpen);
    else if (button.id === 'ec-records-close') showList(false);
    else if (button.id === 'ec-prev') {
      state.page = Math.max(0, state.page - 1);
      if (state.recordsMode === 'products') renderList();
      else loadRecords();
    } else if (button.id === 'ec-next') {
      if (state.recordsMode === 'products') {
        if ((state.page + 1) * PAGE_SIZE >= (intelligence?.products || []).length) return;
        state.page++;
        renderList();
      } else {
        if ((records.offset || 0) + (records.items || []).length >= records.total) return;
        state.page++;
        loadRecords();
      }
    } else if (button.id === 'ec-motion') {
      const enabled = button.getAttribute('aria-pressed') !== 'true';
      scene.motion(enabled);
      window.CosmicBackground?.setMotion?.(enabled);
    } else if (button.id === 'ec-replay') {
      if (replay) {
        stopReplay();
        return;
      }
      state.day = 0;
      state.cutoff = days[0] || '';
      update();
      button.textContent = 'Pause history';
      replay = setInterval(() => {
        if (state.day >= days.length - 1) {
          stopReplay();
          return;
        }
        state.day++;
        state.cutoff = state.day === days.length - 1 ? '' : days[state.day];
        update();
      }, 1500);
    }
  });
  on($('#ec-search'), 'input', (event) => {
    state.search = event.target.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => update({ reset: true }), 220);
  });
  for (const [id, key] of [
    ['ec-entity', 'entity'],
    ['ec-network', 'network'],
    ['ec-intelligence', 'intelligence'],
    ['ec-status', 'status'],
    ['ec-intake', 'intake'],
  ])
    on($('#' + id), 'change', (event) => {
      state[key] = event.target.value;
      if (key === 'entity')
        history.replaceState(
          null,
          '',
          '#eclipse?' +
            new URLSearchParams({
              ...(state.entity ? { entity: state.entity } : {}),
              ...(state.product ? { product: state.product } : {}),
              ...(state.intelligence !== 'all' ? { scope: state.intelligence } : {}),
              ...(state.intake ? { intake: state.intake } : {}),
            }),
        );
      update({ reset: true });
    });
  on($('#ec-time'), 'input', (event) => {
    stopReplay();
    state.day = Number(event.target.value);
    state.cutoff = state.day === days.length - 1 ? '' : days[state.day];
    clearTimeout(searchTimer);
    state.page = 0;
    cancelDetail();
    selection = null;
    sourceDetail = null;
    searchTimer = setTimeout(() => update({ reset: false }), 180);
  });
  on(document, 'keydown', (event) => {
    if (
      event.defaultPrevented ||
      event.ctrlKey ||
      event.metaKey ||
      event.altKey ||
      event.target.closest('input,textarea,select,[contenteditable=true]')
    )
      return;
    if (event.key === 'Escape' && root.querySelector('.ec-instrument-options')?.open) {
      event.preventDefault();
      const details = root.querySelector('.ec-instrument-options');
      details.open = false;
      details.querySelector('summary')?.focus();
    } else if (event.key === '/') {
      event.preventDefault();
      $('#ec-search').focus();
    } else if (
      event.key === 'Escape' &&
      state.inspectorOpen &&
      window.matchMedia('(max-width:1050px)').matches
    ) {
      event.preventDefault();
      openInspector(false);
      $('#ec-inspect-toggle').focus({ preventScroll: true });
    } else if (event.key === 'Escape' && state.listOpen) {
      event.preventDefault();
      showList(false);
    }
  });
  on(document, 'visibilitychange', () => {
    if (document.hidden) stopReplay();
  });
  const drawerMedia = window.matchMedia('(max-width:1050px)');
  on(drawerMedia, 'change', (event) => openInspector(!event.matches));
  on(window, 'companion:motion', (event) => scene.motion(!!event.detail?.enabled));
  scene.motion(window.CosmicBackground?.motionEnabled?.() ?? true);
  openInspector(state.inspectorOpen);
  syncControls();
  if (snapshot.snapshot && snapshot.intelligence) {
    hydrate(snapshot);
    refreshFiltered();
    renderScene({ reset: true });
    renderInspector();
    root.dataset.ready = 'true';
    $('#ec-loading').hidden = true;
    $('#ec-canvas').setAttribute('aria-busy', 'false');
  } else loadIntelligence({ reset: true });
  requestJSON('/modules/observatory/static/geo/states.json', { signal, credentials: 'same-origin' })
    .then((value) => {
      if (alive) scene.geometry(value);
    })
    .catch((error) => {
      if (alive && error.name !== 'AbortError') {
        geographyFailed = true;
        $('#ec-region').disabled = true;
        root.dataset.mapWarning = 'true';
        if (state.view === 'atlas')
          $('#ec-map-caption').textContent =
            'Local geography could not load. Entity profiles and Records remain available.';
      }
    });
  return {
    destroy() {
      alive = false;
      window.CosmicBackground?.resetApproach?.({ immediate: true });
      activeJourney = null;
      scene.cancelApproach?.();
      aborter.abort();
      request?.abort();
      cancelDetail();
      clearTimeout(slowTimer);
      clearTimeout(searchTimer);
      stopReplay();
      scene.destroy();
      root.dataset.ready = 'destroyed';
    },
  };
}
