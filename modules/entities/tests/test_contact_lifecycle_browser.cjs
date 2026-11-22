/** Explicit discovery, finite cancellation and detached polling on current contact UI. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');
const { waitForJSON } = require('../../../tests/browser_wait.cjs');

(async () => {
  const fixture = JSON.parse(fs.readFileSync(process.env.CONTACT_BROWSER_FIXTURE, 'utf8'));
  const { base } = fixture;
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE,
  });
  const errors = [],
    external = [];
  try {
    const context = await browser.newContext();
    await context.route('**/*', (route) => {
      const url = route.request().url();
      if (/^https?:/.test(url) && !url.startsWith(base + '/')) {
        external.push(url);
        return route.abort();
      }
      return route.continue();
    });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    page.on('pageerror', (error) => errors.push(error.message));
    const count = () =>
      fs.existsSync(fixture.requests_path)
        ? fs.readFileSync(fixture.requests_path, 'utf8').trim().split('\n').filter(Boolean).length
        : 0;
    const contactURL = base + '/api/entities/' + fixture.entity_id + '/contacts';
    await page.goto(fixture.launch_url);
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    await page.evaluate(async () => {
      window.contactTestApp = (await import('/modules/ui/static/main.js')).application;
    });
    await page.goto(base + '/#entity/' + fixture.entity_id + '?tab=contacts');
    await page.waitForFunction(
      () => document.querySelector('#contact-root')?.value === 'example.com',
    );
    assert.equal(await page.locator('#contact-root').inputValue(), 'example.com');
    assert.equal(count(), 0, 'Opening saved contact UI performs no website lookup');
    await page.locator('[data-action="start-contact-discovery"]').click();
    const discovered = await waitForJSON(
      context.request,
      contactURL,
      (value) => value.latest_run && !value.active_job,
    );
    assert(discovered.latest_run.request_count <= 8);
    assert(count() <= 8);
    await page
      .locator('.contact-candidate h3')
      .filter({ hasText: 'security@example.com' })
      .waitFor();
    assert(
      discovered.contacts.some((item) => item.value === 'security@example.com' && item.usable),
    );
    const details = page.locator('details[data-contact-detail="details"]');
    await details.locator(':scope > summary').click();
    fs.writeFileSync(fixture.control_path, JSON.stringify({ mode: 'slow' }));
    await page.locator('[data-action="refresh-contact-discovery"]').click();
    const running = await waitForJSON(context.request, contactURL, (value) =>
      Boolean(value.active_job),
    );
    await page.locator('[data-action="cancel-contact-discovery"]').click();
    await waitForJSON(
      context.request,
      base + '/api/contact-discovery/jobs/' + running.active_job.id,
      (job) => job.state === 'cancelled',
    );
    await page.waitForFunction(
      () =>
        !window.contactTestApp.state.contacts.watch &&
        !document.querySelector('#contact-discovery-panel .spinner'),
    );
    const saved = await (await context.request.get(contactURL)).json();
    assert(
      saved.contacts.some((item) => item.value === 'security@example.com'),
      'Cancellation preserves prior captured contacts',
    );
    if (!(await details.evaluate((element) => element.open)))
      await details.locator(':scope > summary').click();
    await page.locator('[data-action="refresh-contact-discovery"]').click();
    const detached = await waitForJSON(context.request, contactURL, (value) =>
      Boolean(value.active_job),
    );
    await page.goto(base + '/#workspace/notifications');
    await page.locator('#case-search').waitFor();
    assert.equal(await page.evaluate(() => window.contactTestApp.state.contacts.watch), null);
    const boot = await (await context.request.get(base + '/api/bootstrap')).json();
    const cancel = await context.request.post(
      base + '/api/contact-discovery/jobs/' + detached.active_job.id + '/cancel',
      { headers: { Origin: base, 'X-Workbench-Token': boot.token } },
    );
    assert.equal(cancel.status(), 200);
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      JSON.stringify({
        passed: true,
        explicit_lookup: true,
        request_budget: discovered.latest_run.request_count,
        cancellation_preserves_contacts: true,
        navigation_stops_polling: true,
        errors,
        external_requests: external,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
