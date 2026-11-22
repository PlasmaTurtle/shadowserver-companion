/** Fresh setup through Settings, against the explicit synthetic local fixture. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const { waitForJSON } = require('./browser_wait.cjs');

(async () => {
  assert(process.env.SETUP_BROWSER_FIXTURE, 'Explicit synthetic workspace required');
  const fixturePath = process.env.SETUP_BROWSER_FIXTURE;
  const screenshotDirectory = process.env.QA_DIR || path.dirname(fixturePath);
  const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
  assert.equal(fixture.mode, 'synthetic-setup-acceptance');
  const { base } = fixture;
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    headless: true,
    args: ['--no-sandbox', '--no-zygote'],
  });
  const checks = [],
    errors = [],
    external = [],
    responses = [];
  let page;
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.route('**/*', (route) => {
      const url = route.request().url();
      if (/^https?:/.test(url) && !url.startsWith(base + '/')) {
        external.push(url);
        return route.abort();
      }
      return route.continue();
    });
    page = await context.newPage();
    page.setDefaultTimeout(15000);
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('response', (response) => {
      const url = new URL(response.url());
      if (url.origin === base && url.pathname.startsWith('/api/')) {
        responses.push({ path: url.pathname, status: response.status() });
        if (responses.length > 30) responses.shift();
      }
    });
    const json = async (url) => (await context.request.get(base + url)).json();
    const mutate = (url, method, body) =>
      page.evaluate(
        async ({ url, method, body }) => {
          const { token } = await (await fetch('/api/bootstrap')).json();
          const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json', 'X-Workbench-Token': token },
            ...(body === undefined ? {} : { body: JSON.stringify(body) }),
          });
          return { status: response.status, body: await response.json() };
        },
        { url, method, body },
      );
    const snapshot = (name) =>
      page.screenshot({
        path: path.join(screenshotDirectory, name + '.png'),
        fullPage: true,
      });
    const nextStep = (step) => page.locator(`.setup-steps [data-step="${step}"]`).click();
    const assertNoOverflow = async () => {
      const overflow = await page
        .locator('#modal')
        .evaluate((el) => el.scrollWidth - el.clientWidth);
      assert(overflow <= 1, `Setup dialog overflows horizontally by ${overflow}px`);
    };
    const dismissNews = async () => {
      const news = page.locator('[data-action="software-whats-new-dismiss"]');
      await news.waitFor();
      await news.click();
      await page.locator('#modal').waitFor({ state: 'hidden' });
    };

    await page.goto(fixture.launch_url);
    await page.locator('#setup-wizard').waitFor();
    assert.equal((await json('/api/setup')).required, true);
    assert.equal(await page.locator('#modal-title').textContent(), 'Set up your workspace');
    for (const id of ['setup-shadow-key', 'setup-shadow-secret', 'setup-nvd-key'])
      assert.equal(await page.locator('#' + id).getAttribute('type'), 'password');
    assert((await mutate('/api/setup/complete', 'POST')).status >= 400);
    await assertNoOverflow();
    await snapshot('setup-connections-desktop');
    checks.push(
      'Fresh installation opens setup before release notes; incomplete setup cannot complete',
    );

    await page.locator('#setup-shadow-key').fill('unsaved-synthetic-key');
    page.once('dialog', (dialog) => dialog.dismiss());
    await page.locator('[data-action="setup-later"]').click();
    assert.equal(await page.locator('#setup-shadow-key').inputValue(), 'unsaved-synthetic-key');
    await page.locator('#setup-shadow-key').fill('');
    await page.locator('[data-action="setup-manual-connections"]').click();
    await page.locator('#setup-profile-form').waitFor();
    const originalRegions = await page
      .locator('#setup-profile-form [name="regions"]:checked')
      .evaluateAll((els) => els.map((el) => el.value));
    await page.locator('#setup-agency-preset').selectOption('fbi');
    assert.equal(
      await page.locator('#setup-agency').inputValue(),
      'Federal Bureau of Investigation',
    );
    assert.equal(
      await page.locator('#setup-department').inputValue(),
      'U.S. Department of Justice',
    );
    assert.deepEqual(
      await page
        .locator('#setup-profile-form [name="regions"]:checked')
        .evaluateAll((els) => els.map((el) => el.value)),
      originalRegions,
    );
    await page.locator('#setup-agency-preset').selectOption('usss');
    await page.locator('#setup-analyst_name').fill('Synthetic Setup Analyst');
    await page.locator('#setup-analyst_title').fill('');
    await page.locator('#setup-office').fill('Charlotte, North Carolina');
    for (const checkbox of await page.locator('#setup-profile-form [name="regions"]:checked').all())
      await checkbox.uncheck();
    await page.locator('#setup-profile-form [name="regions"][value="North Carolina"]').check();
    await page.setViewportSize({ width: 740, height: 900 });
    await assertNoOverflow();
    await snapshot('setup-profile-narrow');
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator('#setup-profile-form button[type="submit"]').click();
    await page.locator('#setup-schedule-form').waitFor();
    assert.equal(await page.locator('#setup-schedule-form [name="enabled"]').isChecked(), false);
    await page.locator('#setup-schedule-form button[type="submit"]').click();
    await dismissNews();
    const manual = await json('/api/setup');
    assert.equal(manual.completed, true);
    assert.equal(manual.required, false);
    assert.equal(manual.steps.connections.mode, 'manual');
    assert.equal(manual.steps.automation.mode, 'manual');
    assert.equal(manual.profile.analyst_title, '');
    await page.reload();
    await page.locator('#main').waitFor();
    assert.equal(await page.locator('#setup-wizard').count(), 0);
    assert.equal((await json('/api/software/whats-new')).should_show, false);
    checks.push(
      'Unsaved keys are protected; manual/offline setup works; presets preserve jurisdiction and blank title; completion survives reload',
    );

    await page.goto(base + '/#settings');
    await page.locator('#settings-form').waitFor();
    await page.locator('[data-action="open-setup"]').first().click();
    await page.locator('#setup-shadow-form').waitFor();
    await nextStep('profile');
    await page.locator('#setup-analyst_name').fill('Updated Synthetic Setup Analyst');
    await nextStep('automation');
    await page.locator('#setup-schedule-time').fill('08:35');
    const scheduleBeforeDraft = await json('/api/schedule');
    const prematureWrites = [];
    const recordPrematureWrite = (request) => {
      if (request.method() !== 'GET' && request.url().startsWith(base + '/api/'))
        prematureWrites.push(new URL(request.url()).pathname);
    };
    page.on('request', recordPrematureWrite);
    await page.locator('#setup-schedule-form button[type="submit"]').click();
    await page.locator('#setup-error:not([hidden])').waitFor();
    page.off('request', recordPrematureWrite);
    assert.match(await page.locator('#setup-error').textContent(), /profile|identity/i);
    assert.deepEqual(prematureWrites, []);
    assert.equal(await page.locator('#setup-schedule-time').inputValue(), '08:35');
    assert.equal((await json('/api/setup')).profile.analyst_name, 'Synthetic Setup Analyst');
    assert.deepEqual((await json('/api/schedule')).config, scheduleBeforeDraft.config);
    await snapshot('setup-unsaved-profile-protected');
    await nextStep('profile');
    assert.equal(
      await page.locator('#setup-analyst_name').inputValue(),
      'Updated Synthetic Setup Analyst',
    );
    await page.locator('#setup-profile-form button[type="submit"]').click();
    await page.locator('#setup-schedule-form').waitFor();
    assert.equal(await page.locator('#setup-schedule-time').inputValue(), '08:35');
    await page.locator('#setup-schedule-form button[type="submit"]').click();
    await page.locator('#modal').waitFor({ state: 'hidden' });
    assert.equal(
      (await json('/api/setup')).profile.analyst_name,
      'Updated Synthetic Setup Analyst',
    );
    assert.equal((await json('/api/schedule')).config.hour, 8);
    assert.equal((await json('/api/schedule')).config.minute, 35);
    checks.push(
      'Finishing setup protects unsaved identity edits and schedule choices until the profile is explicitly saved',
    );

    await page.locator('[data-action="open-setup"]').first().click();
    await page.locator('#setup-shadow-form').waitFor();
    await page.locator('#setup-shadow-key').fill(fixture.api_key);
    await page.locator('#setup-shadow-secret').fill(fixture.secret);
    await page.locator('#setup-shadow-form button[type="submit"]').click();
    await waitForJSON(
      context.request,
      base + '/api/shadowserver/status',
      (value) => value.connected,
    );
    await page
      .locator('#setup-wizard .badge')
      .filter({ hasText: /^Connected$/ })
      .waitFor();
    assert.equal(await page.locator('#setup-shadow-key').inputValue(), '');
    assert.equal(await page.locator('#setup-shadow-secret').inputValue(), '');
    const persisted = await page.evaluate(() =>
      JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }),
    );
    const publicStatus = JSON.stringify(await json('/api/shadowserver/status'));
    for (const secret of [fixture.api_key, fixture.secret]) {
      assert(!persisted.includes(secret));
      assert(!publicStatus.includes(secret));
    }
    await page.locator('[data-action="setup-connections-next"]').click();
    await nextStep('automation');
    await page.locator('#setup-schedule-form').waitFor();
    const choices = await page
      .locator('#setup-subscription option')
      .evaluateAll((els) => els.map((el) => el.value));
    assert(choices.includes('US-NC'));
    assert(!choices.includes('US-SC'));
    assert(choices.includes('united-states') && choices.includes('agency-custom'));
    assert.equal(await page.locator('#setup-subscription').inputValue(), 'US-NC');
    const scope = await json('/api/shadowserver/status');
    assert.deepEqual(scope.jurisdiction.regions, ['North Carolina']);
    assert.equal(scope.selection_defaults.subscription, 'US-NC');
    const rejected = await mutate('/api/shadowserver/catalog', 'POST', {
      start: '2026-11-06',
      end: '2026-11-06',
      subscription: 'US-SC',
      report_type: 'scan_http_vulnerable',
    });
    assert(rejected.status >= 400, 'Server must reject stale off-jurisdiction catalog selections');
    await page.locator('#setup-schedule-form [name="enabled"]').check();
    await page.locator('#setup-schedule-form [name="shadowserver"]').check();
    await page.locator('#setup-schedule-form [name="reference"]').uncheck();
    await page.locator('#setup-schedule-form [name="report_types"]').first().check();
    await snapshot('setup-automation-desktop');
    await page.locator('#setup-schedule-form button[type="submit"]').click();
    await page.locator('#modal').waitFor({ state: 'hidden' });
    const schedule = await json('/api/schedule');
    assert.equal(schedule.config.enabled, true);
    assert.equal(schedule.config.subscription, 'US-NC');
    assert.equal(schedule.config.reference, false);
    assert.equal((await json('/api/setup')).steps.connections.mode, 'configured');
    checks.push(
      'Synthetic connection clears secrets; jurisdiction filters setup choices and rejects stale requests; automatic schedule persists',
    );

    await page.goto(base + '/#data?tab=api');
    await page.locator('#api-catalog-form').waitFor();
    assert.equal(await page.locator('#api-subscription').inputValue(), 'US-NC');
    assert.equal(await page.locator('#api-subscription option[value="US-SC"]').count(), 0);
    await page.goto(base + '/#settings');
    await page.locator('#settings-form').waitFor();
    await page.locator('#f-office').fill('Charlotte Field Office — Synthetic QA');
    page.once('dialog', (dialog) => dialog.dismiss());
    await page.locator('[data-action="open-setup"]').first().click();
    assert.equal(await page.locator('#setup-wizard').count(), 0);
    assert.equal(
      await page.locator('#f-office').inputValue(),
      'Charlotte Field Office — Synthetic QA',
    );
    const saved = page.waitForResponse(
      (response) =>
        response.url() === base + '/api/settings' && response.request().method() === 'PUT',
    );
    await page.locator('#settings-save-button').click();
    assert.equal((await saved).status(), 200);
    await page.locator('#settings-save-status[data-state="saved"]').waitFor();
    await page.reload();
    await page.locator('#f-office').waitFor();
    assert.equal(
      await page.locator('#f-office').inputValue(),
      'Charlotte Field Office — Synthetic QA',
    );
    await page.locator('#software-updates-panel').waitFor();
    await snapshot('settings-release-desktop');
    await page.locator('[data-action="software-whats-new"]').click();
    await page.locator('#modal[open] [data-action="software-whats-new-dismiss"]').waitFor();
    assert.equal(await page.locator('#modal-title').textContent(), 'What’s new');
    await dismissNews();
    checks.push(
      'Catalog and setup share jurisdiction defaults; Settings protect and persist edits; installed release notes reopen without a remote request',
    );

    await page
      .locator('#settings-agency-preset option[value="fbi"]')
      .waitFor({ state: 'attached' });
    const jurisdictionBeforePreset = await page.locator('#f-regions').inputValue();
    await page.locator('#settings-agency-preset').selectOption('fbi');
    assert.equal(await page.locator('#f-agency').inputValue(), 'Federal Bureau of Investigation');
    assert.equal(await page.locator('#f-department').inputValue(), 'U.S. Department of Justice');
    assert.equal(await page.locator('#f-regions').inputValue(), jurisdictionBeforePreset);
    await page.getByText('Import formats and lookup options', { exact: true }).click();
    await page.locator('#f-timeout').fill('');
    await page.getByText('Import formats and lookup options', { exact: true }).click();
    const invalidWrites = [];
    const recordInvalidWrite = (request) => {
      if (request.method() === 'PUT' && request.url() === base + '/api/settings')
        invalidWrites.push(request.url());
    };
    page.on('request', recordInvalidWrite);
    await page.locator('#settings-save-button').click();
    await page.waitForFunction(() => document.activeElement?.id === 'f-timeout');
    assert.equal(
      await page.locator('#f-timeout').evaluate((el) => el.closest('details').open),
      true,
    );
    page.off('request', recordInvalidWrite);
    assert.deepEqual(invalidWrites, []);
    await snapshot('settings-visible-validation');
    await page.locator('#f-timeout').fill('10');
    await page.locator('#settings-save-button').click();
    await page.locator('#settings-save-status[data-state="saved"]').waitFor();
    assert.equal((await json('/api/bootstrap')).settings.agency, 'Federal Bureau of Investigation');

    assert.equal(
      (await mutate('/api/settings', 'PUT', { office: 'Synthetic office saved from another view' }))
        .status,
      200,
    );
    const themeSaved = page.waitForResponse(
      (response) =>
        response.url() === base + '/api/settings' && response.request().method() === 'PUT',
    );
    await page.locator('#theme-toggle').click();
    const themeResponse = await themeSaved;
    assert.equal(themeResponse.status(), 200);
    const themeBody = themeResponse.request().postDataJSON();
    assert.deepEqual(Object.keys(themeBody), ['appearance']);
    assert.equal(
      (await json('/api/bootstrap')).settings.office,
      'Synthetic office saved from another view',
    );
    assert.equal(
      await page.locator('input[name="appearance"]:checked').inputValue(),
      themeBody.appearance,
    );
    await page.reload();
    await page.locator('#settings-form').waitFor();
    checks.push(
      'Settings presets apply, hidden invalid controls become visible, and theme-only saves preserve newer profile values',
    );

    let releaseKeySave;
    let keySaveReceived;
    const receivedKeySave = new Promise((resolve) => {
      keySaveReceived = resolve;
    });
    const keyResponse = new Promise((resolve) => {
      releaseKeySave = resolve;
    });
    const credentialRoute = async (route) => {
      if (route.request().method() !== 'PUT') return route.continue();
      keySaveReceived();
      await keyResponse;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ configured: true, source: 'session', remember_supported: false }),
      });
    };
    await page.route(base + '/api/nvd/credentials', credentialRoute);
    await page.locator('#nvd-api-key').fill('synthetic-first-key');
    await page.locator('#nvd-key-form button[type="submit"]').click();
    await receivedKeySave;
    await page.locator('#nvd-api-key').fill('synthetic-newer-unsaved-key');
    releaseKeySave();
    await page
      .locator('#nvd-key-feedback')
      .filter({ hasText: 'New key edits remain unsaved' })
      .waitFor();
    assert.equal(await page.locator('#nvd-api-key').inputValue(), 'synthetic-newer-unsaved-key');
    const declinedNavigation = page.waitForEvent('dialog');
    await page.evaluate(() => {
      location.hash = '#activity';
    });
    await (await declinedNavigation).dismiss();
    assert.equal(await page.locator('#nvd-api-key').inputValue(), 'synthetic-newer-unsaved-key');
    assert.equal(await page.locator('#settings-form').count(), 1);
    const persistedKeyState = await page.evaluate(() =>
      JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }),
    );
    assert(!persistedKeyState.includes('synthetic-first-key'));
    assert(!persistedKeyState.includes('synthetic-newer-unsaved-key'));
    await page.locator('[data-action="clear-nvd-key"]').click();
    assert.equal(await page.locator('#nvd-api-key').inputValue(), '');
    await page.unroute(base + '/api/nvd/credentials', credentialRoute);
    checks.push(
      'Credential save completion preserves newer input; navigation protects it and explicit clearing removes it without browser persistence',
    );

    await page.setViewportSize({ width: 390, height: 844 });
    if ((await page.locator('#menu-toggle').getAttribute('aria-expanded')) === 'true')
      await page.locator('#menu-toggle').click();
    await page.waitForFunction(
      () => document.querySelector('#sidebar').getBoundingClientRect().right <= 1,
    );
    await page.locator('#main h1').scrollIntoViewIfNeeded();
    assert((await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 1);
    await page.screenshot({ path: path.join(screenshotDirectory, 'settings-narrow-reviewed.png') });

    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      JSON.stringify(
        {
          checks,
          page_errors: errors,
          external_requests: external,
          native_windows_acceptance: false,
        },
        null,
        2,
      ),
    );
  } catch (error) {
    if (page) {
      const setup = await page
        .evaluate(() => ({
          title: document.querySelector('#modal-title')?.textContent,
          error: document.querySelector('#setup-error')?.textContent,
          invalid: [...document.querySelectorAll('#setup-wizard :invalid')].map(
            (element) => element.id || element.name,
          ),
        }))
        .catch(() => null);
      console.error(JSON.stringify({ setup, responses }));
      await page
        .screenshot({
          path: path.join(screenshotDirectory, 'setup-release-failure.png'),
          fullPage: true,
        })
        .catch(() => {});
      console.error(JSON.stringify({ page_errors: errors, external_requests: external }));
    }
    throw error;
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
