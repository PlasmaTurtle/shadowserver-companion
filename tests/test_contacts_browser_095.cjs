/* 0.9.5 operator workflow against contacts_browser_fixture_090.py only. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  assert(process.env.CONTACT_BROWSER_FIXTURE, 'Explicit synthetic workspace is required');
  const fixture = JSON.parse(fs.readFileSync(process.env.CONTACT_BROWSER_FIXTURE, 'utf8'));
  const { base } = fixture;
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const checks = [],
    errors = [],
    external = [];
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    args: ['--no-sandbox', '--no-zygote'],
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
    page.setDefaultTimeout(20000);
    page.on('pageerror', (error) => errors.push(error.message));
    const state = async () =>
      (await context.request.get(`${base}/api/entities/${fixture.entity_id}/contacts`)).json();
    const requests = () =>
      fs.existsSync(fixture.requests_path)
        ? fs.readFileSync(fixture.requests_path, 'utf8').trim().split('\n').filter(Boolean).length
        : 0;
    await page.goto(fixture.launch_url);
    await page.locator('#main').waitFor();
    await page.goto(`${base}/#case/${fixture.case_id}?tab=contact`);
    await page.locator('#contact-root option[value="example.com"]').waitFor({ state: 'attached' });
    assert.equal(requests(), 0);
    await page.locator('[data-action="start-contact-discovery"]').click();
    await page
      .locator('.contact-candidate h3')
      .filter({ hasText: 'security@example.com' })
      .waitFor();
    const security = (await state()).candidates.find(
      (candidate) => candidate.value === 'security@example.com',
    );
    await page.locator(`[data-contact-review="${security.id}"][data-decision="confirm"]`).click();
    await page.locator(`[data-contact-route="${security.id}"][data-route-action="prefer"]`).click();
    await page
      .locator('#contact-route-reason')
      .fill('Security team chosen for this business notification');
    await page.locator('#contact-route-decision button[type="submit"]').click();
    await page.locator('#modal').waitFor({ state: 'hidden' });
    assert((await state()).candidates.find((candidate) => candidate.id === security.id).preferred);
    const sourceDetails = page.locator(`[data-contact-detail="sources-${security.id}"]`);
    await sourceDetails.locator('summary').click();
    await sourceDetails.locator('summary').focus();
    const beforeStatusRefresh = requests();
    await page.evaluate(async () => {
      const { application } = await import('/static/main.js');
      await application.actions.loadContactDiscovery();
    });
    assert(await sourceDetails.evaluate((element) => element.open));
    assert.equal(
      await page.evaluate(() => document.activeElement?.parentElement?.dataset.contactDetail),
      `sources-${security.id}`,
    );
    assert.equal(
      requests(),
      beforeStatusRefresh,
      'Refreshing saved status starts no website lookup',
    );
    checks.push('Contact refresh preserves expanded source evidence and keyboard focus');
    await page.locator(`[data-contact-use="${security.id}"]`).click();
    await page.waitForFunction(
      () =>
        document.querySelector('#case-plan [name="contact_email"]')?.value ===
        'security@example.com',
    );
    checks.push(
      'Discovery confirmation, explicit preference, and adoption work through the real UI/API',
    );
    await page.locator('#attempt-channel').selectOption('email');
    await page.locator('#attempt-outcome').selectOption('bounced');
    await page.locator('#case-attempt [name="recipient"]').fill('Security team');
    await page.locator('#case-attempt [name="destination"]').fill('security@example.com');
    await page
      .locator('#case-attempt [name="notes"]')
      .fill('Synthetic mailbox bounce; no email was sent by the application');
    await page.locator('#case-attempt button[type="submit"]').click();
    await page
      .locator('#contact-discovery-panel')
      .getByText('Route unavailable: bounced', { exact: false })
      .waitFor();
    assert.equal(await page.locator(`[data-contact-use="${security.id}"]`).count(), 0);
    assert((await state()).candidates.find((candidate) => candidate.id === security.id).unusable);
    checks.push(
      'Recording a bounce immediately makes the route unavailable without erasing confirmation',
    );
    await page.goto(`${base}/#leads`);
    const batch = page.locator('[data-action="start-contact-batch"]');
    await batch.waitFor();
    assert(await batch.isDisabled(), 'No implicit first-25 selection');
    await page.locator(`[data-contact-select="${fixture.entity_id}"]`).check();
    assert.equal(await batch.isDisabled(), false);
    await page.goto(`${base}/#leads?q=NoSuchSyntheticBusiness`);
    await page
      .locator('.contact-selection-status')
      .getByText('1 selected outside this view will not be included.', { exact: false })
      .waitFor();
    assert(await batch.isDisabled());
    await page.locator('[data-action="clear-contact-selection"]').click();
    assert.doesNotMatch(
      await page.locator('.contact-selection-status').innerText(),
      /outside this view/,
    );
    await page.goto(`${base}/#leads`);
    await page.locator(`[data-contact-select="${fixture.entity_id}"]`).check();
    checks.push(
      'Filtered selections are explicit, excluded from a batch, and cleared with one action',
    );
    const beforeBatch = requests();
    await batch.click();
    await page
      .locator('#contact-discovery-batch')
      .getByText('Contact discovery finished', { exact: false })
      .waitFor();
    assert(
      requests() > beforeBatch,
      'Bounced saved contact does not suppress a selected fresh lookup',
    );
    checks.push(
      'Explicit row selection researches the bounced route instead of skipping it or reusing cache',
    );
    await page.goto(`${base}/#case/${fixture.case_id}?tab=contact`);
    await page
      .locator(`[data-contact-route="${security.id}"][data-route-action="restore"]`)
      .click();
    await page
      .locator('#contact-route-reason')
      .fill('Business confirmed the synthetic mailbox is restored');
    await page.locator('#contact-route-decision button[type="submit"]').click();
    await page.locator('#modal').waitFor({ state: 'hidden' });
    const restored = (await state()).candidates.find((candidate) => candidate.id === security.id);
    assert(restored.usable && restored.preferred);
    await page.locator('[data-action="outreach-handoff"]').click();
    await page.locator('#outreach-message').waitFor();
    assert.match(
      await page.locator('#modal-body').innerText(),
      /current certified report must be available/,
    );
    assert.match(
      await page.locator('#outreach-message').inputValue(),
      /Complete report certification/,
    );
    await page.locator('#outreach-verification-route').fill('https://office.example/verify');
    await page.locator('#outreach-verification button[type="submit"]').click();
    await page.waitForFunction(() =>
      document.querySelector('#outreach-message')?.value.includes('https://office.example/verify'),
    );
    assert.equal(
      await page.locator('.outreach-verification-settings').evaluate((element) => element.open),
      false,
    );
    assert.equal(
      await page.evaluate(() => document.activeElement?.id),
      'outreach-verification-summary',
    );
    await page
      .locator('#outreach-message')
      .fill(
        'Operator-reviewed synthetic introduction. Verify through https://office.example/verify.',
      );
    await page.locator('[data-action="save-outreach-preparation"]').click();
    await page.waitForFunction(
      () => document.querySelector('#outreach-save-state')?.textContent === 'Saved locally',
    );
    await page.locator('[data-action="copy-outreach-message"]').click();
    assert.match(
      await page.evaluate(() => navigator.clipboard.readText()),
      /Operator-reviewed synthetic introduction/,
    );
    checks.push(
      'Handoff shows certification blocker, configured verification route, editable copy-only introduction',
    );
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2));
    if (process.env.CONTACT_SCREENSHOTS) {
      fs.mkdirSync(process.env.CONTACT_SCREENSHOTS, { recursive: true });
      await page.screenshot({
        path: process.env.CONTACT_SCREENSHOTS + '/095-handoff-mobile.png',
        fullPage: true,
      });
    }
    await page.locator('#close-modal').click();
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.locator('#outreach-state').selectOption('do_not_contact');
    await page
      .locator('#case-outreach-policy [name="reason"]')
      .fill('Synthetic recipient requested no further outreach');
    await page.locator('#case-outreach-policy button[type="submit"]').click();
    await page.locator('[data-action="outreach-handoff"]').click();
    await page.locator('#outreach-message').waitFor();
    assert.match(await page.locator('#modal-body').innerText(), /Outreach is do not contact/);
    const activities = (
      await (await context.request.get(`${base}/api/cases/${fixture.case_id}`)).json()
    ).attempts;
    assert.equal(activities.length, 1, 'Only explicit bounced activity was recorded');
    assert.equal(activities[0].outcome, 'bounced');
    checks.push(
      'Do-not-contact hold remains active; preparation does not mark delivery or create activity',
    );
    await page.locator('#close-modal').click();
    await page.locator('.editor-tabs [data-tab="assets"]').click();
    await page
      .locator('#asset-status-summary')
      .getByText('distinct checks remaining', { exact: false })
      .waitFor();
    const assetSource = page.locator('[data-asset-detail^="source-"]').first();
    const assetSourceKey = await assetSource.getAttribute('data-asset-detail');
    await assetSource.locator('summary').click();
    await assetSource.locator('summary').focus();
    await page.evaluate(async () => {
      const { application } = await import('/static/main.js');
      await application.actions.loadAssetAttribution();
    });
    assert(await assetSource.evaluate((element) => element.open));
    assert.equal(
      await page.evaluate(() => document.activeElement?.parentElement?.dataset.assetDetail),
      assetSourceKey,
    );
    assert.match(
      await page.locator('[data-attribute-asset]').first().getAttribute('aria-label'),
      /attribution for/,
    );
    assert.match(
      await page.locator('[data-entry]').first().getAttribute('aria-label'),
      /original report fields/,
    );
    if (process.env.CONTACT_SCREENSHOTS)
      await page.screenshot({
        path: process.env.CONTACT_SCREENSHOTS + '/095-assets-desktop.png',
        fullPage: true,
      });
    checks.push(
      'Asset status labels, scoped action names, expanded source rows and keyboard focus survive refresh',
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      JSON.stringify(
        { checks, errors, external_requests: external, synthetic_website_requests: requests() },
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
