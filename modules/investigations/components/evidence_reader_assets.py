"""Offline presentation assets embedded into each newly generated evidence reader."""

CSS = """
:root{color-scheme:light;--ink:#171719;--muted:#62605b;--line:#d5d1c8;--paper:#faf8f2;--accent:#59318b;--cyan:#00cdd6;--soft:#eee9f4}
*{box-sizing:border-box}[hidden]{display:none!important}html{scroll-padding-top:110px}body{margin:0;background:#111214;color:var(--ink);font:15px/1.5 system-ui,Segoe UI,sans-serif}main{max-width:1280px;margin:24px auto;background:var(--paper);padding:30px 42px 34px;min-height:calc(100vh - 48px)}.masthead{border-top:3px solid var(--ink);padding-top:14px}.masthead-line{display:flex;align-items:center;justify-content:space-between;gap:18px}.eyebrow,.record-kind{font:650 10px/1.4 system-ui,sans-serif;letter-spacing:.095em;text-transform:uppercase}.eyebrow{color:var(--muted)}.handling{background:var(--ink);color:#ffd63b;padding:3px 7px;font-size:10px;font-weight:750;letter-spacing:.04em}h1{font:600 clamp(29px,3.1vw,43px)/1.14 Georgia,serif;letter-spacing:-.035em;margin:15px 0 10px;overflow-wrap:anywhere}.masthead-meta{display:flex;gap:25px;align-items:center;font-size:13px;color:var(--muted)}.masthead-meta a{margin-left:auto}.dossier-brief{display:flex;align-items:baseline;justify-content:space-between;gap:20px;margin-top:14px;padding:12px 0;border-top:1px solid var(--line);font-size:13px}.dossier-brief p{margin:0}.dossier-brief p>span{color:#aaa49b;margin:0 9px}.dossier-brief strong{font-size:18px;font-weight:650}.brief-contact{display:flex;align-items:baseline;gap:10px;min-width:0}.brief-contact>span{font-size:10px;text-transform:uppercase;color:var(--muted);white-space:nowrap;letter-spacing:.06em}.brief-contact>a{font-weight:600}.brief-contact small{color:var(--muted)}.package-details{font-size:12px;padding:8px 0 11px;border-bottom:1px solid var(--ink);margin:0}.package-details summary{font-weight:500;color:var(--muted)}.summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:15px 22px;margin:15px 0}.summary-grid dt{font-size:11px;color:var(--muted)}.summary-grid dd{margin:3px 0 0;overflow-wrap:anywhere;font-weight:550}.dossier-layout{display:grid;grid-template-columns:172px minmax(0,1fr);gap:32px}.category-rail{align-self:start;position:sticky;top:25px;margin-top:28px;font-size:12px}.category-rail ul{list-style:none;padding:0;margin:12px 0}.category-rail li{display:flex;align-items:center;gap:7px;border-bottom:1px solid var(--line)}.category-rail a{padding:10px 8px 10px 10px;display:block;flex:1;text-decoration:none;color:var(--ink);border-left:3px solid transparent}.category-rail a[aria-current=true]{border-left-color:var(--cyan);background:var(--soft);font-weight:650}.category-rail li>span{font-variant-numeric:tabular-nums;color:var(--muted);font-size:11px;padding-right:5px}.dossier-content{min-width:0}h2{font:600 27px/1.2 Georgia,serif;letter-spacing:-.025em;margin:26px 0 14px}h3{font-size:19px;line-height:1.35;margin:9px 0 14px;overflow-wrap:anywhere}h4{font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin:0 0 10px}.record{border-top:1px solid var(--line);padding:18px 0 23px;margin:0}.record:target{border-top-color:var(--accent);background:linear-gradient(90deg,#eee9f477,transparent)}.record-heading{display:flex;justify-content:space-between;gap:15px;align-items:baseline;color:var(--muted)}.record-heading>a,.record-id{font:11px/1.4 ui-monospace,monospace;text-decoration:none;white-space:nowrap}.finding{border-top:2px solid var(--ink);padding-top:17px}.finding .record-kind{color:var(--accent)}.finding h3{font-size:29px;font-weight:700;letter-spacing:-.035em;margin:8px 0 4px}.finding-asset{font-size:17px;font-weight:550;margin:0 0 7px;overflow-wrap:anywhere}.finding-service{margin:0 0 12px;font-size:13px;color:var(--muted)}.provenance{font-size:12px;line-height:1.55;color:var(--muted);margin:8px 0;overflow-wrap:anywhere}.provenance>span{padding:0 6px;color:#a29c92}.evidence-chain{border-left:2px solid var(--cyan);padding:2px 0 2px 14px;margin:16px 0}.evidence-chain h4{color:var(--muted);font-size:10px}.evidence-chain ul{list-style:none;padding:0;margin:0}.evidence-chain li{display:grid;grid-template-columns:142px 1fr;gap:12px;font-size:12px;padding:4px 0}.evidence-chain li>span{color:var(--muted)}.record-anchor{display:block;scroll-margin-top:110px}.original-records{margin-top:14px}.bibliography-item{display:grid;grid-template-columns:46px minmax(0,1fr);gap:12px;padding:13px 0}.bibliography-label{font:11px/1.5 ui-monospace,monospace;padding-top:3px}.bibliography-label a{text-decoration:none}.bibliography-body h3{font-size:15px;letter-spacing:0;margin:0 0 4px}.bibliography-body .provenance,.reference-url{font-size:11px;margin:3px 0}.bibliography-body details{padding-top:5px;margin-top:5px;border:0}.bibliography-body summary{font-size:11px;color:var(--muted);font-weight:500}.section-note{font-size:12px;color:var(--muted);margin:0 0 16px}a{color:var(--accent);overflow-wrap:anywhere;text-underline-offset:3px}a:focus-visible,button:focus-visible,summary:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:3px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;text-align:left;font-size:13px}th,td{vertical-align:top;border-bottom:1px solid var(--line);padding:7px 8px;overflow-wrap:anywhere;white-space:pre-wrap}th{font-weight:500;color:var(--muted);width:27%;padding-left:0}tr:last-child th,tr:last-child td{border-bottom:0}.path{display:block;font:10px/1.4 ui-monospace,monospace;margin-top:4px;color:var(--muted)}.muted{color:var(--muted)}details{border-top:1px solid var(--line);margin-top:12px;padding-top:9px}summary{cursor:pointer;font-size:12px;font-weight:550}.technical table{margin-top:10px;font-size:12px}.source-links{font-size:11px;margin:10px 0 0}.source-links a+a{margin-left:12px}code{font-size:10px;overflow-wrap:anywhere}.outcome{font-size:12px;border-left:2px solid var(--accent);padding:6px 12px;margin:10px 0}.record img{max-width:100%;max-height:600px;display:block;margin:18px 0;border:1px solid var(--line)}.reader-controls{position:sticky;top:0;z-index:3;background:#faf8f2f5;backdrop-filter:blur(8px);padding:18px 0 10px;border-bottom:1px solid var(--line)}.control-row{display:flex;gap:10px;align-items:center}.search-control{flex:1;min-width:0}.filter-control{display:none}.control-actions{display:flex;align-items:center;gap:12px;margin-top:6px}.control-actions button{border:0;background:none;padding:3px 0;font-size:11px;color:var(--muted)}.result-count{font-size:11px;color:var(--muted);margin-right:auto}input[type=search],select,button{font:inherit;border:1px solid var(--line);border-radius:0;background:var(--paper);color:var(--ink);padding:8px 10px}input[type=search]{width:100%;font-size:13px}button{cursor:pointer;font-size:12px}button:hover{background:var(--soft)}button:disabled{opacity:.65;cursor:wait}.empty-result{padding:24px 0;border-bottom:1px solid var(--line)}.verify-tools{padding:14px 0;margin:15px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);font-size:12px}.verify-tools p{margin:0 0 10px}.verify-result{font-size:12px}.hash-table th{width:auto}.hash-table td:first-child{width:30%}.hash-table td:nth-child(3){width:40%}.verification{font-size:11px;font-weight:600}.verification[data-state=match]{color:#176239}.verification[data-state=mismatch]{color:#a42424}#files>p{font-size:12px;color:var(--muted)}footer{border-top:1px solid var(--ink);font-size:10px;color:var(--muted);padding-top:14px;margin-top:25px}.visually-hidden{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.skip-link{position:absolute;left:15px;top:-80px;background:var(--paper);padding:10px;z-index:10}.skip-link:focus{top:10px}
@media(max-width:760px){body{background:var(--paper)}main{margin:0;padding:18px 18px 28px;min-height:100vh}.masthead-line{gap:10px}.eyebrow{font-size:9px}h1{font-size:31px;margin:13px 0 10px}.masthead-meta{font-size:11px;gap:10px}.dossier-brief{display:block;padding:10px 0;margin-top:12px}.dossier-brief strong{font-size:16px}.dossier-brief p{font-size:11px}.dossier-brief p>span{margin:0 5px}.brief-contact{margin-top:7px;font-size:12px}.brief-contact>span{font-size:9px}.dossier-layout{display:block}html[data-enhanced=true] .category-rail{display:none}.category-rail{position:static;margin:16px 0}.category-rail ul{display:flex;flex-wrap:wrap;gap:4px 12px}.category-rail li{flex:1 0 40%}.reader-controls{padding:10px 0 8px}.control-row{flex-wrap:wrap;gap:7px}.search-control{flex-basis:100%}.filter-control{display:block;flex:1;min-width:0}.filter-control select{width:100%;font-size:12px}.control-actions{gap:14px}.result-count{font-size:10px}.control-actions button{font-size:10px}html{scroll-padding-top:145px}h2{font-size:25px;margin:21px 0 12px}.finding h3{font-size:27px}.finding-asset{font-size:16px}.finding-service{font-size:12px}.record{padding:15px 0 20px}.record-heading{gap:10px}.evidence-chain li{display:block;font-size:12px;padding:5px 0}.evidence-chain li>span{display:block;font-size:10px;margin-bottom:2px}th{width:38%}.bibliography-item{grid-template-columns:38px minmax(0,1fr);gap:8px}.bibliography-body h3{font-size:14px}.summary-grid{grid-template-columns:1fr 1fr}}
@media print{body{background:white;font-size:10pt}main{margin:0;padding:0;max-width:none;min-height:0}.masthead{border-top:2px solid black}.masthead-line .handling{background:none;color:black;border:1px solid black}h1{font-size:25pt}.dossier-layout{display:block}.category-rail,.reader-controls,.package-details,.technical,#files,.skip-link{display:none!important}.dossier-brief{font-size:9pt}.brief-contact{font-size:9pt}h2{font-size:19pt;break-after:avoid}h3{break-after:avoid}.finding h3{font-size:21pt}.record-heading,h3,.outcome{break-inside:avoid}.record{padding:12px 0;box-shadow:none;background:none}.evidence-chain{border-left-color:black}.evidence-chain li{font-size:9pt}.bibliography-item{padding:8px 0}.bibliography-body h3{font-size:10pt}a{color:inherit;text-decoration:none}.table-wrap{overflow:visible}table{font-size:9pt}th,td{padding:4px}.record img{max-height:500px}footer{font-size:8pt}}
"""

