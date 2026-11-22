/** Real UI against the explicitly selected local synthetic Reports API fixture. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');
const { waitForJSON } = require('../../../tests/browser_wait.cjs');

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
    await page.getByRole('button', { name: 'External deconfliction list' }).click();
    await page.getByRole('button', { name: 'Add entry' }).click();
    const referral = page.locator('#deconfliction-form');
    await referral.getByLabel('Identifier').fill('HELP.Example.com.');
    await referral.getByLabel('External reference').fill('SYNTH-17');
    await referral.getByLabel('Reason').fill('Synthetic partner is reviewing this host');
    await referral.getByRole('button', { name: 'Save entry' }).click();
    let record = page.getByRole('row').filter({ hasText: 'help.example.com' });
    await record.getByText('Exact hostname').waitFor();
    await record.getByRole('button', { name: 'Edit' }).click();
    await referral.getByLabel('Matching scope').selectOption('domain');
    await referral.getByLabel('Identifier').fill('example.com');
    await referral.getByRole('button', { name: 'Save entry' }).click();
    record = page.getByRole('row').filter({ hasText: 'SYNTH-17' });
    await record.getByText('Whole domain').waitFor();
    await record.getByRole('button', { name: 'Edit' }).click();
    await referral.getByRole('button', { name: 'Remove entry' }).click();
    await page.getByText('No external entries recorded.').waitFor();
    await page.locator('#close-modal').click();
    checks.push('Created, changed scope and removed an external referral through Data');
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
      return waitForJSON(
        context.request,
        base + '/api/shadowserver/jobs/' + job.id,
        (result) => result.status === expected,
      );
    }
    const imported = await importSelected('completed');
    assert.equal(imported.results.length, 1, JSON.stringify(imported));
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
