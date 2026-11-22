(async () => {
  // Report editor: independent source text, explicit adoption and case-specific prose.
  const fs = require('fs'),
    path = require('path'),
    vm = require('vm'),
    assert = require('assert/strict');
  const nodes = new Map(),
    listeners = {};
  const node = (s) => {
    if (!nodes.has(s))
      nodes.set(s, {
        innerHTML: '',
        textContent: '',
        checked: false,
        classList: { toggle() {}, add() {}, remove() {} },
      });
    return nodes.get(s);
  };
  const context = vm.createContext({
    document: {
      querySelector: node,
      querySelectorAll: () => [],
      addEventListener: (t, fn) => (listeners[t] = fn),
    },
    window: { addEventListener() {} },
    console,
    URLSearchParams,
    FormData,
    Date,
    Number,
    String,
    structuredClone,
    setTimeout,
    clearTimeout,
    location: { hash: '' },
    confirm: () => true,
  });
  await require('../../../tests/frontend_harness.cjs').loadApplication(context, { theme: false });
  const run = (s) => vm.runInContext(s, context);
  run(`boot={explainers:[{id:'general',title:'General',body:'New bank wording',revision:2}],settings:{}};
currentLead={id:'entity',case_id:'case',status:'in_progress',case:{stage:'in_progress'},entries:[{source:{fields:{tag:'CVE-2025-12345'}}}],domain_groups:[{root_domain:'one.example',attribution:{ip:'192.0.2.1'}},{root_domain:'two.example',attribution:{ip:'192.0.2.2'}}]};
draft={selected_explainers:['general'],explainer_snapshots:[{id:'general',title:'General',body:'Pinned wording',revision:1}],explainer_overrides:{},cve_dispositions:{},report_template:{id:'standard',version:1,marking:'Information <script>',font_size:9.5},reviewed:true,cve_records:[{id:'CVE-2025-12345',verification_status:'published',description:'Official <img src=x> description.',cvss_assessments:[{score:9.8,version:'3.1',source:'NVD'},{score:8.1,version:'3.1',source:'Vendor'}],epss:.15,epss_percentile:.92,epss_date:'2026-11-06'}]};`);
  let html = run('cveMarkup()');
  assert(
    html.includes('9.8') && html.includes('8.1') && html.includes('NVD') && html.includes('Vendor'),
  );
  assert(html.includes('15.00% probability') && html.includes('92.00 percentile'));
  assert(html.includes('Known exploitation') && html.includes('Assessment unavailable'));
  assert(html.includes('&lt;img src=x&gt;') && !html.includes('<img src=x>'));
  assert(html.includes('Recipient IT personnel determine applicability'));
  assert(!html.includes('textarea')); // Published descriptions cannot be rewritten in place.
  run(`draft.cve_records[0].sources=[{publisher:'FIRST EPSS',public_url:'https://www.first.org/epss/',retrieved_at:'2026-11-06T12:00:00Z',record_path:'saved.json',sha256:'abc'}];
draft.cve_records[0].acquisition=[{publisher:'FIRST EPSS',completed_at:'2026-11-07T12:00:00Z',outcome:'rate_limited'}];`);
  html = run('cveMarkup()');
  assert(html.includes('Preserved response') && html.includes('Score date 2026-11-06'));
  assert(html.includes('Latest attempt: rate limited') && html.includes('FIRST EPSS'));
  assert.equal(run('draft.cve_records[0].sources[0].retrieved_at'), '2026-11-06T12:00:00Z');
  html = run('explainersMarkup(false)');
  assert(html.includes('Pinned wording') && !html.includes('New bank wording'));
  html = run('templateMarkup(false)');
  assert(html.includes('Information &lt;script&gt;'));
  run(
    `currentLead.attribution_summaries=currentLead.domain_groups.map(g=>({root_domain:g.root_domain,reported_ip:g.attribution.ip,validated_ip:g.attribution.ip,source_name:'ARIN',source_url:'https://rdap.arin.net/registry/ip/'+g.attribution.ip,method:'rdap',match_summary:'Domain in registration',validated_at:null,validated_by:'Attribution Module',validation_kind:'automatic',retrieved_at:'2026-11-06T12:00:00Z',from_cache:false,supporting_ip_count:1,reported_ip_count:1,details:{}}));`,
  );
  html = run('attributionMarkup()');
  assert(
    html.includes('one.example') && html.includes('two.example') && html.includes('192.0.2.2'),
  );
  run(
    "draft.cve_dispositions={'CVE-2025-12345':{action:'fallback',reason:'Source outage',description:'Captured text',evidence_text:'Captured text'}}",
  );
  html = run('cveMarkup()');
  assert(html.includes('Captured text') && html.includes('no screenshot is required'));
  const field = {
    closest: () => null,
    matches: () => false,
    dataset: { cveField: 'description', cveId: 'CVE-2025-12345' },
    value: 'New official text',
  };
  listeners.input({ target: field });
  assert.equal(run("draft.cve_dispositions['CVE-2025-12345'].evidence_text"), 'New official text');
  assert.equal(run('draft.reviewed'), false);
  assert.equal(node('[data-draft][name="reviewed"]').checked, false);
  run("currentLead.case.stage='pending_notification'");
  html = run('cveMarkup()');
  assert(html.includes('disabled'));
  console.log(
    'Report source display, escaping, pinned blocks, fallback capture, all-group attribution and review reset passed.',
  );
  html = run(
    `resourceCitationFields('https://example.com/advisory',[{url:'https://example.com/advisory',publisher:'Publisher <script>',title:'Advisory',retrieved_at:'2026-11-06',date_published:'2026-01-01'}])`,
  );
  assert(html.includes('Publisher &lt;script&gt;') && !html.includes('Publisher <script>'));
  assert(html.includes('2026-11-06') && html.includes('data-citation-key="retrieved_at"'));
  assert(html.includes('Published date') && html.includes('Updated date'));
  console.log('Per-source publisher, title and date fields render safely.');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
