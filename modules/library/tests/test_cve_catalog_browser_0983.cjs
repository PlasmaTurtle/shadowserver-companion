/** Catalog UI acceptance using synthetic catalog responses and the real application shell. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
(async () => {
  const base = process.env.BASE_URL,
    folder = process.env.QA_DIR;
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    headless: true,
  });
  const errors = [],
    external = [],
    requests = [],
    checks = [];
  let downloaded = false,
    running = false,
    enabled = false;
  const status = () => ({
    total: downloaded ? 423897 : 0,
    bootstrap_complete: downloaded,
    enabled,
    stale: false,
    running,
    years_complete: downloaded ? [2002, 2003] : [],
    required_years: [2002, 2003],
    last_success_at: downloaded ? '2026-11-11T04:00:00Z' : null,
    next_check_at: downloaded ? '2026-11-12T04:00:00Z' : null,
    last_error: null,
    job: { status: running ? 'running' : 'idle', message: running ? 'Downloading CVEs…' : '' },
  });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: 'reduce',
    });
    await context.route('**/*', async (route) => {
      const req = route.request(),
        url = new URL(req.url());
      if (/^https?:/.test(url.protocol) && !req.url().startsWith(base + '/')) {
        external.push(req.url());
        return route.abort();
      }
      if (!url.pathname.startsWith('/api/cve-catalog/')) return route.continue();
      requests.push({ path: url.pathname, query: url.search, method: req.method() });
      let data;
      if (url.pathname.endsWith('/sync')) {
        running = true;
        enabled = true;
        data = status();
      } else if (url.pathname.endsWith('/cancel')) {
        running = false;
        data = status();
      } else if (url.pathname.endsWith('/settings')) {
        enabled = req.postDataJSON().enabled;
        data = status();
      } else if (url.pathname.endsWith('/status')) data = status();
      else if (url.pathname.endsWith('/products')) data = { items: [], total: 0 };
      else if (url.pathname.endsWith('/observations')) data = { items: [], total: 0, counts: {} };
      else if (url.pathname.endsWith('/search')) {
        const offset = Number(url.searchParams.get('offset') || 0);
        data = {
          total: downloaded ? 60 : 0,
          limit: 25,
          offset,
          items: downloaded
            ? Array.from({ length: 25 }, (_, i) => ({
                id: `CVE-2026-${10000 + offset + i}`,
                description:
                  i === 0
                    ? '<img src=x onerror="window.catalogInjected=true"> Apache synthetic record'
                    : 'Synthetic CVE description with a readable summary.',
                severity: 'CRITICAL',
                score: 9.8,
                status: 'Analyzed',
                modified: '2026-11-11T03:00:00Z',
              }))
            : [],
        };
      } else if (url.pathname.includes('/records/'))
        data = {
          cve: {
            id: url.pathname.split('/').pop(),
            vulnStatus: 'Analyzed',
            descriptions: [
              {
                lang: 'en',
                value:
                  '<script>window.catalogInjected=true</script> Apache synthetic record. A concise description of the observed vulnerability goes here.',
              },
            ],
            published: '2026-01-01T00:00:00Z',
            lastModified: '2026-11-11T03:00:00Z',
            metrics: {
              cvssMetricV31: [
                {
                  type: 'Primary',
                  source: 'nvd@nist.gov',
                  cvssData: {
                    version: '3.1',
                    baseScore: 9.8,
                    baseSeverity: 'CRITICAL',
                    vectorString: 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H',
                  },
                },
              ],
            },
            references: [
              { url: 'https://example.test/advisory', tags: ['Vendor Advisory'] },
              { url: 'javascript:alert(1)' },
            ],
          },
          source: {
            url: 'https://nvd.nist.gov/feeds/json/cve/2.0/nvdcve-2.0-2026.json.gz',
            retrieved_at: '2026-11-11T04:00:00Z',
            record_sha256: 'a'.repeat(64),
          },
        };
      else throw Error('Unknown fixture endpoint ' + url.pathname);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(data),
      });
    });
    const page = await context.newPage();
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(process.env.LAUNCH_URL);
    await page.locator('.dm-workspace').waitFor();
    await page.locator('[data-nav="library"]').click();
    await page.locator('#cve-catalog').waitFor();
    assert(
      !requests.some((request) => request.path.endsWith('/search')),
      'Inactive CVEs are not fetched',
    );
    await page.locator('[data-catalog-view="cves"]').click();
    await page.getByRole('button', { name: 'Download catalog', exact: true }).click();
    await page.getByRole('button', { name: 'Pause download', exact: true }).waitFor();
    assert.equal(requests.filter((r) => r.path.endsWith('/sync')).length, 1);
    await page.getByRole('button', { name: 'Pause download', exact: true }).click();
    await page.getByRole('button', { name: 'Download catalog', exact: true }).waitFor();
    downloaded = true;
    running = false;
    enabled = true;
    await page.evaluate(async () => {
      const app = (await import('/modules/ui/static/main.js')).application;
      await app.actions.refreshCatalogStatus();
      await app.actions.searchCatalog('', '', 0);
    });
    await page.locator('[data-catalog-cve]').first().waitFor();
    assert.match(await page.locator('.catalog-summary').innerText(), /423,897/);
    await page.locator('[data-catalog-cve]').first().click();
    await page.locator('.catalog-record h3').waitFor();
    assert.equal(await page.locator('.catalog-score strong').innerText(), '9.8');
    assert.equal(await page.evaluate(() => Boolean(window.catalogInjected)), false);
    assert.equal(await page.locator('#cve-catalog a[href^="javascript:"]').count(), 0);
    await page.locator('#catalog-query').fill('Apache');
    await page.locator('#catalog-severity').selectOption('CRITICAL');
    await page.locator('#catalog-search-form button').click();
    await page.waitForFunction(
      () => document.querySelector('#cve-catalog-results')?.getAttribute('aria-busy') !== 'true',
    );
    assert(
      requests.some((r) => r.query.includes('q=Apache') && r.query.includes('severity=CRITICAL')),
    );
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await page.locator('[data-catalog-cve="CVE-2026-10025"]').waitFor();
    checks.push(
      'One-click download, pause, local query/severity, pagination and record disclosure',
    );
    await page.locator('.dm-library-edit > summary').click();
    await page
      .locator('#resource-form [name="body"]')
      .fill('Unsaved explainer survives catalog updates');
    await page.locator('#catalog-enabled').uncheck();
    await page.waitForFunction(() => !document.querySelector('#catalog-enabled')?.checked);
    await page.evaluate(async () => {
      const app = (await import('/modules/ui/static/main.js')).application;
      await app.actions.refreshCatalogStatus();
    });
    assert.equal(
      await page.locator('#resource-form [name="body"]').inputValue(),
      'Unsaved explainer survives catalog updates',
    );
    checks.push('Daily toggle and background status refresh preserve unsaved explainer edits');
    fs.mkdirSync(folder, { recursive: true });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(folder, 'catalog-desktop.png') });
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2),
      false,
    );
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(folder, 'catalog-mobile.png') });
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2),
      false,
    );
    checks.push('Desktop and 390px mobile layout fit; unsafe descriptions and links stay inert');
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    const result = {
      passed: true,
      method: 'Real application shell with synthetic catalog HTTP fixtures',
      checks,
      errors,
      external_requests: external,
    };
    fs.writeFileSync(path.join(folder, 'result.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
