/* Targeted accessibility checks, not a full WCAG conformance audit.
 * 200% layout equivalent = 720x500 CSS viewport at DPR 2, 1440x1000 device pixels.
 * Native browser zoom controls remain part of Windows workstation acceptance. */
const assert = require('node:assert/strict'),
  fs = require('node:fs'),
  path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.ECLIPSE_BASE_URL || 'http://127.0.0.1:8897';
(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    args: ['--no-sandbox'],
  });
  const results = {
    method: 'Targeted Chromium headless checks; not full WCAG certification',
    contrast: [],
    keyboard: [],
    reduced_motion: {},
    zoom_equivalent: {
      method:
        '720x500 CSS viewport, deviceScaleFactor=2; 1440x1000 physical pixels. Native browser-chrome zoom was not exercised.',
      views: [],
    },
    errors: [],
  };
  try {
    const ctx = await browser.newContext({
        viewport: { width: 1440, height: 1000 },
        deviceScaleFactor: 2,
        reducedMotion: 'reduce',
      }),
      page = await ctx.newPage();
    page.on('pageerror', (e) => results.errors.push(e.message));
    assert(process.env.ECLIPSE_LAUNCH_URL, 'An explicit one-time launcher URL is required');
    await page.goto(process.env.ECLIPSE_LAUNCH_URL);
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    await page.goto(base + '/#settings');
    await page.locator('#settings-form').waitFor();
    for (const profile of ['companion', 'usss'])
      for (const [appearance, system] of [
        ['light', 'light'],
        ['dark', 'dark'],
        ['system', 'light'],
        ['system', 'dark'],
      ]) {
        await page.emulateMedia({ colorScheme: system, reducedMotion: 'reduce' });
        await page.evaluate(
          ([a, p]) => window.CompanionPresentation.apply(a, p),
          [appearance, profile],
        );
        const ratios = await page.evaluate(() => {
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
              return +((Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)).toFixed(2);
            };
          return {
            theme: document.documentElement.dataset.theme,
            text: ratio('--text', '--paper'),
            muted: ratio('--muted', '--paper'),
            confirmation: ratio('--confirm', '--confirm-soft'),
            adverse: ratio('--adverse', '--adverse-soft'),
            unknown: ratio('--unknown', '--unknown-soft'),
            review_required: ratio('--review-required', '--paper'),
            review_on_background: ratio('--review-required', '--bg'),
            controls: ratio('--control-line', '--paper'),
          };
        });
        assert.equal(ratios.theme, appearance === 'system' ? system : appearance);
        for (const [key, n] of Object.entries(ratios))
          if (key !== 'theme')
            assert(
              n >= (key === 'controls' ? 3 : 4.5),
              profile + '/' + appearance + '/' + system + ' ' + key + ' ' + n,
            );
        results.contrast.push({ profile, appearance, system, ...ratios });
      }
    const cases = await page.evaluate(async () => await (await fetch('/api/cases')).json()),
      work = cases.find((c) => c.stage === 'in_progress');
    assert(work);
    await page.goto(base + '/#workspace/notifications/' + work.id);
    await page.locator('[data-report-section="Introduction"]').waitFor();
    await page.locator('[data-report-section="Introduction"]').focus();
    for (const name of ['Vulnerabilities', 'Attribution', 'Information']) {
      await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(() => document.activeElement.dataset.reportSection), name);
      await page.keyboard.press('Enter');
      assert.equal(
        await page
          .locator('[aria-current="step"][data-report-section]')
          .getAttribute('data-report-section'),
        name,
      );
      const outline = await page.evaluate(() => {
        const s = getComputedStyle(document.activeElement);
        return { style: s.outlineStyle, width: s.outlineWidth };
      });
      assert.equal(outline.style, 'solid');
      assert(parseFloat(outline.width) >= 3);
      results.keyboard.push({
        section: name,
        activation: 'Tab then Enter',
        focus_outline: outline,
      });
    }
    await page.locator('[data-skip-content]').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'main');
    results.keyboard.push({ skip_link: 'Enter moves focus to main' });
    results.reduced_motion = await page.evaluate(() => ({
      media: matchMedia('(prefers-reduced-motion: reduce)').matches,
      transition: getComputedStyle(document.querySelector('.button')).transitionDuration,
      animation: getComputedStyle(document.querySelector('.button')).animationName,
    }));
    assert.equal(results.reduced_motion.media, true);
    assert.equal(results.reduced_motion.transition, '0s');
    assert.equal(results.reduced_motion.animation, 'none');
    await page.goto(base + '/#eclipse');
    await page.locator('#eclipse[data-ready="true"]').waitFor();
    await page.evaluate(() => {
      window.__qaRafCount = 0;
      window.__qaRaf = requestAnimationFrame;
      window.requestAnimationFrame = (...args) => {
        window.__qaRafCount++;
        return window.__qaRaf(...args);
      };
    });
    await page.locator('#ec-list-toggle').click();
    assert.equal(await page.locator('#ec-list-toggle').getAttribute('aria-expanded'), 'true');
    await page.locator('#ec-records [data-ec-row]').first().click();
    await page.locator('#ec-inspector-content .ec-detail-grid').waitFor();
    assert.match(await page.locator('#ec-inspector-content').innerText(), /Preserved source/);
    await page.waitForTimeout(150);
    // Canvas invalidations may schedule a paint; reduced motion forbids a
    // camera transition or perpetual frame loop, not the initial repaint.
    assert.equal(await page.locator('#eclipse').getAttribute('data-animating'), 'false');
    assert.equal(await page.locator('#ec-motion').isDisabled(), true);
    const settledFrames = await page.evaluate(() => window.__qaRafCount);
    await page.waitForTimeout(180);
    results.reduced_motion.selection_paint_frames = await page.evaluate(() => {
      window.requestAnimationFrame = window.__qaRaf;
      return window.__qaRafCount;
    });
    assert.equal(results.reduced_motion.selection_paint_frames, settledFrames);
    assert(settledFrames <= 4, 'Selection requires only bounded canvas repaints');
    // Reuse the authenticated 2x context with the narrower CSS viewport.
    // Single-process headless hosts cannot maintain a second browser context.
    await page.close();
    const zp = await ctx.newPage();
    await zp.setViewportSize({ width: 720, height: 500 });
    zp.on('pageerror', (e) => results.errors.push(e.message));
    for (const [view, hash, selector] of [
      ['settings', 'settings', '#settings-form'],
      ['builder', 'case/' + work.id, '[data-report-section="Introduction"]'],
      ['observatory', 'eclipse', '#eclipse'],
    ]) {
      await zp.goto(base + '/#' + hash);
      await zp.locator(selector).waitFor();
      const size = await zp.evaluate(() => ({
        viewport: innerWidth,
        scroll: document.documentElement.scrollWidth,
        dpr: devicePixelRatio,
        tlp: !!document.querySelector('.handling-strip .tlp-mark'),
      }));
      assert(size.scroll <= size.viewport + 1, view + ' horizontal overflow');
      assert.equal(size.dpr, 2);
      assert(size.tlp);
      if (view === 'builder') {
        const contextSummary = zp.locator('.investigation-context > summary');
        assert.equal(await zp.locator('.case-progress').isVisible(), false);
        await contextSummary.focus();
        await zp.keyboard.press('Enter');
        assert.equal(await zp.locator('.case-progress').isVisible(), true);
        assert.equal(await zp.locator('.case-progress [aria-current="step"]').count(), 1);
        assert(await zp.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
        await zp.keyboard.press('Enter');
        await zp.locator('[data-report-section="Attribution"]').focus();
        await zp.keyboard.press('Enter');
        assert.equal(
          await zp
            .locator('[aria-current="step"][data-report-section]')
            .getAttribute('data-report-section'),
          'Attribution',
        );
      }
      results.zoom_equivalent.views.push({ view, ...size });
      if (process.env.ECLIPSE_SCREENSHOTS) {
        fs.mkdirSync(process.env.ECLIPSE_SCREENSHOTS, { recursive: true });
        await zp.evaluate(() => window.scrollTo(0, 0));
        await zp.waitForTimeout(60);
        await zp.screenshot({
          path: path.join(process.env.ECLIPSE_SCREENSHOTS, '070-zoom-equivalent-' + view + '.png'),
          fullPage: true,
        });
      }
    }
    assert.deepEqual(results.errors, []);
    const output = JSON.stringify(results, null, 2);
    console.log(output);
    if (process.env.ACCESSIBILITY_RESULT)
      fs.writeFileSync(process.env.ACCESSIBILITY_RESULT, output + '\n');
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
