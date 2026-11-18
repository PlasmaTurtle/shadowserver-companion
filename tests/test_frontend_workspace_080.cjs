/* Exercise workspace controls only against an explicitly launched synthetic demo.
 * Asset requests are intercepted; import/delete are opened and cancelled, never submitted.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.ECLIPSE_BASE_URL || 'http://127.0.0.1:8897';

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    args: ['--no-sandbox'],
  });
  const errors = [],
    external = [],
    checks = [],
    destructive = [];
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: 'reduce',
    });
    await context.route('**/*', async (route) => {
      const url = route.request().url();
      if (/^https?:/.test(url) && !url.startsWith(base + '/')) {
        external.push(url);
        return route.abort();
      }
      if (/\/api\/data\/(import|delete)$/.test(url)) {
        destructive.push(url);
        return route.fulfill({
          status: 409,
          json: { detail: 'Browser test prevents workspace changes' },
        });
      }
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', (error) => errors.push(error.message));
    page.setDefaultTimeout(15000);
    assert(process.env.ECLIPSE_LAUNCH_URL, 'An explicit one-time launcher URL is required');
    await page.goto(process.env.ECLIPSE_LAUNCH_URL);
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    const cases = await (await context.request.get(base + '/api/cases')).json();
    const work = cases.find((item) => item.stage === 'in_progress');
    assert(work, 'Synthetic open notification required');
    const original = await (await context.request.get(base + '/api/cases/' + work.id)).json();
    assert.equal(original.demo, 1, 'This browser test must never edit a working entity');
    await page.goto(base + '/#workspace/notifications/' + work.id);
    await page.locator('[data-report-section="Introduction"]').waitFor();
    // Start with a hostname-only synthetic identity so the incomplete-detail reminders
    // remain applicable; complete business/contact records intentionally suppress them.
    await page.evaluate(async () => {
      const { application } = await import('/static/main.js');
      const current = application.state.editor.currentLead;
      const lead = await application.actions.api(`/api/entities/${current.id}/name`, {
        method: 'PUT',
        body: { name: current.domain, expected_revision: current.entity_revision },
      });
      const field = lead.entity_review.fields.find((item) => item.field === 'name');
      await application.actions.api(`/api/entities/${lead.id}/field-review`, {
        method: 'POST',
        body: {
          field: 'name',
          action: 'pending',
          expected_revision: lead.entity_revision,
          value_hash: field.value_hash,
        },
      });
      await application.actions.route(true);
    });
    await page.locator('.investigation-context > summary').click();
    await page.locator('[data-entity-review-summary]').waitFor({ state: 'visible' });
    await page
      .locator('[data-entity-review-summary]')
      .getByRole('link', { name: 'Review required: business details', exact: true })
      .click();
    const nameReview = page.locator('[data-entity-review-field="name"]');
    assert.match(await nameReview.innerText(), /Review required/);
    assert.equal(await nameReview.locator('.notice').count(), 0);
    const warningColor = await nameReview
      .locator('.entity-review-required')
      .evaluate((node) => getComputedStyle(node).color);
    assert(warningColor && warningColor !== 'rgba(0, 0, 0, 0)', 'Visible review text color');
    await nameReview.locator('[data-review="confirm"]').click();
    await page.waitForFunction(() =>
      document
        .querySelector('[data-entity-review-field="name"]')
        ?.textContent.includes('Confirmed'),
    );
    await page.locator('#entity-details-form [name="city"]').fill('');
    const profileSaved = page.waitForResponse(
      (response) => response.request().method() === 'PUT' && response.url().endsWith('/profile'),
    );
    await page.locator('#entity-details-form button[type="submit"]').click();
    assert.equal((await profileSaved).status(), 200);
    await page.locator('[data-entity-review-field="city"] [data-review="ignore"]').waitFor();
    assert.equal(
      await page.locator('[data-entity-review-field="city"] [data-review="confirm"]').count(),
      0,
    );
    await page.locator('#entity-details-form [name="notes"]').fill('Unsaved synthetic notes');
    await page.locator('[data-entity-review-field="city"] [data-review="ignore"]').click();
    await page.waitForFunction(() =>
      document.querySelector('[data-entity-review-field="city"]')?.textContent.includes('Ignored'),
    );
    assert.equal(
      await page.locator('#entity-details-form [name="notes"]').inputValue(),
      'Unsaved synthetic notes',
    );
    await page
      .locator('#entity-details-form [name="city"]')
      .fill(original.current_entity.entity_profile.city);
    const profileRestored = page.waitForResponse(
      (response) => response.request().method() === 'PUT' && response.url().endsWith('/profile'),
    );
    await page.locator('#entity-details-form button[type="submit"]').click();
    assert.equal((await profileRestored).status(), 200);
    await page.waitForFunction(() =>
      document
        .querySelector('[data-entity-review-field="city"]')
        ?.textContent.includes('Confirmed'),
    );
    await page.reload();
    await page.locator('#entity-details-form').waitFor();
    assert.match(await page.locator('[data-entity-review-field="name"]').innerText(), /Confirmed/);
    assert.match(await page.locator('[data-entity-review-field="city"]').innerText(), /Confirmed/);
    assert.equal(
      (await (await context.request.get(base + '/api/entities/' + work.entity_id)).json())
        .entity_review.required,
      false,
    );
    checks.push(
      'Yellow entity reminders, Confirm/Ignore persistence, automatic review on edits, and preservation of unsaved notes',
    );

    const assetRequests = [];
    const assetPath = `/api/cases/${work.id}/assets/attribution`;
    await page.route(base + assetPath, async (route) => {
      if (route.request().method() === 'POST') {
        assetRequests.push(route.request().postDataJSON());
        return route.fulfill({
          json: {
            id: 'synthetic-asset-job',
            status: 'completed',
            completed: 1,
            total: 1,
            errors: [],
          },
        });
      }
      return route.fulfill({
        json: {
          case_id: work.id,
          remaining: original.entries.length,
          job: null,
          assets: original.entries.map((entry) => ({
            entry_id: entry.id,
            eligible: true,
            supported: false,
            status: 'not_checked',
            latest_lookup: null,
          })),
        },
      });
    });
    await page.goto(base + '/#workspace/notifications/' + work.id + '?tab=assets');
    await page.locator('[data-attribute-asset]:not([disabled])').first().waitFor();
    await page.locator('[data-attribute-asset]').first().click();
    await page.waitForFunction(() =>
      document.querySelector('#editor-content')?.textContent.includes('Asset attribution finished'),
    );
    assert.equal(assetRequests[0].entry_id, original.entries[0].id);
    await page.locator('[data-action="attribute-remaining"]').click();
    await page.waitForFunction(
      () => !document.querySelector('[data-action="attribute-remaining"]')?.disabled,
    );
    assert.equal(assetRequests.length, 2);
    assert.equal(assetRequests[1].entry_id, null);
    checks.push(
      'Individual and remaining-asset buttons dispatch the correct scope without any network lookup',
    );

    // Preview belongs to the Report view in the investigation studio.
    assert.equal(await page.locator('[data-action="preview"]').count(), 0);
    await page.locator('#editor-tab-notification').click();
    await page.locator('[data-action="preview"]').first().waitFor();
    // A successful preview makes exactly one request, then embeds its returned PDF blob.
    let previewRequests = 0;
    page.on('request', (request) => {
      if (request.url().includes('/preview.pdf')) previewRequests++;
    });
    const pdfResponse = page.waitForResponse(
      (response) => response.url().includes('/preview.pdf'),
      { timeout: 120000 },
    );
    await page.locator('[data-action="preview"]').first().click();
    const pdf = await pdfResponse;
    assert.equal(pdf.status(), 200);
    assert.match(pdf.headers()['content-type'], /application\/pdf/);
    assert.equal((await pdf.body()).subarray(0, 5).toString(), '%PDF-');
    await page.locator('iframe.pdf-preview').waitFor();
    assert.match(await page.locator('iframe.pdf-preview').getAttribute('src'), /^blob:/);
    assert.equal(previewRequests, 1);
    await page.locator('#close-modal').click();
    const failureRoute = '**/api/leads/*/preview.pdf?*';
    await page.route(failureRoute, (route) =>
      route.fulfill({ status: 503, json: { detail: 'Synthetic preview failure: please retry' } }),
    );
    await page.locator('[data-action="preview"]').first().click();
    await page.locator('#modal [role="alert"]').waitFor();
    assert.match(
      await page.locator('#modal [role="alert"]').innerText(),
      /Synthetic preview failure/,
    );
    assert.equal(await page.locator('#report-operation-status').count(), 0);
    assert.equal(await page.locator('[data-action="preview"]').first().isDisabled(), false);
    await page.locator('#close-modal').click();
    await page.unroute(failureRoute);
    checks.push(
      'Real PDF bytes and one blob preview request; server error replaces spinner and restores controls',
    );

    await page.goto(base + '/#settings');
    await page.locator('[data-action="backup"]').waitFor();
    // Settings launches status reads after rendering its controls. The server
    // correctly requires an idle workspace before reserving it for export.
    await page.waitForLoadState('networkidle');
    // The complete synthetic archive contains rendered exhibits and embedded fonts.
    const downloadEvent = page
      .waitForEvent('download', { timeout: 120000 })
      .catch((error) => error);
    const exportResponse = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' && response.url().endsWith('/api/backup'),
      { timeout: 120000 },
    );
    await page.locator('[data-action="backup"]').click();
    const exported = await exportResponse;
    assert.equal(
      exported.status(),
      200,
      `Export HTTP status ${exported.status()}: ${exported.status() === 200 ? '' : await exported.text()}`,
    );
    const download = await downloadEvent;
    if (download instanceof Error) {
      console.error(
        'Data export diagnostics',
        await page.evaluate(() => ({
          button: document.querySelector('[data-action="backup"]')?.outerHTML,
          toasts: document.querySelector('#toasts')?.textContent,
          dialog: document.querySelector('#modal')?.open,
        })),
      );
      throw download;
    }
    assert.equal(download.suggestedFilename(), 'shadowserver-companion-backup.zip');
    const chunks = [];
    for await (const chunk of await download.createReadStream()) chunks.push(chunk);
    const archive = Buffer.concat(chunks);
    assert.equal(archive.readUInt32LE(0), 0x04034b50);
    assert(archive.includes(Buffer.from('workbench.sqlite3')), 'Export contains the database');
    for (const action of ['import', 'delete']) {
      if (action === 'delete') await page.locator('.settings-danger > summary').click();
      await page.locator(`[data-action="${action}-data"]`).click();
      await page.locator(`#${action}-data-form`).waitFor();
      assert.equal(
        await page.locator('#data-confirmation').getAttribute('pattern'),
        action.toUpperCase(),
      );
      if (action === 'import') assert.equal(await page.locator('#data-backup').count(), 1);
      await page.locator('#close-modal').click();
      assert.equal(await page.locator('#modal').isVisible(), false);
    }
    assert.deepEqual(destructive, []);
    const status = await (await context.request.get(base + '/api/data/status')).json();
    assert(!status.pending, 'Cancelling the dialogs stages no data change');
    checks.push(
      'Data export downloads a database ZIP; import/delete confirmations can be cancelled without writes',
    );
    if (process.env.ECLIPSE_SCREENSHOTS) {
      fs.mkdirSync(process.env.ECLIPSE_SCREENSHOTS, { recursive: true });
      await page.screenshot({
        path: path.join(process.env.ECLIPSE_SCREENSHOTS, '080-data-management.png'),
        fullPage: true,
      });
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      JSON.stringify(
        {
          checks,
          page_errors: errors,
          external_requests: external,
          destructive_requests: destructive,
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
