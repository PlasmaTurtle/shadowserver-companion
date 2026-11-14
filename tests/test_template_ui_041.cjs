(async () => {
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
  await require('./frontend_harness.cjs').loadApplication(context, { theme: false });
  const run = (s) => vm.runInContext(s, context);
  run(
    `boot={settings:{agency:'Agency',office:'Office'},explainers:[]};currentLead={case_id:'c',id:'e',case:{stage:'in_progress'},status:'in_progress',entries:[],evidence:[],domain_groups:[{root_domain:'example.com',attribution:{}}],entity_profile:{contact_name:'Actual Person',contact_email:'actual@example.com'},narrative_groups:[{key:'test',hostname:'example.com',software:'php',version:'7.3.25',protocol:'tcp',port:443}],approved_copy:{attribution:'Approved attribution',security_intro:'Approved practices',fraud_intro:'Approved fraud paragraph',fraud_risks:['BEC'],fraud_stats_intro:'Approved statistics',fraud_stats:['Template statistic'],responsibility:'Approved responsibility'}};draft={company:'Example',contact_name:'Principle Executive / IT Director',sender_name:'Configured Sender',sender_title:'Special Agent',subject:'Fixed subject',intro:'Exact introduction',narrative:'Generated narrative <script>',report_date:'2026-11-06',severity:'Critical',recommendations:'Step one',limitations:'Exact partnership',resources:'https://example.com',closing:'Exact closing',selected_explainers:[],cve_records:[]};`,
  );
  let html = run('reportBuilderMarkup()');
  for (const section of [
    'Introduction',
    'Vulnerabilities',
    'Attribution',
    'Information',
    'Closing',
  ])
    assert(html.includes(`data-report-section="${section}"`));
  assert(html.includes('Principle Executive / IT Director') && html.includes('Configured Sender'));
  for (const field of [
    'contact_name',
    'contact_title',
    'contact_email',
    'sender_name',
    'sender_title',
    'intro',
    'narrative',
  ])
    assert(!html.includes(`name="${field}"`));
  run("reportSection='Vulnerabilities'");
  html = run('reportBuilderMarkup()');
  assert(html.includes('Generated narrative &lt;script&gt;'));
  assert(!html.includes('name="narrative"'));
  assert(html.includes('data-finding-field="affected_versions"'));
  run("reportSection='Information'");
  html = run('reportBuilderMarkup()');
  assert(html.includes('Approved practices') && html.includes('Exact partnership'));
  assert(!html.includes('name="recommendations"'));
  html = run('entityProfileMarkup()');
  assert(html.includes('Actual Person') && html.includes('actual@example.com'));
  for (const field of [
    'contact_name',
    'contact_title',
    'contact_email',
    'address',
    'city',
    'state',
  ])
    assert(html.includes(`name="${field}"`));
  assert(!html.includes('data-draft'));
  run("reportSection='Closing'");
  html = run('reportBuilderMarkup()');
  assert(html.includes('Approved responsibility') && html.includes('Exact closing'));
  assert(!html.includes('name="reviewed"'));
  assert(html.includes('data-action="validate-section"'));
  assert(html.includes('data-section="closing"'));
  run("currentLead.case.stage='pending_notification'");
  html = run('reportBuilderMarkup()');
  assert(html.includes('Open certified report'));
  assert(!html.includes('Approved responsibility'));
  assert(!html.includes('data-draft'));
  console.log(
    'Five sections, read-only approved wording, Settings sender, fixed addressee, scoped insertables, entity-only contact fields and escaping passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
