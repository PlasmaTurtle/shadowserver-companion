const assert = require('node:assert/strict');
const test = require('node:test');
const { waitForJSON } = require('./browser_wait.cjs');

test('Browser API wait retries asynchronous false and returns the completed state', async () => {
  let calls = 0;
  const request = {
    async get(url, options) {
      assert.equal(url, 'http://127.0.0.1/api/job');
      assert(options.timeout > 0 && options.timeout <= 1000);
      const state = { status: ++calls === 3 ? 'completed' : 'running' };
      return { ok: () => true, json: async () => state };
    },
  };
  const result = await waitForJSON(
    request,
    'http://127.0.0.1/api/job',
    async (state) => state.status === 'completed',
    { timeout: 1000, interval: 1 },
  );
  assert.equal(calls, 3);
  assert.equal(result.status, 'completed');
});

test('Browser API wait rejects persistent false with last state and rejects HTTP errors', async () => {
  const request = {
    get: async () => ({ ok: () => true, json: async () => ({ status: 'running' }) }),
  };
  await assert.rejects(
    waitForJSON(request, '/api/job', async () => false, { timeout: 20, interval: 2 }),
    /timed out after \d+ms; last state: .*running/,
  );
  await assert.rejects(
    waitForJSON(
      { get: async () => ({ ok: () => false, status: () => 401 }) },
      '/api/job',
      () => true,
    ),
    /HTTP 401/,
  );
});
