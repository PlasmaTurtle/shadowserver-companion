/* Browser session and origin checks against an isolated synthetic workspace. */
const assert = require('node:assert/strict');
const http = require('node:http');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.ECLIPSE_BASE_URL;
const launch = process.env.ECLIPSE_LAUNCH_URL;
assert(base && launch, 'Explicit synthetic server and one-time launcher URL required');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    args: ['--no-sandbox'],
  });
  const foreign = http.createServer((request, response) => {
    response.setHeader('Content-Type', 'text/html');
    response.end('<!doctype html><title>Session boundary test</title>');
  });
  await new Promise((resolve) => foreign.listen(0, '127.0.0.1', resolve));
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    assert.equal((await context.request.get(base + '/api/bootstrap')).status(), 401);
    await page.goto(launch);
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    assert(!page.url().includes('launch='));
    const cookies = await context.cookies(base + '/api/bootstrap');
    assert(cookies.some((cookie) => cookie.httpOnly && cookie.sameSite === 'Strict'));
    await page.reload();
    await page.getByRole('heading', { name: 'Workspace', exact: true }).waitFor();
    assert.equal((await context.request.get(base + '/api/bootstrap')).status(), 200);
    const untrusted = await context.newPage();
    await untrusted.goto('http://127.0.0.1:' + foreign.address().port);
    const attempt = await untrusted.evaluate(async (target) => {
      try {
        const response = await fetch(target + '/api/bootstrap', { credentials: 'include' });
        return { readable: true, status: response.status };
      } catch {
        return { readable: false };
      }
    }, base);
    assert.equal(attempt.readable, false);
    const stranger = await browser.newContext();
    assert.equal((await stranger.request.get(base + '/api/bootstrap')).status(), 401);
    assert.equal(
      (
        await stranger.request.post(base + '/api/session/exchange', {
          headers: { 'X-Workbench-Launch': launch.split('#launch=')[1] },
        })
      ).status(),
      401,
    );
    console.log(
      JSON.stringify({
        launcher_exchange: true,
        fragment_scrubbed: true,
        reload_authenticated: true,
        cookie_httponly_strict: true,
        foreign_origin_cannot_read: true,
        stranger_rejected: true,
        replay_rejected: true,
        limitation:
          'Cookies are host/path scoped, not port scoped; other same-host local web services remain trusted.',
      }),
    );
  } finally {
    await browser.close();
    await new Promise((resolve) => foreign.close(resolve));
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
