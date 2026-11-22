/** Initiate a browser download; the caller owns content, naming and confirmation. */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
  } finally {
    // Keep the URL alive while the browser consumes the click, including cleanup
    // if initiating the download throws. This is not confirmation of a saved file.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
