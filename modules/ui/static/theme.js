/* Resolve appearance before first paint; appearance and agency identity are independent. */
'use strict';
(() => {
  const root = document.documentElement;
  const read = (key) => {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  };
  const write = (key, value) => {
    try {
      localStorage.setItem(key, value);
    } catch {}
  };
  const preference = () => read('companion-appearance') || read('companion-theme') || 'dark';
  const media = window.matchMedia?.('(prefers-color-scheme: dark)');
  const apply = (appearance = preference(), profile = read('companion-brand') || 'companion') => {
    appearance = ['light', 'dark', 'system'].includes(appearance) ? appearance : 'light';
    profile = ['companion', 'usss'].includes(profile) ? profile : 'companion';
    root.dataset.appearance = appearance;
    root.dataset.theme = appearance === 'system' ? (media?.matches ? 'dark' : 'light') : appearance;
    root.dataset.brand = profile;
    write('companion-appearance', appearance);
    write('companion-theme', root.dataset.theme);
    write('companion-brand', profile);
    window.dispatchEvent(new Event('companion:presentation'));
  };
  window.CompanionPresentation = { apply, preference };
  media?.addEventListener?.('change', () => {
    if (root.dataset.appearance === 'system') apply('system', root.dataset.brand);
  });
  apply();
})();
