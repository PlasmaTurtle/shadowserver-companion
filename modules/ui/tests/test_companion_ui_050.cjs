(async () => {
  /* Behavioral UI checks for the four-stage workspace and frozen section workflow. */
  const fs = require('fs'),
    path = require('path'),
    vm = require('vm'),
    assert = require('node:assert/strict');
  const nodes = new Map(),
    listeners = {},
    storage = new Map();
  const node = (s) => {
    if (!nodes.has(s))
      nodes.set(s, {
        innerHTML: '',
        textContent: '',
        disabled: false,
        open: false,
        dataset: {},
        classList: { toggle() {}, add() {}, remove() {} },
        setAttribute(k, v) {
          this[k] = v;
        },
        focus() {
          this.focused = true;
        },
        showModal() {
          this.open = true;
        },
        close() {
          this.open = false;
        },
      });
    return nodes.get(s);
  };
  const document = {
    documentElement: { dataset: { theme: 'light' } },
    querySelector: node,
    querySelectorAll: () => [],
    addEventListener: (type, fn) => (listeners[type] = fn),
  };
  const context = vm.createContext({
    document,
    window: { addEventListener() {} },
    console,
    URLSearchParams,
    FormData,
    Date,
    Number,
    String,
    Intl,
    structuredClone,
    setTimeout,
    clearTimeout,
    location: { hash: '' },
    confirm: () => true,
    localStorage: { setItem: (k, v) => storage.set(k, v), getItem: (k) => storage.get(k) },
  });
  await require('../../../tests/frontend_harness.cjs').loadApplication(context, { theme: false });
  const run = (code) => vm.runInContext(code, context);
  run(
    `boot={settings:{agency:'Agency',office:'Office',analyst_name:'Configured Analyst'},explainers:[]};currentLead={id:'entity1',case_id:'case1',domain:'example.com',company:'Example',case:{stage:'in_progress',version:4},draft_revision:9,status:'in_progress',entries:[],evidence:[],reports:[],history:[],hostnames:[],domain_groups:[],narrative_groups:[],approved_copy:{attribution:'Approved attribution'},section_reviews:['Introduction','Vulnerabilities','Attribution','Information','Closing'].map(name=>({key:name.toLowerCase(),label:name,status:'draft',revision:0,can_validate:true,issues:[]})),section_history:[]};draft={company:'Example',contact_name:'Principle Executive / IT Director',sender_name:'Configured Sender',sender_title:'Special Agent',report_date:'2026-11-07',severity:'Critical',subject:'Approved subject',intro:'Current introduction',narrative:'Approved narrative',selected_explainers:[],cve_records:[],cve_dispositions:{}};currentLead.draft=structuredClone(draft);`,
  );
  assert.equal(run('caseStages.length'), 5);
  assert.deepEqual(JSON.parse(run('JSON.stringify(caseStages.map(x=>x[1]))')), [
    'Scan Validation',
    'Work in Progress',
    'Completed & Pending Notification',
    'Notification Completed',
    'Closing Report Completed',
  ]);
  let html = run('stageCards({closed:7})');
  assert.equal((html.match(/class="metric"/g) || []).length, 5);
  assert.match(html, /Completed archive/);
  assert.match(html, /#workspace\/notifications\?stage=closed/);
  run("currentLead.case.stage='closed';currentLead.case.delivered_at=null");
  html = run('caseProgress()');
  assert.equal((html.match(/<li /g) || []).length, 5);
  assert.match(html, /Delivery not recorded/);
  assert.match(html, /aria-current="step"/);
  run("currentLead.case.stage='in_progress'");
  // Frozen content is rendered from its recorded snapshot without replacing the editable draft.
  run(
    `currentLead.section_reviews[0]={key:'introduction',label:'Introduction',status:'stale',revision:2,validated_by:'Analyst <One>',validated_at:'2026-11-06T19:32:09Z',can_validate:false,issues:[],changed:true,frozen_fields:{intro:'Frozen original introduction',report_date:'2026-11-06'}};`,
  );
  html = run('reportBuilderMarkup()');
  assert.match(html, /Frozen original introduction/);
  assert.doesNotMatch(html, /Current introduction/);
  assert.match(html, /Related information changed after validation/);
  assert.match(html, /Analyst &lt;One&gt;/);
  assert.match(html, /datetime="2026-11-06T19:32:09Z"/);
  assert.match(html, /name="report_date" data-draft disabled/);
  assert.match(html, /data-action="reopen-section"/);
  assert.equal(run('draft.intro'), 'Current introduction');
  assert.equal(run('draft.report_date'), '2026-11-07');
  assert.equal((html.match(/data-report-section=/g) || []).length, 5);
  assert.match(run("stamp('2026-11-06T19:32:09Z')"), /UTC|GMT|[A-Z]{2,5}/);
  assert.equal(run('stamp(null)'), 'Not recorded');
  // Registered evidence is separate from validation. Missing validation dates stay missing.
  run(
    `currentLead.attribution_summaries=[{supported:true,root_domain:'example.com',reported_ip:'192.0.2.10',validated_ip:'192.0.2.10',source_name:'ARIN / RDAP',source_url:'https://rdap.arin.net/registry/ip/192.0.2.10',method:'registration',match_summary:'example.com matches a registration contact domain.',validation_kind:'automatic',validated_at:'2026-11-06T19:32:09Z',validated_by:'Attribution Module',retrieved_at:'2026-11-06T19:31:00Z',from_cache:true,supporting_ip_count:1,reported_ip_count:70,details:{matched_value:'contact@example.com',raw_record:{remark:'<script>alert(1)</script>'}}}];`,
  );
  html = run('attributionMarkup()');
  assert.match(html, /Reported IP/);
  assert.match(html, /Validated IP/);
  assert.match(html, /ARIN \/ RDAP/);
  assert.match(html, /1 IP used for attribution · 70 reported IPs included/);
  assert.match(html, /Automatically validated/);
  assert.match(html, /Attribution Module/);
  assert.match(html, /Source retrieved/);
  assert.match(html, /View supporting details/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
  run(
    `currentLead.attribution_summaries[0].validated_at=null;currentLead.attribution_summaries[0].validated_by=null;currentLead.attribution_summaries[0].validation_kind='unknown';currentLead.attribution_summaries[0].source_url='dns://example.com';`,
  );
  html = run('attributionMarkup()');
  assert.match(html, /Not recorded/);
  assert.match(html, /Author not recorded/);
  assert.equal((html.match(/datetime="2026-11-06T19:31:00Z"/g) || []).length, 1);
  assert.doesNotMatch(html, /href="dns:/);
  assert.match(html, /dns:\/\/example.com/);
  run('currentLead.attribution_summaries[0].supported=false');
  html = run('attributionMarkup()');
  assert.match(html, /Support needs review/);
  assert.match(html, /Not established/);
  assert.doesNotMatch(html, /badge green/);
  // Chronology is escaped and keeps the required reason, author, revision, and absolute time.
  run(
    `currentLead.section_history=[{section_key:'introduction',action:'reopened',actor:'Analyst One',created_at:'2026-11-07T14:00:00Z',reason:'Correct <address>',revision:2},{section_key:'attribution',action:'validated',actor:'Analyst Two',created_at:'2026-11-07T12:00:00Z',revision:1}];`,
  );
  html = run("workChronology('introduction')");
  assert.match(html, /Correct &lt;address&gt;/);
  assert.match(html, /Analyst One/);
  assert.doesNotMatch(html, /Analyst Two/);
  assert.match(html, /revision 2/);
  html = run("reopenFormMarkup('section-reopen-form','introduction')");
  assert.match(html, /name="reason"[^>]*required/);
  assert.match(html, /data-case="case1"/);
  run(`currentLead.readiness=[{ok:true,label:'Ready'}];currentLead.entries=[];`);
  html = run('caseSidebar()');
  assert.match(html, /data-action="finalize" disabled/);
  run(`currentLead.section_reviews.forEach(s=>s.status='validated');`);
  html = run('caseSidebar()');
  assert.match(html, /data-action="finalize" >/);
  run(`currentLead.readiness[0].ok=false;`);
  html = run('caseSidebar()');
  assert.match(html, /data-action="finalize" disabled/);
  // Theme switching persists and updates its accessible action label.
  run('toggleTheme()');
  assert.equal(document.documentElement.dataset.theme, 'dark');
  assert.equal(storage.get('companion-theme'), 'dark');
  assert.equal(node('#theme-toggle')['aria-label'], 'Switch to light workspace');
  run('toggleTheme()');
  assert.equal(storage.get('companion-theme'), 'light');
  assert.equal(
    run(`ignoredEmptyRows({config:JSON.stringify({intake_stats:{ignored_empty_rows:1}})})`),
    1,
  );
  html = run(
    `importRow({id:'i',name:'Workbook',status:'done',rows_read:13,valid_rows:13,qualified:9,ignored_empty_rows:1})`,
  );
  assert.match(html, /13 observations/);
  assert.match(html, /1 empty rows ignored/);
  (async () => {
    // Save first, then validate using the newly returned revision. These are server actions, not cosmetic toggles.
    run(
      `globalThis.calls=[];globalThis.applied=null;dirty=true;currentLead.section_reviews[0].status='draft';saveDraft=async()=>{calls.push({save:true});currentLead.draft_revision=10;dirty=false;};api=async(url,opts)=>{calls.push({url,body:opts.body});return {draft:{},section_reviews:[]};};applyLeadUpdate=value=>{applied=value;};toast=()=>{};`,
    );
    await run("validateSection('introduction')");
    const calls = JSON.parse(run('JSON.stringify(calls)'));
    assert.equal(calls.length, 2);
    assert.equal(calls[1].url, '/api/cases/case1/sections/introduction/validate');
    assert.equal(calls[1].body.expected_revision, 10);
    assert(run('applied!==null'));
    await assert.rejects(
      run(
        "submitReopen({id:'section-reopen-form',dataset:{case:'case1',section:'introduction'}},{reason:'   '})",
      ),
      /Enter a reason/,
    );
    await assert.rejects(
      run(
        "submitReopen({id:'section-reopen-form',dataset:{case:'different',section:'introduction'}},{reason:'New source'})",
      ),
      /notification changed/,
    );
    run('calls=[]');
    await run(
      "submitReopen({id:'section-reopen-form',dataset:{case:'case1',section:'introduction'}},{reason:'  Address corrected  '})",
    );
    let request = JSON.parse(run('JSON.stringify(calls[0])'));
    assert.equal(request.url, '/api/cases/case1/sections/introduction/reopen');
    assert.deepEqual(request.body, { reason: 'Address corrected', expected_revision: 10 });
    run('calls=[]');
    await run(
      "submitReopen({id:'report-revise-form',dataset:{case:'case1'}},{reason:'Additional reported assets'})",
    );
    request = JSON.parse(run('JSON.stringify(calls[0])'));
    assert.equal(request.url, '/api/cases/case1/revise');
    assert.deepEqual(request.body, { reason: 'Additional reported assets', expected_version: 4 });
    // Exercise the actual delegated submit route; reason forms must never fall through to contact-plan handling.
    context.FormData = class extends Map {
      constructor(form) {
        super(form.fields || []);
      }
    };
    run('calls=[];busy=async(button,fn)=>fn();');
    await listeners.submit({
      target: {
        id: 'section-reopen-form',
        dataset: { case: 'case1', section: 'introduction' },
        fields: [['reason', 'Submitted through the UI']],
      },
      submitter: {},
      preventDefault() {},
    });
    request = JSON.parse(run('JSON.stringify(calls[0])'));
    assert.equal(request.url, '/api/cases/case1/sections/introduction/reopen');
    assert.equal(request.body.reason, 'Submitted through the UI');
    console.log(
      'Five-stage workflow, frozen snapshots, section authority, reopen reasons, attribution provenance, chronology, certification gate, theme, and import counts passed.',
    );
  })().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
