/** API setup, key isolation and partial catalog coverage. */
const assert = require('node:assert/strict');
(async () => {
  const { install } = await import('../../settings/static/settings.js');
  const { install: installCatalog } = await import('../../library/static/cve_catalog.js');
  const nodes = new Map();
  const requests = [];
  const ctx = {
    state: { resources: {}, navigation: { boot: { settings: {} } } },
    actions: {
      esc: (v) =>
        String(v ?? '')
          .replaceAll('<', '&lt;')
          .replaceAll('"', '&quot;'),
      num: (v) => String(v),
      stamp: (v) => String(v),
      $: (selector) => nodes.get(selector),
      toast: () => {},
      api: async (url, request) => {
        requests.push([url, request]);
        return url === '/api/shadowserver/status'
          ? { configured: true, connected: true }
          : { configured: true, source: 'windows', remember_supported: true };
      },
    },
  };
  installCatalog(ctx);
  install(ctx);
  let html = ctx.actions.nvdKeyMarkup({
    configured: true,
    source: 'windows',
    remember_supported: true,
  });
  assert.match(html, /API connections/);
  assert.match(html, /Windows Credential Manager/);
  assert.match(html, /type="password"/);
  assert.doesNotMatch(html, /value="[a-f0-9-]{36}"/i);
  assert.match(html, /href="#data\?tab=api"/);
  const panel = { outerHTML: 'original', querySelector: () => ({ value: '' }) };
  nodes.set('#nvd-key-panel', panel);
  await ctx.actions.loadNvdKeyStatus();
  assert.deepEqual(
    requests.map(([url]) => url),
    ['/api/nvd/credentials', '/api/shadowserver/status'],
  );
  assert.match(panel.outerHTML, /Connected/);
  panel.outerHTML = 'typed form';
  panel.querySelector = () => ({ value: 'new secret' });
  await ctx.actions.loadNvdKeyStatus();
  assert.equal(panel.outerHTML, 'typed form', 'Status retrieval preserves typed credentials');
  // Catalog daily updates remain independent when the retrieval schedule is off.
  const librarySummary = { innerHTML: '' };
  nodes.set('#settings-library-automation', librarySummary);
  nodes.set('#settings-section-automation', { outerHTML: '' });
  let resolveCatalog;
  ctx.actions.api = async (url) => {
    if (url === '/api/cve-catalog/status')
      return new Promise((resolve) => {
        resolveCatalog = resolve;
      });
    return url === '/api/shadowserver/status'
      ? { connected: true, schedule: { config: { enabled: false } } }
      : { configured: true, source: 'windows' };
  };
  panel.querySelector = () => ({ value: '' });
  await ctx.actions.loadNvdKeyStatus();
  assert.match(
    panel.outerHTML,
    /Connected/,
    'Optional Library read does not block connection status',
  );
  resolveCatalog({ enabled: true, risk: { enabled: false } });
  await Promise.resolve();
  await Promise.resolve();
  html = ctx.actions.settingsAutomationMarkup({ schedule: { config: { enabled: false } } });
  assert.match(html, /This retrieval schedule is off/);
  assert.match(html, /Library daily reference updates: Enabled/);
  assert.match(html, /NVD catalog updates are enabled separately/);
  assert.match(html, /href="#library">Manage daily updates/);
  assert.doesNotMatch(html, /Reports and reference updates run when you request them|>Manual</);
  ctx.actions.api = async () => ({ enabled: false, risk: { enabled: true } });
  await ctx.actions.loadSettingsLibraryAutomation();
  assert.match(librarySummary.innerHTML, /Library daily reference updates: Enabled/);
  assert.match(librarySummary.innerHTML, /EPSS &amp; KEV|EPSS & KEV/);
  ctx.actions.api = async () => {
    throw new Error('Catalog unavailable');
  };
  await ctx.actions.loadSettingsLibraryAutomation();
  assert.match(librarySummary.innerHTML, /Status unavailable/);
  const status = {
    api_access: { configured: false },
    total: 2,
    bootstrap_complete: false,
    api_bootstrap: { start_index: 2 },
    job: {},
  };
  html = ctx.actions.catalogStatusMarkup(status);
  assert.match(html, /optional NVD key/);
  assert.match(html, /href="#settings">Configure NVD key/);
  assert.doesNotMatch(html, /data-action="catalog-sync"[^>]*disabled/);
  assert.match(html, /Resume download/);
  assert.match(html, /Partially downloaded/);
  status.api_access.configured = true;
  status.running = true;
  status.job = { status: 'running', records: 2000, total_records: 4000 };
  html = ctx.actions.catalogStatusMarkup(status);
  assert.match(html, /2000 of 4000 CVEs/);
  assert.match(html, /Pause download/);
  status.running = false;
  status.bootstrap_complete = true;
  status.stale = false;
  status.job = {};
  html = ctx.actions.catalogStatusMarkup(status);
  assert.match(html, /Sync now/);
  assert.doesNotMatch(html, /Add NVD API key/);
  console.log(
    'API setup, asynchronous status isolation, secret-free controls and resumable catalog progress passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
