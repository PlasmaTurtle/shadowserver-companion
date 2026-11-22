/* Real local API/UI acceptance against workflow_browser_fixture_095.py. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  assert(process.env.WORKFLOW_BROWSER_FIXTURE, 'Explicit isolated fixture metadata is required');
  const fixture = JSON.parse(fs.readFileSync(process.env.WORKFLOW_BROWSER_FIXTURE));
  const base = fixture.base;
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    args: ['--no-sandbox', '--no-zygote'],
  });
  const checks = [],
    errors = [],
    external = [];
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1100 },
      reducedMotion: 'reduce',
    });
    await context.route('**/*', (route) => {
      const url = route.request().url();
      if (/^https?:/.test(url) && !url.startsWith(base + '/')) {
        external.push(url);
        return route.abort();
      }
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', (error) => errors.push(error.message));
    page.setDefaultTimeout(15000);
    await page.goto(fixture.launch_url);
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    assert.equal(await page.locator('.dm-ledger a').count(), 4);
    assert.match(await page.locator('.dm-priority-row').innerText(), /follow.up/i);
    checks.push('Workspace is the default with current totals and an explainable due action');
    await page.goto(base + '/#workspace/notifications/' + fixture.case_id + '?tab=contact');
    await page.locator('.outreach-tools > summary').click();
    await page.getByRole('heading', { name: 'Finding history', exact: true }).waitFor();
    assert.match(await page.locator('#main').innerText(), /1 distinct findings/);
    await page.getByText('Compare observations and prior notifications', { exact: true }).click();
    assert.match(await page.locator('#main').innerText(), /3 reported · 3 approved/);
    assert.match(await page.locator('#main').innerText(), /Changed version/);
    assert.match(await page.locator('#main').innerText(), /Not seen does not mean remediated/);
    checks.push(
      'Three retained source occurrences become one finding with an explicit version change and unknown coverage',
    );
    await page.locator('.saved-plan-editor > summary').click();
    await page.locator('#case-plan [name="contact_name"]').fill('Pending manual value');
    await page.locator('#case-outreach-policy [name="state"]').selectOption('deferred');
    await page.locator('#case-outreach-policy [name="review_on"]').fill('2099-01-01');
    await page.locator('#case-outreach-policy [name="reason"]').fill('Synthetic policy review');
    await page.locator('#case-outreach-policy button[type="submit"]').click();
    await page.getByText('Outreach decision saved.', { exact: true }).waitFor();
    assert.equal(
      await page.locator('#case-plan [name="contact_name"]').inputValue(),
      'Pending manual value',
    );
    let dismissed = false;
    page.once('dialog', async (dialog) => {
      dismissed = true;
      await dialog.dismiss();
    });
    await page.locator('.sidebar [data-nav="workspace"]').click();
    await page.waitForFunction(() => location.hash.includes('workspace/notifications/'));
    assert(dismissed);
    assert.equal(
      await page.locator('#case-plan [name="contact_name"]').inputValue(),
      'Pending manual value',
    );
    checks.push(
      'Saving the outreach decision preserves the unsaved contact form; refused navigation preserves those edits',
    );
    await page.locator('#case-plan button[type="submit"]').click();
    await page.getByText('Contact plan saved.', { exact: true }).waitFor();
    await page.locator('.sidebar [data-nav="workspace"]').click();
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    assert.match(await page.locator('.dm-queue-meta').innerText(), /1 held/);
    const due = await page.evaluate(
      async ({ base, id }) => {
        const response = await fetch(base + '/api/workspace/queue?as_of=2099-01-01');
        return (await response.json()).items.find((item) => item.id === id);
      },
      { base, id: fixture.case_id },
    );
    assert.equal(due.outreach_policy.state, 'deferred');
    assert.equal(due.reconsideration_due, true);
    checks.push(
      'A deferred case leaves Workspace until its review date and returns without clearing its hold',
    );
    await page.goto(base + '/#activity');
    await page.locator('#activity-search [name="q"]').fill('Synthetic policy review');
    await page.locator('#activity-search button[type="submit"]').click();
    await page.waitForFunction(() =>
      document.querySelector('#main')?.textContent.includes('outreach policy changed'),
    );
    assert.match(await page.locator('#main').innerText(), /Workflow Reviewer/);
    checks.push('Activity search locates the reasoned policy event and recorded operator');
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      JSON.stringify(
        { passed: true, checks, browser_errors: errors, external_requests: external },
        null,
        2,
      ),
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
