/** Shared feature. Dependencies and mutable state are provided by the application context. */
export function observedVersion(entry) {
  if (entry.normalized && Object.hasOwn(entry.normalized, 'raw_version'))
    return String(entry.normalized.raw_version ?? '');
  const fields = entry.source?.fields || entry;
  const protocol = ['protocol', 'unspecified'].includes(
    entry.normalized?.profile?.version_semantics,
  );
  return String((!protocol && fields.component_version) || entry.version || fields.version || '');
}

export function install(ctx) {
  const $ = (s, root = document) => root.querySelector(s);

  const $$ = (s, root = document) => [...root.querySelectorAll(s)];

  const esc = (v) =>
    String(v ?? '').replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );

  const num = (v) => Number(v || 0).toLocaleString();

  const date = (v) =>
    v
      ? new Date(/^\d{4}-\d{2}-\d{2}$/.test(v) ? v + 'T12:00:00' : v).toLocaleDateString(
          undefined,
          { month: 'short', day: 'numeric', year: 'numeric' },
        )
      : '—';

  const stamp = (v) => {
    const d = new Date(v);
    return v && !Number.isNaN(d.getTime())
      ? new Intl.DateTimeFormat(undefined, {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
          hour: 'numeric',
          minute: '2-digit',
          second: '2-digit',
          timeZone:
            (typeof ctx.state.navigation.boot !== 'undefined' &&
              ctx.state.navigation.boot?.settings?.display_timezone) ||
            'America/New_York',
          timeZoneName: 'short',
        }).format(d)
      : 'Not recorded';
  };

  const timeMarkup = (v) =>
    v
      ? `<time datetime="${ctx.actions.esc(v)}">${ctx.actions.esc(ctx.actions.stamp(v))}</time>`
      : 'Not recorded';

  ctx.constants.titles = {
    workspace: 'Workspace',
    investigations: 'Investigations',
    eclipse: 'Eclipse Observatory',
    entities: 'Entities',
    entity: 'Entity',
    leads: 'Leads',
    attribution: 'Attribution',
    data: 'Shadowserver Data',
    library: 'Library',
    activity: 'Activity',
    settings: 'Settings',
    dashboard: 'Workspace',
    imports: 'Shadowserver Data',
    reviews: 'Attribution',
    reports: 'Packages',
    cases: 'Notifications',
    case: 'Notification',
    resources: 'Library',
    lead: 'Entity',
  };

  ctx.constants.paths = {
    entity: 'M4 21V7l8-4 8 4v14 M2 21h20 M8 9h2 M14 9h2 M8 13h2 M14 13h2 M10 21v-4h4v4',
    signal: 'M3 12h3l3-7 6 14 3-7h3',
    grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
    layers: 'm12 3 10 5-10 5L2 8z M2 12l10 5 10-5 M2 16l10 5 10-5',
    upload: 'M12 16V3 m-5 5 5-5 5 5 M3 15v6h18v-6',
    file: 'M14 2H5v20h14V7z M14 2v6h5 M8 12h8 M8 16h6',
    book: 'M12 5c-3-3-7-3-10-2v16c3-1 7-1 10 2 3-3 7-3 10-2V3c-3-1-7-1-10 2z M12 5v16',
    settings:
      'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2',
    search: 'M21 21l-5-5 M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14',
    shield: 'M12 2 3 6v6c0 5 5 8 9 10 4-2 9-5 9-10V6z m-5 10 3 3 7-7',
    menu: 'M3 6h18 M3 12h18 M3 18h18',
    arrow: 'M4 12h16 m-6-6 6 6-6 6',
    check: 'm5 12 4 4L19 6',
    clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M12 7v5l3 2',
    plus: 'M12 4v16 M4 12h16',
    download: 'M12 3v13 m-5-5 5 5 5-5 M3 17v4h18v-4',
    globe: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M3 12h18 M12 3c-5 5-5 13 0 18 5-5 5-13 0-18',
    refresh: 'M20 7a9 9 0 1 0 1 8 M20 3v5h-5',
    image: 'M3 3h18v18H3z M3 17l6-6 4 4 3-3 5 5 M16 7h.01',
    mail: 'M3 5h18v14H3z m0 0 9 7 9-7',
    external: 'M14 3h7v7 M21 3 11 13 M10 3H3v18h18v-7',
    back: 'M20 12H4 m6-6-6 6 6 6',
    save: 'M3 3h15l3 3v15H3z M7 3v6h10V3 M7 21v-8h10v8',
    lock: 'M5 10h14v11H5z M8 10V6a4 4 0 0 1 8 0v4',
    pin: 'M12 22s8-8 8-14A8 8 0 0 0 4 8c0 6 8 14 8 14 M12 5a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  };

  const icon = (name, cls = '') =>
    `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${ctx.constants.paths[name] || ctx.constants.paths.file}"/></svg>`;

  const statusBadge = (s) =>
    `<span class="badge ${['completed', 'done', 'notification_completed', 'closed', 'qualified'].includes(s) ? 'green' : s === 'in_progress' || s === 'running' ? 'blue' : s === 'error' ? 'red' : s === 'needs_retry' || s === 'review' ? 'amber' : 'gray'}">${ctx.actions.esc({ pending_notification: 'Pending Notification', notification_completed: 'Notification completed', closed: 'Closing report completed', in_progress: 'Work in progress', completed: 'Completed', new: 'New lead', done: 'Finished', needs_retry: 'Retry available', no_match: 'No match', no_public_ip: 'No public IP', review: 'Needs review', qualified: 'Qualified', dismissed: 'Dismissed', pending: 'Pending', deferred: 'Deferred', queued: 'Queued', failed: 'Failed' }[s] || s)}</span>`;

  const safeHref = (v) => (/^https?:\/\//i.test(v || '') ? ctx.actions.esc(v) : '#');

  function viewAborted() {
    const error = Error('This view is no longer active.');
    error.name = 'AbortError';
    error.code = 'VIEW_CHANGED';
    return error;
  }

  function beginViewRequests() {
    ctx.state.navigation.requestController?.abort();
    ctx.state.navigation.requestController =
      typeof AbortController === 'undefined' ? null : new AbortController();
  }

  function stopViewRequests() {
    ctx.state.navigation.requestController?.abort();
    ctx.state.navigation.requestController = null;
  }

  async function api(url, opts = {}) {
    const { blob, timeoutMs: requestedTimeout, background = false, ...request } = opts;
    // Only reads are cancelled on navigation. A submitted mutation may already
    // be running on the server; detaching its old view must not cancel the job.
    const viewSignal = background ? null : ctx.state.navigation.requestController?.signal;
    const read = ['GET', 'HEAD'].includes((request.method || 'GET').toUpperCase());
    // A stalled local read must release loading states and coalesced pollers.
    // Mutations retain their caller-owned deadlines: a timeout does not undo a write.
    const timeoutMs = requestedTimeout ?? (read ? 30000 : undefined);
    const headers = { ...(request.headers || {}) };
    if (request.method && !['GET', 'HEAD'].includes(request.method))
      headers['X-Workbench-Token'] = ctx.state.navigation.boot?.token || '';
    if (request.body && !(request.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
      request.body = JSON.stringify(request.body);
    }
    const signals = [request.signal, read && viewSignal].filter(Boolean);
    if (viewSignal?.aborted || signals.some((signal) => signal.aborted)) throw viewAborted();
    const controller =
      typeof AbortController !== 'undefined' && (timeoutMs || signals.length)
        ? new AbortController()
        : null;
    const abort = () => controller?.abort();
    for (const signal of signals) signal.addEventListener('abort', abort, { once: true });
    let timedOut = false;
    const timer =
      controller && timeoutMs
        ? setTimeout(() => {
            timedOut = true;
            controller.abort();
          }, timeoutMs)
        : null;
    try {
      const response = await fetch(url, {
        ...request,
        headers,
        ...(controller ? { signal: controller.signal } : {}),
      });
      if (viewSignal?.aborted || signals.some((signal) => signal.aborted)) throw viewAborted();
      if (!response.ok) {
        let body;
        try {
          body = await response.json();
        } catch (error) {
          if (timedOut) throw error;
          body = { detail: `Request failed (${response.status})` };
        }
        throw Error(
          Array.isArray(body.detail)
            ? body.detail.map((x) => `${x.loc.slice(1).join('.')}: ${x.msg}`).join('; ')
            : body.detail || 'Request failed',
        );
      }
      const value = blob ? await response.blob() : await response.json();
      // Also reject late responses from a transport that did not honor abort.
      if (viewSignal?.aborted || signals.some((signal) => signal.aborted)) throw viewAborted();
      return value;
    } catch (error) {
      if (timedOut) {
        const timeout = Error(
          'The request timed out. The server may still finish the operation. ' +
            'Refresh its status before trying again.',
        );
        timeout.code = 'REQUEST_TIMEOUT';
        throw timeout;
      }
      throw error;
    } finally {
      if (timer !== null) clearTimeout(timer);
      for (const signal of signals) signal.removeEventListener('abort', abort);
    }
  }

  let modalOpener = null;
  let modalRevision = 0;
  const busyTriggers = new Set();

  function toast(message, error = false) {
    const el = document.createElement('div');
    el.className = 'toast' + (error ? ' error' : '');
    const text = document.createElement('span');
    text.className = 'toast-message';
    text.textContent = message;
    const dismiss = document.createElement('button');
    dismiss.type = 'button';
    dismiss.className = 'toast-dismiss';
    dismiss.setAttribute('aria-label', 'Dismiss notification');
    dismiss.textContent = '×';
    dismiss.addEventListener('click', () => el.remove());
    el.append(text, dismiss);
    el.setAttribute?.('role', error ? 'alert' : 'status');
    el.setAttribute?.('aria-atomic', 'true');
    const region = ctx.actions.$('#toasts');
    if (!error) {
      const notices = ctx.actions.$$('.toast:not(.error)', region);
      while (notices.length >= 3) notices.shift().remove();
    }
    region.append(el);
    setTimeout(() => el.remove(), error ? 12000 : 6000);
  }

  function modal(title, body) {
    if (ctx.actions.setupModalCanReplace?.(title) === false) return false;
    if (ctx.actions.outreachModalCanReplace?.(title) === false) return false;
    const dialog = ctx.actions.$('#modal');
    const titleNode = ctx.actions.$('#modal-title');
    if (!dialog.open) {
      const active = document.activeElement;
      modalOpener =
        active && active !== document.body && !dialog.contains?.(active)
          ? active
          : [...busyTriggers].at(-1) || modalOpener || null;
    }
    modalRevision++;
    titleNode.textContent = title;
    titleNode.tabIndex = -1;
    dialog.setAttribute?.('aria-labelledby', 'modal-title');
    ctx.actions.$('#modal-body').innerHTML = body;
    if (!dialog.open) dialog.showModal();
    // Native <dialog> owns focus trapping. Replacing its content while open
    // still needs an explicit focus target, particularly progress -> result.
    const initial =
      ctx.actions.$('#modal-body [autofocus]') ||
      ctx.actions.$(
        '#modal-body input:not([type="hidden"]):not(:disabled), #modal-body textarea:not(:disabled), #modal-body select:not(:disabled)',
      ) ||
      titleNode;
    initial?.focus?.({ preventScroll: true });
  }

  function restoreModalFocus() {
    const revision = ++modalRevision;
    const opener = modalOpener;
    setTimeout(() => {
      if (revision !== modalRevision || ctx.actions.$('#modal')?.open) return;
      const target =
        opener?.isConnected !== false && !opener?.disabled && opener?.focus
          ? opener
          : ctx.actions.$('#main');
      target?.focus?.({ preventScroll: true });
      modalOpener = null;
    }, 0);
  }

  function trapModalFocus(event) {
    const dialog = ctx.actions.$('#modal');
    if (!dialog?.open || event.key !== 'Tab') return false;
    const targets = ctx.actions
      .$$(
        'a[href],button:not(:disabled),input:not(:disabled):not([type="hidden"]),select:not(:disabled),textarea:not(:disabled),summary,iframe,[tabindex]:not([tabindex="-1"])',
        dialog,
      )
      .filter((el) => !el.hidden && (!el.getClientRects || el.getClientRects().length));
    const first = targets[0],
      last = targets.at(-1);
    const active = document.activeElement;
    if (!first) {
      event.preventDefault();
      ctx.actions.$('#modal-title')?.focus?.();
    } else if (
      !targets.includes(active) ||
      (event.shiftKey && active === first) ||
      (!event.shiftKey && active === last)
    ) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    }
    return true;
  }

  function closeModal() {
    if (ctx.actions.confirmDiscardSetup?.() === false) return false;
    if (ctx.actions.confirmDiscardOutreach?.() === false) return false;
    ctx.actions.$('#modal').close();
    restoreModalFocus();
  }

  async function busy(button, fn) {
    if (button?.disabled) return;
    const old = button?.innerHTML;
    const previousBusy = button?.getAttribute?.('aria-busy');
    if (button) {
      busyTriggers.add(button);
      button.setAttribute?.('aria-busy', 'true');
      button.disabled = true;
      button.innerHTML = '<span class="spinner"></span> Working…';
    }
    try {
      return await fn();
    } catch (e) {
      if (e.name !== 'AbortError') ctx.actions.toast(e.message, true);
      return null;
    } finally {
      busyTriggers.delete(button);
      if (button?.isConnected) {
        if (previousBusy == null) button.removeAttribute?.('aria-busy');
        else button.setAttribute?.('aria-busy', previousBusy);
        button.disabled = false;
        button.innerHTML = old;
      }
    }
  }

  function heading(title, subtitle, actions = '') {
    return `<div class="page-heading"><div><h1>${title}</h1>${subtitle ? `<p>${subtitle}</p>` : ''}</div><div class="actions">${actions}</div></div>`;
  }

  function empty(title, text, action = '') {
    return `<div class="empty"><div class="empty-icon">${ctx.actions.icon('layers')}</div><h3>${title}</h3><p>${text}</p>${action}</div>`;
  }

  function linkButton(href, text, which = 'primary', ic = 'plus') {
    return `<a class="button ${which}" href="${href}">${ctx.actions.icon(ic)}${text}</a>`;
  }

  function field(label, name, value, options = {}) {
    const attr = `id="f-${name}" name="${name}" ${options.draft === false ? '' : 'data-draft'} ${options.disabled ? 'disabled' : ''} ${options.required ? 'required' : ''}`;
    return `<div class="field ${options.full ? 'full' : ''}"><label for="f-${name}">${label}</label>${options.area ? `<textarea ${attr} rows="${options.rows || 4}">${ctx.actions.esc(value)}</textarea>` : options.choices ? `<select ${attr}>${options.choices.map((x) => `<option ${x === value ? 'selected' : ''}>${ctx.actions.esc(x)}</option>`).join('')}</select>` : `<input ${attr} type="${options.type || 'text'}" value="${ctx.actions.esc(value)}">`}${options.help ? `<small>${options.help}</small>` : ''}</div>`;
  }
  Object.assign(ctx.actions, {
    $,
    $$,
    esc,
    num,
    date,
    stamp,
    timeMarkup,
    icon,
    statusBadge,
    safeHref,
    api,
    beginViewRequests,
    stopViewRequests,
    toast,
    modal,
    currentModalRevision: () => modalRevision,
    closeModal,
    restoreModalFocus,
    trapModalFocus,
    busy,
    heading,
    empty,
    linkButton,
    field,
  });
}
