/** Real shell acceptance with deterministic public-reference fixtures. */
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
    args: ['--no-sandbox', '--no-zygote', '--single-process'],
  });
  const errors = [],
    external = [],
    requests = [],
    checks = [];
  const product = {
    id: 'p-example',
    vendor: 'Example Software',
    product: 'Mail Server',
    cve_count: 2,
    critical_count: 2,
    kev_count: 1,
    sources: ['CPE', 'CNA'],
  };
  const observation = {
    counts: {
      observations: 4,
      endpoints: 2,
      entities: 1,
      pending_entities: 1,
      notified_entities: 0,
    },
    items: [
      {
        id: 'row1',
        hostname: 'mail.example.test',
        ip: '192.0.2.1',
        product: 'Mail Server',
        version: '1.1.0',
        observed_day: '2026-11-10',
        entity_name: 'Example Organization',
        entity_url: '#entity/example',
        case_url: '#investigations/example',
        case_stage: 'Documentation',
        matched_cves: ['CVE-2026-12345'],
        basis: 'Reported CVE',
      },
    ],
    versions: [{ version: '1.1.0', count: 4, entities: 1 }],
    total: 4,
  };
  const risk = {
    epss: { score: 0.25, percentile: 0.99, score_date: '2026-11-11', model_version: 'fixture-v1' },
    kev: {
      listed: true,
      entry: {
        dateAdded: '2026-11-10',
        requiredAction: 'Apply vendor updates.',
        knownRansomwareCampaignUse: 'Unknown',
      },
      source: { retrieved_at: '2026-11-11T00:00:00Z' },
    },
  };
  let enabled = true;
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
      if (url.pathname.endsWith('/settings')) enabled = req.postDataJSON().enabled;
      if (['/status', '/settings', '/sync', '/risk/sync'].some((end) => url.pathname.endsWith(end)))
        data = {
          total: 423897,
          enabled,
          bootstrap_complete: true,
          stale: false,
          running: false,
          job: { status: 'idle' },
          index_status: { ready: true },
          last_success_at: '2026-11-11T00:00:00Z',
          risk: {
            epss: {
              count: 400000,
              last_success_at: '2026-11-11T00:00:00Z',
              score_date: '2026-11-11',
            },
            kev: { count: 1779, last_success_at: '2026-11-11T00:00:00Z' },
            running: false,
          },
        };
      else if (url.pathname.endsWith('/observations')) data = observation;
      else if (url.pathname.endsWith('/products'))
        data = { items: [product], total: 1, index: { ready: true } };
      else if (url.pathname.includes('/products/'))
        data = {
          product,
          total: 1,
          items: [
            {
              id: 'CVE-2026-12345',
              description: 'Synthetic reference. <img src=x onerror="window.catalogInjected=true">',
              severity: 'CRITICAL',
              score: 9.8,
              kev: true,
              versions: [
                {
                  source: 'CNA',
                  range: '>= 1.0.0, < 2.0.0',
                  status: 'affected',
                  match: url.searchParams.get('version')
                    ? { state: 'candidate', reason: 'Version falls within this affected range' }
                    : null,
                  conditions: 'Windows edition required',
                },
              ],
            },
          ],
        };
      else if (url.pathname.endsWith('/fields/records') || url.pathname.endsWith('/search'))
        data = {
          items: [
            {
              id: 'CVE-2026-12345',
              description: 'Synthetic reference record',
              severity: 'CRITICAL',
              score: 9.8,
            },
          ],
          total: 1,
        };
      else if (url.pathname.endsWith('/fields'))
        data = {
          field: url.searchParams.get('field'),
          population: 2,
          covered: 1,
          missing: 1,
          available_fields: [
            { id: 'weakness', label: 'Weakness' },
            { id: 'attack_vector', label: 'Attack vector' },
          ],
          items: [
            {
              value: url.searchParams.get('field') === 'attack_vector' ? 'NETWORK' : 'CWE-79',
              count: 1,
            },
          ],
          index: { ready: true },
        };
      else if (url.pathname.endsWith('/changes'))
        data = {
          items: [
            {
              id: 1,
              cve_id: 'CVE-2026-12345',
              changed_at: '2026-11-11T00:00:00Z',
              fields: [{ field: 'severity', before: 'HIGH', after: 'CRITICAL' }],
            },
          ],
          total: 1,
        };
      else if (url.pathname.includes('/records/'))
        data = {
          cve: {
            id: 'CVE-2026-12345',
            vulnStatus: 'Analyzed',
            descriptions: [
              {
                lang: 'en',
                value:
                  'Synthetic reference description. <script>window.catalogInjected=true</script>',
              },
            ],
            metrics: {
              cvssMetricV40: [
                {
                  source: 'Example CNA',
                  type: 'Secondary',
                  cvssData: {
                    version: '4.0',
                    baseScore: 9.3,
                    baseSeverity: 'CRITICAL',
                    vectorString: 'CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N',
                  },
                },
              ],
              cvssMetricV31: [
                {
                  source: 'NVD',
                  type: 'Primary',
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
          risk,
          source: {
            retrieved_at: '2026-11-11T00:00:00Z',
            url: 'https://nvd.nist.gov/feeds/json/cve/2.0/nvdcve-2.0-2026.json.gz',
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
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(process.env.LAUNCH_URL);
    await page.locator('.dm-workspace').waitFor();
    await page.locator('[data-nav="library"]').click();
    await page.locator('[data-catalog-product="p-example"]').waitFor();
    assert.equal(await page.locator('#catalog-product-scope').inputValue(), 'critical');
    await page.locator('[data-catalog-product="p-example"]').click();
    await page.locator('#catalog-product-detail .catalog-product-dossier').waitFor();
    await page.locator('#catalog-product-detail .catalog-observation-details > summary').click();
    assert.match(await page.locator('#catalog-product-detail').innerText(), /Reported CVE/);
    assert.match(await page.locator('#catalog-product-detail').innerText(), /KEV/);
    await page.locator('[data-catalog-observed-version="1.1.0"]').click();
    await page.waitForFunction(() => document.querySelector('#catalog-version')?.value === '1.1.0');
    assert.match(await page.locator('.catalog-version-ranges').innerText(), /candidate/i);
    assert(requests.some((r) => r.query.includes('version=1.1.0')));
    assert.match(
      await page.locator('#catalog-product-detail .text-link').getAttribute('href'),
      /^#eclipse\?product=p-example&scope=critical$/,
    );
    await page.locator('#catalog-product-scope').selectOption('critical_kev');
    await page.locator('#catalog-product-form button[type="submit"]').click();
    await page.waitForFunction(
      () => document.querySelector('#catalog-products-panel')?.getAttribute('aria-busy') !== 'true',
    );
    assert(requests.some((r) => r.query.includes('scope=critical_kev')));
    await page.locator('.dm-library-edit > summary').click();
    await page
      .locator('#resource-form [name="body"]')
      .fill('Unsaved explainer survives product research');
    await page.locator('#catalog-product-detail [data-catalog-cve]').first().click();
    await page.locator('.catalog-record h3').waitFor();
    assert.equal(await page.locator('.catalog-score strong').innerText(), '9.3');
    assert.match(await page.locator('.catalog-record-risk').innerText(), /25.00% probability/);
    assert.match(await page.locator('.catalog-record-risk').innerText(), /CISA KEV/);
    await page.getByText('CVSS assessments · 2', { exact: true }).click();
    assert.match(await page.locator('.catalog-record').innerText(), /Example CNA/);
    assert.equal(await page.evaluate(() => Boolean(window.catalogInjected)), false);
    assert.equal(await page.locator('#cve-catalog a[href^="javascript:"]').count(), 0);
    checks.push(
      'Product-first critical scope, observed versions, candidate comparison, KEV/EPSS and all CVSS assessments',
    );
    await page.locator('[data-catalog-view="fields"]').click();
    await page.locator('[data-catalog-field-value="CWE-79"]').waitFor();
    assert.match(
      await page.locator('.catalog-field-coverage').innerText(),
      /1 missing or unclassified/,
    );
    await page.locator('#catalog-field').selectOption('attack_vector');
    await page.locator('#catalog-field-form button').click();
    await page.locator('[data-catalog-field-value="NETWORK"]').click();
    await page.locator('#catalog-cves-panel').waitFor({ state: 'visible' });
    assert.match(await page.locator('#catalog-cve-context').innerText(), /NETWORK/);
    await page.locator('[data-action="catalog-save-view"]').click();
    assert.equal(await page.locator('#catalog-saved-view option').count(), 2);
    assert.match(
      await page.locator('#catalog-view-link').getAttribute('href'),
      /field_value=NETWORK/,
    );
    await page.locator('[data-catalog-view="changes"]').click();
    await page.locator('.catalog-change').waitFor();
    assert.match(await page.locator('.catalog-change').innerText(), /HIGH/);
    assert.match(await page.locator('.catalog-change').innerText(), /CRITICAL/);
    await page.locator('#catalog-saved-view').selectOption('0');
    await page.locator('#catalog-cves-panel').waitFor({ state: 'visible' });
    assert.match(await page.locator('#catalog-cve-context').innerText(), /NETWORK/);
    checks.push(
      'Field coverage and value drilldown, saved cohort restoration, shareable selection and semantic changes',
    );
    await page.locator('#catalog-enabled').uncheck();
    await page.waitForFunction(() => !document.querySelector('#catalog-enabled')?.checked);
    assert.equal(
      await page.locator('#resource-form [name="body"]').inputValue(),
      'Unsaved explainer survives product research',
    );
    await page.locator('[data-catalog-view="products"]').click();
    fs.mkdirSync(folder, { recursive: true });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(folder, 'library-products-desktop.png') });
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2),
      false,
    );
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: path.join(folder, 'library-products-mobile.png'),
      fullPage: true,
    });
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2),
      false,
    );
    checks.push(
      'Unsaved explainer preservation; 1440px desktop and 390px mobile fit; hostile source text remains inert',
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    const result = {
      passed: true,
      method: 'Real application shell with deterministic catalog, product and risk HTTP fixtures',
      checks,
      errors,
      external_requests: external,
    };
    fs.writeFileSync(path.join(folder, 'result.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
