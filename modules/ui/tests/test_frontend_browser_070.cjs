/* Run against an isolated synthetic demonstration workspace; no external requests. */
const assert = require('node:assert/strict'),
  fs = require('node:fs'),
  path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.ECLIPSE_BASE_URL || 'http://127.0.0.1:8897',
  screens = process.env.ECLIPSE_SCREENSHOTS;
(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    args: ['--no-sandbox'],
  });
  const errors = [],
    external = [],
    checks = [];
  try {
    const ctx = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: 'reduce',
    });
    ctx.on('request', (r) => {
      if (/^https?:/.test(r.url()) && !r.url().startsWith(base)) external.push(r.url());
    });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => errors.push(e.message));
    async function shot(name) {
      if (screens) {
        fs.mkdirSync(screens, { recursive: true });
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.waitForTimeout(60);
        await page.screenshot({ path: path.join(screens, name + '.png'), fullPage: true });
      }
    }
    assert(process.env.ECLIPSE_LAUNCH_URL, 'An explicit one-time launcher URL is required');
    assert.equal((await ctx.request.get(base + '/api/bootstrap')).status(), 401);
    await page.route('**/api/bootstrap', (route) => route.abort('connectionreset'), { times: 1 });
    await page.goto(process.env.ECLIPSE_LAUNCH_URL);
    await page.getByRole('heading', { name: 'Unable to connect' }).waitFor();
    assert.match(
      await page.locator('#main').innerText(),
      /No complete response from the local app/,
    );
    const healthLink = page.getByRole('link', { name: 'Check local service' });
    const healthUrl = new URL(await healthLink.getAttribute('href'), base);
    assert.equal(healthUrl.origin, new URL(base).origin);
    assert.equal(
      (await (await ctx.request.get(healthUrl.href)).json()).app,
      'notification-workbench',
    );
    await page.getByRole('button', { name: 'Reload app' }).click();
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    checks.push(
      'A lost bootstrap response recovers through the shell action and the established session',
    );
    await page.goto(base + '/#eclipse');
    await page.locator('#eclipse[data-ready="true"]').waitFor();
    const expectedRelease = JSON.parse(
      fs.readFileSync(path.join(__dirname, '../../../RELEASE.json'), 'utf8'),
    );
    const health = await (await ctx.request.get(base + '/api/health')).json();
    assert.equal(health.release.version, expectedRelease.version);
    assert.equal(health.release.channel, expectedRelease.channel);
    assert((await page.locator('#release-status').innerText()).includes(expectedRelease.version));
    assert(await page.locator('#release-status').isVisible());
    assert.equal(await page.locator('#release-status').innerText(), `v${expectedRelease.version}`);
    assert.match(await page.locator('#release-status').getAttribute('title'), /Version/);
    assert.doesNotMatch(await page.locator('#release-status').innerText(), /Chaos|Pre-release/);
    assert.match(await page.title(), /Shadowserver Eclipse/);
    checks.push(
      'Runtime release metadata matches the installed version and the version remains visible',
    );
    assert(!page.url().includes('launch='), 'Launch credential removed from browser history');
    assert.equal(
      (
        await ctx.request.post(base + '/api/session/exchange', {
          headers: { 'X-Workbench-Launch': process.env.ECLIPSE_LAUNCH_URL.split('#launch=')[1] },
        })
      ).status(),
      401,
    );
    checks.push(
      'Launcher exchange, unauthenticated read rejection, token replay rejection and fragment removal',
    );
    assert.equal(await page.locator('.handling-strip .tlp-mark').textContent(), 'TLP:AMBER');
    const originalRows = await page.locator('#ec-rows').textContent();
    for (const view of ['atlas', 'pulse', 'field']) {
      const control = page.locator('.ec-views [data-ec-view="' + view + '"]');
      await control.click();
      assert.equal(await control.getAttribute('aria-pressed'), 'true');
    }
    await shot('070-observatory-light');
    await page.locator('#ec-filter-toggle').click();
    assert.equal(await page.locator('#ec-filter-toggle').getAttribute('aria-expanded'), 'true');
    await page.locator('#ec-intelligence').selectOption('kev');
    await page.waitForFunction(() => document.querySelector('#ec-rows')?.textContent === '0');
    assert.match(await page.locator('#ec-map-empty').innerText(), /No findings match/);
    await page.locator('#ec-reset').click();
    await page.waitForFunction(
      (value) => document.querySelector('#ec-rows')?.textContent === value,
      originalRows,
    );
    checks.push('Field, Atlas and Pulse views, intelligence filter, reset and persistent TLP');
    await page.goto(base + '/#settings');
    await page.locator('#settings-form').waitFor();
    assert((await page.locator('#release-version').innerText()).includes(expectedRelease.version));
    assert(await page.locator('#release-status').isVisible());
    await page.locator('.settings-appearance > summary').click();
    await page.locator('#brand-profile').selectOption('usss');
    await page.locator('input[name="appearance"][value="dark"]').check();
    await page.locator('#settings-form button[type=submit]').click();
    await page.waitForFunction(
      () =>
        document.documentElement.dataset.brand === 'usss' &&
        document.documentElement.dataset.theme === 'dark',
    );
    await shot('070-settings-usss-dark');
    await page.reload();
    await page.locator('#settings-form').waitFor();
    assert.equal(await page.locator('#brand-profile').inputValue(), 'usss');
    assert.equal(await page.locator('input[name="appearance"][value="dark"]').isChecked(), true);
    checks.push('Settings persistence and appearance independence');
    await page.goto(base + '/#eclipse');
    await page.locator('#eclipse[data-ready="true"]').waitFor();
    await shot('070-observatory-usss-dark');
    const contrast = await page.evaluate(() => {
      const s = getComputedStyle(document.documentElement),
        rgb = (hex) => {
          hex = hex.trim().replace('#', '');
          if (hex.length === 3)
            hex = hex
              .split('')
              .map((c) => c + c)
              .join('');
          return [0, 2, 4]
            .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
            .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
        },
        lum = (hex) => rgb(hex).reduce((n, c, i) => n + c * [0.2126, 0.7152, 0.0722][i], 0),
        ratio = (a, b) => {
          const x = lum(s.getPropertyValue(a)),
            y = lum(s.getPropertyValue(b));
          return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
        };
      return {
        text: ratio('--text', '--paper'),
        muted: ratio('--muted', '--paper'),
        confirmation: ratio('--confirm', '--confirm-soft'),
        adverse: ratio('--adverse', '--adverse-soft'),
        controls: ratio('--control-line', '--paper'),
      };
    });
    for (const [key, value] of Object.entries(contrast))
      assert(value >= (key === 'controls' ? 3 : 4.5), key + ' contrast ' + value);
    checks.push('Semantic dark theme text and control contrast');
    await page.goto(base + '/#workspace/notifications');
    await page.locator('#case-search').waitFor();
    await shot('070-queue-usss-dark');
    const cases = await page.evaluate(async () => await (await fetch('/api/cases')).json());
    const work = cases.find((c) => c.stage === 'in_progress');
    assert(work, 'Synthetic open case');
    await page.goto(base + '/#workspace/notifications/' + work.id);
    await page.locator('[data-report-section="Introduction"]').waitFor();
    const appendix = page.locator('details.appendix-overview');
    assert.match(
      await appendix.locator(':scope > summary').innerText(),
      /Appendix & output options/,
    );
    await appendix.locator(':scope > summary').click();
    assert.match(await appendix.innerText(), /Supporting appendix/);
    await appendix.locator(':scope > summary').click();
    assert.match(
      await page.locator('#editor-content').innerText(),
      /Principal Executive \/ IT Director/,
    );
    await shot('070-builder-introduction');
    for (const name of ['Vulnerabilities', 'Attribution', 'Information', 'Closing']) {
      await page.locator('[data-report-section="' + name + '"]').click();
      await page.waitForTimeout(150);
      await shot('070-builder-' + name.toLowerCase());
    }
    // Preview must come from the server PDF, not a colored HTML approximation.
    let previewRequests = 0;
    page.on('request', (request) => {
      if (request.url().includes('/preview.pdf')) previewRequests++;
    });
    const pdfResponse = page.waitForResponse((r) => r.url().includes('/preview.pdf'));
    await page.locator('[data-action="preview"]').first().click();
    const pdf = await pdfResponse;
    assert.equal(pdf.status(), 200);
    assert.match(pdf.headers()['content-type'], /application\/pdf/);
    await page.locator('iframe.pdf-preview').waitFor();
    assert.match(await page.locator('iframe.pdf-preview').getAttribute('src'), /^blob:/);
    assert.equal(previewRequests, 1, 'Preview fetches the PDF once; iframe reuses its blob');
    assert.equal(await page.locator('#modal .tlp-mark').textContent(), 'TLP:AMBER');
    await page.locator('#close-modal').click();
    checks.push('Five sections, fixed addressee, appendix ownership, actual PDF preview');
    // Synthetic browser-only intelligence fixture; no source lookup or database mutation.
    await page.evaluate(async () => {
      const { application } = await import('/modules/ui/static/main.js');
      const { currentLead, draft } = application.state.editor;
      currentLead.entries[0].source.fields.tag = 'CVE-2026-10000';
      draft.cve_records = [
        {
          id: 'CVE-2026-10000',
          verification_status: 'published',
          description:
            'SYNTHETIC browser fixture: conditional information disclosure when the affected feature is enabled.',
          publisher: 'Synthetic advisory',
          retrieved_at: '2026-11-07T13:00:00Z',
          kev: true,
          kev_date: '2026-11-06',
          ransomware: { status: 'known', label: 'Known ransomware use' },
          epss: 0,
          epss_percentile: 0,
          epss_date: '2026-11-06',
          selected_ssvc_assessment_id: 'fixture-ssvc',
          ssvc_assessments: [
            {
              id: 'fixture-ssvc',
              publisher: 'Synthetic CISA fixture',
              exploitation: 'active',
              label: 'Active exploitation reported',
              assessed_at: '2026-11-06T12:00:00Z',
            },
          ],
          impacts: [
            {
              label: 'Information disclosure',
              source_text:
                'SYNTHETIC: Information may be disclosed when the affected feature is enabled.',
              basis: 'explicit_structured_data',
              conditions: 'Affected feature must be enabled',
            },
          ],
        },
      ];
    });
    await page.locator('[data-report-section="Vulnerabilities"]').click();
    await page.locator('.intel-panel').waitFor();
    assert.match(await page.locator('.intel-panel').innerText(), /0.00% probability/);
    await shot('070-vulnerability-intelligence');
    checks.push('Independent intelligence cards, real zero EPSS, dated assessment and conditions');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(base + '/#settings');
    await page.locator('#settings-form').waitFor();
    await shot('070-settings-mobile');
    assert(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
      'Settings mobile horizontal overflow',
    );
    await page.goto(base + '/#eclipse');
    await page.locator('#eclipse[data-ready="true"]').waitFor();
    await shot('070-observatory-mobile');
    assert(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
      'Map mobile horizontal overflow',
    );
    checks.push('390px responsive layouts');
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      JSON.stringify({ checks, page_errors: errors, external_requests: external }, null, 2),
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
