/** Exact CVE/product scope plus optional live Library → Observatory → entity acceptance. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

async function modelChecks() {
  const { filterRows } = await import('../static/eclipse_model.js');
  const critical = { id: 'CVE-2026-80001', severity: 'CRITICAL', kev: false };
  const highKev = { id: 'CVE-2026-80002', severity: 'HIGH', kev: true };
  const ransomware = { kev: { entry: { knownRansomwareCampaignUse: 'Known' } } };
  const unrelated = { id: 'CVE-2026-80003', severity: 'CRITICAL', kev: true, risk: ransomware };
  const both = { id: 'CVE-2026-80004', severity: 'CRITICAL', kev: true, risk: ransomware };
  const common = { catalog_product_id: 'product:test', kev: true, ransomware_known: true };
  const rows = [
    {
      ...common,
      id: 'split',
      catalog_product_cves: [critical.id, highKev.id],
      catalog_findings: [critical, highKev],
    },
    {
      ...common,
      id: 'wrong-product',
      catalog_product_cves: [highKev.id],
      catalog_findings: [highKev, unrelated],
    },
    { ...common, id: 'correct', catalog_product_cves: [both.id], catalog_findings: [both] },
    { ...common, id: 'name-only', catalog_product_cves: [], catalog_findings: [unrelated] },
    { id: 'no-reference', tag: both.id, catalog_findings: [] },
  ];
  const selected = (filters) => filterRows(rows, filters).map((row) => row.id);
  assert.deepEqual(selected({ intelligence: 'critical_kev' }), [
    'wrong-product',
    'correct',
    'name-only',
  ]);
  assert.deepEqual(selected({ product: 'product:test', intelligence: 'critical_kev' }), [
    'correct',
  ]);
  assert.deepEqual(selected({ product: 'product:test', intelligence: 'critical' }), [
    'split',
    'correct',
  ]);
  assert.deepEqual(selected({ product: 'product:test', intelligence: 'kev' }), [
    'split',
    'wrong-product',
    'correct',
  ]);
  assert.equal(selected({}).length, rows.length);
  assert.deepEqual(selected({ product: 'product:test', intelligence: 'ransomware' }), ['correct']);
  assert.deepEqual(
    filterRows(
      [
        { id: 'exact', tag: both.id },
        { id: 'longer-identifier', tag: both.id + '0' },
      ],
      { search: both.id },
    ).map((row) => row.id),
    ['exact'],
    'A complete CVE search must not include another longer CVE identifier',
  );
  assert.deepEqual(
    filterRows(
      [
        { id: 'tag', tag: both.id },
        { id: 'explicit', reported_cves: [both.id] },
        { id: 'prefix', tag: both.id + '0' },
      ],
      { search: '  ' + both.id.toLowerCase() + '  ' },
    ).map((row) => row.id),
    ['tag', 'explicit'],
  );
  // Background lifecycle moved to test_cosmic_background_0985.cjs.
  return [
    'Critical + KEV requires one CVE; selected product scope cannot borrow unrelated criticals or KEVs; missing reference keeps observations',
  ];
}

async function browserChecks(checks) {
  const { chromium } = require('playwright');
  const fixture = JSON.parse(fs.readFileSync(process.env.ECLIPSE_FIXTURE, 'utf8'));
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    args: ['--no-sandbox'],
  });
  const errors = [],
    external = [],
    mutations = [];
  const out = process.env.ECLIPSE_SCREENSHOTS;
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: 'reduce',
    });
    context.on('request', (request) => {
      if (/^https?:/.test(request.url()) && !request.url().startsWith(fixture.base + '/'))
        external.push(request.url());
      if (
        request.url().includes('/api/') &&
        request.method() !== 'GET' &&
        !request.url().endsWith('/api/desktop/session')
      )
        mutations.push(request.method() + ' ' + request.url());
    });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    page.on('pageerror', (error) => errors.push(error.message));
    const ready = () => page.locator('#eclipse[data-ready="true"]').waitFor();
    const count = async () =>
      Number((await page.locator('#ec-rows').innerText()).replaceAll(',', ''));
    const shot = async (name) => {
      if (!out) return;
      fs.mkdirSync(out, { recursive: true });
      await page.screenshot({ path: path.join(out, name + '.png'), fullPage: true });
    };
    await page.goto(fixture.launch_url);
    await page.waitForFunction(() => !location.hash.includes('launch='));
    mutations.length = 0;
    await page.goto(fixture.base + '/#library');
    await page.locator('#catalog-product-query').fill('mail_gateway');
    await page.locator('#catalog-product-scope').selectOption('critical_kev');
    await page.locator('#catalog-product-form button[type="submit"]').click();
    await page.locator('[data-catalog-product="' + fixture.product_id + '"]').click();
    await page
      .locator('#catalog-product-detail [data-catalog-cve="' + fixture.cve_id + '"]')
      .waitFor();
    assert.equal(await page.locator('#catalog-product-detail .catalog-product-cve').count(), 1);
    assert.match(await page.locator('#catalog-product-detail').innerText(), /Affected versions/);
    assert.match(
      await page.locator('#catalog-product-detail .catalog-version-ranges').innerText(),
      /1\.0/,
    );
    await page.locator('#catalog-version').fill('1.5');
    await page.locator('#catalog-version-form button[type="submit"]').click();
    await page.locator('#catalog-product-detail .catalog-match').waitFor();
    const compared = await page
      .locator('#catalog-product-detail .catalog-version-ranges')
      .innerText();
    assert(!compared.includes('[object Object]'));
    assert.match(compared, /candidate|match|within|possible|unresolved/i);
    await shot('0984-library-products-desktop');
    const observed = await page.evaluate(
      async (product) =>
        (
          await fetch('/api/cve-catalog/products/' + product + '/observations?scope=critical_kev')
        ).json(),
      fixture.product_id,
    );
    assert.equal(observed.counts.reported, 3);
    assert(observed.counts.product_candidates > 0);
    checks.push(
      'Real local Catalog + KEV imports populate product, source version ranges, and separate reported findings from product research candidates',
    );
    await page
      .locator('#catalog-product-detail')
      .getByRole('link', { name: 'See observed connections' })
      .click();
    await ready();
    assert.equal(await count(), 3);
    assert.equal(await page.locator('#ec-intelligence').inputValue(), 'critical_kev');
    assert.match(await page.locator('#ec-scope-caption').innerText(), /mail[ _]gateway/i);
    assert.equal(new URLSearchParams(page.url().split('?')[1]).get('product'), fixture.product_id);
    const atmosphere = await page.evaluate(() => ({
      artwork: getComputedStyle(document.body, '::before').backgroundImage,
      motion: getComputedStyle(document.body, '::before').animationName,
      paused: document.documentElement.dataset.cosmicPaused,
      observatoryBackground: getComputedStyle(document.querySelector('#eclipse')).backgroundColor,
      canvasAlpha: document.querySelector('#ec-canvas').getContext('2d').getImageData(2, 2, 1, 1)
        .data[3],
      loaded: performance
        .getEntriesByType('resource')
        .some((entry) => entry.name.endsWith('/static/cosmic-data-field.png')),
    }));
    assert(atmosphere.artwork.includes('cosmic-data-field.png') && atmosphere.loaded);
    assert.equal(atmosphere.motion, 'none');
    assert.equal(atmosphere.paused, 'true');
    assert.equal(atmosphere.observatoryBackground, 'rgba(0, 0, 0, 0)');
    assert(atmosphere.canvasAlpha < 255, 'Data canvas reveals shared artwork');
    assert.equal(await page.locator('.dm-gravity-packet').count(), 4);
    assert.equal(await page.locator('.dm-gravity-field').getAttribute('aria-hidden'), 'true');
    assert.equal(
      await page
        .locator('.dm-gravity-packet')
        .first()
        .evaluate((node) => getComputedStyle(node).animationName),
      'none',
    );
    await shot('0984-observatory-product-desktop');
    await page.reload();
    await ready();
    assert.equal(await count(), 3);
    checks.push(
      'Library product deep link preserves exact product + Critical/KEV scope, counts, and reload state',
    );
    await page.locator('#ec-list-toggle').click();
    await page.locator('#ec-record-list [data-ec-row]').first().click();
    const entityLink = page.locator('#ec-inspector a[href^="#entity/"]').first();
    await entityLink.waitFor();
    assert.deepEqual(mutations, [], 'Library and Observatory are read-only');
    const entityURL = await entityLink.getAttribute('href');
    await entityLink.click();
    await page.waitForFunction((hash) => location.hash === hash, entityURL);
    await page
      .locator('h1')
      .filter({ hasText: /aster|meridian/i })
      .waitFor();
    assert.match(await page.locator('main').innerText(), /mail\./i);
    checks.push('Preserved observation opens its actual associated entity dossier');
    await page.goto(
      fixture.base +
        '/#eclipse?product=' +
        encodeURIComponent(fixture.product_id) +
        '&scope=critical_kev',
    );
    await ready();
    await page.locator('#ec-reset').click();
    await ready();
    assert.equal(new URL(page.url()).hash, '#eclipse');
    assert.equal(await count(), fixture.rows);
    checks.push('Reset clears product and risk scope and restores every preserved imported row');
    await page.goto(fixture.base + '/#eclipse?cve=' + fixture.cve_id);
    await ready();
    assert.equal(await count(), 3, 'CVE link excludes the longer prefix-only identifier');
    await page.goto(fixture.base + '/#eclipse?cve=' + fixture.cve_id.toLowerCase());
    await ready();
    assert.equal(await count(), 3, 'Lowercase CVE link resolves the same exact identifier');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(
      fixture.base +
        '/#library?view=products&product=' +
        encodeURIComponent(fixture.product_id) +
        '&scope=critical_kev',
    );
    await page
      .locator('#catalog-product-detail [data-catalog-cve="' + fixture.cve_id + '"]')
      .waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await shot('0984-library-products-mobile');
    await page
      .locator('#catalog-product-detail')
      .getByRole('link', { name: 'See observed connections' })
      .click();
    await ready();
    assert.equal(await count(), 3);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await shot('0984-observatory-product-mobile');
    checks.push(
      '390px Library and Observatory product scope remain usable without document overflow',
    );
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    const packet = page.locator('.dm-gravity-approach').first();
    const packetStart = await packet.evaluate((node) => getComputedStyle(node).transform);
    const firstTransform = await page.evaluate(
      () => getComputedStyle(document.body, '::before').transform,
    );
    await page.waitForTimeout(500);
    assert.notEqual(
      await page.evaluate(() => getComputedStyle(document.body, '::before').transform),
      firstTransform,
    );
    assert.notEqual(await packet.evaluate((node) => getComputedStyle(node).transform), packetStart);
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { configurable: true, value: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    assert.equal(
      await packet.evaluate((node) => getComputedStyle(node).animationPlayState),
      'paused',
    );
    const pausedPacket = await packet.evaluate((node) => getComputedStyle(node).transform);
    await page.waitForTimeout(150);
    assert.equal(await packet.evaluate((node) => getComputedStyle(node).transform), pausedPacket);
    await page.evaluate(() => {
      delete document.hidden;
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    assert.equal(
      await page.evaluate(() => getComputedStyle(document.body, '::before').animationName),
      'none',
    );
    assert.equal(await packet.evaluate((node) => getComputedStyle(node).animationName), 'none');
    checks.push(
      'Generated artwork loads in shell and transparent Observatory canvas; compositor drift runs and reduced-motion makes it static; lifecycle tests pause hidden tabs',
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    assert(mutations.every((request) => request.endsWith('/connections/dns')));
    checks.push(
      'Library/Observatory remain read-only; entity DNS uses injected synthetic resolver; no external browser requests, case mutations, or JavaScript errors',
    );
    const result = { passed: true, checks, errors, external, mutations };
    if (out) fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
}

(async () => {
  const checks = await modelChecks();
  if (process.env.ECLIPSE_FIXTURE) await browserChecks(checks);
  else console.log(JSON.stringify({ passed: true, checks }, null, 2));
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
