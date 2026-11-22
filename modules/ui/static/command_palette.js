/** Keyboard-first navigation and bounded, read-only cross-record search. */
export function install(ctx) {
  let generation = 0,
    timer = null,
    controller = null,
    results = [],
    active = -1;
  const commands = [
    ['Workspace', 'Priorities and saved activity', '#workspace', 'grid'],
    ['Investigations', 'Reports, outreach and closure', '#investigations', 'file'],
    ['Leads', 'Incoming findings awaiting action', '#leads', 'layers'],
    ['Entities', 'Contacts, assets and history', '#entities', 'layers'],
    ['Eclipse Observatory', 'Explore the observed field', '#eclipse', 'globe'],
    ['Import report files', 'Shadowserver Data', '#data', 'upload'],
    ['Shadowserver API', 'Select and acquire reports', '#data?tab=api', 'download'],
    ['Attribution', 'Review address and domain evidence', '#attribution', 'search'],
    ['Library', 'Reusable explanations', '#library', 'book'],
    ['Settings', 'Profile, appearance and records', '#settings', 'settings'],
  ];
  const isOpen = () => !!ctx.actions.$('#command-query') && !!ctx.actions.$('#modal')?.open;
  function disposeCommandPalette() {
    generation++;
    clearTimeout(timer);
    controller?.abort();
    controller = null;
    results = [];
    active = -1;
    ctx.actions.$('#modal')?.classList?.remove('command-dialog');
  }
  function selected(index, scroll = false) {
    active = results.length ? (index + results.length) % results.length : -1;
    ctx.actions.$$('[data-palette-index]').forEach((el, i) => {
      el.classList.toggle('is-active', i === active);
      el.setAttribute('aria-selected', String(i === active));
      if (i === active && scroll) el.scrollIntoView?.({ block: 'nearest' });
    });
    const input = ctx.actions.$('#command-query');
    if (active >= 0) input?.setAttribute('aria-activedescendant', 'command-result-' + active);
    else input?.removeAttribute('aria-activedescendant');
  }
  function paint(query, data, error = '') {
    if (!isOpen()) return;
    const container = ctx.actions.$('#command-results');
    const focused = document.activeElement?.closest?.('[data-palette-index]');
    const focusedItem =
      focused && container.contains(focused) ? results[Number(focused.dataset.paletteIndex)] : null;
    const commandQuery = query.replace(/^>/, '').trim().toLowerCase();
    const found = commands.filter(
      (c) => !commandQuery || (c[0] + ' ' + c[1]).toLowerCase().includes(commandQuery),
    );
    const sections = [
      {
        label: query ? 'Go to' : 'Navigate',
        items: found.map((c) => ({
          title: c[0],
          detail: c[1],
          href: c[2],
          icon: c[3],
          kind: 'command',
        })),
      },
    ];
    if (!query.startsWith('>')) sections.push(...(data?.groups || []));
    results = [];
    const esc = ctx.actions.esc;
    container.innerHTML =
      sections
        .filter((s) => s.items.length)
        .map(
          (section) =>
            `<section class="command-group"><h3>${esc(section.label)}${section.has_more ? '<span>Top matches</span>' : ''}</h3><div role="group" aria-label="${esc(section.label)}">${section.items
              .map((item) => {
                const index = results.push(item) - 1;
                return `<button type="button" role="option" aria-selected="false" id="command-result-${index}" data-palette-index="${index}" class="command-result"><span class="command-icon">${ctx.actions.icon(item.icon || { entity: 'layers', notification: 'file', lead: 'shield', import: 'upload', explainer: 'book' }[item.kind])}</span><span><strong>${esc(item.title)}</strong><small>${esc(item.detail?.replaceAll('_', ' '))}</small></span><span class="command-enter" aria-hidden="true">↵</span></button>`;
              })
              .join('')}</div></section>`,
        )
        .join('') ||
      `<div class="command-empty">${query.length === 1 && !query.startsWith('>') ? 'Type at least two characters to search records.' : 'No matching records or destinations.'}</div>`;
    ctx.actions.$('#command-status').textContent =
      error || `${results.length} ${query ? 'matches' : 'destinations and recent records'}`;
    const focusedIndex = focusedItem
      ? results.findIndex(
          (item) =>
            item.kind === focusedItem.kind &&
            item.id === focusedItem.id &&
            item.href === focusedItem.href,
        )
      : -1;
    selected(focusedIndex >= 0 ? focusedIndex : 0);
    if (focusedItem)
      ctx.actions
        .$(focusedIndex >= 0 ? '#command-result-' + focusedIndex : '#command-query')
        ?.focus({ preventScroll: true });
  }
  async function search(query) {
    clearTimeout(timer);
    controller?.abort();
    const current = ++generation;
    paint(query, null);
    if (query.startsWith('>') || (query.length > 0 && query.length < 2)) return;
    controller = new AbortController();
    ctx.actions.$('#command-status').textContent = 'Searching saved records…';
    try {
      const data = await ctx.actions.api('/api/search?' + new URLSearchParams({ q: query }), {
        signal: controller.signal,
      });
      if (current === generation && isOpen()) paint(query, data);
    } catch (error) {
      if (current === generation && isOpen() && error.name !== 'AbortError')
        paint(query, null, 'Records unavailable. Navigation still works.');
    }
  }
  function openCommandPalette() {
    disposeCommandPalette();
    ctx.actions.modal(
      'Search & jump',
      `<div class="command-search"><span>${ctx.actions.icon('search')}</span><input id="command-query" maxlength="120" autocomplete="off" spellcheck="false" autofocus role="combobox" aria-label="Search entities, notifications, IPs, CVEs or source files" aria-expanded="true" aria-controls="command-results" aria-autocomplete="list" placeholder="Entity, hostname, IP, CVE…"><kbd>Esc</kbd></div><div id="command-results" role="listbox" aria-label="Search results"></div><div class="command-footer"><span id="command-status" role="status" aria-live="polite"></span><span><kbd>↑</kbd><kbd>↓</kbd> move <kbd>Enter</kbd> open <kbd>&gt;</kbd> navigate</span></div>`,
    );
    ctx.actions.$('#modal').classList.add('command-dialog');
    void search('');
  }
  async function choose(index) {
    const item = results[index];
    if (!item) return;
    ctx.actions.closeModal();
    disposeCommandPalette();
    if (item.kind === 'import') return ctx.actions.showImport(item.id);
    if (item.href?.startsWith('#')) location.hash = item.href.slice(1);
  }
  function commandPaletteKeydown(event) {
    if (!isOpen()) return false;
    if (
      ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key) &&
      event.target?.id === 'command-query'
    ) {
      event.preventDefault();
      selected(
        event.key === 'Home'
          ? 0
          : event.key === 'End'
            ? results.length - 1
            : active + (event.key === 'ArrowDown' ? 1 : -1),
        true,
      );
      return true;
    }
    if (event.key === 'Enter' && event.target?.id === 'command-query') {
      event.preventDefault();
      void choose(active);
      return true;
    }
    return false;
  }
  function commandPaletteInput(event) {
    if (event.target.id !== 'command-query') return;
    const query = event.target.value.trim();
    generation++;
    controller?.abort();
    clearTimeout(timer);
    paint(query, null);
    if (!query.startsWith('>') && query.length !== 1)
      ctx.actions.$('#command-status').textContent = 'Searching saved records…';
    timer = setTimeout(() => search(query), 150);
  }
  Object.assign(ctx.actions, {
    openCommandPalette,
    disposeCommandPalette,
    commandPaletteKeydown,
    commandPaletteInput,
    chooseCommandResult: choose,
  });
}

export function createHandlers(ctx) {
  return {
    input: (event) => ctx.actions.commandPaletteInput(event),
    change: [],
    forms: {},
    actions: { 'search-records': () => ctx.actions.openCommandPalette() },
    click: [
      {
        matches: (el) => el.dataset.paletteIndex !== undefined,
        run: (el) => ctx.actions.chooseCommandResult(Number(el.dataset.paletteIndex)),
      },
    ],
  };
}
