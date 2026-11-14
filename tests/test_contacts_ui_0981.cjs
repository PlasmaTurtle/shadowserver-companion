/** Saved contact source previews, copied values, and preserved operator fields. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('./frontend_harness.cjs');
(async () => {
  const nodes = new Map(),
    copies = [];
  const node = (id) => {
    if (!nodes.has(id)) nodes.set(id, { innerHTML: '', outerHTML: '', value: '' });
    return nodes.get(id);
  };
  const context = vm.createContext({
    console,
    URL,
    URLSearchParams,
    structuredClone,
    setTimeout,
    clearTimeout,
    clearInterval,
    document: { querySelector: node, querySelectorAll: () => [] },
    window: { Eclipse: { destroy() {} } },
    navigator: { clipboard: { writeText: async (value) => copies.push(value) } },
  });
  const { application: app } = await loadApplication(context, { attach: false });
  const { state: s, actions: a } = app;
  a.toast = () => {};
  a.api = async () => {
    throw new Error('Rendering/copy/autocomplete must not request data');
  };
  s.navigation.currentRoute = 'entity/business';
  s.entities.current = { id: 'business' };
  s.editor.currentLead = null;
  const candidate = {
    id: 'email',
    kind: 'email',
    value: 'security@example.org',
    purpose: 'security',
    known: true,
    decision: 'pending',
    missing_from_latest: false,
    last_successful_use: '2026-11-01T12:00:00Z',
    sources: [
      { url: 'https://example.org/contact', purpose: 'general', excerpt: 'General contacts' },
      {
        url: 'https://example.org/security',
        purpose: 'security',
        excerpt: '<script>Published security contact</script>',
        truncated: true,
      },
    ],
  };
  s.contacts.entities.set('business', { contacts: [candidate], roots: [] });
  const markup = a.contactDiscoveryMarkup(s.entities.current);
  assert.match(markup, /Source · example.org/);
  assert.match(markup, /Known contact/);
  assert.match(markup, /Delivery recorded/);
  assert.match(markup, /In latest search/);
  assert.match(markup, /class="contact-finder"/);
  assert.doesNotMatch(markup, /class="panel"|contact-badges/);
  assert.equal((markup.match(/data-primary-route="true"/g) || []).length, 1);
  assert.match(markup, /data-contact-detail="source-email"/);
  assert.doesNotMatch(markup, /data-contact-detail="source-email" open|<script>/);
  const preview = markup.split('data-contact-detail="source-email"')[1].split('</details>')[0];
  assert.match(preview, /example.org\/security/);
  assert.match(preview, /&lt;script&gt;Published security contact&lt;\/script&gt;/);
  assert.match(preview, /Partial capture/);
  assert.doesNotMatch(preview, /General contacts/);
  assert.doesNotMatch(markup, /Verify|Adopt|Next step/);
  await a.copyContactValue('email');
  assert.deepEqual(copies, ['security@example.org']);
  const fields = { contact_email: { value: 'typed@example.org' }, contact_name: { value: '' } };
  const disclosure = { open: false };
  let focused = false;
  fields.contact_name.focus = () => {
    focused = true;
  };
  node('#entity-contact-form').elements = { namedItem: (name) => fields[name] };
  node('#entity-contact-form').closest = () => disclosure;
  candidate.name = 'Published Name';
  await a.useContactCandidate('email');
  assert.equal(fields.contact_email.value, 'typed@example.org');
  assert.equal(fields.contact_name.value, 'Published Name');
  assert(disclosure.open && focused, 'Filled fields are revealed in their editor');
  disclosure.open = false;
  await a.useContactCandidate('email');
  assert.equal(disclosure.open, false, 'No-op selection does not open a closed editor');
  candidate.decision = 'ignored';
  fields.contact_name.value = '';
  await a.useContactCandidate('email');
  assert.equal(fields.contact_name.value, '');
  assert.doesNotMatch(a.contactDiscoveryMarkup(), /data-contact-use="email"/);
  candidate.sources[0].url = 'javascript:alert(1)';
  candidate.sources[1].url = 'javascript:alert(1)';
  assert.doesNotMatch(a.contactDiscoveryMarkup(), /href="javascript:|class="contact-proof"/);
  const current = { ...candidate, id: 'current', decision: 'pending', name: '', unusable: false };
  const old = { ...current, id: 'old', value: 'previous@example.org', missing_from_latest: true };
  const failed = {
    ...current,
    id: 'failed',
    value: 'bounced@example.org',
    unusable: true,
    preferred: true,
    usability_reason: 'Bounced',
  };
  const referral = { ...current, id: 'referral', value: 'help@example.org', purpose: 'it' };
  s.contacts.entities.set('business', { contacts: [old, failed, referral, current], roots: [] });
  let findings = a.contactDiscoveryMarkup();
  const main = findings.split('data-contact-detail="details"')[0];
  assert.match(main, /data-contact-id="current" data-primary-route="true"/);
  assert.equal((findings.match(/data-primary-route="true"/g) || []).length, 1);
  assert.doesNotMatch(main, /previous@example.org|bounced@example.org/);
  assert.match(findings, /Unavailable · Bounced/);
  assert.match(findings, /Previously found · not in the latest search/);
  assert.match(findings, /data-contact-detail="history-old"/);
  assert.doesNotMatch(
    findings,
    /data-contact-use="failed"|Verified recipient|Recommended recipient/,
  );
  s.contacts.entities.set('business', { contacts: [old, failed], roots: [] });
  findings = a.contactDiscoveryMarkup();
  assert.doesNotMatch(findings, /data-primary-route="true"/);
  app.destroy();
  console.log(
    '0.9.81 contact source preview, copy, hidden-route preservation and blank-only autocomplete passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
