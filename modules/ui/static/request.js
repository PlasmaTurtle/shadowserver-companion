/** Fetch response decoding and cancellation, independent of app state or workflow. */
function cancelled() {
  const error = new Error('The request was cancelled.');
  error.name = 'AbortError';
  return error;
}

function responseError(response, body) {
  const detail = body?.detail;
  const fallback = `Request failed (${response.status})`;
  const message = Array.isArray(detail)
    ? detail
        .map((item) => `${(item.loc || []).slice(1).join('.')}: ${item.msg || 'Invalid value'}`)
        .join('; ')
    : typeof detail === 'string'
      ? detail
      : detail?.message || fallback;
  return Object.assign(new Error(message), {
    name: 'RequestError',
    status: response.status,
    detail,
    body,
  });
}

async function request(url, options, readBody) {
  const { timeoutMs, signals = [], signal, ...init } = options;
  const inputs = [signal, ...signals].filter(Boolean);
  if (inputs.some((input) => input.aborted)) throw cancelled();
  const controller =
    typeof AbortController !== 'undefined' && (timeoutMs || inputs.length)
      ? new AbortController()
      : null;
  let timedOut = false;
  let timer = null;
  const abort = () => {
    // Superseded work releases its deadline even while a transport is unwinding.
    if (timer !== null) clearTimeout(timer);
    controller?.abort();
  };
  for (const input of inputs) input.addEventListener('abort', abort, { once: true });
  if (controller && timeoutMs) {
    timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
  }
  function checkCancellation() {
    if (timedOut) {
      throw Object.assign(new Error('The request timed out.'), {
        name: 'TimeoutError',
        code: 'REQUEST_TIMEOUT',
      });
    }
    if (inputs.some((input) => input.aborted)) throw cancelled();
  }
  try {
    const response = await fetch(url, {
      ...init,
      ...(controller ? { signal: controller.signal } : signal ? { signal } : {}),
    });
    checkCancellation();
    if (!response.ok) {
      let body;
      try {
        body = await response.json();
      } catch {
        // Non-JSON HTTP failures still retain their status; aborts stay aborts.
        checkCancellation();
      }
      checkCancellation();
      throw responseError(response, body);
    }
    const value = await readBody(response);
    // Also reject a late result if a transport or test double ignored abort.
    checkCancellation();
    return value;
  } catch (error) {
    checkCancellation();
    throw error;
  } finally {
    if (timer !== null) clearTimeout(timer);
    for (const input of inputs) input.removeEventListener('abort', abort);
  }
}

export const requestJSON = (url, options = {}) =>
  request(url, options, (response) => response.json());

export const requestBlob = (url, options = {}) =>
  request(url, options, (response) => response.blob());
