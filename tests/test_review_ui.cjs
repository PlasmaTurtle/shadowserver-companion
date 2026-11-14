(async () => {
  // Run with node tests/test_review_ui.cjs. Tests rendering/data handling without a browser.
  const fs = require('fs'),
    vm = require('vm'),
    assert = require('assert/strict');
  const path = require('path');
  const nodes = new Map(),
    listeners = {};
  const node = (s) => {
    if (!nodes.has(s))
      nodes.set(s, {
        innerHTML: '',
        textContent: '',
        open: false,
        showModal() {
          this.open = true;
        },
        close() {
          this.open = false;
        },
        classList: { toggle() {} },
      });
    return nodes.get(s);
  };
  const context = vm.createContext({
    document: {
      querySelector: node,
      querySelectorAll: () => [],
      addEventListener: (type, fn) => {
        listeners[type] = fn;
      },
    },
    window: { addEventListener() {} },
    console,
    URLSearchParams,
    FormData,
    Date,
    Number,
    String,
    setTimeout,
    clearTimeout,
  });
  await require('./frontend_harness.cjs').loadApplication(context, { theme: false });
  const match = {
    method: 'rdap_keyword',
    ip: '8.8.8.8',
    source_name: 'Fixture registry',
    source_url: 'https://rdap.arin.net/registry/ip/8.8.8.8',
    retrieved_at: '2026-11-06T12:00:00Z',
    snapshot_id: 'fixture',
    match: {
      value: 'Example Medical Center <img src=x onerror=alert(1)>',
      field_type: 'organization_name',
      field_path: '/entities/0/vcardArray/1/0/3',
    },
    details: {
      matched_words: ['example'],
      domain_label: 'example',
      network_start: '8.8.8.0',
      network_end: '8.8.8.255',
    },
  };
  const result = { result_id: 'a'.repeat(32), partial_evidence: [match] };
  const group = {
    id: 'g1',
    domain: 'example.com',
    status: 'review',
    entries: [{ ip: '8.8.8.8' }],
    attempts: [],
    reviews: [],
    can_retry: true,
    attribution_result: result,
    partial_records: { fixture: { name: match.match.value } },
  };
  context.reviewFixture = group;
  vm.runInContext(
    `api=async url=>url==='/api/reviews'?[{id:'g1',domain:'example.com',observations:1,assets:1,import_name:'fixture.csv',matches:reviewFixture.attribution_result.partial_evidence}]:reviewFixture`,
    context,
  );
  (async () => {
    const html = await vm.runInContext('reviewsPage()', context);
    assert(html.includes('<mark>Example</mark>'));
    assert(html.includes('&lt;img'));
    assert(!html.includes('<img src=x'));
    await vm.runInContext("showGroup('g1')", context);
    const body = node('#modal-body').innerHTML;
    assert(body.includes('data-result="' + result.result_id + '"'));
    assert(body.includes('value="accept"') && body.includes('value="dismiss"'));
    assert(body.includes('Inspect saved registration response') && body.includes('Retry lookups'));
    assert(body.includes('id="match-0" value="0" checked'));
    assert(!body.includes('<img src=x'));
    assert.equal(node('#review-count').textContent, 1);
    console.log(
      'Review queue/detail rendering, escaping, action bindings, evidence selection and count checks passed.',
    );
  })().catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
