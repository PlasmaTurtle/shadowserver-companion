/** Consume a short-lived launcher credential without retaining it in history. */
export async function establishSession() {
  const fragment = window.location.hash;
  if (!fragment.startsWith('#launch=')) return;
  const token = fragment.slice('#launch='.length);
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
  const response = await fetch('/api/session/exchange', {
    method: 'POST',
    headers: { 'X-Workbench-Launch': token },
    credentials: 'same-origin',
    cache: 'no-store',
  });
  if (!response.ok)
    throw new Error('Launch link expired or already used. Reopen the desktop launcher.');
}
