/** Real document work, five freezes, contact-plan continuity and responsive task views. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
(async () => {
  assert(process.env.INVESTIGATIONS_FIXTURE, 'Explicit synthetic fixture required');
  const fixture = JSON.parse(fs.readFileSync(process.env.INVESTIGATIONS_FIXTURE, 'utf8'));
  assert.match(fixture.base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const output = process.env.INVESTIGATIONS_SCREENSHOTS;
  if (output) fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    headless: true,
    args: ['--no-sandbox', '--no-zygote'],
  });
  const errors = [],
    external = [],
    checks = [],
    freezeMs = [];
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
    page.setDefaultTimeout(15000);
    async function screenshot(name) {
      if (!output) return;
      const dismiss = page.getByRole('button', { name: 'Dismiss notification', exact: true });
      while (await dismiss.count()) await dismiss.first().click();
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: path.join(output, name), fullPage: true });
    }
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(fixture.launch_url);
    await page
      .getByRole('heading', { name: 'Workspace', exact: true })
      .waitFor()
      .catch(async (error) => {
        console.error('Startup failure:', await page.locator('#main').innerText(), errors);
        throw error;
      });
    await page.goto(fixture.base + '/#investigations/' + fixture.case_id);
    await page.locator('.document-paper').waitFor();
    assert.equal(await page.locator('.section-rail [data-report-section]').count(), 5);
    assert.equal(await page.locator('.investigation-context').evaluate((el) => el.open), false);
    const paper = await page.locator('.document-paper').evaluate((el) => ({
      background: getComputedStyle(el).backgroundColor,
      width: el.clientWidth,
    }));
    assert.equal(paper.background, 'rgb(255, 254, 250)');
    assert(paper.width > 700);
    await page.locator('[name="report_date"]').fill('2026-11-11');
    await page.locator('[data-action="save"]').click();
    await page.getByText('Draft saved.', { exact: true }).waitFor();
    assert.equal(await page.locator('#save-state').innerText(), 'Saved locally');
    await screenshot('report-desktop.png');
    checks.push(
      'Investigation alias opens a large paper canvas, section rail, collapsed scope and working Save draft',
    );
    for (const label of [
      'Introduction',
      'Vulnerabilities',
      'Attribution',
      'Information',
      'Closing',
    ]) {
      await page.locator(`[data-report-section="${label}"]`).click();
      const start = Date.now();
      await page.locator('[data-action="validate-section"]').click();
      await page.locator('[data-action="reopen-section"]').waitFor();
      freezeMs.push({ section: label, elapsed_ms: Date.now() - start });
    }
    assert.equal(await page.locator('[data-action="finalize"]').isEnabled(), true);
    await page.locator('[data-report-section="Introduction"]').click();
    assert.equal(await page.locator('[name="report_date"]').isDisabled(), true);
    await screenshot('report-frozen-desktop.png');
    checks.push(
      'All five production freeze actions preserve section locks and unlock contextual report certification',
    );

    await page.locator('#editor-tab-contact').click();
    await page.locator('#case-plan').waitFor({ state: 'attached' });
    assert.equal(await page.locator('.report-certification').count(), 0);
    assert.equal(await page.locator('[data-action="save"], [data-action="preview"]').count(), 0);
    assert.equal(await page.locator('.saved-plan-editor').evaluate((el) => el.open), false);
    await page.locator('[data-action="open-contact-activity"]').click();
    assert.equal(
      await page.locator('#attempt-outcome').evaluate((el) => el === document.activeElement),
      true,
    );
    await page
      .locator('#case-attempt [name="notes"]')
      .fill('Unsaved call notes retained across plan save');
    await page.locator('.saved-plan-editor summary').click();
    await page.locator('#case-plan [name="contact_name"]').fill('Synthetic Technology Team');
    await page.locator('#case-plan [name="contact_email"]').fill('team@example.com');
    await page.locator('#case-plan button[type="submit"]').click();
    await page.getByText('Contact plan saved.', { exact: true }).waitFor();
    assert.equal(
      await page.locator('#case-attempt [name="notes"]').inputValue(),
      'Unsaved call notes retained across plan save',
    );
    assert.equal(await page.locator('#contact-activity-compose').evaluate((el) => el.open), true);
    let prevented = false;
    page.once('dialog', async (dialog) => {
      prevented = true;
      await dialog.dismiss();
    });
    await page.locator('#editor-tab-closing').click();
    assert(prevented);
    assert.equal(
      await page.locator('.investigation-workbench').getAttribute('data-investigation-view'),
      'contact',
    );
    await page.locator('#case-attempt button[type="submit"]').click();
    await page.getByText('Contact activity recorded.', { exact: true }).waitFor();
    assert.match(
      await page.locator('.outreach-timeline').innerText(),
      /Unsaved call notes retained across plan save/,
    );
    assert.equal(await page.locator('#contact-activity-compose').evaluate((el) => el.open), false);
    await screenshot('contact-desktop.png');
    checks.push(
      'Contact starts with results and saved plan; recording opens/focuses its form; cross-form save preserves visible notes; dirty navigation refuses safely; saved activity returns to timeline',
    );

    await page.locator('#editor-tab-closing').click();
    await page.locator('#case-close').waitFor();
    assert.equal(await page.locator('.report-certification, [data-action="preview"]').count(), 0);
    assert.equal(await page.locator('.closing-history').evaluate((el) => el.open), false);
    await screenshot('closing-desktop.png');
    for (const width of [768, 390]) {
      await page.setViewportSize({ width, height: 900 });
      for (const tab of ['notification', 'contact', 'closing']) {
        await page.locator('#editor-tab-' + tab).click();
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
          true,
          `${tab} fits ${width}px`,
        );
        if (width === 390) await screenshot(tab + '-mobile.png');
      }
    }
    checks.push('Report, contact and closing views fit 768px and 390px without page overflow');
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator('#editor-tab-notification').click();
    await page.locator('#theme-toggle').click();
    assert.equal(
      await page.locator('.document-paper').evaluate((el) => getComputedStyle(el).backgroundColor),
      'rgb(255, 254, 250)',
    );
    await screenshot('report-light-desktop.png');
    checks.push('The document reading surface remains paper-white in light mode');
    const lead = await (
      await context.request.get(fixture.base + '/api/cases/' + fixture.case_id)
    ).json();
    assert(lead.section_reviews.every((section) => section.status === 'validated'));
    assert.equal(lead.case.contact_email, 'team@example.com');
    assert.equal(lead.attempts.length, 1);
    assert.equal(lead.case.stage, 'in_progress');
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      JSON.stringify(
        {
          passed: true,
          checks,
          freeze_ms: freezeMs,
          browser_errors: errors,
          external_requests: external,
        },
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