SCRIPT = r"""
(() => {
  'use strict';
  const controls = document.querySelector('.reader-controls');
  const search = document.querySelector('#evidence-search');
  const filter = document.querySelector('#evidence-filter');
  const cards = [...document.querySelectorAll('.record')];
  const sections = [...document.querySelectorAll('section')].filter(s => s.querySelector('.record'));
  const records = cards.map(card => ({card, section:card.closest('section').id, text:card.textContent.toLocaleLowerCase()}));
  const count = document.querySelector('#result-count');
  const empty = document.querySelector('#empty-result');
  const filterRecords = () => {
    const terms = search.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    let visible = 0;
    for (const record of records) {
      record.card.hidden = (filter.value !== 'all' && filter.value !== record.section) || !terms.every(term => record.text.includes(term));
      if (!record.card.hidden) visible++;
    }
    for (const section of sections) section.hidden = ![...section.querySelectorAll('.record')].some(c => !c.hidden);
    count.textContent = `${visible.toLocaleString()} of ${cards.length.toLocaleString()} records`;
    empty.hidden = visible !== 0;
    for (const link of document.querySelectorAll('[data-group]')) {if (link.dataset.group === filter.value) link.setAttribute('aria-current','true');else link.removeAttribute('aria-current');}
  };
  const reset = () => {search.value=''; filter.value='all'; filterRecords();};
  search.addEventListener('input', filterRecords);
  filter.addEventListener('change', () => {filterRecords();document.querySelector('#dossier-records').scrollIntoView({block:'start'});});
  for (const link of document.querySelectorAll('[data-group]')) link.addEventListener('click', event => {event.preventDefault();filter.value=link.dataset.group;filterRecords();document.querySelector('#dossier-records').scrollIntoView({block:'start'});});
  document.querySelector('#reset-filters').addEventListener('click', () => {reset(); search.focus();});
  document.querySelector('#collapse-records').addEventListener('click', () => {for (const detail of document.querySelectorAll('.record details')) detail.open = false;});
  document.querySelector('#print-evidence').addEventListener('click', () => window.print());
  document.addEventListener('keydown', event => {
    const editing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
    if (event.key === '/' && !editing && !event.ctrlKey && !event.metaKey && !event.altKey) {event.preventDefault();search.focus();}
    if (event.key === 'Escape' && (document.activeElement === search || document.activeElement === filter)) {reset();search.focus();}
  });
  const revealRecord = target => {
    if (target?.closest('.record') || target?.querySelector('.record')) {
      reset();
      let ancestor=target.closest('details');while(ancestor){ancestor.open=true;ancestor=ancestor.parentElement.closest('details');}
      if (target.classList.contains('record-anchor') && target.nextElementSibling?.tagName === 'DETAILS') target.nextElementSibling.open=true;
      target.scrollIntoView({block:'start'});
    }
  };
  const revealTarget = () => {
    let id; try {id = decodeURIComponent(location.hash.slice(1));} catch {return;}
    revealRecord(document.getElementById(id));
  };
  for (const link of document.querySelectorAll('a[href^="#"]:not([data-group])')) link.addEventListener('click', () => {
    let target;try {target=document.getElementById(decodeURIComponent(link.hash.slice(1)));} catch {return;}
    // A repeated link does not fire hashchange; reveal its original record on every click.
    revealRecord(target);
  });
  window.addEventListener('hashchange', revealTarget);
  document.documentElement.dataset.enhanced = 'true';
  controls.hidden = false;
  filterRecords();
  if (location.hash) revealTarget();

  const verifyTools = document.querySelector('.verify-tools');
  const fileInput = document.querySelector('#verify-files');
  const folderInput = document.querySelector('#verify-folder');
  const result = document.querySelector('#verify-result');
  const rows = [...document.querySelectorAll('[data-sha256]')];
  const basenameCounts = new Map();
  for (const row of rows) {const name=row.dataset.path.split('/').at(-1);basenameCounts.set(name,(basenameCounts.get(name)||0)+1);}
  const verify = async input => {
    if (!input.files.length) return;
    const files = [...input.files];
    let matched=0, changed=0, missing=0, ambiguous=0, unreadable=0;
    const selected = new Set();
    const buttons = [...verifyTools.querySelectorAll('button')];
    for (const button of buttons) button.disabled = true;
    result.textContent = 'Checking selected files locally…';
    try {
      for (const row of rows) {
        const expected = row.dataset.path;
        const candidates = files.filter(file => {
          const path = file.webkitRelativePath || file.name;
          return path === expected || (file.webkitRelativePath && path.slice(path.indexOf('/') + 1) === expected) || (!file.webkitRelativePath && file.name === expected.split('/').at(-1));
        });
        const cell = row.querySelector('.verification');
        cell.dataset.state = 'missing';
        if (!candidates.length) {missing++;cell.textContent='Not selected';continue;}
        if (candidates.length !== 1 || (!candidates[0].webkitRelativePath && basenameCounts.get(candidates[0].name) > 1)) {ambiguous++;cell.textContent='Ambiguous selection';continue;}
        const file = candidates[0]; selected.add(file);
        try {
          const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', await file.arrayBuffer()))].map(byte=>byte.toString(16).padStart(2,'0')).join('');
          if (hash === row.dataset.sha256 && file.size === Number(row.dataset.size)) {matched++;cell.textContent='Matches';cell.dataset.state='match';}
          else {changed++;cell.textContent='Does not match';cell.dataset.state='mismatch';}
        } catch {unreadable++;cell.textContent='Could not read';cell.dataset.state='mismatch';}
      }
      result.textContent = `${matched} matched · ${changed} changed · ${missing} not selected` + (ambiguous ? ` · ${ambiguous} ambiguous` : '') + (unreadable ? ` · ${unreadable} unreadable` : '') + (files.length > selected.size ? ` · ${files.length-selected.size} selected files not in this index` : '');
    } finally {
      for (const button of buttons) button.disabled = false;
      input.value = '';
    }
  };
  if (globalThis.crypto?.subtle) {
    verifyTools.hidden = false;
    document.querySelector('#choose-files').addEventListener('click', () => fileInput.click());
    document.querySelector('#choose-folder').addEventListener('click', () => folderInput.click());
    fileInput.addEventListener('change', () => verify(fileInput));
    folderInput.addEventListener('change', () => verify(folderInput));
  }
})();
"""
