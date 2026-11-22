/** Real file:// checks for the portable evidence reader; no application server. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

(async () => {
  assert(
    process.env.EVIDENCE_READER_FILE,
    'EVIDENCE_READER_FILE must name the generated test package reader',
  );
  const file = path.resolve(process.env.EVIDENCE_READER_FILE);
  const output = process.env.EVIDENCE_QA_OUTPUT && path.resolve(process.env.EVIDENCE_QA_OUTPUT);
  if (output) fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    headless: true,
    args: ['--no-sandbox'],
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
    const errors = [],
      network = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('request', (request) => {
      if (/^https?:/.test(request.url())) network.push(request.url());
    });
    await page.goto(pathToFileURL(file).href);
    assert(await page.locator('.reader-controls').isVisible());
    const count = await page.locator('.record').count();
    const observationId = await page.locator('#records-a .record').first().getAttribute('id');
    assert(count >= 6);
    assert(
      await page
        .locator('.finding h3')
        .first()
        .evaluate((el) => el.getBoundingClientRect().top < 570),
    );
    assert(await page.locator('.category-rail').isVisible());
    assert.equal(await page.locator('#evidence-filter').isVisible(), false);
    assert.equal(await page.locator('.record details[open]').count(), 0);
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
      false,
    );
    if (output) await page.screenshot({ path: path.join(output, 'reader-desktop.png') });
    await page.keyboard.press('/');
    assert.equal(
      await page.locator('#evidence-search').evaluate((el) => el === document.activeElement),
      true,
    );
    await page.locator('#evidence-search').fill('mail.example.test');
    assert.equal(await page.locator('.record:visible').count(), 1);
    await page.locator('[data-group="records-b"]').click();
    assert(await page.locator('#empty-result').isVisible());
    await page.locator('#evidence-search').focus();
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.record:visible').count(), count);
    await page.locator('[data-group="contacts"]').click();
    assert.equal(await page.locator('.record:visible').count(), 2);
    await page.locator('.record:visible .technical summary').first().click();
    assert.equal(await page.locator('.record details[open]').count(), 1);
    await page.locator('#collapse-records').click();
    assert.equal(await page.locator('.record details[open]').count(), 0);
    await page.locator('#evidence-search').fill('no matches at all');
    await page.evaluate((id) => {
      location.hash = '#' + id;
    }, observationId);
    await page.waitForFunction((id) => !document.getElementById(id).hidden, observationId);
    assert.equal(await page.locator('.record:visible').count(), count);
    assert(
      await page.locator('.observation-batch').count(),
      'Fixture must include repeated observations',
    );
    {
      const repeatedId = await page.locator('.record-anchor').first().getAttribute('id');
      await page.evaluate((id) => {
        location.hash = '#' + id;
      }, repeatedId);
      await page.waitForFunction(
        (id) => document.getElementById(id).closest('details').open,
        repeatedId,
      );
      assert(await page.locator('#' + repeatedId + ' + details[open]').isVisible());
      await page.locator('#collapse-records').click();
      const historyLength = await page.evaluate(() => history.length);
      // Returning to an unchanged fragment must reveal the source again after collapse,
      // including when a category filter currently hides that source.
      const repeatedLink = page.locator(`a[href="#${repeatedId}"]`).first();
      assert(await repeatedLink.count());
      const sourceSection = await repeatedLink.evaluate((link) => link.closest('section').id);
      assert.notEqual(sourceSection, 'records-a');
      await page.locator(`[data-group="${sourceSection}"]`).click();
      await repeatedLink.locator('xpath=ancestor::details[1]').locator('summary').click();
      await repeatedLink.click();
      assert.equal(await page.evaluate(() => location.hash), '#' + repeatedId);
      assert.equal(await page.evaluate(() => history.length), historyLength);
      assert(await page.locator('#' + repeatedId + ' + details[open]').isVisible());
      assert.equal(await page.locator('.record:visible').count(), count);
      const linked = page.locator('.finding .evidence-chain a').first();
      assert(await linked.count());
      await linked.click();
      assert.equal(await page.locator('.record:visible').count(), count);
    }
    const rawLink = page.locator('a[href="evidence/unknown%23source.json"]').first();
    assert(await rawLink.count());
    assert.equal(
      await page.evaluate(() =>
        [...document.querySelectorAll('a[href^="#"]')].every((a) =>
          document.getElementById(decodeURIComponent(a.hash.slice(1))),
        ),
      ),
      true,
    );
    const raw = path.join(path.dirname(file), 'evidence', 'unknown#source.json');
    await page.locator('#verify-files').setInputFiles(raw);
    await page.waitForFunction(() =>
      document.querySelector('#verify-result').textContent.includes('1 matched'),
    );
    assert.equal(
      await page.locator('[data-path="evidence/unknown#source.json"] .verification').textContent(),
      'Matches',
    );
    await page.locator('#verify-files').setInputFiles({
      name: 'unknown#source.json',
      mimeType: 'application/json',
      buffer: Buffer.from('{"modified":true}'),
    });
    await page.waitForFunction(() =>
      document.querySelector('#verify-result').textContent.includes('1 changed'),
    );
    assert.equal(
      await page.locator('[data-path="evidence/unknown#source.json"] .verification').textContent(),
      'Does not match',
    );
    await page.locator('#verify-folder').setInputFiles(path.dirname(file));
    await page.waitForFunction(() => !document.querySelector('#choose-folder').disabled);
    const verification = await page.locator('#verify-result').textContent();
    assert(verification.includes('0 changed · 0 not selected'), verification);
    await page.locator('[data-group="records-a"]').click();
    await page.emulateMedia({ media: 'print' });
    assert.equal(await page.locator('.record:visible').count(), 1);
    assert.equal(await page.locator('.reader-controls').isVisible(), false);
    assert.equal(await page.locator('.technical:visible').count(), 0);
    await page.emulateMedia({ media: 'screen' });
    await page.locator('#reset-filters').click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => scrollTo(0, 0));
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
      false,
    );
    assert.equal(await page.locator('.category-rail').isVisible(), false);
    assert(await page.locator('#evidence-filter').isVisible());
    assert(
      await page
        .locator('.finding h3')
        .first()
        .evaluate((el) => el.getBoundingClientRect().top < 700),
    );
    await page.locator('#evidence-filter').selectOption('contacts');
    assert.equal(await page.locator('.record:visible').count(), 2);
    await page.locator('#reset-filters').click();
    await page.evaluate(() => scrollTo(0, 0));
    if (output) {
      await page.screenshot({ path: path.join(output, 'reader-mobile.png') });
      await page.locator('#' + observationId).scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(output, 'reader-mobile-record.png') });
    }
    const plain = page;
    const session = await plain.context().newCDPSession(plain);
    await session.send('Emulation.setScriptExecutionDisabled', { value: true });
    await plain.goto(pathToFileURL(file).href);
    assert.equal(await plain.locator('.record:visible').count(), count);
    assert.equal(await plain.locator('.reader-controls').isVisible(), false);
    await plain.locator('.technical summary').first().click();
    assert.equal(await plain.locator('.technical[open]').count(), 1);
    assert.equal(errors.length, 0, JSON.stringify(errors));
    assert.equal(network.length, 0, JSON.stringify(network));
    console.log(
      JSON.stringify({
        records: count,
        desktop_mobile: 'pass',
        search_filter_keyboard: 'pass',
        same_hash_reopens_original: 'pass',
        hash_match_changed_folder: verification,
        no_script: 'pass',
        network_requests: network.length,
        errors,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
