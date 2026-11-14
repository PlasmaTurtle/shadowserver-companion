/* Real local API/core/UI contact discovery pipeline against synthetic websites.
 * Start contacts_browser_fixture_090.py with a new scratch workspace, then set
 * CONTACT_BROWSER_FIXTURE to its browser.json. No real contact is messaged.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  assert(process.env.CONTACT_BROWSER_FIXTURE, 'Explicit synthetic fixture metadata is required');
  const fixture = JSON.parse(fs.readFileSync(process.env.CONTACT_BROWSER_FIXTURE, 'utf8'));
  const base = fixture.base;
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const screenshots = process.env.CONTACT_SCREENSHOTS;
  const checks = [],
    errors = [],
    external = [];
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    args: [
      '--no-sandbox',
      ...(process.env.CONTACT_BROWSER_SINGLE_PROCESS ? ['--no-zygote', '--single-process'] : []),
    ],
  });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1100 },
      reducedMotion: 'reduce',
    });
    await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: base });
    await context.route('**/*', async (route) => {
      const url = route.request().url();
      if (/^https?:/.test(url) && !url.startsWith(base + '/')) {
        external.push(url);
        return route.abort();
      }
      return route.continue();
    });
    const page = await context.newPage();
    page.setDefaultTimeout(18000);
    page.on('pageerror', (error) => errors.push(error.message));
    const state = async () =>
      (await context.request.get(base + '/api/entities/' + fixture.entity_id + '/contacts')).json();
    const caseState = async () =>
      (await context.request.get(base + '/api/cases/' + fixture.case_id)).json();
    const requestCount = () =>
      fs.existsSync(fixture.requests_path)
        ? fs.readFileSync(fixture.requests_path, 'utf8').trim().split('\n').filter(Boolean).length
        : 0;
    const shot = async (name) => {
      if (!screenshots) return;
      fs.mkdirSync(screenshots, { recursive: true });
      await page.waitForFunction(() => !document.querySelector('#toasts .toast'));
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: path.join(screenshots, name + '.png'), fullPage: true });
    };
    await page.goto(fixture.launch_url);
    await page.locator('#eclipse').waitFor();
    await page.evaluate(async () => {
      window.contactTestApp = (await import('/static/main.js')).application;
    });
    await page.goto(base + '/#case/' + fixture.case_id + '?tab=contact');
    await page.locator('#contact-root option[value="example.com"]').waitFor({ state: 'attached' });
    assert.equal(await page.locator('#contact-root').inputValue(), 'example.com');
    assert.equal(await page.locator('#contact-include-www').count(), 0);
    assert.equal(requestCount(), 0, 'Opening contact tab does not fetch company websites');
    assert.match(
      await page.locator('#contact-discovery-panel').innerText(),
      /eight requests and 30 seconds/,
    );
    await shot('090-contact-empty-desktop');
    checks.push(
      'Explicit attributed hostname; apex/www pair included automatically; opening panel performs no website lookup',
    );

    await page.locator('[data-action="start-contact-discovery"]').click();
    await page
      .locator('.contact-candidate h3')
      .filter({ hasText: 'security@example.com' })
      .waitFor();
    const first = await state();
    assert.equal(first.latest_run.status, 'relevant_found');
    assert(first.latest_run.request_count <= 8);
    assert(requestCount() <= 8);
    assert(first.candidates.every((candidate) => candidate.decision === 'pending'));
    assert(first.latest_run.coverage.length);
    assert.match(
      await page.locator('#contact-discovery-panel').innerText(),
      /Pages checked and unresolved routes/,
    );
    await page.locator('details[data-contact-detail="focused-source"] summary').click();
    await page.locator('#contact-source-url').fill('https://external.example/report');
    const beforeRejected = requestCount();
    await page.locator('[data-action="inspect-contact-source"]').click();
    await page
      .getByText('Inspect a page on the selected hostname or its www counterpart.', {
        exact: false,
      })
      .waitFor();
    assert.equal(requestCount(), beforeRejected);
    await page.locator('#contact-source-url').fill('');
    assert.equal(await page.evaluate(() => window.sourceExecuted), undefined);
    const security = first.candidates.find(
      (candidate) => candidate.value === 'security@example.com',
    );
    assert(security && security.sources.length);
    assert.match(security.provenance_text, /example\.com/);
    assert.match(security.provenance_text, /SHA-256/);
    await page
      .locator('[data-contact-review="' + security.id + '"][data-decision="confirm"]')
      .click();
    await page.locator('[data-contact-use="' + security.id + '"]').waitFor();
    assert.equal(
      (await state()).candidates.find((c) => c.id === security.id).decision,
      'confirmed',
    );
    checks.push(
      'Real core finds synthetic first-party contacts within budget and UI confirmation records reviewer decision',
    );
    await page.locator('[data-contact-copy="' + security.id + '"]').click();
    await page.waitForFunction(
      () =>
        document.querySelector('.contact-copy') ||
        document.body.textContent.includes('Source explanation copied.'),
    );
    if (await page.locator('.contact-copy').count()) {
      assert.match(await page.locator('.contact-copy').inputValue(), /security@example\.com/);
      assert.match(await page.locator('.contact-copy').inputValue(), /SHA-256/);
      await page.locator('#close-modal').click();
    } else {
      const copied = await page.evaluate(() => navigator.clipboard.readText());
      assert.match(copied, /security@example\.com/);
      assert.match(copied, /SHA-256/);
    }
    checks.push(
      'Copy source explanation returns the retained contact, source and SHA-256 provenance',
    );

    await page.locator('[data-contact-use="' + security.id + '"]').click();
    await page.waitForFunction(
      () =>
        document.querySelector('#case-plan [name="contact_email"]')?.value ===
        'security@example.com',
    );
    assert.equal((await caseState()).case.contact_email, 'security@example.com');
    await page.locator('#case-plan [name="contact_phone"]').fill('704-555-0199');
    const planSave = page.waitForResponse(
      (response) => response.url().includes('/plan') && response.request().method() === 'PUT',
    );
    await page.locator('#case-plan button[type="submit"]').click();
    assert.equal((await planSave).status(), 200);
    checks.push(
      'Confirmed contact fills blank plan field through API; manual phone is retained separately',
    );

    await page
      .locator('.contact-candidate')
      .filter({ has: page.locator('h3', { hasText: 'security@example.com' }) })
      .locator('details[data-contact-detail^="sources-"]')
      .click();
    await shot('090-contact-confirmed-desktop');
    await page.setViewportSize({ width: 390, height: 844 });
    await shot('090-contact-confirmed-mobile');
    assert(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2),
      'No mobile horizontal overflow',
    );
    await page.setViewportSize({ width: 1440, height: 1100 });
    const downloadResponse = await context.request.get(
      base + '/api/entities/' + fixture.entity_id + '/contacts/evidence.zip',
    );
    assert.equal(downloadResponse.status(), 200);
    const bytes = await downloadResponse.body();
    assert.equal(bytes.subarray(0, 2).toString(), 'PK');
    if (screenshots) fs.writeFileSync(path.join(screenshots, '090-contact-evidence.zip'), bytes);
    checks.push(
      'Source excerpt/provenance visible, evidence ZIP downloads, desktop/mobile layouts captured',
    );

    const runId = first.latest_run.id;
    await page.locator('[data-action="refresh-contact-discovery"]').click();
    await page.waitForFunction((oldId) => {
      const application = window.contactTestApp;
      const current = application.state.contacts.entities.get('business')?.latest_run?.id;
      return current && current !== oldId && !application.state.contacts.watch;
    }, runId);
    const refreshed = await state();
    assert.notEqual(refreshed.latest_run.id, runId);
    assert.equal(refreshed.candidates.find((c) => c.id === security.id).decision, 'confirmed');
    assert.equal((await caseState()).case.contact_phone, '704-555-0199');
    assert.equal((await caseState()).case.contact_email, 'security@example.com');
    checks.push(
      'Refresh appends evidence and preserves confirmed decision plus manual contact-plan values',
    );
    const reviewColors = await page.evaluate(() => {
      const root = document.documentElement,
        original = root.dataset.theme;
      const review = document.querySelector('.contact-candidate .entity-review-required');
      root.dataset.theme = 'light';
      const light = getComputedStyle(review).color;
      root.dataset.theme = 'dark';
      const dark = getComputedStyle(review).color;
      root.dataset.theme = original;
      return { light, dark };
    });
    assert.deepEqual(reviewColors, { light: 'rgb(130, 90, 9)', dark: 'rgb(243, 206, 128)' });
    checks.push('Review required text is amber in both light and dark themes');

    fs.writeFileSync(fixture.control_path, JSON.stringify({ mode: 'slow' }));
    await page.locator('[data-action="refresh-contact-discovery"]').click();
    await page.locator('[data-action="cancel-contact-discovery"]').waitFor();
    const cancellingJob = await page.evaluate(
      () => window.contactTestApp.state.contacts.entities.get('business').active_job.id,
    );
    await page.locator('[data-action="cancel-contact-discovery"]').click();
    await page.waitForFunction(() => {
      const application = window.contactTestApp;
      return (
        !application.state.contacts.watch &&
        !document.querySelector('#contact-discovery-panel .spinner')
      );
    });
    const cancelled = await (
      await context.request.get(base + '/api/contact-discovery/jobs/' + cancellingJob)
    ).json();
    assert.equal(cancelled.state, 'cancelled');
    checks.push('Cancellation settles API job and removes UI spinner');

    await page.locator('[data-action="refresh-contact-discovery"]').click();
    await page.locator('[data-action="cancel-contact-discovery"]').waitFor();
    await page.goto(base + '/#cases');
    await page.locator('#case-search').waitFor();
    assert.equal(
      await page.evaluate(async () => {
        const { application } = await import('/static/main.js');
        return application.state.contacts.watch;
      }),
      null,
    );
    fs.writeFileSync(fixture.control_path, JSON.stringify({ mode: 'normal' }));
    checks.push('Navigating away removes contact polling without disturbing the new view');
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      JSON.stringify(
        { checks, errors, external_requests: external, synthetic_website_requests: requestCount() },
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
