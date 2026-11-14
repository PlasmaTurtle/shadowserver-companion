/** Real keyboard/focus/navigation acceptance on a synthetic local workspace. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const base = process.env.ECLIPSE_BASE_URL;
  const out = process.env.QA_OUT;
  const results = {
    checks: [],
    errors: [],
    environment: 'Chromium on Linux; native Windows acceptance remains separate',
  };
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    args: ['--no-sandbox', '--no-zygote'],
  });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    const decideDialog = async (action, decision) => {
      const shown = page.waitForEvent('dialog');
      const pending = action();
      const dialog = await shown;
      await dialog[decision]();
      await pending;
    };
    page.on('pageerror', (error) => results.errors.push(error.message));
    await page.route('**/*', (route) =>
      route.request().url().startsWith(base) || route.request().url().startsWith('data:')
        ? route.continue()
        : route.abort(),
    );
    const initialSave = page.waitForResponse(
      (response) =>
        response.url() === base + '/api/settings' && response.request().method() === 'PUT',
    );
    await page.goto(process.env.ECLIPSE_LAUNCH_URL);
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    const initialResponse = await initialSave;
    assert.equal(
      initialResponse.status(),
      200,
      'Initial appearance must satisfy the settings API contract',
    );
    const originalSettings = await initialResponse.json();
    const themeSave = page.waitForResponse(
      (response) =>
        response.url() === base + '/api/settings' && response.request().method() === 'PUT',
    );
    await page.locator('#theme-toggle').click();
    const themeResponse = await themeSave;
    assert.equal(themeResponse.status(), 200, 'Header appearance must persist to the actual API');
    const savedTheme = await themeResponse.json();
    for (const key of ['regions', 'office', 'critical_only'])
      assert.deepEqual(savedTheme[key], originalSettings[key]);
    await page.reload();
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    assert.equal(await page.locator('html').getAttribute('data-theme'), savedTheme.appearance);
    results.checks.push(
      'Startup and header appearance save through the real API, retain preferences, and survive reload',
    );
    await page.locator('#global-search').click();
    await page.getByRole('dialog', { name: 'Find a business', exact: true }).waitFor();
    assert.equal(await page.evaluate(() => document.activeElement.name), 'q');
    for (let i = 0; i < 9; i++) {
      await page.keyboard.press('Tab');
      assert(
        await page.evaluate(() =>
          document.querySelector('#modal').contains(document.activeElement),
        ),
        'Native dialog must contain keyboard focus',
      );
    }
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => document.activeElement.id === 'global-search');
    results.checks.push(
      'Named search dialog, initial field focus, native Tab containment and Escape focus return',
    );
    const cases = await page.evaluate(async () => await (await fetch('/api/cases')).json());
    const work = cases.find((row) => row.stage === 'in_progress');
    assert(work);
    await page.goto(base + '/#workspace/notifications/' + work.id);
    await page.getByRole('tab', { name: 'Report', exact: true }).waitFor();
    const docs = page.getByRole('tab', { name: 'Report', exact: true });
    await docs.focus();
    await page.keyboard.press('ArrowRight');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'editor-tab-assets');
    assert.equal(
      await docs.getAttribute('aria-selected'),
      'true',
      'Arrow movement alone must not discard a form',
    );
    await page.keyboard.press('Enter');
    await page.getByRole('tabpanel', { name: /^Assets(?:\s|$)/ }).waitFor();
    await page.getByRole('tab', { name: /^Assets(?:\s|$)/ }).focus();
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('Enter');
    await page.locator('#case-plan').waitFor();
    const address = page.locator('#case-plan [name="contact_name"]');
    await address.fill('Unsaved keyboard contact');
    await page.getByRole('tab', { name: 'Contact & delivery', exact: true }).focus();
    await page.keyboard.press('ArrowRight');
    await decideDialog(() => page.keyboard.press('Enter'), 'dismiss');
    assert.equal(
      await page
        .getByRole('tab', { name: 'Contact & delivery', exact: true })
        .getAttribute('aria-selected'),
      'true',
    );
    assert.equal(await address.inputValue(), 'Unsaved keyboard contact');
    await decideDialog(() => page.keyboard.press('Enter'), 'accept');
    await page.locator('#editor-tab-closing[aria-selected="true"]').waitFor();
    results.checks.push(
      'Manual arrow-key tabs, linked tabpanel, and unchanged dirty-form confirmation',
    );
    await page.getByRole('tab', { name: 'Contact & delivery', exact: true }).click();
    await page.locator('#case-plan').waitFor();
    await page.locator('#case-plan [name="contact_name"]').fill('Unsaved contact form');
    const draftSaves = [];
    const requestListener = (request) => {
      if (request.method() === 'PUT' && request.url().includes('/draft'))
        draftSaves.push(request.url());
    };
    page.on('request', requestListener);
    await page.keyboard.press('Control+s');
    await page
      .getByText('Use the current form’s Save or Record button to save these changes.', {
        exact: true,
      })
      .waitFor();
    assert.equal(draftSaves.length, 0, 'Contact edits must not produce an unrelated draft save');
    page.off('request', requestListener);
    await decideDialog(() => page.locator('#sidebar [data-nav="settings"]').click(), 'accept');
    await page.locator('#settings-form').waitFor();
    await page.locator('#f-office').fill('Unsaved settings test');
    await decideDialog(() => page.locator('#sidebar [data-nav="workspace"]').click(), 'dismiss');
    assert.equal(await page.locator('#f-office').inputValue(), 'Unsaved settings test');
    await decideDialog(() => page.locator('#sidebar [data-nav="workspace"]').click(), 'accept');
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    results.checks.push(
      'Ctrl+S respects contact edits, and dirty Settings prevent accidental navigation',
    );
    await page.locator('#sidebar [data-nav="library"]').click();
    await page.locator('#resource-form').waitFor();
    const explanation = page.locator('#resource-form [name="body"]');
    await explanation.fill('Unsaved library explanation');
    await decideDialog(() => page.locator('#sidebar [data-nav="workspace"]').click(), 'dismiss');
    assert.equal(await explanation.inputValue(), 'Unsaved library explanation');
    await decideDialog(() => page.locator('[data-action="new-block"]').click(), 'dismiss');
    assert.equal(await explanation.inputValue(), 'Unsaved library explanation');
    await decideDialog(() => page.locator('#sidebar [data-nav="workspace"]').click(), 'accept');
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    results.checks.push('Library navigation and new explainer actions preserve unsaved wording');
    await page.goto(base + '/#workspace/notifications/' + work.id);
    await page.getByRole('button', { name: 'Recent report activity', exact: true }).click();
    await page.getByRole('dialog', { name: 'Recent report activity', exact: true }).waitFor();
    assert.equal(await page.evaluate(() => document.activeElement.id), 'modal-title');
    await page.locator('[data-action="report-activity"]').evaluate((node) => node.remove());
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => document.activeElement.id === 'main');
    results.checks.push(
      'Read-only activity dialog receives focus; removed opener falls back to main content',
    );
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForFunction(() => document.querySelector('#sidebar').inert);
    assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'), 'false');
    await page.locator('#menu-toggle').click();
    await page.getByRole('dialog', { name: 'Main navigation', exact: true }).waitFor();
    assert(await page.locator('.shell').evaluate((node) => node.inert));
    for (let i = 0; i < 18; i++) {
      await page.keyboard.press(i % 2 ? 'Shift+Tab' : 'Tab');
      assert(
        await page.locator('#sidebar').evaluate((node) => node.contains(document.activeElement)),
        'Open drawer must contain keyboard focus',
      );
    }
    if (out) {
      fs.mkdirSync(out, { recursive: true });
      await page.screenshot({ path: path.join(out, 'mobile-navigation-focus.png') });
    }
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => document.activeElement.id === 'menu-toggle');
    assert(await page.locator('#sidebar').evaluate((node) => node.inert));
    assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'), 'false');
    await page.locator('#menu-toggle').click();
    await page.locator('#close-navigation').click();
    await page.waitForFunction(() => document.activeElement.id === 'menu-toggle');
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.waitForFunction(() => !document.querySelector('#sidebar').inert);
    assert(!(await page.locator('.shell').evaluate((node) => node.inert)));
    results.checks.push(
      'Mobile drawer hidden-state inertness, focus containment, Escape/close return and desktop resize recovery',
    );
    await page.goto(base + '/#entity/' + work.entity_id + '?tab=assets');
    await page.getByRole('heading', { name: 'Associated hostnames', exact: true }).waitFor();
    assert.equal(
      await page.locator('#sidebar [data-nav="entities"]').getAttribute('aria-current'),
      'page',
    );
    await page.goto(base + '/#workspace/notifications/' + work.id + '?tab=entity');
    await page.locator('#entity-details-form').waitFor();
    assert.equal(
      await page.locator('#sidebar [data-nav="entities"]').getAttribute('aria-current'),
      'page',
    );
    results.checks.push(
      'Independent entity deep links and legacy report-to-entity redirects agree with the sidebar',
    );
    assert.deepEqual(results.errors, []);
    results.passed = true;
  } finally {
    if (out) {
      fs.mkdirSync(out, { recursive: true });
      fs.writeFileSync(
        path.join(out, 'interaction-results.json'),
        JSON.stringify(results, null, 2),
      );
    }
    await browser.close();
  }
  console.log(JSON.stringify(results));
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
