(async () => {
  // Node checks for case rendering, field escaping and API payloads.
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
        open: false,
        showModal() {
          this.open = true;
        },
        close() {
          this.open = false;
        },
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
  const script = (s) => vm.runInContext(s, context);
  script(`boot={settings:{analyst_name:'Demo Analyst'},explainers:[]};
currentLead={id:'entity1',case_id:'case1',company:'Example <img src=x onerror=alert(1)>',domain:'example.com',
 case:{id:'case1',stage:'pending_notification',version:7,contact_name:'Technology team',contact_email:'it@example.com',certified_report_id:'report1',created_at:'2026-11-06T14:00:00Z'},
 readiness:[{ok:true,label:'Reviewed'}],entries:[{ip:'192.0.2.10',source:{fields:{tag:'eol-php',version:'7.3.25'},workbook:'fixture.csv',sheet:'CSV',row:2}}],domain_groups:[{}],reports:[{id:'report1',revision:2,certified_by:'Demo Analyst',certification_source:'analyst'}],
 attribution:{ip:'192.0.2.10'},hostnames:[],history:[],evidence:[],cases:[],attempts:[{id:'a1',report_id:'report1',occurred_at:'2026-11-06T15:00:00Z',outcome:'recipient_update',channel:'phone',recipient:'Tech team',information_source:'recipient_reported',notes:'<script>alert(1)</script>',recorded_by:'Demo Analyst'}]};
draft={selected_explainers:[],cve_records:[]};`);
  (async () => {
    let html = script(
      'stageCards({in_progress:2,pending_notification:3,notification_completed:4,closed:5,scan_validation:1,delivered_total:9,closed_without_delivery:0,due:2})',
    );
    assert.equal((html.match(/class="metric"/g) || []).length, 5);
    assert(
      html.includes('#workspace/notifications?stage=pending_notification') &&
        html.includes('successfully notified'),
    );
    assert(
      html.includes('Completed archive') &&
        html.includes('Work in Progress') &&
        html.includes('Closing Report'),
    );
    assert(html.includes('5. Closing Report Completed'));
    assert(html.includes('hostname group</small>') && html.includes('notification cases</small>'));
    script("currentLead.case.stage='closed';currentLead.case.delivered_at=null");
    const progress = script('caseProgress()');
    assert.equal((progress.match(/<li /g) || []).length, 5);
    assert(progress.includes('Delivery not recorded'));
    assert(
      !(progress.match(/<li\b[^]*?<\/li>/g) || [])
        .find((item) => item.includes('Delivery not recorded'))
        .includes('class="passed"'),
    );
    script("currentLead.case.stage='pending_notification'");
    html = script(
      `caseTable([{id:'case1',company:'<img>',domain:'example.com',title:'Critical <script>',next_action:'Review contact',stage:'pending_notification',assets:1,observations:2}])`,
    );
    assert(html.includes('&lt;img&gt;') && html.includes('&lt;script&gt;'));
    assert(html.includes('#workspace/notifications/case1') && html.includes('Review contact'));
    html = script(`outreachPolicyMarkup({state:'do_not_contact',reason:'Recipient <request>'})`);
    assert(html.includes('value="do_not_contact" selected'));
    assert(html.includes('Recipient &lt;request&gt;'));
    html = script(
      `outreachPolicyMarkup({state:'deferred',reason:'Wait <review>',review_on:'2026-11-10'})`,
    );
    assert(html.includes('id="case-outreach-policy"') && html.includes('Wait &lt;review&gt;'));
    assert(html.includes('Review dates create reminders'));
    html = script('contactMarkup()');
    assert(html.includes('Email sent') && html.includes('Receipt acknowledged'));
    assert(html.includes('value="report1" selected'));
    assert(html.includes('&lt;script&gt;') && !html.includes('<script>'));
    assert(html.includes('Reported by the recipient') && html.includes('type="datetime-local"'));
    assert.equal(script("leadURL('/draft')"), '/api/leads/entity1/draft?case_id=case1');
    for (const view of [
      'entity',
      'notification',
      'assets',
      'evidence',
      'attribution',
      'contact',
      'closing',
      'activity',
    ]) {
      script('tab=' + JSON.stringify(view));
      assert(script('editorContent()').length > 0);
    }
    html = script('leadMarkup()');
    assert(html.includes('&lt;img') && !html.includes('<img src=x'));
    script("currentLead.case.stage='in_progress'");
    html = script('contactMarkup()');
    assert(!html.includes('value="delivered"'));
    script("currentLead.case.stage='closed'");
    html = script('contactMarkup()');
    assert(!html.includes('id="case-attempt"'));
    assert(html.includes('disabled'));
    script("currentLead.case.stage='pending_notification'");
    html = script('closingMarkup()');
    assert(html.includes('Closed by') && html.includes('Unable to contact'));
    assert(!html.includes('value="notified"'));
    script("currentLead.case.delivered_at='2026-11-06T16:00:00Z'");
    html = script('closingMarkup()');
    assert(html.includes('value="notified"'));
    assert(!html.includes('value="unable_to_contact"'));
    script(
      `let calls=[];api=async (url,opts)=>{calls.push({url,opts});return currentLead;};route=async()=>{};toast=()=>{};`,
    );
    context.form = { id: 'case-attempt' };
    context.values = {
      occurred_at: '2026-11-06T14:30',
      channel: 'email',
      outcome: 'delivered',
      report_id: 'report1',
      recipient: 'Tech team',
      destination: 'it@example.com',
      notes: 'Received',
      recorded_by: 'Demo Analyst',
      information_source: 'administrative',
    };
    await script('caseSubmit(form,values,new Set(),undefined)');
    let calls = script('calls');
    assert.equal(calls[0].url, '/api/cases/case1/attempts');
    assert.equal(calls[0].opts.body.expected_version, 7);
    assert.equal(
      calls[0].opts.body.occurred_at,
      new Date(context.values.occurred_at).toISOString(),
    );
    assert.equal(calls[0].opts.body.report_id, 'report1');
    context.form = { id: 'case-close' };
    context.values = {
      disposition: 'notified',
      conclusion: 'Received report.',
      closed_by: 'Analyst',
    };
    await script("caseSubmit(form,values,new Set(['reviewed']),'close')");
    calls = script('calls');
    assert.equal(calls[1].url, '/api/cases/case1/close');
    assert.equal(calls[1].opts.body.reviewed, true);
    assert.equal(calls[1].opts.body.expected_version, 7);
    console.log(
      'Five-stage dashboard and truthful non-delivery closure, case UI, locked states, escaping, scoped URLs and contact/closing submit payloads passed.',
    );
  })().catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
