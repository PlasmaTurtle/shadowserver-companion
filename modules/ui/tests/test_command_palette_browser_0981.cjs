/** Real launcher session, production search routes and keyboard navigation offline. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

(async () => {
  assert(process.env.NAVIGATION_FIXTURE, 'Explicit synthetic fixture required');
  const fixture = JSON.parse(fs.readFileSync(process.env.NAVIGATION_FIXTURE, 'utf8'));
  assert.match(fixture.base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    headless: true,
    args: ['--no-sandbox', '--no-zygote'],
  });
  const errors = [],
    external = [],
    checks = [];
  try {
    const context = await browser.newContext({
      viewport: { width: 1366, height: 900 },
      reducedMotion: 'reduce',
    });
    await context.route('**/*', (route) => {
      if (
        /^https?:/.test(route.request().url()) &&
        !route
          .request()
          .url()
          .startsWith(fixture.base + '/')
      ) {
        external.push(route.request().url());
        return route.abort();
      }
      return route.continue();
    });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    page.on('pageerror', (error) => errors.push(error.message));
    const searchRequests = [];
    const searchPath = (request) => {
      const url = new URL(request.url());
      return url.pathname === '/api/search' ? url.pathname + url.search : null;
    };
    page.on('request', (request) => {
      const path = searchPath(request);
      if (path) searchRequests.push({ path, state: 'requested' });
    });
    page.on('response', (response) => {
      const path = searchPath(response.request());
      if (path) searchRequests.push({ path, state: 'response', status: response.status() });
    });
    page.on('requestfailed', (request) => {
      const path = searchPath(request);
      if (path) searchRequests.push({ path, state: 'failed', error: request.failure()?.errorText });
    });
    await page.goto(fixture.launch_url);
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    const boot = await (await context.request.get(fixture.base + '/api/bootstrap')).json();
    const created = await context.request.post(fixture.base + '/api/explainers', {
      headers: { 'X-Workbench-Token': boot.token, Origin: fixture.base },
      data: {
        title: 'Unique palette reference',
        body: 'Synthetic searchable explanation.',
        sources: '',
      },
    });
    assert.equal(created.status(), 200);
    const libraryId = (await created.json()).id;
    let releaseSearch;
    const searchGate = new Promise((resolve) => {
      releaseSearch = resolve;
    });
    const delayedSearch = async (route) => {
      await searchGate;
      await route.continue();
    };
    await page.route(fixture.base + '/api/search?*', delayedSearch);
    const requestedSearch = page.waitForRequest((request) =>
      request.url().startsWith(fixture.base + '/api/search?'),
    );
    await page.locator('#global-search').click();
    await requestedSearch;
    const workspaceOption = page
      .getByRole('option')
      .filter({ has: page.locator('strong', { hasText: /^Workspace$/ }) });
    await workspaceOption.focus();
    releaseSearch();
    await page.waitForFunction(
      () => !document.querySelector('#command-status')?.textContent.includes('Searching'),
    );
    assert.equal(
      await workspaceOption.evaluate((element) => element === document.activeElement),
      true,
      'Async palette results must preserve the focused destination',
    );
    await page.unroute(fixture.base + '/api/search?*', delayedSearch);
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => document.activeElement.id === 'global-search');
    checks.push(
      'A delayed real local search preserves the focused destination and Escape returns focus',
    );
    async function openSearch(query, reopenBeforeCloseEvent = false) {
      await page.keyboard.press('Control+k');
      await page.locator('#command-query').waitFor();
      assert.equal(
        await page.locator('#command-query').evaluate((el) => el === document.activeElement),
        true,
      );
      if (reopenBeforeCloseEvent) {
        // close() queues its event. Reopen and type before that event is delivered,
        // using the native dialog and the real shell action rather than a fake event.
        await page.evaluate((value) => {
          document.querySelector('#modal').close();
          document.querySelector('#global-search').click();
          const input = document.querySelector('#command-query');
          input.value = value;
          input.dispatchEvent(new Event('input', { bubbles: true }));
        }, query);
      } else await page.locator('#command-query').fill(query);
      try {
        await page.waitForFunction(
          () => !document.querySelector('#command-status')?.textContent.includes('Searching'),
        );
      } catch (error) {
        const state = await page.evaluate(() => ({
          route: location.hash,
          query: document.querySelector('#command-query')?.value,
          status: document.querySelector('#command-status')?.textContent,
          modalOpen: document.querySelector('#modal')?.open,
          modalClass: document.querySelector('#modal')?.className,
          focused: document.activeElement?.id,
        }));
        throw new Error(
          'Palette search did not settle: ' + JSON.stringify({ state, searchRequests, errors }),
          { cause: error },
        );
      }
    }
    await openSearch('>Investigations');
    assert.equal(await page.getByRole('option').count(), 1);
    assert.equal(await page.getByRole('option').locator('strong').innerText(), 'Investigations');
    await page.locator('#command-query').press('Enter');
    await page.getByRole('heading', { name: 'Investigations', exact: true }).waitFor();
    assert.equal(
      await page.locator('#sidebar [aria-current="page"]').getAttribute('data-nav'),
      'investigations',
    );
    assert.equal(new URL(page.url()).hash, '#workspace/notifications');
    checks.push(
      'Investigations command opens the canonical queue with its matching rail item active',
    );

    await openSearch('mail.example.com', true);
    assert.equal(
      await page
        .locator('#modal')
        .evaluate((element) => element.classList.contains('command-dialog')),
      true,
      'A queued close event must not dispose the newly reopened palette',
    );
    checks.push('Reopening before a queued native close event preserves the new search');
    const entityGroup = page
      .locator('.command-group')
      .filter({ has: page.getByRole('heading', { name: 'Entities', exact: true }) });
    await entityGroup.getByRole('option').first().waitFor();
    await page.locator('#command-query').press('Home');
    await page.locator('#command-query').press('Enter');
    await page.locator('.dossier-overview').waitFor();
    assert.equal(await page.locator('#entity-details-form').count(), 0);
    assert.equal(new URL(page.url()).hash, '#entity/' + fixture.entity_id);
    checks.push(
      'Ctrl+K opens a focused palette; keyboard search opens the independent entity record',
    );

    await openSearch('Unique palette reference');
    await page.getByRole('option').filter({ hasText: 'Unique palette reference' }).waitFor();
    await page.locator('#command-query').press('Enter');
    await page.waitForURL((url) => url.hash === '#library?item=' + libraryId);
    await page.locator('.dm-library-sheet').waitFor();
    assert.equal(
      await page.locator('.dm-library-sheet h2').innerText(),
      'Unique palette reference',
    );
    assert.equal(await page.locator('.dm-library-edit').evaluate((element) => element.open), false);
    assert.equal(
      await page.locator('#resource-form [name="title"]').inputValue(),
      'Unique palette reference',
    );
    checks.push('Library result deep-link opens the matching explanation in its read view');

    await openSearch('navigation-fixture');
    await page.getByRole('option').filter({ hasText: 'navigation-fixture.csv' }).waitFor();
    await page.locator('#command-query').press('Enter');
    await page.getByRole('heading', { name: 'navigation-fixture.csv', exact: true }).waitFor();
    await page.getByRole('heading', { name: 'Hostname groups', exact: true }).waitFor();
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('#modal').open);
    checks.push('Source-file result opens authenticated import detail without route confusion');

    await page.locator('#global-search').focus();
    await page.keyboard.press('Control+k');
    await page.locator('#command-query').fill('private-palette-query-0981');
    await page.keyboard.press('Escape');
    await page.waitForFunction(
      () =>
        !document.querySelector('#modal').open && document.activeElement?.id === 'global-search',
    );
    const storage = await page.evaluate(() =>
      JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }),
    );
    assert(!storage.includes('private-palette-query-0981'));
    assert(!storage.includes(boot.token));
    checks.push(
      'Escape closes the palette and restores focus; search text and authentication token stay out of browser persistence',
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      JSON.stringify({ checks, page_errors: errors, external_requests: external }, null, 2),
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
