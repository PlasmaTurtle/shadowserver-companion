/** Production UI interruption replay with isolated case responses, no browser storage. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');
const decode = (s) =>
  (s || '')
    .replaceAll('&quot;', '"')
    .replaceAll('&#39;', "'")
    .replaceAll('&lt;', '<')
    .replaceAll('&gt;', '>')
    .replaceAll('&amp;', '&');

(async () => {
  const nodes = new Map(),
    copies = [],
    calls = [],
    prompts = [],
    notices = [];
  let allowDiscard = false;
  const target = (obj) =>
    Object.assign(obj, {
      listeners: new Map(),
      addEventListener(type, fn) {
        this.listeners.set(type, [...(this.listeners.get(type) || []), fn]);
      },
      removeEventListener(type, fn) {
        this.listeners.set(
          type,
          (this.listeners.get(type) || []).filter((f) => f !== fn),
        );
      },
      async dispatch(type, event = {}) {
        for (const fn of this.listeners.get(type) || []) await fn(event);
      },
    });
  const document = target({
    querySelector: (s) => node(s),
    querySelectorAll: () => [],
    activeElement: null,
  });
  function node(selector) {
    if (!nodes.has(selector)) {
      const classes = new Set();
      let html = '';
      const el = target({
        id: selector.startsWith('#') ? selector.slice(1) : '',
        value: '',
        dataset: {},
        textContent: '',
        open: false,
        disabled: false,
        hidden: false,
        checked: false,
        isConnected: true,
        classList: {
          add: (x) => classes.add(x),
          remove: (x) => classes.delete(x),
          contains: (x) => classes.has(x),
          toggle: (x, value) => (value ? classes.add(x) : classes.delete(x)),
        },
        setAttribute() {},
        removeAttribute() {},
        getAttribute() {
          return null;
        },
        focus() {
          document.activeElement = this;
        },
        setSelectionRange(start, end, direction) {
          this.selectionStart = start;
          this.selectionEnd = end;
          this.selectionDirection = direction;
        },
        contains() {
          return false;
        },
        showModal() {
          this.open = true;
        },
        close() {
          this.open = false;
          void this.dispatch('close');
        },
        matches() {
          return false;
        },
        closest() {
          return null;
        },
        querySelector: (s) => node(s),
        querySelectorAll: () => [],
      });
      Object.defineProperty(el, 'innerHTML', {
        get: () => html,
        set: (value) => {
          html = value;
          for (const m of value.matchAll(/<input\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
            node('#' + m[2]).value = decode(m[1].match(/\bvalue="([^"]*)"/)?.[1]);
            node('#' + m[2]).checked = /\bchecked\b/.test(m[1]);
          }
          for (const m of value.matchAll(
            /<textarea\b[^>]*\bid="([^"]+)"[^>]*>([\s\S]*?)<\/textarea>/g,
          )) {
            node('#' + m[1]).value = decode(m[2]);
            node('#' + m[1]).selectionStart = 0;
            node('#' + m[1]).selectionEnd = 0;
          }
        },
      });
      nodes.set(selector, el);
    }
    return nodes.get(selector);
  }
  document.body = node('body');
  const location = { hash: '#workspace/notifications/c1?tab=contact' };
  const window = target({
    scrollY: 0,
    scrollTo() {},
    matchMedia: () => ({ matches: false }),
    Eclipse: { destroy() {} },
  });
  const context = vm.createContext({
    console,
    URL,
    URLSearchParams,
    structuredClone,
    AbortController,
    FormData,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    document,
    window,
    location,
    history: {
      replaceState(_s, _t, url) {
        location.hash = url;
      },
    },
    localStorage: {
      getItem() {
        return null;
      },
      setItem() {
        assert.fail('Sensitive drafts must not enter browser storage');
      },
    },
    navigator: { clipboard: { writeText: async (value) => copies.push(value) } },
    confirm: (message) => {
      prompts.push(message);
      return allowDiscard;
    },
  });
  const { application: app } = await loadApplication(context, { attach: false });
  const { actions: a, state: s } = app;
  const model = (id) => ({
    case_id: id,
    ready: false,
    blockers: ['A current certified report must be available'],
    warnings: [],
    contact: { value: 'security@example.invalid', usable: true },
    report: null,
    source_explanation: 'Synthetic published contact',
    verification_route: '',
    context_hash: 'a'.repeat(64),
    context_changes: [],
    preparation_stale: false,
    preparation_editable: true,
    copy_allowed: true,
    copy_blockers: [],
    generated: { subject: id + ' subject', message: id + ' message', call_outline: id + ' call' },
    preparation: {
      revision: 0,
      subject: id + ' subject',
      message: id + ' message',
      call_outline: id + ' call',
      context_hash: 'a'.repeat(64),
    },
  });
  const models = new Map([
    ['c1', model('c1')],
    ['c2', model('c2')],
  ]);
  let deferSave = null,
    deferCopy = null,
    deferRead = null;
  a.api = async (url, options = {}) => {
    calls.push({ url, method: options.method || 'GET', body: options.body });
    const id = url.match(/\/cases\/([^/]+)/)?.[1];
    if (url === '/api/navigation-counts') return {};
    if (url === '/api/cases/' + id)
      return {
        id: 'entity-' + id,
        case_id: id,
        case: { stage: 'pending_notification', version: 1 },
        draft: {},
        entries: [],
      };
    if (url.endsWith('/outreach-handoff')) {
      if (deferRead) {
        const gate = deferRead;
        deferRead = null;
        const snapshot = structuredClone(models.get(id));
        return new Promise((resolve) => gate(() => resolve(snapshot)));
      }
      return structuredClone(models.get(id));
    }
    if (url === '/api/contact-discovery/verification-route') {
      const data = models.get(s.editor.currentLead.case_id);
      data.verification_route = options.body.value;
      data.context_hash = 'b'.repeat(64);
      data.generated.message = 'New verification: ' + options.body.value;
      data.preparation_stale = data.preparation.revision > 0;
      data.context_changes = ['Sender, entity or verification details'];
      data.copy_allowed = !data.preparation_stale;
      data.copy_blockers = data.preparation_stale ? ['Review changed context'] : [];
      return {};
    }
    if (url.endsWith('/outreach-preparation') || url.endsWith('/reset')) {
      const finish = () => {
        const data = models.get(id);
        if (options.body.expected_revision !== data.preparation.revision)
          throw Error('This outreach draft changed in another window.');
        assert.equal(options.body.expected_context, data.context_hash);
        data.preparation = {
          ...(url.endsWith('/reset') ? data.generated : options.body),
          revision: data.preparation.revision + 1,
          context_hash: data.context_hash,
        };
        data.preparation_stale = false;
        data.context_changes = [];
        data.copy_allowed = true;
        data.copy_blockers = [];
        return structuredClone(data);
      };
      if (deferSave) {
        const gate = deferSave;
        deferSave = null;
        return new Promise((resolve) => gate(() => resolve(finish())));
      }
      return finish();
    }
    if (url.endsWith('/copy')) {
      const finish = () => {
        const data = models.get(id);
        if (!data.copy_allowed) throw Error('Outreach is on hold.');
        assert.equal(options.body.expected_revision, data.preparation.revision);
        return { text: 'Subject: ' + data.preparation.subject + '\n\n' + data.preparation.message };
      };
      if (deferCopy) {
        const gate = deferCopy;
        deferCopy = null;
        return new Promise((resolve) => gate(() => resolve(finish())));
      }
      return finish();
    }
    throw Error('Unexpected API ' + url);
  };
  a.leadMarkup = () => '<div>Notification</div>';
  a.dashboard = async () => '<h1>Workspace</h1>';
  a.loadContactDiscovery = async () => {};
  a.toast = (message) => notices.push(message);
  a.updateThemeLabel = () => {};
  s.navigation.boot = { settings: { analyst_name: 'Synthetic analyst' } };
  app.attach();
  await a.route();
  const edit = async (id, value) => {
    node('#' + id).value = value;
    await document.dispatch('input', { target: node('#' + id) });
  };
  await a.showOutreachHandoff();
  assert.match(node('#modal-body').innerHTML, /Contact research only/);
  await edit('outreach-subject', 'My subject');
  await edit('outreach-message', 'Context from the phone call');
  await edit('outreach-call', 'Ask for Alex');
  assert.equal(node('#outreach-save-state').textContent, 'Unsaved changes');
  assert.equal(a.closeModal(), false);
  assert(node('#modal').open);
  const escape = {
    prevented: false,
    preventDefault() {
      this.prevented = true;
    },
  };
  await node('#modal').dispatch('cancel', escape);
  assert(escape.prevented);
  const unload = {
    prevented: false,
    preventDefault() {
      this.prevented = true;
    },
  };
  await window.dispatch('beforeunload', unload);
  assert(unload.prevented);
  assert.equal(a.modal('Another dialog', 'Other content'), false);
  assert.equal(node('#outreach-message').value, 'Context from the phone call');
  location.hash = '#workspace';
  await a.route();
  assert.equal(location.hash, '#workspace/notifications/c1?tab=contact');
  assert(s.outreachPreparation.session);
  await assert.rejects(a.copyOutreachMessage(), /Save your outreach/);
  await a.saveOutreachPreparation();
  assert(!a.hasUnsavedOutreach());
  a.closeModal();
  assert(!node('#modal').open);
  await a.showOutreachHandoff();
  assert.equal(node('#outreach-message').value, 'Context from the phone call');
  await a.copyOutreachMessage();
  assert.equal(copies[0], 'Subject: My subject\n\nContext from the phone call');

  // A save finishing after the operator keeps typing must retain newer input.
  await edit('outreach-message', 'Earlier edit');
  let finishSave;
  deferSave = (finish) => {
    finishSave = finish;
  };
  const pendingSave = a.saveOutreachPreparation();
  await edit('outreach-message', 'Newer unsaved edit');
  node('#outreach-message').focus();
  node('#outreach-message').setSelectionRange(6, 9, 'forward');
  finishSave();
  await pendingSave;
  assert.equal(models.get('c1').preparation.message, 'Earlier edit');
  assert.equal(node('#outreach-message').value, 'Newer unsaved edit');
  assert.equal(document.activeElement, node('#outreach-message'));
  assert.equal(node('#outreach-message').selectionStart, 6);
  assert.equal(node('#outreach-message').selectionEnd, 9);
  assert(a.hasUnsavedOutreach());
  await a.saveOutreachPreparation();

  // Verification refresh and source/context refresh retain custom wording.
  await edit('outreach-verification-route', 'https://office.example/verify');
  await a.saveOutreachVerification({ value: 'https://office.example/verify' });
  assert.equal(node('#outreach-message').value, 'Newer unsaved edit');
  assert.match(node('#modal-body').innerHTML, /Outreach context changed/);
  await assert.rejects(a.saveOutreachPreparation(), /Review the current/);
  node('#outreach-context-reviewed').checked = true;
  await document.dispatch('input', { target: node('#outreach-context-reviewed') });
  await a.saveOutreachPreparation();

  // Competing-window saves cannot be silently adopted as the base for our edits.
  await edit('outreach-message', 'Local competing edit');
  models.get('c1').preparation.revision++;
  models.get('c1').preparation.message = 'Other window';
  await a.refreshOutreachContext();
  assert.equal(node('#outreach-message').value, 'Local competing edit');
  await assert.rejects(a.saveOutreachPreparation(), /Reload the saved/);
  await a.reloadOutreachPreparation();
  assert.equal(node('#outreach-message').value, 'Local competing edit');
  allowDiscard = true;
  await a.reloadOutreachPreparation();
  assert.equal(node('#outreach-message').value, 'Other window');
  allowDiscard = false;

  // A hold added after the dialog opens is rechecked before touching clipboard.
  models.get('c1').copy_allowed = false;
  models.get('c1').copy_blockers = ['Outreach is on hold.'];
  const copyCount = copies.length;
  await assert.rejects(a.copyOutreachMessage(), /hold/);
  assert.equal(copies.length, copyCount);
  models.get('c1').copy_allowed = true;
  models.get('c1').copy_blockers = [];
  await a.refreshOutreachContext();
  let finishCopy;
  deferCopy = (finish) => {
    finishCopy = finish;
  };
  const pendingCopy = a.copyOutreachMessage();
  a.discardOutreachPreparation({ close: true });
  location.hash = '#workspace/notifications/c2?tab=contact';
  await a.route();
  await a.showOutreachHandoff();
  finishCopy();
  await pendingCopy;
  assert.equal(copies.length, copyCount, 'Late clipboard response must not act in another case');
  assert.equal(node('#outreach-message').value, 'c2 message');

  // Reset is explicit and remains per case; unedited generated fields follow setup.
  await edit('outreach-verification-route', 'https://new.example/verify');
  await a.saveOutreachVerification({ value: 'https://new.example/verify' });
  assert.equal(node('#outreach-message').value, 'New verification: https://new.example/verify');
  await edit('outreach-message', '</textarea><script>Literal custom text</script>');
  await a.saveOutreachPreparation();
  assert.doesNotMatch(node('#modal-body').innerHTML, /<script>/);
  allowDiscard = true;
  await a.saveOutreachPreparation(true);
  assert.equal(node('#outreach-message').value, 'New verification: https://new.example/verify');
  assert.equal(models.get('c1').preparation.message, 'Other window');

  // A slow context refresh must not roll the displayed recipient context back.
  let finishRead;
  deferRead = (finish) => {
    finishRead = finish;
  };
  const oldRefresh = a.refreshOutreachContext();
  models.get('c2').contact.value = 'new-route@example.invalid';
  models.get('c2').context_hash = 'c'.repeat(64);
  models.get('c2').preparation_stale = true;
  models.get('c2').context_changes = ['Selected contact route'];
  await a.refreshOutreachContext();
  finishRead();
  await oldRefresh;
  assert.equal(s.outreachPreparation.session.data.contact.value, 'new-route@example.invalid');

  // Opening one case late cannot replace another case's currently open draft.
  a.discardOutreachPreparation({ close: true });
  location.hash = '#workspace/notifications/c1?tab=contact';
  await a.route();
  deferRead = (finish) => {
    finishRead = finish;
  };
  const oldOpen = a.showOutreachHandoff();
  location.hash = '#workspace/notifications/c2?tab=contact';
  await a.route();
  await a.showOutreachHandoff();
  finishRead();
  await oldOpen;
  assert.equal(s.outreachPreparation.session.caseId, 'c2');
  assert.equal(node('#outreach-message').value, 'New verification: https://new.example/verify');
  models.get('c2').scope_warning = { message: 'Retained nonpublic address needs <review>.' };
  models.get('c2').copy_allowed = false;
  models.get('c2').copy_blockers = [models.get('c2').scope_warning.message];
  await a.refreshOutreachContext();
  assert.match(node('#modal-body').innerHTML, /Certified scope needs review/);
  assert.match(node('#modal-body').innerHTML, /Retained nonpublic address needs &lt;review&gt;/);
  assert.match(node('#modal-body').innerHTML, /data-action="reopen">Revise report/);
  assert.match(node('#modal-body').innerHTML, /Copying new outreach is blocked/);
  assert(node('[data-action="copy-outreach-message"]').disabled);
  assert(
    node('#modal-body').innerHTML.indexOf('Retained certified report') <
      node('#modal-body').innerHTML.indexOf('Why this contact was selected'),
  );

  // An unchanged setup field follows an external settings change without
  // becoming an accidental unsaved reversal; a real local edit still wins.
  a.discardOutreachPreparation({ close: true });
  models.set('c3', model('c3'));
  location.hash = '#workspace/notifications/c3?tab=contact';
  await a.route();
  await a.showOutreachHandoff();
  models.get('c3').verification_route = 'https://current.example/verify';
  models.get('c3').generated.message = 'Current verification wording';
  models.get('c3').context_hash = 'd'.repeat(64);
  await a.refreshOutreachContext();
  assert.equal(node('#outreach-verification-route').value, 'https://current.example/verify');
  assert.equal(node('#outreach-message').value, 'Current verification wording');
  assert(!a.hasUnsavedOutreach(), 'Untouched setup must not become an unsaved reversal');
  await edit('outreach-verification-route', 'https://operator.example/verify');
  models.get('c3').verification_route = 'https://external.example/verify';
  models.get('c3').context_hash = 'e'.repeat(64);
  await a.refreshOutreachContext();
  assert.equal(node('#outreach-verification-route').value, 'https://operator.example/verify');
  assert(a.hasUnsavedOutreach());
  await edit('outreach-verification-route', 'https://external.example/verify');
  await a.saveOutreachPreparation();

  // A read taken before a save cannot undo the successful saved revision or
  // manufacture a competing-window conflict when its response arrives late.
  deferRead = (finish) => {
    finishRead = finish;
  };
  const beforeSaveRead = a.refreshOutreachContext();
  await edit('outreach-message', 'Saved while context read was in flight');
  await a.saveOutreachPreparation();
  const savedRevision = s.outreachPreparation.session.revision;
  finishRead();
  await beforeSaveRead;
  assert.equal(s.outreachPreparation.session.data.preparation.revision, savedRevision);
  assert(!s.outreachPreparation.session.conflict);
  assert(!a.hasUnsavedOutreach());

  // A successful server copy check may arrive after the same dialog has learned
  // about a new hold. The earlier response must not reach the clipboard.
  const beforeContextCopy = copies.length;
  const originalApi = a.api;
  let finishCheckedCopy;
  a.api = async (url, options = {}) => {
    if (url.endsWith('/outreach-preparation/copy')) {
      const checked = await originalApi(url, options);
      return new Promise((resolve) => {
        finishCheckedCopy = () => resolve(checked);
      });
    }
    return originalApi(url, options);
  };
  const copyBeforeContextChange = a.copyOutreachMessage();
  await new Promise((resolve) => setTimeout(resolve, 0));
  models.get('c3').context_hash = 'f'.repeat(64);
  models.get('c3').preparation_stale = true;
  models.get('c3').context_changes = ['Outreach decision'];
  models.get('c3').copy_allowed = false;
  models.get('c3').copy_blockers = ['Outreach is on hold.'];
  await a.refreshOutreachContext();
  assert(s.outreachPreparation.session.contextChanged);
  finishCheckedCopy();
  await copyBeforeContextChange;
  assert.equal(copies.length, beforeContextCopy);
  a.api = originalApi;

  // A save that committed before a newer context read must update its saved
  // revision without erasing the newer warning when its response arrives late.
  a.discardOutreachPreparation({ close: true });
  models.set('c4', model('c4'));
  location.hash = '#workspace/notifications/c4?tab=contact';
  await a.route();
  await a.showOutreachHandoff();
  await edit('outreach-message', 'Wording saved before the recipient context changed');
  let finishCommittedSave;
  a.api = async (url, options = {}) => {
    if (url.endsWith('/outreach-preparation') && options.method === 'PUT') {
      const committed = await originalApi(url, options);
      return new Promise((resolve) => {
        finishCommittedSave = () => resolve(committed);
      });
    }
    return originalApi(url, options);
  };
  const saveBeforeContextChange = a.saveOutreachPreparation();
  await new Promise((resolve) => setTimeout(resolve, 0));
  models.get('c4').context_hash = 'f'.repeat(64);
  models.get('c4').preparation_stale = true;
  models.get('c4').context_changes = ['Selected contact route'];
  models.get('c4').copy_allowed = false;
  models.get('c4').copy_blockers = ['Review changed context'];
  await a.refreshOutreachContext();
  let finishReconciliation;
  deferRead = (finish) => {
    finishReconciliation = finish;
  };
  finishCommittedSave();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(s.outreachPreparation.session.data.context_hash, 'f'.repeat(64));
  assert(node('[data-action="copy-outreach-message"]').disabled);
  finishReconciliation();
  await saveBeforeContextChange;
  assert.equal(s.outreachPreparation.session.data.context_hash, 'f'.repeat(64));
  assert.equal(s.outreachPreparation.session.revision, models.get('c4').preparation.revision);
  assert(s.outreachPreparation.session.contextChanged);
  assert(!s.outreachPreparation.session.conflict, 'The same committed revision is not a conflict');
  assert(!s.outreachPreparation.session.reviewed, 'A context refresh cannot approve changed facts');
  assert.equal(
    node('#outreach-message').value,
    'Wording saved before the recipient context changed',
  );
  assert(!a.hasUnsavedOutreach());
  a.api = originalApi;
  app.destroy();
  console.log(
    'Saved outreach: close/Escape/unload/navigation guards, reload, async edits, context/verification refresh, stale saves, held copy, reset and cross-case isolation passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
