/** Real-browser contact finder + independent entity UI; synthetic websites only. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { waitForJSON } = require('../../../tests/browser_wait.cjs');
(async () => {
  assert(process.env.CONTACT_BROWSER_FIXTURE, 'Synthetic fixture metadata required');
  const fixture = JSON.parse(fs.readFileSync(process.env.CONTACT_BROWSER_FIXTURE, 'utf8'));
  const { base } = fixture;
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const checks = [],
    errors = [],
    external = [],
    layout = [];
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
    page.setDefaultTimeout(18000);
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('dialog', (dialog) => dialog.accept());
    const state = async () =>
      (await context.request.get(`${base}/api/entities/${fixture.entity_id}/contacts`)).json();
    const count = () =>
      fs.existsSync(fixture.requests_path)
        ? fs.readFileSync(fixture.requests_path, 'utf8').trim().split('\n').filter(Boolean).length
        : 0;
    const shot = async (name) => {
      if (!process.env.CONTACT_SCREENSHOTS) return;
      fs.mkdirSync(process.env.CONTACT_SCREENSHOTS, { recursive: true });
      await page.waitForFunction(() => !document.querySelector('#toasts .toast'));
      await page.evaluate(() => {
        document.activeElement?.blur?.();
        window.scrollTo(0, 0);
      });
      await page.screenshot({
        path: path.join(process.env.CONTACT_SCREENSHOTS, name + '.png'),
        fullPage: true,
      });
    };
    const setTheme = async (theme) => {
      if ((await page.evaluate(() => document.documentElement.dataset.theme || 'light')) !== theme)
        await page.locator('#theme-toggle').click();
      await page.waitForFunction(
        (theme) => (document.documentElement.dataset.theme || 'light') === theme,
        theme,
      );
    };
    const measure = async (view) => {
      const measured = await page.evaluate(() => {
        const first = document.querySelector('[data-primary-route="true"] h3');
        const channels = (color) => color.match(/[\d.]+/g).map(Number);
        let parent = first,
          background;
        while (parent) {
          const value = channels(getComputedStyle(parent).backgroundColor);
          if (value.length === 3 || value[3] >= 0.99) {
            background = value;
            break;
          }
          parent = parent.parentElement;
        }
        background ||= channels(getComputedStyle(document.documentElement).backgroundColor);
        const luminance = (rgb) =>
          rgb.slice(0, 3).reduce((sum, channel, i) => {
            const value = channel / 255;
            return (
              sum +
              (value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4) *
                [0.2126, 0.7152, 0.0722][i]
            );
          }, 0);
        const foregroundLuminance = luminance(channels(getComputedStyle(first).color));
        const backgroundLuminance = luminance(background);
        return {
          viewport_width: innerWidth,
          viewport_height: innerHeight,
          first_contact_bottom: first.getBoundingClientRect().bottom,
          contact_font_size: getComputedStyle(first).fontSize,
          list_height: document.querySelector('.contact-primary-list').getBoundingClientRect()
            .height,
          horizontal_overflow: document.documentElement.scrollWidth > innerWidth + 2,
          text_contrast:
            (Math.max(foregroundLuminance, backgroundLuminance) + 0.05) /
            (Math.min(foregroundLuminance, backgroundLuminance) + 0.05),
        };
      });
      assert(!measured.horizontal_overflow);
      assert(
        measured.first_contact_bottom < measured.viewport_height,
        'First contact should be visible without scrolling',
      );
      assert(parseFloat(measured.contact_font_size) >= 24);
      assert(measured.text_contrast >= 4.5, 'Contact value must remain readable in this theme');
      layout.push({ view, ...measured });
    };
    await page.goto(fixture.launch_url);
    await page.locator('#main').waitFor();
    await page.goto(`${base}/#entity/${fixture.entity_id}?tab=contacts`);
    await page.locator('#entity-contact-form').waitFor();
    await page.waitForFunction(
      () => document.querySelector('#contact-root')?.value === 'example.com',
    );
    assert.equal(count(), 0, 'Entity view must not start a website lookup');
    assert.equal(await page.locator('#case-plan').count(), 0);
    assert.match(await page.locator('#sidebar [aria-current="page"]').innerText(), /Entities/);
    await page.locator('[data-action="start-contact-discovery"]').click();
    await page
      .locator('.contact-candidate h3')
      .filter({ hasText: 'security@example.com' })
      .waitFor();
    const first = await state();
    const security = first.contacts.find((c) => c.value === 'security@example.com');
    const technical = first.contacts.find((c) => c.value === 'it@example.com');
    assert(security && security.decision === 'pending' && security.usable);
    assert.equal(await page.locator('[data-decision="confirm"]').count(), 0);
    assert.equal(
      await page.locator('details[data-contact-detail="details"]').evaluate((e) => e.open),
      false,
    );
    assert.match(await page.locator('#contact-discovery-panel h2').innerText(), /Contact found/i);
    assert.equal(await page.locator('[data-primary-route="true"]').count(), 1);
    assert.match(
      await page.locator('[data-primary-route="true"] h3').innerText(),
      /security@example.com/,
    );
    assert.equal(await page.locator('#contact-discovery-panel.panel').count(), 0);
    assert.equal(await page.locator('#contact-discovery-panel .panel').count(), 0);
    const sourcePreview = page.locator(`details[data-contact-detail="source-${security.id}"]`);
    const beforePreview = count();
    assert.equal(await sourcePreview.evaluate((e) => e.open), false);
    await sourcePreview.locator('summary').click();
    assert.match(await sourcePreview.innerText(), /Captured/);
    assert.equal(count(), beforePreview, 'Opening a saved source preview must not fetch the site');
    await sourcePreview.locator('summary').click();
    checks.push('Per-contact captured source preview opens locally without a website request');
    await page.locator('#entity-contact-form [name="contact_name"]').fill('Existing analyst entry');
    await page.locator(`[data-contact-use="${security.id}"]`).click();
    assert.equal(
      await page.locator('#entity-contact-form [name="contact_email"]').inputValue(),
      'security@example.com',
    );
    assert.equal(
      await page.locator('#entity-contact-form [name="contact_name"]').inputValue(),
      'Existing analyst entry',
    );
    await page.locator('#entity-contact-form button[type="submit"]').click();
    await waitForJSON(
      context.request,
      `${base}/api/entities/${fixture.entity_id}`,
      (value) => value.entity_profile?.contact_email === 'security@example.com',
    );
    checks.push(
      'Independent entity finder, immediate suggestions, no verification gates, blank-field autocomplete, manual name preserved',
    );
    for (const theme of ['light', 'dark']) {
      await setTheme(theme);
      await shot('0982-entity-contacts-' + theme);
      await measure('entity-desktop-' + theme);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await shot('0982-entity-contacts-mobile');
    await measure('entity-mobile');
    await page.setViewportSize({ width: 1440, height: 1100 });
    const details = page.locator('details[data-contact-detail="details"]');
    await details.locator(':scope > summary').click();
    await details.locator(':scope > summary').focus();
    const beforeReload = count();
    await page.evaluate(async () =>
      (await import('/modules/ui/static/main.js')).application.actions.loadContactDiscovery(),
    );
    assert.equal(count(), beforeReload);
    assert(await details.evaluate((e) => e.open));
    assert.equal(
      await page.evaluate(() => document.activeElement?.parentElement?.dataset.contactDetail),
      'details',
    );
    const download = await context.request.get(
      `${base}/api/entities/${fixture.entity_id}/contacts/evidence.zip`,
    );
    assert.equal(download.status(), 200);
    assert.equal((await download.body()).subarray(0, 2).toString(), 'PK');
    checks.push(
      'Saved-state refresh preserves collapsed-detail state and focus; evidence ZIP downloads',
    );
    await details.locator(':scope > summary').click();
    await page.locator(`[data-contact-value-copy="${security.id}"]`).click();
    assert.equal(await page.evaluate(() => navigator.clipboard.readText()), 'security@example.com');
    const beforeCase = count();
    await page.goto(`${base}/#workspace/notifications/${fixture.case_id}?tab=contact`);
    await page.locator('#case-plan').waitFor({ state: 'attached' });
    await page
      .locator('.contact-candidate h3')
      .filter({ hasText: 'security@example.com' })
      .waitFor();
    assert.equal(count(), beforeCase);
    assert.match(await page.locator('#contact-discovery-panel').innerText(), /Known contact/);
    assert.match(
      await page.locator('#sidebar [aria-current="page"]').innerText(),
      /Investigations/,
    );
    assert.equal(await page.locator('.saved-plan-editor').evaluate((e) => e.open), false);
    await page.locator(`[data-contact-use="${technical.id}"]`).click();
    assert.equal(await page.locator('.saved-plan-editor').evaluate((e) => e.open), true);
    assert.equal(
      await page.locator('#case-plan [name="contact_role"]').inputValue(),
      'IT Department',
    );
    assert.equal(await page.evaluate(() => document.activeElement?.name), 'contact_role');
    checks.push('Fill reveals the saved-plan editor and focuses the first newly filled field');
    await page.locator('#case-plan [name="contact_email"]').fill('typed@example.com');
    await page.locator(`[data-contact-use="${security.id}"]`).click();
    assert.equal(
      await page.locator('#case-plan [name="contact_email"]').inputValue(),
      'typed@example.com',
    );
    checks.push(
      'Known entity contact reused in notification without lookup; typed email survives selection',
    );
    await page.locator('#case-plan button[type="submit"]').click();
    await waitForJSON(
      context.request,
      `${base}/api/cases/${fixture.case_id}`,
      (value) => value.case.contact_email === 'typed@example.com',
    );
    for (const theme of ['light', 'dark']) {
      await setTheme(theme);
      await shot('0982-notification-contacts-' + theme);
      await measure('investigation-desktop-' + theme);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    assert(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2),
      'Mobile horizontal overflow',
    );
    await shot('0982-notification-contacts-mobile');
    await measure('investigation-mobile');
    checks.push('Contact view inspected in light/dark at desktop and mobile widths');
    await details.locator(':scope > summary').click();
    await page.locator('#contact-source-url').fill('https://example.com/contact');
    const beforeFocused = count();
    await page.locator('[data-action="inspect-contact-source"]').click();
    await waitForJSON(
      context.request,
      `${base}/api/entities/${fixture.entity_id}/contacts`,
      (saved) =>
        saved.latest_run?.source_url === 'https://example.com/contact' && !saved.active_job,
    );
    assert.equal(count() - beforeFocused, 1, 'Focused lookup fetches one page only');
    assert.equal(
      await page.locator('#case-plan [name="contact_email"]').inputValue(),
      'typed@example.com',
    );
    checks.push('Focused company-page lookup uses one request and preserves typed contact fields');
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      JSON.stringify(
        { passed: true, checks, layout, page_errors: errors, external_requests: external },
        null,
        2,
      ),
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
