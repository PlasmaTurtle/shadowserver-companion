/** Actual app shell and background DNS flow with bounded synthetic provider responses. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const fixture = JSON.parse(fs.readFileSync(process.env.NAVIGATION_FIXTURE, 'utf8'));
(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    args: ['--no-sandbox'],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: 'reduce',
  });
  const page = await context.newPage(),
    errors = [];
  let posts = 0;
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().endsWith('/connections/dns')) posts++;
  });
  try {
    await page.goto(fixture.launch_url);
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    await page.goto(fixture.base + '/#entity/' + fixture.entity_id);
    await page.locator('[data-dossier-dns-graph]').waitFor();
    await page.getByRole('button', { name: 'Refresh root DNS', exact: true }).waitFor();
    await page.waitForFunction(() =>
      document.querySelector('[data-entity-dns]')?.textContent.includes('8.8.8.8'),
    );
    assert.equal(posts, 1);
    assert((await page.locator('[data-root-link]').count()) > 0);
    assert((await page.locator('[data-dns-link]').count()) > 0);
    const api = async () =>
      (await context.request.get(fixture.base + '/api/entities/' + fixture.entity_id)).json();
    const initial = await api(),
      revision = initial.dns_connections.roots[0].lookup.revision_id;
    await page.reload();
    await page.locator('[data-dns-link]').first().waitFor();
    assert.equal(posts, 1, 'Fresh DNS is reused on reopen without another lookup action');
    assert.equal((await api()).dns_connections.roots[0].lookup.revision_id, revision);
    if (process.env.DNS_SCREENSHOTS) {
      fs.mkdirSync(process.env.DNS_SCREENSHOTS, { recursive: true });
      await page.screenshot({
        path: path.join(process.env.DNS_SCREENSHOTS, 'entity-root-dns-desktop.png'),
        fullPage: true,
      });
    }
    await page.getByRole('button', { name: 'Refresh root DNS', exact: true }).click();
    await page.waitForFunction(
      () => !document.querySelector('[data-action="entity-dns-refresh"]')?.disabled,
    );
    await page.waitForTimeout(100);
    assert.equal(posts, 2);
    const latest = await api();
    assert.notEqual(latest.dns_connections.roots[0].lookup.revision_id, revision);
    assert.equal(latest.entity_revision, initial.entity_revision);
    assert.deepEqual(latest.entries, initial.entries);
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    assert((await page.locator('[data-dossier-dns-graph]').boundingBox()).width >= 680);
    if (process.env.DNS_SCREENSHOTS)
      await page.screenshot({
        path: path.join(process.env.DNS_SCREENSHOTS, 'entity-root-dns-mobile.png'),
        fullPage: true,
      });
    assert.deepEqual(errors, []);
    console.log(
      JSON.stringify({
        passed: true,
        automatic_start: true,
        cache_reuse: true,
        manual_refresh: true,
        original_entries_unchanged: true,
        desktop_mobile_fit: true,
        browser_errors: errors,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
