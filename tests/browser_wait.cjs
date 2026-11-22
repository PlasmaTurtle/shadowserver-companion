/** Poll the authenticated browser request context; await asynchronous predicates explicitly. */
const { setTimeout: delay } = require('node:timers/promises');

async function waitForJSON(request, url, predicate, { timeout = 15000, interval = 100 } = {}) {
  if (!Number.isFinite(timeout) || timeout <= 0 || !Number.isFinite(interval) || interval <= 0)
    throw Error('Browser polling needs a positive timeout and interval');
  const started = performance.now();
  const deadline = started + timeout;
  let last;
  while (performance.now() < deadline) {
    const response = await request.get(url, {
      timeout: Math.max(1, Math.ceil(deadline - performance.now())),
    });
    if (!response.ok()) throw Error(`Polling ${url} returned HTTP ${response.status()}`);
    last = await response.json();
    if (await predicate(last)) return last;
    const remaining = deadline - performance.now();
    if (remaining > 0) await delay(Math.min(interval, remaining));
  }
  throw Error(
    `Polling ${url} timed out after ${Math.round(performance.now() - started)}ms; last state: ${String(JSON.stringify(last)).slice(0, 2048)}`,
  );
}

module.exports = { waitForJSON };
