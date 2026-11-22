/** Real editor, revision conflicts and case pins through the authenticated local app. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const base = process.env.BASE_URL;
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  assert(process.env.LAUNCH_URL?.startsWith(base + '/#launch='));
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    headless: true,
  });
  const checks = [],
    errors = [],
    external = [];
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1100 },
      reducedMotion: 'reduce',
    });
    await context.route('**/*', (route) => {
      const url = route.request().url();
      if (/^https?:/.test(url) && !url.startsWith(base + '/')) {
        external.push(url);
        return route.abort();
      }
      return route.continue();
    });
    context.on('page', (page) => {
      page.setDefaultTimeout(15000);
      page.on('pageerror', (error) => errors.push(error.message));
      page.on('dialog', (dialog) => dialog.accept());
    });
    const get = async (url) => {
      const response = await context.request.get(base + url);
      assert.equal(response.status(), 200, await response.text());
      return response.json();
    };
    const submit = async (page, selector, url, method = 'POST', expected = 200) => {
      const pending = page.waitForResponse(
        (response) => response.url() === base + url && response.request().method() === method,
      );
      await page.locator(selector).click();
      const response = await pending;
      assert.equal(response.status(), expected, await response.text());
      return response.json();
    };
    const page = await context.newPage();
    await page.goto(process.env.LAUNCH_URL);
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    await page.goto(base + '/#library');
    await page.locator('#library-new-explainer:enabled').click();
    const title = 'Synthetic explainer lifecycle';
    const original = 'Original wording pinned by the synthetic case.';
    const source = 'https://example.test/guidance';
    await page.locator('#resource-form [name="title"]').fill(title);
    await page.locator('#resource-form [name="body"]').fill(original);
    await page.locator('#resource-form [name="sources"]').fill(source);
    await page.locator('#resource-form [name="sources"]').press('Tab');
    await page.locator('#resource-form details > summary').click();
    await page.locator('[data-citation-key="publisher"]').fill('Original source publisher');
    await page.locator('[data-citation-key="title"]').fill('Published source guidance');
    const created = await submit(page, '#resource-form [type="submit"]', '/api/explainers');
    assert.equal(created.revision, 1);
    assert.equal(created.source_metadata[0].publisher, 'Original source publisher');
    const endpoint = '/api/explainers/' + created.id;
    await page.locator('#resource-form[data-expected-revision="1"]').waitFor({ state: 'attached' });
    checks.push('Created wording and citation metadata through the real editor');

    // The existing synthetic navigation fixture supplies qualified entities.
    // Use public case/draft APIs to establish the independent pinned consumer.
    const boot = await get('/api/bootstrap');
    const headers = { 'X-Workbench-Token': boot.token, Origin: base };
    const leads = await get('/api/leads');
    assert(leads.length, 'The registered fixture must provide a qualified entity');
    const caseResponse = await context.request.post(base + '/api/cases', {
      headers,
      data: { entity_id: leads[0].id, title: 'Pinned Library wording case' },
    });
    assert.equal(caseResponse.status(), 200, await caseResponse.text());
    const opened = await caseResponse.json();
    const saveResponse = await context.request.put(
      base + '/api/leads/' + opened.id + '/draft?case_id=' + opened.case_id,
      {
        headers,
        data: {
          expected_revision: opened.draft_revision,
          fields: { ...opened.draft, selected_explainers: [created.id] },
        },
      },
    );
    assert.equal(saveResponse.status(), 200, await saveResponse.text());
    const selected = await saveResponse.json();
    const pinned = selected.draft.explainer_snapshots.find((item) => item.id === created.id);
    assert.equal(pinned.revision, 1);
    assert.equal(pinned.body, original);
    assert.deepEqual(pinned.source_metadata, created.source_metadata);

    const second = await context.newPage();
    await second.goto(base + '/#library?item=' + created.id);
    await second
      .locator('#resource-form[data-expected-revision="1"]')
      .waitFor({ state: 'attached' });
    await page.locator('.dm-library-edit > summary').click();
    await second.locator('.dm-library-edit > summary').click();
    await page.locator('#resource-form [name="body"]').fill('Window A shared wording.');
    await page.locator('#resource-form details > summary').click();
    await page.locator('[data-citation-key="publisher"]').fill('Updated source publisher');
    await second.locator('#resource-form [name="body"]').fill('Window B retained draft.');
    const firstSave = await submit(page, '#resource-form [type="submit"]', endpoint, 'PUT');
    assert.equal(firstSave.revision, 2);
    await submit(second, '#resource-form [type="submit"]', endpoint, 'PUT', 409);
    await second.locator('[data-action="resource-rebase"]').waitFor();
    assert.equal(
      await second.locator('#resource-form [name="body"]').inputValue(),
      'Window B retained draft.',
    );
    assert.match(await second.locator('#resource-status').innerText(), /Window A shared wording/);
    assert.match(await second.locator('#resource-status').innerText(), /Updated source publisher/);
    assert.equal((await get(endpoint)).body, 'Window A shared wording.');
    assert.deepEqual(
      (await get(endpoint + '/history')).items.map((item) => item.revision),
      [2, 1],
    );
    checks.push(
      'A stale second-window save returns409, retains its draft and compares the latest wording/citations',
    );

    await second.locator('[data-action="resource-rebase"]').click();
    assert.equal(
      await second.locator('#resource-form [name="body"]').inputValue(),
      'Window B retained draft.',
    );
    const rebased = await submit(second, '#resource-form [type="submit"]', endpoint, 'PUT');
    assert.equal(rebased.revision, 3);
    assert.equal(rebased.body, 'Window B retained draft.');
    assert.deepEqual(rebased.source_metadata, created.source_metadata);
    await second.locator('[data-action="resource-history"]').click();
    await second.locator('[data-action="resource-compare"][data-revision="2"]').click();
    const comparison = second.locator('#resource-comparison');
    await comparison.getByText('Window A shared wording.', { exact: true }).waitFor();
    assert.match(await comparison.innerText(), /Window B retained draft/);
    assert.match(await comparison.innerText(), /Updated source publisher/);
    assert.match(await comparison.innerText(), /Original source publisher/);
    checks.push(
      'Explicit comparison and rebase preserve both full historical wording and citation metadata',
    );

    const restored = await submit(
      second,
      '[data-action="resource-restore"][data-revision="1"]',
      endpoint + '/restore/1',
    );
    assert.equal(restored.revision, 4);
    assert.equal(restored.body, original);
    assert.deepEqual(restored.source_metadata, created.source_metadata);
    const archived = await submit(
      second,
      '[data-action="resource-archive"][data-archived="true"]',
      endpoint + '/archive',
    );
    assert.equal(archived.revision, 5);
    assert(archived.archived_at);
    await second.getByText(/Archived explanations are unavailable/).waitFor();
    assert(!(await get('/api/explainers')).some((item) => item.id === created.id));
    assert(!(await get('/api/bootstrap')).explainers.some((item) => item.id === created.id));
    assert.deepEqual((await get('/api/cases/' + opened.case_id)).draft, selected.draft);
    const active = await submit(
      second,
      '[data-action="resource-archive"][data-archived="false"]',
      endpoint + '/archive',
    );
    assert.equal(active.revision, 6);
    assert.equal(active.archived_at, '');
    assert((await get('/api/explainers')).some((item) => item.id === created.id));
    assert.deepEqual((await get('/api/cases/' + opened.case_id)).draft, selected.draft);
    checks.push(
      'Restore creates a new revision; archive/unarchive change availability without changing the case pin',
    );

    await second.reload();
    await second
      .locator('#resource-form[data-expected-revision="6"]')
      .waitFor({ state: 'attached' });
    await second.locator('[data-action="resource-usage"]').click();
    await second
      .locator('#resource-usage a[href="#workspace/notifications/' + opened.case_id + '"]')
      .waitFor();
    assert.match(await second.locator('#resource-usage').innerText(), /explainer revision 1/);
    const usage = await get(endpoint + '/usage');
    assert.deepEqual(
      usage.items.map((item) => [item.id, item.explainer_revision]),
      [[opened.case_id, 1]],
    );
    await second.locator('[data-action="resource-history"]').click();
    await second.locator('[data-action="resource-compare"][data-revision="3"]').click();
    await second
      .locator('#resource-comparison')
      .getByText('Window B retained draft.', { exact: true })
      .waitFor();
    const expectedActions = ['created', 'updated', 'updated', 'restored', 'archived', 'unarchived'];
    const history = await get(endpoint + '/history');
    assert.deepEqual(
      history.items.map((item) => [item.revision, item.action]),
      expectedActions.map((action, index) => [index + 1, action]).reverse(),
    );
    assert.equal(history.items.find((item) => item.revision === 4).restored_from, 1);
    const activity = await get('/api/activity?q=' + encodeURIComponent(title));
    const events = activity.items
      .filter((item) => item.metadata.explainer_id === created.id)
      .sort((a, b) => a.metadata.revision - b.metadata.revision);
    assert.deepEqual(
      events.map((item) => [item.metadata.revision, item.action]),
      expectedActions.map((action, index) => [index + 1, 'explainer_' + action]),
    );
    assert(events.every((item) => item.actor_recorded && item.actor));
    checks.push(
      'Reloaded history, Used by and Activity identify exact revisions, actions and the unchanged case selection',
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    const result = { passed: true, checks, page_errors: errors, external_requests: external };
    if (process.env.QA_DIR) {
      fs.mkdirSync(process.env.QA_DIR, { recursive: true });
      await second.locator('#resource-history').scrollIntoViewIfNeeded();
      await second.screenshot({
        path: path.join(process.env.QA_DIR, 'explainer-lifecycle.png'),
        fullPage: true,
      });
      fs.writeFileSync(
        path.join(process.env.QA_DIR, 'result.json'),
        JSON.stringify(result, null, 2),
      );
    }
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
