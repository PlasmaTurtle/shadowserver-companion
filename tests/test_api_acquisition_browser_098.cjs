/** Real UI against the explicitly selected local synthetic Reports API fixture. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

(async () => {
  assert(process.env.API_BROWSER_FIXTURE, 'Explicit synthetic workspace required');
  const fixture = JSON.parse(fs.readFileSync(process.env.API_BROWSER_FIXTURE, 'utf8'));
  const { base } = fixture;
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    headless: true,
    args: ['--no-sandbox', '--no-zygote'],
  });
  const errors = [],
    external = [],
    checks = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.route('**/*', (route) => {
      if (
        /^https?:/.test(route.request().url()) &&
        !route
          .request()
          .url()
          .startsWith(base + '/')
      ) {
        external.push(route.request().url());
        return route.abort();
      }
      return route.continue();
    });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(fixture.launch_url);
    await page.locator('#main').waitFor();
    await page.goto(base + '/#data?tab=api');
    await page.locator('#api-key').fill(fixture.api_key);
    await page.locator('#api-secret').fill(fixture.secret);
    await page.locator('#api-credentials-form button[type="submit"]').click();
    await page.locator('#api-catalog-form').waitFor();
    assert.equal(await page.locator('#api-key').inputValue(), '');
    assert.equal(await page.locator('#api-secret').inputValue(), '');
    const browserStorage = await page.evaluate(() =>
      JSON.stringify({ ...localStorage, ...sessionStorage }),
    );
    assert(!browserStorage.includes(fixture.api_key) && !browserStorage.includes(fixture.secret));
    checks.push('Credentials clear after submission and are absent from browser persistence');
    assert.equal(await page.locator('#api-subscription').inputValue(), '');
    await page.locator('#api-subscription').selectOption('synthetic-example');
    await page.locator('#api-start').fill('2026-11-06');
    await page.locator('#api-end').fill('2026-11-06');
    await page.locator('#api-catalog-form button[type="submit"]').click();
    await page.locator('#api-import-form').waitFor();
    assert.equal(await page.locator('#api-import-form [name="report_ids"]').count(), 1);

    assert.equal(await page.locator('#api-import-form [name="next_day"]').count(), 0);
    assert(
      !(await page
        .locator('#api-import-form')
        .innerText()
        .then((text) => text.includes('Narrative date'))),
    );

    async function importSelected(expected) {
      const response = page.waitForResponse(
        (r) => r.url() === base + '/api/shadowserver/import' && r.request().method() === 'POST',
      );
      await page.locator('#api-import-form button[type="submit"]').click();
      const job = await (await response).json();
      await page.waitForFunction(
        async ({ id, status }) => {
          const result = await (await fetch('/api/shadowserver/jobs/' + id)).json();
          return result.status === status;
        },
        { id: job.id, status: expected },
      );
      return (await context.request.get(base + '/api/shadowserver/jobs/' + job.id)).json();
    }
    const imported = await importSelected('completed');
    assert.equal(imported.results.length, 1);
    await page.locator('#api-import-form button[type="submit"]:enabled').waitFor();
    const duplicate = await importSelected('completed');
    assert.equal(duplicate.results[0].duplicate, true);
    const rows = await (await context.request.get(base + '/api/imports')).json();
    assert.equal(rows.length, 1);
    checks.push('Connect, list, download and repeated import use the real receipt/intake pipeline');
    await page.locator('#api-import-form button[type="submit"]:enabled').waitFor();
    fs.writeFileSync(fixture.control_path, JSON.stringify({ mode: 'slow' }));
    await page.locator('#api-import-form button[type="submit"]').click();
    await page.locator('[data-action="api-cancel"]').click();
    await page.locator('#api-job-progress').getByText('Cancelled', { exact: true }).waitFor();
    checks.push('Cancellation finishes in the UI and retains completed imports');
    await page.locator('#shadowserver-api details').first().locator('summary').click();
    await page.locator('[data-action="api-forget"]').click();
    await page.locator('#shadowserver-api').getByText('Not configured', { exact: true }).waitFor();
    assert.equal(
      (await (await context.request.get(base + '/api/shadowserver/status')).json()).configured,
      false,
    );
    checks.push('Credential removal returns the UI to an unconfigured state');
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      JSON.stringify({ checks, page_errors: errors, external_requests: external }, null, 2),
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
