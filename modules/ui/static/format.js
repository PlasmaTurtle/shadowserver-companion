/** Pure text presentation shared by the shell and independent feature renderers. */
export const escapeHTML = (value) =>
  String(value ?? '').replace(
    /[&<>"']/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character],
  );

export const formatCount = (value) => Number(value || 0).toLocaleString();

/** Format an instant. Calendar dates and schedule execution zones remain separate. */
export function formatTimestamp(value, { timeZone = 'America/New_York', locale } = {}) {
  const date = new Date(value);
  return value && !Number.isNaN(date.getTime())
    ? new Intl.DateTimeFormat(locale, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        second: '2-digit',
        timeZone,
        timeZoneName: 'short',
      }).format(date)
    : 'Not recorded';
}
