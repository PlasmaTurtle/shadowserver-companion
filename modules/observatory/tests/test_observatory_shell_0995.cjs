/** Observatory shell contracts: production stylesheet order and controller DOM hooks. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const base = path.resolve(__dirname, '../../..');
const read = (name) => fs.readFileSync(path.join(base, name), 'utf8');
const index = read('modules/ui/static/index.html');
const styles = [...index.matchAll(/<link\b[^>]*href="([^"]+\.css)"[^>]*>/g)].map((m) => m[1]);
const observatoryStyle = styles.indexOf('/modules/observatory/static/eclipse.css');
assert.ok(observatoryStyle >= 0, 'Observatory stylesheet is loaded');
for (const inherited of ['presentation', 'chaos', 'darkmatter', 'cosmic_motion', 'cockpit']) {
  const position = styles.indexOf('/modules/ui/static/' + inherited + '.css');
  assert.ok(
    position >= 0 && position < observatoryStyle,
    inherited +
      ' must load before Observatory: legacy surfaces otherwise replace its optical palette',
  );
}
assert.equal(styles.filter((s) => s === '/modules/observatory/static/eclipse.css').length, 1);

(async () => {
  const { escapeHTML } = await import('../../ui/static/format.js');
  const context = { window: {} };
  vm.runInNewContext(read('modules/observatory/static/eclipse.js'), context, {
    filename: 'eclipse.js',
  });
  const html = context.window.Eclipse.render(
    {
      entities: [{ id: 'entity-"<unsafe>', name: '<img src=x onerror=alert(1)>' }],
      warnings: ['<script>alert(1)</script>'],
    },
    escapeHTML,
  );
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(new Set(ids).size, ids.length, 'Every shell ID is unique');
  assert.ok(!html.includes('<img src=x') && !html.includes('<script>alert'));
  assert.ok(html.includes('&lt;img') && html.includes('&lt;script&gt;'));
  for (const match of read('modules/observatory/static/eclipse_controller.js').matchAll(
    /(?:querySelector|\$)\(\s*['"]#(ec-[\w-]+)['"]\s*\)/g,
  )) {
    assert.ok(ids.includes(match[1]), 'Controller DOM hook must exist: ' + match[1]);
  }
  for (const view of ['field', 'atlas', 'pulse', 'records']) {
    assert.match(
      html,
      new RegExp('<button[^>]*data-ec-view="' + view + '"[^>]*aria-pressed="(?:true|false)"'),
    );
  }
  assert.match(html, /data-ec-view="field" aria-pressed="true"/);
  assert.match(html, /id="ec-back-field" hidden/);
  assert.match(html, /<details class="ec-instrument-options">/);
  assert.match(html, /<details class="ec-history-panel">/);
  assert.match(html, /<canvas[^>]*aria-describedby="ec-canvas-help"/);
  assert.match(html, /id="ec-records"[^>]*aria-label="Finding records"/);
  assert.match(context.window.Eclipse.loading(), /role="status" aria-live="polite"/);

  const css = read('modules/observatory/static/eclipse.css');
  assert.match(
    css,
    /:root\[data-theme\] body\.eclipse-view #dm-viewport\s*\{[^}]*display:\s*block/s,
    'The optical field must remain visible when the surrounding app uses light theme',
  );
  assert.match(css, /#eclipse\s*\{[^}]*--ec-text:\s*#edf5ff/s);
  assert.match(css, /#eclipse\s*\{[^}]*color-scheme:\s*dark/s);
  assert.match(
    css,
    /#eclipse \.ec-records-head\s*\{[^}]*flex-wrap:\s*wrap/s,
    'Product-view title and return actions must wrap at narrow widths',
  );
  assert.match(
    css,
    /#eclipse \.ec-scope-chip\s*\{[^}]*overflow-wrap:\s*anywhere/s,
    'Long exact search scopes must not push the viewport sideways',
  );
  assert.match(css, /@media \(prefers-reduced-motion:\s*reduce\)/);
  assert.match(
    css,
    /#eclipse \.ec-inspector\s*\{[^}]*max-height:\s*calc\(var\(--ec-viewport-height\) - 96px\)/s,
    'The desktop inspector must leave room for the camera controls',
  );
  console.log(
    'Observatory 0.9.95 shell: production CSS ordering, controller hooks, scoped palette, escaping, and responsive contracts pass.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
