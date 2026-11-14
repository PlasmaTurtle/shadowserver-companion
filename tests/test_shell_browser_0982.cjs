/** Final shell interactions against an isolated synthetic demo; no external requests. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const base = process.env.BASE_URL,
    folder = process.env.QA_DIR;
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    headless: true,
    args: ['--no-sandbox', '--no-zygote'],
  });
  const checks = [],
    layouts = [],
    errors = [],
    external = [],
    dialogs = [];
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: 'reduce',
    });
    await context.route('**/*', (route) => {
      if (
        /^https?:/.test(route.request().url()) &&
        !route
          .request()
          .url()
          .startsWith(base + '/')
      ) {
        external.push(route.request().url());
        return route.abort();
      }
      return route.continue();
    });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('dialog', (dialog) => {
      dialogs.push(dialog.message());
      return dialog.dismiss();
    });
    const api = async (url) => {
      const response = await context.request.get(base + url);
      assert.equal(response.status(), 200, url);
      return response.json();
    };
    const ready = async () =>
      page.waitForFunction(
        () => document.querySelector('#main')?.getAttribute('aria-busy') !== 'true',
      );
    const go = async (route, selector) => {
      await page.goto(base + '/#' + route);
      await ready();
      await page.locator(selector).first().waitFor();
    };
    const setTheme = async (theme) => {
      if ((await page.evaluate(() => document.documentElement.dataset.theme || 'light')) !== theme)
        await page.locator('#theme-toggle').click();
      await page.waitForFunction(
        (theme) => document.documentElement.dataset.theme === theme,
        theme,
      );
    };
    const shot = async (name) => {
      await page.waitForFunction(() => !document.querySelector('#toasts .toast'));
      await page.evaluate(() => {
        document.activeElement?.blur?.();
        window.scrollTo(0, 0);
      });
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth + 2,
      );
      assert(!overflow, name + ' horizontal overflow');
      fs.mkdirSync(path.join(folder, 'screenshots'), { recursive: true });
      await page.screenshot({
        path: path.join(folder, 'screenshots', name + '.png'),
        fullPage: false,
      });
      layouts.push({ view: name, viewport: page.viewportSize(), horizontal_overflow: overflow });
    };
    await page.goto(process.env.LAUNCH_URL);
    await page.locator('.dm-workspace').waitFor();
    const priorityWork = await page.evaluate(async () => {
      const app = (await import('/static/main.js')).application;
      return (await fetch('/api/workspace/queue?as_of=' + app.actions.localDay())).json();
    });
    const actualIds = await page
      .locator('.dm-priority-row')
      .evaluateAll((rows) => rows.map((row) => row.hash.split('/')[2].split('?')[0]));
    assert.deepEqual(
      actualIds,
      priorityWork.items.slice(0, 8).map((row) => row.id),
    );
    assert.equal(new Set(actualIds).size, actualIds.length);
    assert.equal(await page.locator('.workspace-focus,.workspace-next-actions').count(), 0);
    assert.deepEqual(
      await page.locator('.dm-rank').allTextContents(),
      actualIds.map((_, i) => String(i + 1).padStart(2, '0')),
    );
    assert.equal(
      await page.locator('#sidebar [aria-current="page"]').getAttribute('data-nav'),
      'workspace',
    );
    await page.locator('.dm-priority-row').first().click();
    await page.locator('.investigation-header').waitFor();
    assert.equal(
      await page.locator('#sidebar [aria-current="page"]').getAttribute('data-nav'),
      'investigations',
    );
    assert.match(page.url(), /#workspace\/notifications\//);
    checks.push(
      'Workspace preserves exact ranked backend order once; priority route activates Investigations',
    );

    await go('library', '.dm-library-sheet');
    const beforeExplainers = await api('/api/explainers');
    const selectedId = await page.locator('.resource-item.active').getAttribute('data-resource');
    const selected = beforeExplainers.find((item) => item.id === selectedId);
    assert.equal(await page.locator('.dm-library-edit').evaluate((el) => el.open), false);
    assert.equal(await page.locator('.dm-library-sheet h2').innerText(), selected.title);
    assert((await page.locator('.library-copy').innerText()).includes(selected.body.slice(0, 60)));
    await page.locator('.dm-library-edit > summary').click();
    const edited = selected.body + '\n\nSynthetic shell browser validation.';
    await page.locator('#resource-form [name="body"]').fill(edited);
    await page.locator('#sidebar [data-nav="workspace"]').click();
    await page.waitForFunction(() => location.hash.startsWith('#library'));
    assert.equal(await page.locator('#resource-form [name="body"]').inputValue(), edited);
    assert(dialogs.some((text) => /without saving/.test(text)));
    const other = page.locator(`.resource-item:not([data-resource="${selectedId}"])`).first();
    await other.click();
    assert.equal(
      await page.locator('.resource-item.active').getAttribute('data-resource'),
      selectedId,
    );
    await page.locator('#resource-form [name="body"]').focus();
    await page.keyboard.press('Control+s');
    await page.waitForFunction(
      (text) => document.querySelector('.library-copy')?.textContent.includes(text),
      'Synthetic shell browser validation.',
    );
    const changed = (await api('/api/explainers')).find((item) => item.id === selectedId);
    assert.equal(changed.revision, selected.revision + 1);
    assert.equal(changed.body, edited);
    assert.equal(await page.locator('.dm-library-edit').evaluate((el) => el.open), false);
    await page.locator('[data-action="new-block"]').click();
    assert.equal(await page.locator('.dm-library-edit').evaluate((el) => el.open), true);
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'f-title');
    await page.locator('#resource-form [name="title"]').fill('Shell browser QA explainer');
    await page
      .locator('#resource-form [name="body"]')
      .fill('A synthetic explanation saved through the real Library form.');
    await page
      .locator('#resource-form [name="sources"]')
      .fill('https://example.org/primary-source');
    await page.locator('#resource-form button[type="submit"]').click();
    await page.getByRole('heading', { name: 'Shell browser QA explainer', exact: true }).waitFor();
    assert(
      (await api('/api/explainers')).some((item) => item.title === 'Shell browser QA explainer'),
    );
    assert.equal(
      await page.locator('.dm-library-sheet footer a').getAttribute('href'),
      'https://example.org/primary-source',
    );
    checks.push(
      'Library reads first, opens editing on request, guards route and selection changes, saves by Ctrl+S, creates a new explainer',
    );

    await go('workspace/completed', '.dm-packages');
    const reports = (await api('/api/reports')).filter((item) => item.files_available);
    assert(reports.length > 0, 'Synthetic certified packages required');
    assert.equal(await page.locator('.dm-package-row').count(), (await api('/api/reports')).length);
    const report = reports[0];
    const kinds = [
      'recipient-zip',
      'zip',
      'pdf',
      'docx',
      ...(report.supporting_appendix_available ? ['appendix-pdf', 'appendix-docx'] : []),
    ];
    for (const kind of kinds) {
      const href = `/api/reports/${report.id}/${kind}`;
      assert.equal(await page.locator(`a[href="${href}"]`).count(), 1, href + ' link retained');
      const response = await context.request.get(base + href);
      assert.equal(response.status(), 200, href);
      const bytes = await response.body();
      assert(bytes.length > 50);
      assert.equal(
        bytes.subarray(0, kind.includes('pdf') ? 4 : 2).toString(),
        kind.includes('pdf') ? '%PDF' : 'PK',
      );
      if (kind === 'pdf')
        checks.push('Saved PDF SHA-256: ' + createHash('sha256').update(bytes).digest('hex'));
    }
    const downloadLink = page.locator(`a[href="/api/reports/${report.id}/recipient-zip"]`);
    const downloadPromise = page.waitForEvent('download');
    await downloadLink.click();
    const download = await downloadPromise;
    assert.equal(await download.failure(), null);
    checks.push(
      'Packages retain recipient/internal archives, PDF/DOCX and available appendix links; actual recipient download succeeds',
    );

    await go('activity', '#activity-search');
    await page.locator('#activity-query').fill('Shell browser pagination');
    await page.locator('#activity-search button[type="submit"]').click();
    await page.waitForFunction(() => location.hash.includes('q=Shell'));
    await page.locator('.dm-event').first().waitFor();
    assert.equal(await page.locator('.dm-event').count(), 50);
    const firstPage = await page.locator('.dm-event-body > p').allTextContents();
    assert.equal(firstPage[0], 'Shell browser pagination 64');
    assert(firstPage.every((text) => text.includes('Shell browser pagination')));
    await page.getByRole('link', { name: /Older events/ }).click();
    await ready();
    await page.waitForFunction(() => document.querySelectorAll('.dm-event').length === 15);
    const secondPage = await page.locator('.dm-event-body > p').allTextContents();
    assert.equal(secondPage[0], 'Shell browser pagination 14');
    assert(!secondPage.some((item) => firstPage.includes(item)));
    assert.match(page.url(), /q=Shell\+browser\+pagination/);
    assert.match(page.url(), /before=/);
    await page.getByRole('link', { name: 'Newest events', exact: true }).click();
    await ready();
    await page.waitForFunction(() => document.querySelectorAll('.dm-event').length === 50);
    assert(!page.url().includes('before='));
    await page.locator('#activity-query').fill('A phrase with no recorded match');
    await page.locator('#activity-search button[type="submit"]').click();
    await page.getByRole('heading', { name: 'No matching events', exact: true }).waitFor();
    assert.equal(await page.locator('.dm-event').count(), 0);
    checks.push(
      'Activity search, empty state and 50+15 pagination preserve query and return newest without duplicates',
    );

    const views = [
      ['workspace', 'workspace', '.dm-workspace'],
      ['library', 'library', '.dm-library-sheet'],
      ['packages', 'workspace/completed', '.dm-packages'],
      ['activity', 'activity?q=Shell+browser+pagination', '.dm-event'],
    ];
    for (const theme of ['light', 'dark']) {
      await setTheme(theme);
      for (const [name, route, selector] of views) {
        await go(route, selector);
        await shot(name + '-' + theme);
      }
    }
    await page.setViewportSize({ width: 390, height: 844 });
    for (const [name, route, selector] of views) {
      await go(route, selector);
      await shot(name + '-mobile');
    }
    await go('workspace', '.dm-workspace');
    assert(await page.locator('#sidebar').evaluate((el) => el.inert));
    await page.locator('#menu-toggle').click();
    assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'), 'true');
    assert(
      await page.evaluate(() =>
        document.querySelector('#sidebar').contains(document.activeElement),
      ),
    );
    assert(await page.locator('.shell').evaluate((el) => el.inert));
    await page.locator('#sidebar [data-nav="settings"]').focus();
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'close-navigation');
    await page.keyboard.press('Shift+Tab');
    assert.equal(await page.evaluate(() => document.activeElement?.dataset.nav), 'settings');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'), 'false');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'menu-toggle');
    await page.locator('#menu-toggle').click();
    await page.locator('#sidebar [data-nav="investigations"]').click();
    await page.getByRole('heading', { name: 'Investigations', exact: true }).waitFor();
    assert.equal(
      await page.locator('#sidebar [aria-current="page"]').getAttribute('data-nav'),
      'investigations',
    );
    assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'), 'false');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'main');
    checks.push(
      'Mobile rail traps focus, Escape returns focus, route activation closes navigation and focuses content',
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    const result = {
      passed: true,
      checks,
      layouts,
      page_errors: errors,
      external_requests: external,
      guarded_dialogs: dialogs.length,
    };
    fs.writeFileSync(path.join(folder, 'checks.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
