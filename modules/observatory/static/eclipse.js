/* Eclipse Observatory: local observed records, never a simulated threat feed. */
(() => {
  'use strict';
  let active = null,
    generation = 0;
  const arrow =
    '<svg class="ec-arrow" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 13 13 3M4 3h9v9"/></svg>';
  window.Eclipse = {
    loading() {
      return `<section id="eclipse" class="ec-opening" aria-label="Eclipse Observatory" aria-busy="true">
<header class="ec-mast"><div class="ec-view-identity"><span class="ec-aperture" aria-hidden="true"></span><div><h1>Observatory</h1><span>Dark Matter Field</span></div></div><a class="ec-exit ec-text-btn" href="#workspace">Workspace ${arrow}</a></header>
<div class="ec-opening-stage"><div class="ec-opening-status" role="status" aria-live="polite"><span class="spinner" aria-hidden="true"></span><h2>Opening the field</h2><p>Resolving findings and their connections…</p></div></div></section>`;
    },
    render(data, esc) {
      return `<section id="eclipse" aria-label="Eclipse Observatory" data-inspector-open="false" data-view="field">
<header class="ec-mast">
  <div class="ec-view-identity"><span class="ec-aperture" aria-hidden="true"></span><div><h1>Observatory</h1><span id="ec-scope-caption">All local findings</span></div></div>
  <nav class="ec-views" aria-label="Observatory views"><button type="button" data-ec-view="field" aria-pressed="true">Field</button><button type="button" data-ec-view="atlas" aria-pressed="false">Atlas</button><button type="button" data-ec-view="pulse" aria-pressed="false">Pulse</button><button type="button" id="ec-view-records" data-ec-view="records" aria-pressed="false">Records</button></nav>
  <button type="button" class="ec-btn ec-back-field" id="ec-back-field" hidden>← Return to field</button>
  <a class="ec-exit ec-text-btn" href="#workspace" aria-label="Return to Workspace">Workspace ${arrow}</a>
</header>
<div class="ec-command">
  <div class="ec-search-wrap"><label class="ec-sr-only" for="ec-search">Search findings</label><span aria-hidden="true">⌕</span><input id="ec-search" type="search" maxlength="300" placeholder="Organization, hostname, IP or finding" autocomplete="off"><kbd>/</kbd></div>
  <button type="button" class="ec-btn" id="ec-filter-toggle" aria-expanded="false" aria-controls="ec-filters">Filters <span id="ec-filter-count"></span></button>
  <button type="button" class="ec-btn ec-quiet" id="ec-reset">Reset</button>
  <a class="ec-text-btn" href="#library?view=dark-matter">Filter source fields</a>
  <button type="button" class="ec-btn ec-quiet" id="ec-refresh" aria-label="Refresh current scope">↻</button>
  <button type="button" class="ec-btn ec-inspect-toggle" id="ec-inspect-toggle" aria-expanded="false" aria-controls="ec-inspector">Explore <span id="ec-pattern-count">0</span></button>
  <details class="ec-instrument-options"><summary>Instruments</summary><div class="ec-instrument-menu">
    <div class="ec-lenses" role="group" aria-label="Connection lens"><span class="ec-eyebrow">Group by</span>${[
      ['organization', 'Organization'],
      ['vulnerability', 'Finding'],
      ['ip', 'IP'],
      ['service', 'Service'],
      ['version', 'Version'],
    ]
      .map(
        ([value, label]) =>
          `<button type="button" data-ec-lens="${value}" aria-pressed="${value === 'organization'}">${label}</button>`,
      )
      .join('')}</div>
    <div class="ec-levels" role="group" aria-label="Detail level"><span class="ec-eyebrow">Depth</span><button type="button" data-ec-level="overview" aria-pressed="true">Signals</button><button type="button" data-ec-level="endpoints" aria-pressed="false">Assets</button><button type="button" data-ec-level="sources" aria-pressed="false">Evidence</button></div>
    <button type="button" class="ec-motion-control ec-btn ec-quiet" id="ec-motion" aria-pressed="true">Motion on</button>
  </div></details>
</div>
<div id="ec-scope-chips" class="ec-scope-chips" aria-label="Active scope" hidden></div>
<div id="ec-filters" class="ec-filters" hidden>
  <label>Entity<select id="ec-entity"><option value="">All entities</option>${(data.entities || []).map((e) => `<option value="${esc(e.id)}">${esc(e.name || e.domain)}</option>`).join('')}</select></label>
  <label>Network<select id="ec-network"><option value="">All ASNs</option></select></label>
  <label>Intelligence<select id="ec-intelligence"><option value="all">All findings</option><option value="critical">Critical findings</option><option value="critical_kev">Critical + KEV</option><option value="kev">Known exploited · KEV</option><option value="ransomware">Known ransomware use</option></select></label>
  <label>Intake<select id="ec-intake"><option value="">All observations</option><option value="lead">Admitted</option><option value="dark_matter">Dark Matter</option><option value="unclassified">Not classified by Accretion</option></select></label>
  <label>Status<select id="ec-status"><option value="">All statuses</option><option value="qualified">Qualified</option><option value="review">Attribution review</option><option value="pending">Pending</option><option value="delivered">Delivered</option><option value="excluded">Excluded</option><option value="unqualified">Unqualified</option></select></label>
  <button type="button" id="ec-unplaced" class="ec-btn" aria-pressed="false">Unplaced <span id="ec-unplaced-count">0</span></button>
</div>
${(data.warnings || []).length ? `<div class="ec-warning" role="status">${data.warnings.map(esc).join('<br>')}</div>` : ''}
<div class="ec-census" aria-label="Current scope"><span><strong id="ec-rows">—</strong> findings</span><span><strong id="ec-hosts">—</strong> assets</span><span class="ec-census-entities"><strong id="ec-entities">—</strong> entities</span><span class="ec-census-evidence"><strong id="ec-dark-matter">—</strong> dark observations</span><span class="ec-census-evidence"><strong id="ec-observations">—</strong> observations</span></div>
<div id="ec-selection" class="ec-selection" hidden>
  <span class="ec-selection-indicator" aria-hidden="true"></span>
  <div class="ec-selection-identity"><span id="ec-selection-kind">Selected</span><strong id="ec-selection-name"></strong><span id="ec-selection-support"></span></div>
  <div class="ec-selection-navigation"><span id="ec-drill-context" class="ec-drill-context"></span><div id="ec-drill-actions" class="ec-drill-actions" role="group" aria-label="Explore selected object"></div></div>
  <button type="button" class="ec-btn ec-quiet" id="ec-locate">Focus</button><button type="button" class="ec-btn" id="ec-selection-inspect">Details</button><button type="button" class="ec-text-btn" data-ec-action="clear" aria-label="Clear selection">×</button>
</div>
<div class="ec-workbench">
  <div class="ec-stage">
    <div class="ec-viewport" id="ec-viewport">
      <canvas id="ec-canvas" tabindex="0" role="img" aria-label="Observed relationship field" aria-describedby="ec-canvas-help"></canvas>
      <div class="ec-data-heading"><span id="ec-scene-kicker" class="ec-eyebrow">DARK MATTER FIELD</span><h2 id="ec-scene-title">Dark Matter Field</h2><span id="ec-scene-subtitle"></span></div>
      <div id="ec-map-empty" class="ec-map-empty" hidden></div><div id="ec-tooltip" class="ec-tooltip" hidden></div><div id="ec-loading" class="ec-loading" role="status">Resolving findings…</div>
      <div class="ec-space-key"><span id="ec-space-key">● organization &nbsp; ◇ finding</span><span id="ec-density-legend" class="ec-density-legend" aria-label="Observation density, separate from outreach priority"><span>Density</span><i data-density="normal"></i>≤50 <i data-density="yellow"></i>51–200 <i data-density="red"></i>201–1,000 <i data-density="purple"></i>&gt;1,000</span><span id="ec-scene-coordinate">FIELD / SIGNALS</span></div>
      <div class="ec-scene-controls"><button type="button" class="ec-btn" id="ec-zoom-out" aria-label="Zoom out">−</button><output id="ec-zoom-level" aria-label="Zoom level">100%</output><button type="button" class="ec-btn" id="ec-zoom-in" aria-label="Zoom in">+</button><button type="button" class="ec-btn" id="ec-fit">Fit</button><button type="button" class="ec-btn" id="ec-region" hidden>Fit jurisdiction</button></div>
      <button type="button" class="ec-mobile-inspect" id="ec-mobile-inspect">Inspect selection ${arrow}</button>
    </div>
    <nav id="ec-field-navigation" class="ec-field-navigation" aria-label="Field pages" hidden><button type="button" class="ec-btn" id="ec-field-prev">← Newer</button><output id="ec-field-range" aria-live="polite"></output><button type="button" class="ec-btn" id="ec-field-next">Older →</button></nav>
    <div class="ec-scene-caption"><span id="ec-map-caption">Newest changes nearest.</span><button type="button" class="ec-text-btn" id="ec-list-toggle" aria-expanded="false" aria-controls="ec-records">Records <span id="ec-list-total">0</span> ${arrow}</button></div>
    <p id="ec-canvas-help" class="ec-sr-only">Drag to pan. Scroll or plus and minus to zoom. Arrow keys pan; zero fits. Left and right brackets select objects; Enter focuses. Use Explore for the entity directory or Records for findings.</p>
    <details class="ec-history-panel"><summary>Observation history <span>Time range &amp; replay</span></summary><div class="ec-timebar"><div class="ec-time-heading"><span>Observed through</span><output id="ec-cutoff" for="ec-time">All dates</output><button type="button" class="ec-text-btn" id="ec-replay">Play history</button></div><div id="ec-histogram" class="ec-histogram" aria-hidden="true"></div><label class="ec-sr-only" for="ec-time">Include observations through scan date</label><input id="ec-time" type="range" min="0" max="0" value="0"><div class="ec-time-labels"><span id="ec-first-day"></span><span id="ec-unknown-dates"></span><span id="ec-last-day"></span></div></div></details>
  </div>
  <aside class="ec-inspector" id="ec-inspector" aria-label="Selection and connections" tabindex="-1"><div class="ec-drawer-bar"><span id="ec-drawer-title">Explore the field</span><button type="button" id="ec-drawer-close" class="ec-btn" aria-label="Close inspector">×</button></div><div id="ec-inspector-content"></div></aside>
</div>
<section id="ec-records" class="ec-records" aria-label="Finding records" hidden><div class="ec-records-head"><h2><span id="ec-record-title">Findings</span> <span id="ec-record-count"></span></h2><button type="button" id="ec-record-findings" class="ec-btn ec-quiet" data-ec-action="record-findings" hidden>Findings</button><button type="button" class="ec-btn" id="ec-records-close">Return to view</button></div><div id="ec-record-list"></div><div class="ec-pagination"><button type="button" class="ec-btn" id="ec-prev">Previous</button><output id="ec-page"></output><button type="button" class="ec-btn" id="ec-next">Next</button></div></section>
<footer class="ec-status-strip"><span id="ec-data-status">Local source observations</span><span id="ec-coverage">Local records only</span><span id="ec-revision" class="ec-revision"></span><a href="#data">Shadowserver Data ${arrow}</a></footer><div id="ec-announcement" class="ec-sr-only" role="status" aria-live="polite"></div></section>`;
    },
    mount(container, data) {
      this.destroy();
      const ticket = ++generation,
        root = container.querySelector('#eclipse');
      if (!root) return;
      import('/modules/observatory/static/eclipse_controller.js')
        .then(({ mount }) => {
          if (ticket !== generation || !root.isConnected) return;
          active = mount(root, data);
        })
        .catch((error) => {
          if (ticket !== generation) return;
          const status = root.querySelector('#ec-loading');
          status.textContent = 'Observatory could not open: ' + error.message;
          status.setAttribute('role', 'alert');
        });
    },
    destroy() {
      generation++;
      active?.destroy();
      active = null;
    },
  };
})();
