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
  });
  const errors = [],
    external = [],
    requests = [],
    checks = [];
  const fieldValues = { weakness: 'CWE-79', attack_vector: 'NETWORK' };
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
  let releaseInitialProducts;
  const initialProductsReady = new Promise((resolve) => {
    releaseInitialProducts = resolve;
  });
  let firstProducts = true;
  let fieldGate;
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
      if (url.pathname.endsWith('/fields') && fieldGate) {
        const gate = fieldGate;
        fieldGate = null;
        await gate();
      }
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
      else if (url.pathname.endsWith('/products')) {
        if (firstProducts) {
          firstProducts = false;
          await initialProductsReady;
        }
        data = { items: [product], total: 1, index: { ready: true } };
      } else if (url.pathname.includes('/products/'))
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
      else if (
        url.pathname.endsWith('/fields/records') &&
        fieldValues[url.searchParams.get('field')] !== url.searchParams.get('value')
      )
        data = { items: [], total: 0 };
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
              value: fieldValues[url.searchParams.get('field')],
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
    await page.locator('#catalog-product-query').fill('Unsubmitted product query');
    await page.locator('#catalog-product-scope').selectOption('kev');
    releaseInitialProducts();
    await page.locator('[data-catalog-product="p-example"]').waitFor();
    assert.equal(
      await page.locator('#catalog-product-query').inputValue(),
      'Unsubmitted product query',
    );
    assert.equal(await page.locator('#catalog-product-scope').inputValue(), 'kev');
    await page.locator('#catalog-product-query').fill('');
    await page.locator('#catalog-product-scope').selectOption('critical');
    checks.push(
      'Delayed initial results preserve query and scope edits in the already usable search form',
    );
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
      await page.locator('#catalog-fields-panel .catalog-field-coverage').innerText(),
      /1 missing or unclassified/,
    );
    await page.locator('#catalog-field').selectOption('attack_vector');
    await page.locator('#catalog-field-form button').click();
    await page.locator('[data-catalog-field-value="NETWORK"]').click();
    await page.locator('#catalog-cves-panel').waitFor({ state: 'visible' });
    assert.match(await page.locator('#catalog-cve-context').innerText(), /NETWORK/);
    let resumeField;
    const holdField = new Promise((resolve) => {
      resumeField = resolve;
    });
    let fieldRequested;
    const oldFieldRequested = new Promise((resolve) => {
      fieldRequested = resolve;
    });
    fieldGate = () => {
      fieldRequested();
      return holdField;
    };
    await page.locator('[data-catalog-view="fields"]').click();
    await oldFieldRequested;
    await page.locator('#catalog-field').selectOption('weakness');
    resumeField();
    await page.waitForFunction(
      () => !document.querySelector('#catalog-fields-panel').hasAttribute('aria-busy'),
    );
    assert.equal(await page.locator('#catalog-field').inputValue(), 'weakness');
    await page.locator('#catalog-field-form button').click();
    await page.locator('[data-catalog-field-value="CWE-79"]').waitFor();
    await page.locator('[data-catalog-view="cves"]').click();
    await page.locator('#cve-catalog-results [data-catalog-cve="CVE-2026-12345"]').waitFor();
    await page.locator('[data-action="catalog-save-view"]').click();
    await page.waitForFunction(
      () => document.querySelectorAll('#catalog-saved-view option').length === 2,
    );
    const savedViewId = await page.locator('#catalog-saved-view').inputValue();
    assert(savedViewId);
    await page.locator('#catalog-view-name').fill('Network critical review');
    await page.locator('[data-action="catalog-update-view"]').click();
    await page.waitForFunction(
      () =>
        document.querySelector('#catalog-saved-view option:checked')?.textContent ===
        'Network critical review',
    );
    const persisted = await page.evaluate(async () => (await fetch('/api/library/views')).json());
    const savedView = persisted.find((view) => view.id === savedViewId);
    assert.equal(savedView.revision, 2);
    assert.equal(savedView.selection.field, 'weakness');
    assert.deepEqual(savedView.selection.fieldSelection, {
      field: 'attack_vector',
      value: 'NETWORK',
    });
    const shareLink = await page.locator('#catalog-view-link').getAttribute('href');
    assert.match(shareLink, /field_value=NETWORK/);
    await page.locator('[data-catalog-view="changes"]').click();
    await page.locator('.catalog-change').waitFor();
    assert.match(await page.locator('.catalog-change').innerText(), /HIGH/);
    assert.match(await page.locator('.catalog-change').innerText(), /CRITICAL/);
    await page.locator('[data-action="catalog-review-impact"]').click();
    await page.locator('#catalog-impact-completed').waitFor();
    assert.match(await page.locator('#catalog-change-impact').innerText(), /changes no draft/);
    assert.match(
      await page.locator('#catalog-change-impact').innerText(),
      /No investigations in this scope/,
    );
    await page.locator('#catalog-impact-completed').check();
    await page.waitForFunction(
      () => document.querySelector('#catalog-change-impact')?.getAttribute('aria-busy') !== 'true',
    );
    assert.equal(await page.locator('#catalog-impact-completed').isChecked(), true);
    await page.locator('#catalog-saved-view').selectOption(savedViewId);
    await page.locator('#catalog-cves-panel').waitFor({ state: 'visible' });
    assert.match(await page.locator('#catalog-cve-context').innerText(), /NETWORK/);
    const another = await context.newPage();
    await another.goto(base + '/#library?view=changes');
    await another
      .locator('#catalog-saved-view option[value="' + savedViewId + '"]')
      .waitFor({ state: 'attached' });
    await another.locator('#catalog-saved-view').selectOption(savedViewId);
    await another.locator('#catalog-cves-panel').waitFor({ state: 'visible' });
    await another.locator('#cve-catalog-results [data-catalog-cve="CVE-2026-12345"]').waitFor();
    assert.match(
      await another.locator('#catalog-cve-context').innerText(),
      /attack_vector.*NETWORK/,
    );
    assert.equal(
      await another.locator('#catalog-view-name').inputValue(),
      'Network critical review',
    );
    await another.locator('#catalog-view-name').fill('Temporary research');
    await another.locator('[data-action="catalog-save-view"]').click();
    await another.waitForFunction(
      () => document.querySelectorAll('#catalog-saved-view option').length === 3,
    );
    await another.locator('[data-action="catalog-remove-view"]').click();
    await another.waitForFunction(
      () => document.querySelectorAll('#catalog-saved-view option').length === 2,
    );
    const explainers = await another.evaluate(async () => (await fetch('/api/explainers')).json());
    assert(explainers.length > 0);
    await another.locator('#library-search-query').fill(explainers[0].title);
    await another.locator('#library-search-form button').click();
    await another
      .locator('#library-search-results a[href*="item=' + explainers[0].id + '"]')
      .waitFor();
    assert.equal(await another.locator('.catalog-search-group').count(), 4);
    for (const title of ['CVEs', 'Products']) {
      const group = another.locator('.catalog-search-group').filter({
        has: another.getByRole('heading', { name: title, exact: true }),
      });
      assert.match(await group.innerText(), /No CVE records are stored locally/i);
      assert.doesNotMatch(await group.innerText(), /No matching references/);
    }
    await another.locator('#library-search-query').fill('basic-auth');
    await another.locator('#library-search-form button').click();
    const guideLink = another.locator('#library-search-results a[href*="guide="]').first();
    await guideLink.click();
    const openedGuide = another.locator('#library-reviewed-guides details[data-guide-id][open]');
    await openedGuide.locator('a[href*="rfc7617"]').waitFor();
    await another.reload();
    await openedGuide.locator('a[href*="rfc7617"]').waitFor();
    await another.locator('[data-catalog-view="reported"]').click();
    await another.getByRole('heading', { name: 'Most reported CVEs' }).waitFor();
    let observationRevision = 'A';
    await another.route('**/api/library/observed-references?*', (route) => {
      const offset = Number(new URL(route.request().url()).searchParams.get('cve_offset'));
      const group = { total: 11, offset, limit: 10, observations_with_value: 20 };
      return route.fulfill({
        json: {
          revision: observationRevision,
          observation_count: 23,
          coverage_complete: false,
          warnings: ['Partial archive'],
          cves: {
            ...group,
            items: [{ value: offset ? 'CVE-2026-1023' : 'CVE-2026-1001', count: offset ? 1 : 9 }],
          },
          products: {
            ...group,
            total: 1,
            offset: 0,
            items: [{ value: 'Example <em>router</em>', count: 15 }],
          },
        },
      });
    });
    await another.locator('[data-catalog-view="reported"]').click();
    const ranking = another.locator('#catalog-reported-panel');
    await ranking.getByRole('link', { name: 'CVE-2026-1001' }).waitFor();
    assert.match(await ranking.innerText(), /Coverage is partial/);
    assert.equal(await ranking.locator('td em').count(), 0);
    await ranking.getByRole('button', { name: 'Next' }).click();
    await ranking.getByRole('link', { name: 'CVE-2026-1023' }).waitFor();
    await ranking.getByRole('button', { name: 'Previous' }).click();
    await ranking.getByRole('link', { name: 'CVE-2026-1001' }).waitFor();
    observationRevision = 'B';
    await ranking.getByRole('button', { name: 'Next' }).click();
    await ranking.getByText(/ranking changed/).waitFor();
    await ranking.getByRole('link', { name: 'CVE-2026-1001' }).waitFor();
    await another.locator('[data-catalog-view="changes"]').click();
    await another.locator('#library-open-kev p').first().waitFor();
    let vendorFetches = 0;
    await another.route('**/api/library/vendor-statements/redhat/*/refresh', async (route) => {
      vendorFetches++;
      return route.fulfill({
        json: {
          status: 'available',
          retrieved_at: '2026-11-22',
          sha256: 'f'.repeat(64),
          revision_id: 'synthetic-redhat-revision',
          publisher_statement: 'Exact <em>publisher text</em>.',
          total: 0,
          statements: [],
        },
      });
    });
    await another.goto(base + '/#library?view=cves&cve=CVE-2026-12345');
    await another.getByRole('button', { name: 'Fetch from Red Hat' }).click();
    assert.equal(vendorFetches, 1);
    const statement = another.locator('#catalog-vendor-guidance blockquote');
    assert.equal(await statement.innerText(), 'Exact <em>publisher text</em>.');
    assert.equal(await statement.locator('em').count(), 0);
    await another.getByText('Captured source', { exact: true }).click();
    assert.equal(
      await another.locator('#catalog-vendor-guidance code').innerText(),
      'f'.repeat(64),
    );
    await another.close();
    const shared = await context.newPage();
    await shared.goto(base + '/' + shareLink);
    await shared.locator('#cve-catalog-results [data-catalog-cve="CVE-2026-12345"]').waitFor();
    assert.match(
      await shared.locator('#catalog-cve-context').innerText(),
      /attack_vector.*NETWORK/,
    );
    await shared.locator('[data-catalog-view="fields"]').click();
    await shared.locator('[data-catalog-field-value="CWE-79"]').waitFor();
    assert.equal(await shared.locator('#catalog-field').inputValue(), 'weakness');
    await shared.close();
    checks.push(
      'Field coverage and value drilldown, saved cohort restoration, shareable selection and semantic changes',
      'Named views persist across windows, rename with revision checks, and remove independently; typed search uses real local reference endpoints',
      'Changes review loads through the actual impact endpoint with completed-work toggle and explicit read-only guidance',
      'Reviewed finding links survive reload, workspace frequency and open-case comparisons load, and vendor prose and capture receipts render safely',
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
