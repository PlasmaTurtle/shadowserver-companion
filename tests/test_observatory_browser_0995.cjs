/** Native-browser Observatory acceptance. Run through tools/verify.py for a fresh session.
 * This suite is deliberately not replaced by portable DOM checks when Chromium is unavailable.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const fixture = process.env.ECLIPSE_FIXTURE
    ? JSON.parse(fs.readFileSync(process.env.ECLIPSE_FIXTURE, 'utf8'))
    : {};
  const base = process.env.ECLIPSE_BASE_URL || fixture.base;
  const launch = process.env.ECLIPSE_LAUNCH_URL || fixture.launch_url;
  assert(base && launch, 'Provide a fresh isolated synthetic fixture and one-time launcher URL.');
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    chromiumSandbox: true,
  });
  const errors = [],
    external = [],
    checks = [];
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: 'reduce',
    });
    context.on('request', (request) => {
      if (/^https?:/.test(request.url()) && new URL(request.url()).origin !== new URL(base).origin)
        external.push(request.url());
    });
    const page = await context.newPage();
    page.on('pageerror', (error) => errors.push(error.message));
    page.setDefaultTimeout(15000);
    const ready = () => page.locator('#eclipse[data-ready="true"]').waitFor();
    const counts = async () => ({
      findings: await page.locator('#ec-rows').innerText(),
      observations: await page.locator('#ec-observations').innerText(),
      revision: await page.locator('#eclipse').getAttribute('data-revision'),
    });
    const fieldRequest = () =>
      page.waitForResponse(
        (response) =>
          new URL(response.url()).pathname === '/api/eclipse/view' && response.status() === 200,
      );
    const screenshot = async (name) => {
      if (!process.env.ECLIPSE_SCREENSHOTS) return;
      fs.mkdirSync(process.env.ECLIPSE_SCREENSHOTS, { recursive: true });
      await page.screenshot({
        path: path.join(process.env.ECLIPSE_SCREENSHOTS, name + '.png'),
        fullPage: true,
      });
    };
    await page.goto(launch);
    await page.waitForFunction(() => !location.hash.includes('launch='));
    await page.evaluate(() => localStorage.removeItem('companion.eclipse.view.0995'));
    const initialResponse = fieldRequest();
    await page.goto(base + '/#eclipse');
    const initial = await (await initialResponse).json();
    await ready();
    assert(initial.records.total > 0, 'Synthetic fixture must contain canonical findings.');
    assert.equal(await page.locator('#eclipse').getAttribute('data-view'), 'field');
    assert.equal((await counts()).findings.replace(/,/g, ''), String(initial.records.total));
    assert.equal((await counts()).revision, initial.revision);
    assert.equal(initial.snapshot.revision, initial.intelligence.revision);
    await screenshot('0995-default-field');
    checks.push('Field is the default; visible totals and revision match one server response.');

    // The same mass selection is reachable by keyboard, without guessing canvas coordinates.
    if ((await page.locator('#ec-inspect-toggle').getAttribute('aria-expanded')) !== 'true')
      await page.locator('#ec-inspect-toggle').click();
    const object = page.locator('[data-ec-node]').first();
    await object.waitFor();
    await object.focus();
    await page.keyboard.press('Enter');
    await page.locator('#ec-selection:not([hidden])').waitFor();
    const selectedName = await page.locator('#ec-selection-name').innerText();
    await page.locator('#ec-zoom-in').click();
    await page.waitForFunction(
      () => document.querySelector('#eclipse').dataset.animating !== 'true',
    );
    const zoom = await page.locator('#ec-zoom-level').innerText();
    const fieldCounts = await counts();
    const scopedResponse = fieldRequest();
    await page.locator('[data-ec-drill="locations"]').click();
    const scoped = await (await scopedResponse).json();
    await ready();
    assert.equal(await page.locator('#eclipse').getAttribute('data-view'), 'atlas');
    assert.equal((await counts()).findings.replace(/,/g, ''), String(scoped.records.total));
    assert(await page.locator('#ec-back-field').isVisible());
    assert(await page.locator('#ec-scope-chips').isVisible());
    await screenshot('0995-focused-atlas');
    await page.locator('#ec-back-field').click();
    await ready();
    assert.equal(await page.locator('#eclipse').getAttribute('data-view'), 'field');
    assert.deepEqual(await counts(), fieldCounts);
    assert.equal(await page.locator('#ec-selection-name').innerText(), selectedName);
    assert.equal(await page.locator('#ec-zoom-level').innerText(), zoom);
    checks.push(
      'Keyboard mass selection resolves into scoped Atlas and returns to the same field, object, camera and revision.',
    );

    const unchanged = await counts();
    for (const mode of ['atlas', 'pulse', 'records', 'field']) {
      await page.locator('.ec-views [data-ec-view="' + mode + '"]').click();
      assert.equal(await page.locator('#eclipse').getAttribute('data-view'), mode);
      assert.deepEqual(await counts(), unchanged);
    }
    await page.locator('.ec-views [data-ec-view="atlas"]').click();
    await ready();
    assert.equal(await page.locator('#ec-scene-title').innerText(), 'Entity map');
    await page.waitForFunction(
      () => Number(document.querySelector('#eclipse').dataset.nodeCount) > 0,
    );
    assert.match(await page.locator('#ec-space-key').innerText(), /Number = entities/);
    if ((await page.locator('#ec-inspect-toggle').getAttribute('aria-expanded')) !== 'true')
      await page.locator('#ec-inspect-toggle').click();
    const clearSelection = page.locator('#ec-inspector-content [data-ec-action="clear"]');
    if (await clearSelection.count()) await clearSelection.click();
    const entityButton = page.locator('[data-ec-map-entity]').first();
    await entityButton.waitFor();
    const entityMapId = await entityButton.getAttribute('data-ec-map-entity');
    await entityButton.focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(
      () => document.querySelector('#eclipse').dataset.hasSelection === 'true',
    );
    assert.match(entityMapId, /^entity-location:/);
    const entityName = await page.locator('#ec-selection-name').innerText();
    assert(await page.locator('#ec-inspector-content a[href^="#entity/"]').count());
    await page.locator('#ec-list-toggle').click();
    await page.locator('#ec-records-close').click();
    await ready();
    assert.equal(await page.locator('#eclipse').getAttribute('data-view'), 'atlas');
    assert.equal(await page.locator('#ec-selection-name').innerText(), entityName);
    await page.locator('#ec-unplaced').click();
    const unplacedEntities = page.locator('[data-ec-map-entity]');
    await unplacedEntities.first().waitFor();
    if (fixture.entity_map)
      assert.equal(await unplacedEntities.count(), fixture.entity_map.unplaced_entities);
    checks.push(
      'Entity map uses saved business locations; keyboard entity selection and Records return preserve identity; unplaced entities remain discoverable.',
    );
    await screenshot('0100-entity-map');
    await page.locator('.ec-views [data-ec-view="records"]').click();
    await page.reload();
    await ready();
    assert.equal(await page.locator('#eclipse').getAttribute('data-view'), 'records');
    checks.push('Traditional modes share scope; an explicit preferred mode survives reload.');

    const record = page.locator('#ec-record-list [data-ec-row]').first();
    const recordId = await record.getAttribute('data-ec-row');
    const selectedRecord = initial.records.items.find((item) => item.id === recordId);
    assert(selectedRecord, 'The current record comes from the shared canonical page');
    const detailPath = new URL(
      selectedRecord.detail_url || '/api/eclipse/observations/' + encodeURIComponent(recordId),
      base,
    ).pathname;
    const detailResponse = page.waitForResponse(
      (response) => new URL(response.url()).pathname === detailPath,
    );
    await record.click();
    const detail = await (await detailResponse).json();
    await page.locator('#ec-inspector-content .ec-detail-grid').waitFor();
    assert(
      (await page.locator('#ec-inspector-content').innerText()).includes(detail.source.workbook),
    );
    assert.equal(await page.locator('.ec-source-fields script,.ec-source-fields img').count(), 0);
    checks.push(
      'Finding details retain original source provenance and render source values as inert text.',
    );

    await page.setViewportSize({ width: 720, height: 500 });
    await page.locator('.ec-views [data-ec-view="field"]').click();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await screenshot('0995-compact-field');
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    assert.equal(await page.locator('#eclipse').getAttribute('data-animating'), 'false');
    await screenshot('0995-narrow-field');
    checks.push(
      'Compact layouts avoid horizontal overflow; reduced motion keeps the camera at rest.',
    );
    await page.locator('.ec-views [data-ec-view="atlas"]').click();
    await ready();
    assert.equal(await page.locator('#ec-scene-title').innerText(), 'Entity map');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    assert.equal(await page.locator('#eclipse').getAttribute('data-animating'), 'false');
    await screenshot('0100-narrow-entity-map');
    checks.push('Narrow entity map retains its entity semantics without horizontal page overflow.');
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      JSON.stringify(
        { passed: true, method: 'Native Chromium against synthetic local data', checks },
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
