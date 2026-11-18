/** Real-browser acceptance for independent entities/leads and canonical Workspace routing. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const fixture = JSON.parse(fs.readFileSync(process.env.NAVIGATION_FIXTURE, 'utf8'));
(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE || '/usr/bin/chromium',
    args: ['--no-sandbox'],
  });
  const context = await browser.newContext({
    viewport: { width: 1366, height: 900 },
    reducedMotion: 'reduce',
  });
  const page = await context.newPage(),
    errors = [],
    external = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('request', (r) => {
    if (/^https?:/.test(r.url()) && !r.url().startsWith(fixture.base)) external.push(r.url());
  });
  const api = async (url) => (await context.request.get(fixture.base + url)).json();
  const screenshot = async (name) => {
    if (!process.env.NAVIGATION_SCREENSHOTS) return;
    fs.mkdirSync(process.env.NAVIGATION_SCREENSHOTS, { recursive: true });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(60);
    await page.screenshot({
      path: path.join(process.env.NAVIGATION_SCREENSHOTS, name + '.png'),
      fullPage: true,
    });
  };
  try {
    await page.goto(fixture.launch_url);
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    assert.equal(new URL(page.url()).hash, '#workspace');
    assert.equal((await api('/api/cases')).length, 0);
    await page.locator('.sidebar [data-nav="entities"]').click();
    await page.getByRole('heading', { name: 'Entities', exact: true }).waitFor();
    await screenshot('0982-entities');
    await page
      .locator('a[href="#entity/' + fixture.entity_id + '"]')
      .first()
      .click();
    await page.locator('.dossier-overview').waitFor();
    assert.equal(await page.locator('#entity-details-form').count(), 0);
    const entityRecord = await api('/api/entities/' + fixture.entity_id);
    const observedPairs = new Map();
    for (const entry of entityRecord.entries) {
      const fields = entry.source?.fields || entry;
      const host = String(entry.hostname || fields.hostname || '')
        .trim()
        .toLowerCase()
        .replace(/\.$/, '');
      const ip = String(entry.ip || fields.ip || '').trim();
      if (host && ip) {
        const key = JSON.stringify([host, ip]);
        observedPairs.set(key, (observedPairs.get(key) || 0) + 1);
      }
    }
    const drawnPairs = await page.locator('[data-dossier-edge]').evaluateAll((edges) =>
      edges.map((edge) => ({
        host: edge.dataset.host,
        ip: edge.dataset.ip,
        count: Number(edge.dataset.count),
      })),
    );
    assert(drawnPairs.length > 0);
    for (const pair of drawnPairs)
      assert.equal(observedPairs.get(JSON.stringify([pair.host, pair.ip])), pair.count);
    assert.equal(await page.locator('[data-dossier-graph]').getAttribute('role'), 'img');
    const graphBounds = await page.locator('[data-dossier-graph]').boundingBox();
    assert(
      graphBounds.width > 500 && graphBounds.height > 180,
      'Source graph must retain its intrinsic aspect ratio instead of inheriting icon dimensions',
    );
    await screenshot('0982-dossier-overview');
    await page
      .locator('.record-tabs')
      .getByRole('link', { name: 'Details / edit', exact: true })
      .click();
    await page.locator('#entity-details-form').waitFor();
    assert.equal(await page.locator('[data-action="preview"]').count(), 0);
    assert.equal(
      await page.locator('.sidebar [aria-current="page"]').getAttribute('data-nav'),
      'entities',
    );
    await page.locator('#entity-details-form [name="name"]').fill('Independent Example');
    page.once('dialog', (d) => d.dismiss());
    await page.locator('.sidebar [data-nav="leads"]').click();
    await page.waitForURL(/#entity\//);
    assert.equal(
      await page.locator('#entity-details-form [name="name"]').inputValue(),
      'Independent Example',
    );
    assert.match(new URL(page.url()).hash, /^#entity\//);
    await page.locator('#entity-details-form [name="address"]').fill('100 Example Street');
    await page.locator('#entity-details-form [name="city"]').fill('Charlotte');
    await page.locator('#entity-details-form [name="state"]').fill('North Carolina');
    await page.locator('#entity-details-form button[type="submit"]').click();
    await page.getByRole('heading', { name: 'Independent Example', exact: true }).waitFor();
    await page.waitForFunction(() => document.querySelector('#nav-count').hidden);
    await screenshot('098-entity-light');
    assert.equal((await api('/api/cases')).length, 0);
    await page.locator('.record-tabs').getByRole('link', { name: 'Contacts', exact: true }).click();
    await page.locator('#entity-contact-form').waitFor();
    await page.locator('#entity-contact-form [name="contact_email"]').fill('security@example.com');
    await page.locator('#entity-contact-form button[type="submit"]').click();
    await page.waitForFunction(
      () => document.querySelector('#entity-save-state')?.textContent === 'Saved',
    );
    assert.equal((await api('/api/cases')).length, 0);
    await page.locator('.sidebar [data-nav="leads"]').click();
    await page.getByRole('heading', { name: 'Leads', exact: true }).waitFor();
    const lead = (await api('/api/pending-leads')).find((l) => l.can_start);
    assert(lead, 'Fixture must contain a qualified pending lead');
    await page.locator('a[href="#leads/' + lead.id + '"]').click();
    await page.getByRole('heading', { name: 'Source observations', exact: true }).waitFor();
    await screenshot('098-lead-light');
    await page.getByRole('button', { name: 'Start notification', exact: true }).click();
    await page.locator('.editor-tabs').waitFor();
    const caseId = new URL(page.url()).hash.split('/')[2];
    assert(caseId);
    assert.equal(
      await page.locator('.sidebar [aria-current="page"]').getAttribute('data-nav'),
      'investigations',
    );
    assert.equal(await page.getByRole('tab', { name: 'Business record' }).count(), 0);
    assert.equal((await api('/api/cases')).length, 1);
    await page.getByRole('tab', { name: 'Contact & delivery', exact: true }).click();
    assert.match(new URL(page.url()).hash, /\?tab=contact$/);
    assert.equal(
      await page.locator('#case-plan [name="contact_email"]').inputValue(),
      'security@example.com',
    );
    await page.reload();
    await page.getByText('Edit contact plan', { exact: true }).click();
    await page.locator('#case-plan').waitFor();
    assert.equal(
      await page
        .getByRole('tab', { name: 'Contact & delivery', exact: true })
        .getAttribute('aria-selected'),
      'true',
    );
    const before = await api('/api/cases/' + caseId);
    await page
      .locator('a[href="#entity/' + fixture.entity_id + '"]')
      .first()
      .click();
    await page.locator('.record-tabs').getByRole('link', { name: 'Contacts', exact: true }).click();
    await page.locator('#entity-contact-form [name="contact_phone"]').fill('704-555-0123');
    await page.locator('#entity-contact-form button[type="submit"]').click();
    await page.waitForFunction(
      () => document.querySelector('#entity-save-state')?.textContent === 'Saved',
    );
    const after = await api('/api/cases/' + caseId);
    assert.equal(
      after.draft_revision,
      before.draft_revision,
      'Entity contact edits do not revise report content',
    );
    await page.locator('#theme-toggle').click();
    await screenshot('098-contacts-dark');
    await page.goto(fixture.base + '/#data?tab=api');
    await page.locator('#shadowserver-api').waitFor();
    assert.match(await page.locator('#main').innerText(), /Not configured/i);
    await screenshot('098-data-api-dark');
    await page.goto(fixture.base + '/#case/' + caseId + '?tab=activity');
    await page.locator('#editor-tab-activity[aria-selected="true"]').waitFor();
    assert.equal(new URL(page.url()).hash, '#workspace/notifications/' + caseId + '?tab=activity');
    await page.goto(fixture.base + '/#entities?q=Independent');
    await page
      .locator('a[href="#entity/' + fixture.entity_id + '"]')
      .first()
      .click();
    await page.locator('.dossier-overview').waitFor();
    await page.goBack();
    await page.getByRole('heading', { name: 'Entities', exact: true }).waitFor();
    assert.equal(await page.locator('#entity-search [name="q"]').inputValue(), 'Independent');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(fixture.base + '/#entity/' + fixture.entity_id);
    await page.locator('.dossier-overview').waitFor();
    assert(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
    );
    assert(
      await page
        .locator('.dossier-graph-viewport')
        .first()
        .evaluate((node) => node.scrollWidth > node.clientWidth),
      'Mobile graph scrolls inside its own region to keep source labels readable',
    );
    assert((await page.locator('[data-dossier-graph]').boundingBox()).width >= 680);
    await screenshot('0982-dossier-mobile');
    await page
      .locator('.record-tabs')
      .getByRole('link', { name: 'Details / edit', exact: true })
      .click();
    await page.locator('#entity-details-form').waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await screenshot('0982-dossier-edit-mobile');
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      'Independent entity edits and contacts, dirty guard, correct review badge, intake-only leads, explicit start, canonical Workspace routes, tab reload, unchanged report revisions, API unconfigured state, history and mobile layout passed.',
    );
  } catch (error) {
    console.error('Browser errors:', errors);
    console.error('Page:', await page.locator('body').innerText());
    await screenshot('0982-navigation-failure');
    throw error;
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
