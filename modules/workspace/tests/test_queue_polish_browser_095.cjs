/* Live synthetic UI checks for queue hierarchy, recovery and inline feedback. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const fixture = JSON.parse(fs.readFileSync(process.env.WORKFLOW_BROWSER_FIXTURE));
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
      viewport: { width: 1440, height: 1000 },
      reducedMotion: 'reduce',
    });
    await context.route('**/*', (route) => {
      const url = route.request().url();
      if (/^https?:/.test(url) && !url.startsWith(fixture.base + '/')) {
        external.push(url);
        return route.abort();
      }
      return route.continue();
    });
    const page = await context.newPage();
    page.setDefaultTimeout(12000);
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(fixture.launch_url);
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    const suggested = page.locator('.dm-priority-row');
    assert.equal(await suggested.count(), 1);
    assert.match(
      await suggested.getAttribute('href'),
      new RegExp('#workspace/notifications/' + fixture.case_id),
    );
    assert.match(await suggested.innerText(), /follow.up/i);
    checks.push('Priority work gives the overdue synthetic case an actionable notification link');
    await page.goto(fixture.base + '/#entities');
    const row = page.locator('[data-entity-row="' + fixture.entity_id + '"]');
    await row.waitFor();
    await page.locator('#entity-search [name="q"]').fill('no-such-business');
    await page.locator('#entity-search button[type="submit"]').click();
    await page.getByRole('heading', { name: 'No entities match' }).waitFor();
    await page.getByRole('link', { name: 'Clear filters', exact: true }).click();
    await row.waitFor();
    assert.equal(await page.locator('#entity-search [name="q"]').inputValue(), '');
    checks.push(
      'Filtered empty entity directories explain recovery and clearing filters restores the saved entity',
    );
    await page.goto(fixture.base + '/#workspace/notifications?stage=closed');
    await page.getByRole('navigation', { name: 'Notification stage filters' }).waitFor();
    assert.match(
      await page.locator('.case-filter-tabs [aria-current="page"]').innerText(),
      /Closing Report Completed/,
    );
    await page.getByRole('link', { name: 'Clear filters', exact: true }).click();
    await page
      .locator('a[href="#workspace/notifications/' + fixture.case_id + '"]')
      .first()
      .waitFor();
    checks.push(
      'The chosen notification stage is announced and an empty stage can recover to all cases',
    );
    await page.goto(fixture.base + '/#workspace/notifications/' + fixture.case_id + '?tab=contact');
    await page.locator('.outreach-tools > summary').click();
    await page.locator('#case-outreach-policy').waitFor();
    const discovery = await page.locator('#contact-discovery-panel').boundingBox();
    const policy = await page.locator('#case-outreach-policy').boundingBox();
    assert(discovery.y < policy.y);
    let policyWrites = 0;
    page.on('request', (r) => {
      if (r.method() === 'PUT' && r.url().endsWith('/outreach-policy')) policyWrites++;
    });
    await page.locator('#outreach-state').selectOption('deferred');
    assert(await page.locator('#outreach-review-on').evaluate((e) => e.required));
    await page.locator('#case-outreach-policy [name="reason"]').fill('UI acceptance hold');
    await page.locator('#case-outreach-policy button[type="submit"]').click();
    assert.equal(policyWrites, 0);
    assert(await page.locator('#outreach-review-on').evaluate((e) => e.validity.valueMissing));
    await page.locator('#outreach-review-on').fill('2099-01-01');
    await page.locator('#case-outreach-policy button[type="submit"]').click();
    await page.getByText('Outreach decision saved.', { exact: true }).waitFor();
    await page.locator('.outreach-hold-notice [data-action="review-outreach-decision"]').click();
    await page.waitForFunction(() => document.activeElement?.id === 'outreach-state');
    assert.match(await page.locator('.outreach-hold-notice').innerText(), /UI acceptance hold/);
    checks.push(
      'Contact work comes first; deferred dates validate before submission and hold review moves focus to the decision control',
    );
    await page.goto(fixture.base + '/#activity');
    await page.locator('#activity-search').waitFor();
    assert.equal(await page.locator('.activity-advanced').getAttribute('open'), null);
    await page.getByText('Filter by operator or action', { exact: true }).click();
    await page.getByLabel('Recorded operator', { exact: true }).fill('No such operator');
    await page.locator('#activity-search button[type="submit"]').click();
    await page.getByRole('heading', { name: 'No matching events', exact: true }).waitFor();
    assert.notEqual(await page.locator('.activity-advanced').getAttribute('open'), null);
    await page.getByRole('link', { name: 'Clear filters', exact: true }).first().click();
    await page.waitForFunction(
      () =>
        !document.querySelector('#activity-operator')?.value &&
        !document.querySelector('.activity-advanced')?.open,
    );
    await page.locator('#activity-query').fill('UI acceptance hold');
    await page.locator('#activity-search button[type="submit"]').click();
    await page.waitForFunction(() =>
      document
        .querySelector('.activity-result-summary')
        ?.textContent.includes('Showing 1 of 1 matching recorded event.'),
    );
    assert.match(await page.locator('#main').innerText(), /Workflow Reviewer/);
    assert.equal(await page.locator('.activity-pagination').count(), 0);
    checks.push(
      'Activity keeps exact-match controls optional, restores filtered empty views, and reports visible counts without a redundant first-page button',
    );
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
