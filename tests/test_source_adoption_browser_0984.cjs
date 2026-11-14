/** Real browser numeric round-trip: local search → retrieval → adoption → save → freeze. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const metadata = JSON.parse(fs.readFileSync(process.env.SOURCE_FIXTURE_METADATA, 'utf8'));
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    headless: true,
    args: ['--no-sandbox', '--no-zygote', '--single-process'],
  });
  const errors = [],
    external = [],
    checks = [],
    writes = [];
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: 'reduce',
    });
    await context.route('**/*', (route) => {
      const url = route.request().url();
      if (/^https?:/.test(url) && !url.startsWith(metadata.base + '/')) {
        external.push(url);
        return route.abort();
      }
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('request', (req) => {
      if (req.method() === 'PUT' && req.url().includes('/draft')) writes.push(req.postDataJSON());
    });
    await page.goto(metadata.launch_url);
    await page.locator('.dm-workspace').waitFor();
    await page.goto(metadata.base + '/#case/' + metadata.case_id);
    await page.locator('[data-report-section="Vulnerabilities"]').click();
    await page.getByRole('button', { name: 'Search catalog', exact: true }).click();
    await page
      .getByRole('button', { name: 'Retrieve for this notification', exact: true })
      .waitFor();
    await page.locator('#report-catalog-query').fill('CVE-2025');
    await page
      .locator('#report-catalog-search-form')
      .getByRole('button', { name: 'Search', exact: true })
      .click();
    await page
      .getByText('Reference only · not reported in this notification', { exact: true })
      .waitFor();
    assert.equal(
      await page
        .getByRole('button', { name: 'Retrieve for this notification', exact: true })
        .count(),
      1,
    );
    checks.push(
      'Local search returns catalog records, with adoption limited to this notification’s reported CVEs',
    );
    await page.getByRole('button', { name: 'Retrieve for this notification', exact: true }).click();
    await page
      .getByRole('button', { name: 'Adopt retrieved records', exact: true })
      .waitFor({ timeout: 30000 });
    assert.match(await page.locator('#modal-body').innerText(), /Local catalog \/ saved feed/);
    await page.getByRole('button', { name: 'Adopt retrieved records', exact: true }).click();
    await page.getByRole('button', { name: 'Save draft', exact: true }).click();
    await page.waitForFunction(
      () => document.querySelector('#save-state')?.textContent === 'Saved locally',
    );
    assert.equal(writes.at(-1).fields.cve_records[0].cvss, 10);
    const saved = await page.evaluate(
      async (caseId) => (await fetch('/api/cases/' + caseId)).json(),
      metadata.case_id,
    );
    assert.equal(saved.draft.cve_records[0].cvss, 10);
    assert.equal(saved.draft.cve_records[0].epss, 1);
    assert.equal(saved.draft.cve_records[0].from_catalog, true);
    assert.match(saved.draft.cve_records[0].description, /Exact official local catalog wording/);
    checks.push(
      'Browser JSON number normalization preserves local CVSS 10.0 and EPSS 1.0 during authenticated save',
    );
    await page.getByRole('button', { name: 'Freeze section', exact: true }).click();
    await page
      .getByRole('button', { name: 'Reopen section', exact: true })
      .waitFor({ timeout: 30000 });
    await page.reload();
    await page.locator('[data-report-section="Vulnerabilities"]').click();
    await page.getByRole('button', { name: 'Reopen section', exact: true }).waitFor();
    const frozen = await page.evaluate(
      async (caseId) => (await fetch('/api/cases/' + caseId)).json(),
      metadata.case_id,
    );
    assert.equal(
      frozen.section_reviews.find((s) => s.key === 'vulnerabilities').status,
      'validated',
    );
    assert.deepEqual(frozen.draft.cve_records, saved.draft.cve_records);
    checks.push(
      'Vulnerabilities freeze completes and survives reload with selected source content unchanged',
    );
    const editRejected = await page.evaluate(async (caseId) => {
      const app = (await import('/static/main.js')).application;
      const lead = await app.actions.api('/api/cases/' + caseId);
      lead.draft.cve_records[0].description = 'Tampered description';
      try {
        await app.actions.api('/api/leads/' + lead.id + '/draft?case_id=' + caseId, {
          method: 'PUT',
          body: { expected_revision: lead.draft_revision, fields: lead.draft },
        });
        return false;
      } catch (e) {
        return e.message.includes('read-only');
      }
    }, metadata.case_id);
    assert.equal(editRejected, true);
    checks.push('Published source text remains protected after the save compatibility fix');
    await page.getByRole('button', { name: 'Reopen section', exact: true }).click();
    await page
      .locator('#reopen-reason')
      .fill('Validate direct freeze after adopting a saved source.');
    await page.locator('#section-reopen-form button[type="submit"]').click();
    await page.getByRole('button', { name: 'Freeze section', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Find CVE sources', exact: true }).click();
    await page.getByRole('button', { name: 'Adopt retrieved records', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Adopt retrieved records', exact: true }).click();
    const savesBeforeFreeze = writes.length;
    await page.getByRole('button', { name: 'Freeze section', exact: true }).click();
    await page.getByRole('button', { name: 'Reopen section', exact: true }).waitFor();
    assert.equal(writes.length, savesBeforeFreeze + 1);
    checks.push('Freeze directly after adoption automatically saves the valid source selection');
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    const result = { passed: true, checks, browser_errors: errors, external_requests: external };
    if (process.env.SOURCE_QA_DIR) {
      fs.mkdirSync(process.env.SOURCE_QA_DIR, { recursive: true });
      fs.writeFileSync(
        path.join(process.env.SOURCE_QA_DIR, 'result.json'),
        JSON.stringify(result, null, 2),
      );
      await page.screenshot({
        path: path.join(process.env.SOURCE_QA_DIR, 'frozen-vulnerabilities.png'),
        fullPage: true,
      });
    }
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
