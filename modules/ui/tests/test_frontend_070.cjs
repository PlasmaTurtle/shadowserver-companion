(async () => {
  /* v0.7 behavioral contracts: signals, safe adoption, presentation, and field coverage. */
  const fs = require('node:fs'),
    path = require('node:path'),
    vm = require('node:vm'),
    assert = require('node:assert/strict');
  const nodes = new Map(),
    listeners = {},
    storage = new Map([['companion-theme', 'dark']]);
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
        focus() {},
        showModal() {
          this.open = true;
        },
        close() {
          this.open = false;
        },
      });
    return nodes.get(s);
  };
  const doc = {
    documentElement: { dataset: {} },
    querySelector: node,
    querySelectorAll: () => [],
    addEventListener: (type, fn) => (listeners[type] = fn),
  };
  const win = {
    addEventListener() {},
    dispatchEvent() {},
    matchMedia: () => ({ matches: true, addEventListener() {} }),
  };
  const context = vm.createContext({
    document: doc,
    window: win,
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
    Event: class {},
    location: { hash: '' },
    confirm: () => true,
    localStorage: { setItem: (k, v) => storage.set(k, v), getItem: (k) => storage.get(k) },
  });
  await require('../../../tests/frontend_harness.cjs').loadApplication(context, { theme: true });
  const run = (code) => vm.runInContext(code, context);
  assert.equal(
    doc.documentElement.dataset.theme,
    'dark',
    'Existing browser preference survives first paint',
  );
  run(
    "boot={settings:{brand_profile:'usss',appearance:'system',display_timezone:'America/New_York'}};applyPresentation(boot.settings)",
  );
  assert.equal(doc.documentElement.dataset.brand, 'usss');
  assert.equal(doc.documentElement.dataset.appearance, 'system');
  assert.equal(doc.documentElement.dataset.theme, 'dark');
  run(
    `currentLead={id:'e',case_id:'c',draft_revision:2,case:{stage:'in_progress'},entries:[{source:{fields:{tag:'CVE-2026-10000 CVE-2026-10001'}}}],section_reviews:[],report_model:{appendix:{index:[{id:'A',entry_ids:['A-1','A-2']}]}}};draft={cve_records:[],selected_ssvc_assessments:{'CVE-2026-10000':'older'},cve_dispositions:{}};`,
  );
  let html = run(
    `intelligenceMarkup({id:'CVE-2026-10000',kev:true,epss:0,epss_percentile:0,epss_date:'2026-11-06',ransomware:{status:'unknown',label:'Ransomware use unconfirmed by CISA'},selected_ssvc_assessment_id:'latest',ssvc_assessments:[{id:'older',publisher:'CISA',exploitation:'none',label:'No exploitation evidence reported in this assessment',assessed_at:'2026-10-01T10:00:00Z'},{id:'latest',publisher:'CISA',exploitation:'active',label:'Active exploitation reported',assessed_at:'2026-11-01T10:00:00Z'}],impacts:[{label:'Information disclosure',source_text:'Only when <script> configured.',basis:'explicit_structured_data',conditions:'Authenticated users'}]},true)`,
  );
  assert.match(html, /0.00% probability/);
  assert.match(html, /0.00 percentile/);
  assert.match(html, /Known exploited/);
  assert.match(html, /Ransomware use unconfirmed/);
  assert.match(html, /No exploitation evidence reported/);
  assert.match(html, /data-ssvc-id="CVE-2026-10000" disabled/);
  assert.match(html, /value="older" selected/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
  html = run("intelligenceMarkup({id:'CVE-2026-10001'},false)");
  assert.match(html, /Assessment unavailable/);
  assert.match(html, /No selected assessment/);
  assert.doesNotMatch(html, /No exploitation evidence reported/);
  assert.doesNotMatch(html, /Known ransomware use/);
  run(
    `draft.cve_records=[{id:'CVE-2026-10000',verification_status:'rejected'},{id:'CVE-2026-10001',verification_status:'published',kev:true}];`,
  );
  html = run('cveMarkup()');
  assert.match(html, /<option value="fallback"\s+disabled>/);
  assert.match(html, /Load local CVEs/);
  assert.match(html, /Missing records stay visible/);
  assert.doesNotMatch(html, /Missing records are retrieved from their publishers/);
  assert.doesNotMatch(html, /Retrieve and adopt latest/);
  run("cveSignalFilter='kev'");
  html = run('cveMarkup()');
  assert.match(html, /1 of 2 CVEs/);
  assert.doesNotMatch(html, /disposition-CVE-2026-10000/);
  html = run('appendixOverview()');
  assert.match(html, /2 indexed entries/);
  assert.match(html, /follow the closing page/);
  assert.match(html, /Reviewed with Vulnerabilities/);
  assert.match(html, /name="include_appendix" checked/);
  run('draft.include_appendix=false');
  html = run('appendixOverview()');
  assert.doesNotMatch(html, /name="include_appendix" checked/);
  assert.match(html, /The full supporting appendix is available upon request/);
  run(
    'globalThis.savedReviews=currentLead.section_reviews;currentLead.section_reviews=[{key:"closing",status:"validated"}]',
  );
  // Appendix inclusion is output-only and remains editable through section freezes.
  assert.doesNotMatch(run('appendixOverview()'), /name="include_appendix"\s+disabled/);
  run("currentLead.case.stage='pending_notification'");
  assert.match(run('appendixOverview()'), /name="include_appendix"\s+disabled/);
  run("currentLead.case.stage='in_progress'");
  run('currentLead.section_reviews=savedReviews;draft.include_appendix=true');
  html = run(
    `attributionCard({supported:true,reported_ip:'192.0.2.10',root_domain:'example.com',method:'registration',details:{network_start:'192.0.2.0',network_end:'192.0.2.255'},supporting_ip_count:1,reported_ip_count:70})`,
  );
  assert.match(html, /Covering network/);
  assert.match(html, /192.0.2.0 – 192.0.2.255/);
  assert.match(html, /1 IP used for attribution · 70 reported IPs/);
  // Upgrade views disclose the historical report's recorded handling without adding new exhibits.
  run(
    `boot.version='0.7.0';currentLead.case.stage='pending_notification';currentLead.historical_report={id:'old',revision:2,app_version:'0.6.0',handling_label:null};`,
  );
  html = run('reportSectionContent()');
  assert.match(html, /Certified in v0.6.0. Viewing the preserved report revision/);
  assert.match(html, /Report handling recorded at certification: <strong>Not recorded/);
  assert.match(html, /Current workspace handling is TLP:AMBER/);
  assert.doesNotMatch(html, /Companion Appendix/);
  assert.doesNotMatch(html, /data-action="adopt-presentation"/);
  assert.match(html, /Use Revise report/);
  run(`currentLead.case.stage='closed';currentLead.historical_report.handling_label='TLP:RED';`);
  html = run('reportSectionContent()');
  assert.match(html, /TLP:RED/);
  assert.doesNotMatch(html, /Use Revise report/);
  run(`currentLead.historical_report.app_version='0.7.0';`);
  assert.equal(run('historicalReportNotice()'), '');
  run(`currentLead.case.stage='in_progress';delete currentLead.historical_report;`);
  // Explicitly loading local records populates the current editable draft without a second acceptance step.
  (async () => {
    run(
      `globalThis.calls=[];globalThis.sourceRequests=[];toast=()=>{};scheduleNarrative=()=>{};editorContent=()=>'';api=async(url,opts)=>{calls.push(url);sourceRequests.push(opts?.body);if(url==='/api/source-jobs')return {id:'job1',status:'completed',results:[{id:'CVE-2026-10001',verification_status:'published',description:'Updated source'}],errors:[]};throw Error('unexpected request')};`,
    );
    await run('retrieveCveSources()');
    assert.equal(run('sourceRequests[0].refresh'), false);
    assert.equal(run('sourceRequests[0].local_only'), true);
    assert.equal(run('pendingCveRefresh'), null);
    assert.equal(
      run("draft.cve_records.find(c=>c.id==='CVE-2026-10000').verification_status"),
      'rejected',
    );
    assert.equal(
      run("draft.cve_records.find(c=>c.id==='CVE-2026-10001').description"),
      'Updated source',
    );
    assert.equal(run('dirty'), true);
    run(`pendingCveRefresh={caseId:'another',revision:2,running:false,records:[]}`);
    assert.throws(() => run('adoptCveSources()'), /notification changed/);
    run(
      `pendingCveRefresh={caseId:'c',revision:2,running:false,records:[]};currentLead.section_reviews=[{key:'vulnerabilities',status:'validated'}]`,
    );
    assert.throws(() => run('adoptCveSources()'), /Reopen/);
    run(
      `currentLead.section_reviews=[];pendingCveRefresh=null;api=async()=>({total:2,items:[{id:'CVE-2026-10001',description:'<img src=x onerror=alert(1)>',severity:'CRITICAL'},{id:'CVE-2026-99999',description:'Not reported',severity:'HIGH'}]})`,
    );
    await run('openReportCatalog()');
    assert.match(node('#report-catalog-results').innerHTML, /&lt;img src=x/);
    assert.doesNotMatch(node('#report-catalog-results').innerHTML, /<img src=x/);
    assert.match(node('#report-catalog-results').innerHTML, /Reference only/);
    assert.equal(
      (node('#report-catalog-results').innerHTML.match(/data-action="retrieve-catalog-cve"/g) || [])
        .length,
      1,
    );
    await assert.rejects(
      run("retrieveCveSources({cveIds:['CVE-2026-99999']})"),
      /reported in this notification/,
    );
    run(`globalThis.resolveCatalog=null;api=()=>new Promise(resolve=>resolveCatalog=resolve)`);
    const staleSearch = run("searchReportCatalog('Exchange')");
    run(
      "currentLead.case_id='other-case';resolveCatalog({total:1,items:[{id:'CVE-2026-99999',description:'Stale case response'}]})",
    );
    await staleSearch;
    assert.doesNotMatch(node('#report-catalog-results').innerHTML, /Stale case response/);
    const css = fs.readFileSync(path.join(__dirname, '../static/presentation.css'), 'utf8');
    assert.match(css, /--green:\s*var\(--confirm\)/);
    assert.match(css, /color:\s*#ffc000\s*!important/);
    const index = fs.readFileSync(path.join(__dirname, '../static/index.html'), 'utf8');
    assert.match(index, /class="handling-strip"/);
    // The version comes from backend release metadata at bootstrap. The
    // pre-bootstrap shell identifies the app; browser tests verify the
    // actual version after loading the application.
    assert.match(index, /id="release-version"/);
    assert.match(index, /<title>Shadowserver Eclipse<\/title>/);
    assert.match(index, /class="dm-wordmark"[^>]*>ECLIPSE<span>SHADOWSERVER COMPANION<\/span>/);
    assert.match(index, /id="release-status"[\s\S]*?Shadowserver Eclipse/);
    console.log(
      'v0.7 presentation migration, independent signals, null/zero distinction, source escaping, local-only automatic adoption, case guards, appendix counts, range attribution, and TLP chrome passed.',
    );
  })().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
