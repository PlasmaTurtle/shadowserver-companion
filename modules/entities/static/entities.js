import { observedVersion } from '../../ui/static/shared.js';
export const entityName = (entity) =>
  entity.company || entity.entity_name || entity.domain || 'Entity';
/** Entity directory, dossier and evidence presentation owned by Entities. No startup requests or event listeners are installed here. */
export function install(ctx) {
  const esc = (value) => ctx.actions.esc(value ?? '');

  const encode = encodeURIComponent;

  const list = (value) => (Array.isArray(value) ? value : []);

  function leadTable(rows, filtered = false) {
    if (!rows.length)
      return ctx.actions.empty(
        filtered ? 'No businesses match these filters' : 'No business entities yet',
        filtered
          ? 'Clear the search or intelligence filter to see the rest of your queue.'
          : 'Import a report to find your next notification.',
        filtered
          ? ctx.actions.linkButton('#entities', 'Clear filters', '', 'search')
          : ctx.actions.linkButton('#data', 'Import a report'),
      );
    return `<div class="table-wrap"><table><thead><tr><th scope="col">Select</th><th scope="col">Organization / hostname</th><th scope="col">Reported finding</th><th scope="col">Assets</th><th scope="col">Notifications</th><th scope="col">Last activity</th><th scope="col">Actions</th></tr></thead><tbody>${rows.map((r, i) => `<tr class="clickable ${ctx.state.contacts.selectedEntityIds?.has(r.id) ? 'is-selected' : ''}" data-open-lead="${r.id}"><td><input type="checkbox" data-contact-select="${ctx.actions.esc(r.id)}" aria-label="Select ${ctx.actions.esc(r.company || r.domain)} for contact discovery" ${ctx.state.contacts.selectedEntityIds?.has(r.id) ? 'checked' : ''}></td><td><a class="business" href="#entity/${r.id}"><span class="business-avatar color-${i % 4}">${ctx.actions.esc((r.company || r.domain).slice(0, 2).toUpperCase())}</span><span><strong>${ctx.actions.esc(r.company || r.domain)}</strong><small>${ctx.actions.esc(r.company ? r.domain : 'Attribution recorded')}</small></span></a></td><td><span class="software">${ctx.actions.esc((r.versions || '').split(',')[0] || 'Version not reported')}</span><small>${ctx.actions.esc(/eol/i.test(r.tags) ? 'End-of-life software' : /cve-/i.test(r.tags) ? 'Reported CVE' : r.tags)}</small></td><td><strong>${ctx.actions.num(r.assets)}</strong><small>${ctx.actions.num(r.observations)} observations · ${ctx.actions.num(r.hostname_count)} hostnames</small></td><td>${ctx.actions.num(r.open_cases)} open / ${ctx.actions.num(r.case_count)} total${r.unassigned_observations ? `<small class="save-dirty">${ctx.actions.num(r.unassigned_observations)} observations awaiting review</small>` : ''}</td><td>${ctx.actions.date(r.updated_at)}</td><td class="row-end"><a class="button small" href="#entity/${encodeURIComponent(r.id)}?tab=contact" aria-label="Contacts for ${ctx.actions.esc(r.company || r.domain)}">Contacts</a></td></tr>`).join('')}</tbody></table></div>`;
  }

  async function leadsPage(params) {
    const q = params.get('q') || '',
      signal = params.get('signal') || 'all';
    const allRows = await ctx.actions.api('/api/leads?' + new URLSearchParams({ q }));
    const rows = allRows.filter((r) =>
      signal === 'kev'
        ? r.kev === true
        : signal === 'ransomware'
          ? ctx.actions.hasKnownRansomware(r)
          : true,
    );
    ctx.state.contacts.batchEntityIds = rows.map((row) => row.id);
    ctx.state.contacts.selectedEntityIds ||= new Set();
    for (const row of rows)
      ctx.state.contacts.entityNames.set(row.id, row.company || row.domain || 'Business entity');
    return (
      ctx.actions.heading(
        'Entities',
        '',
        ctx.actions.linkButton('#workspace/notifications', 'Notifications', '', 'file'),
      ) +
      ctx.actions.contactBatchMarkup() +
      `<section class="panel"><div class="filter-bar"><span>${ctx.actions.num(rows.length)} business ${rows.length === 1 ? 'entity' : 'entities'}</span><form id="lead-search" class="input-search">${ctx.actions.icon('search')}<input name="q" aria-label="Search businesses" placeholder="Search company or hostname…" value="${ctx.actions.esc(q)}"><select name="signal" aria-label="Filter business intelligence" data-submit-filter>${ctx.actions.signalOptions(signal)}</select><button class="button small" type="submit">Apply</button></form></div>${ctx.actions.leadTable(rows, !!q || signal !== 'all')}</section>`
    );
  }

  function canonicalDossierModel(entity) {
    const summary = entity.awareness,
      edges = list(entity.awareness_connections),
      hosts = new Map(list(entity.hostnames).map((h) => [typeof h === 'string' ? h : h.name, 0])),
      ips = new Map();
    for (const pair of edges) {
      hosts.set(pair.host, (hosts.get(pair.host) || 0) + pair.count);
      ips.set(pair.ip, (ips.get(pair.ip) || 0) + pair.count);
    }
    const rank = (values) =>
      [...values]
        .map(([value, count]) => ({ value, count }))
        .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value));
    const hostRows = rank(hosts),
      ipRows = rank(ips),
      graphHosts = hostRows.slice(0, 6),
      graphIPs = ipRows.slice(0, 6),
      hostSet = new Set(graphHosts.map((h) => h.value)),
      ipSet = new Set(graphIPs.map((ip) => ip.value));
    return {
      hosts: hostRows,
      ips: ipRows,
      edges,
      findings: list(entity.awareness_findings).map((f) => ({
        id: f.id,
        label: f.condition,
        version: f.version,
        count: f.observation_count,
        reportedCount: f.reported_observation_count,
        unknownCount: f.legacy_unknown_observation_count,
        hostname: f.hostname,
        service: f.service_scope,
        workflow: f.workflow,
        riskChanged: f.risk_changed,
        riskReasons: f.risk_change_reasons,
      })),
      findingCount: summary.findings,
      observedFrom: String(summary.first_seen || '').slice(0, 10),
      observedTo: String(summary.last_seen || '').slice(0, 10),
      entryCount: summary.observations,
      approvedCount: summary.approved_observations,
      darkMatterCount: summary.dark_matter_observations,
      unknownCount: summary.legacy_unknown_observation_count || 0,
      hostCount: summary.hostname_count,
      ipCount: summary.ips,
      connectionCount: edges.length,
      graph: {
        hosts: graphHosts,
        ips: graphIPs,
        edges: edges.filter((e) => hostSet.has(e.host) && ipSet.has(e.ip)),
      },
    };
  }

  function entityDossierModel(entity) {
    if (entity.awareness) return canonicalDossierModel(entity);
    const hosts = new Map(),
      ips = new Map(),
      pairs = new Map(),
      findings = new Map(),
      dates = [];
    const add = (map, value, count = 0) => {
      value = String(value || '').trim();
      if (!value) return '';
      map.set(value, (map.get(value) || 0) + count);
      return value;
    };
    const hostname = (value) =>
      String(value || '')
        .trim()
        .toLowerCase()
        .replace(/\.$/, '');
    for (const item of list(entity.hostnames))
      add(hosts, hostname(typeof item === 'string' ? item : item.name));
    for (const item of list(entity.ip_associations)) add(ips, item.ip);
    for (const entry of list(entity.entries)) {
      const fields = entry.source?.fields || entry.normalized || entry;
      const host = add(hosts, hostname(entry.hostname || fields.hostname), 1);
      const ip = add(ips, entry.ip || fields.ip, 1);
      if (host && ip) {
        const key = JSON.stringify([host, ip]);
        if (!pairs.has(key)) pairs.set(key, { host, ip, count: 0, entry_ids: [] });
        const pair = pairs.get(key);
        pair.count++;
        if (entry.id && !pair.entry_ids.includes(entry.id)) {
          pair.entry_ids.push(entry.id);
          pair.entry_ids.sort();
          pair.entry_ids = pair.entry_ids.slice(0, 3);
        }
      }
      const label = String(entry.tag || fields.tag || entry.product || fields.product || '').trim();
      const version = observedVersion(entry).trim();
      if (label || version) {
        const key = JSON.stringify([label, version]);
        if (!findings.has(key))
          findings.set(key, { label: label || 'Version reported', version, count: 0 });
        findings.get(key).count++;
      }
      const date = String(entry.observed_at || fields.timestamp || '').slice(0, 10);
      if (/^\d{4}-\d{2}-\d{2}$/.test(date)) {
        const parsed = new Date(date + 'T00:00:00Z');
        if (Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === date)
          dates.push(date);
      }
    }
    const ranked = (map) =>
      [...map]
        .map(([value, count]) => ({ value, count }))
        .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value));
    const hostRows = ranked(hosts),
      ipRows = ranked(ips);
    const edges = [...pairs.values()]
      .map((pair) => ({ ...pair, entry_ids: pair.entry_ids.sort().slice(0, 3) }))
      .sort(
        (a, b) => b.count - a.count || a.host.localeCompare(b.host) || a.ip.localeCompare(b.ip),
      );
    const graphHosts = hostRows.slice(0, 6),
      graphIPs = ipRows.slice(0, 6);
    const hostSet = new Set(graphHosts.map((item) => item.value)),
      ipSet = new Set(graphIPs.map((item) => item.value));
    dates.sort();
    return {
      hosts: hostRows,
      ips: ipRows,
      edges,
      findings: [...findings.values()].sort(
        (a, b) =>
          b.count - a.count || a.label.localeCompare(b.label) || a.version.localeCompare(b.version),
      ),
      observedFrom: dates[0] || '',
      observedTo: dates.at(-1) || '',
      entryCount: list(entity.entries).length,
      hostCount: hosts.size,
      ipCount: ips.size,
      connectionCount: edges.length,
      graph: {
        hosts: graphHosts,
        ips: graphIPs,
        edges: edges.filter((pair) => hostSet.has(pair.host) && ipSet.has(pair.ip)),
      },
    };
  }

  function sharedIpMarkup(rows) {
    if (!list(rows).length) return '';
    return `<details class="panel"><summary>Shared IP associations (${rows.length})</summary><div class="panel-body"><div class="table-wrap"><table><thead><tr><th>IP</th><th>Also observed for</th><th>Observed dates</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.ip)}</td><td><a href="#entity/${encode(r.entity_id)}">${esc(r.entity_name)}</a></td><td>${ctx.actions.date(r.first_seen)} – ${ctx.actions.date(r.last_seen)}</td></tr>`).join('')}</tbody></table></div></div></details>`;
  }

  function entityDnsMarkup(entity) {
    const state = entity.dns_connections;
    if (!state?.total_roots) return '';
    const roots = list(state.roots),
      shown = roots.slice(0, 4),
      hostPairs = shown
        .flatMap((r) =>
          list(r.associated_hostnames || r.reported_hostnames)
            .filter((h) => h !== r.root_domain)
            .map((h) => ({ host: h, root: r.root_domain })),
        )
        .slice(0, 6),
      dnsPairs = shown
        .flatMap((r) =>
          list(r.lookup?.answers).flatMap((a) =>
            list(a.addresses).map((ip) => ({ root: r.root_domain, ip })),
          ),
        )
        .slice(0, 8),
      hostNames = [...new Set(hostPairs.map((p) => p.host))],
      rootNames = shown.map((r) => r.root_domain),
      ipNames = [...new Set(dnsPairs.map((p) => p.ip))],
      height = Math.max(
        180,
        Math.max(hostNames.length, rootNames.length, ipNames.length) * 38 + 60,
      ),
      at = (values, name) =>
        32 + ((height - 42) * (values.indexOf(name) + 1)) / (values.length + 1),
      short = (v) => (v.length > 25 ? v.slice(0, 24) + '…' : v),
      job = state.job || {},
      title = state.running
        ? 'Resolving root DNS…'
        : job.error
          ? 'DNS lookup unavailable'
          : 'Root DNS',
      graph = `<div class="dossier-graph-viewport" role="region" aria-label="Associated subdomains, registrable roots and current DNS addresses" tabindex="0"><svg class="dossier-constellation" data-dossier-dns-graph role="img" aria-label="Solid lines connect a hostname to its registrable root. Dashed lines show current DNS answers; these do not establish ownership." viewBox="0 0 680 ${height}"><g class="dossier-links">${hostPairs.map((p) => `<path data-root-link d="M 150 ${at(hostNames, p.host)} C 220 ${at(hostNames, p.host)}, 255 ${at(rootNames, p.root)}, 335 ${at(rootNames, p.root)}"><title>${esc(p.host)} → ${esc(p.root)} · registrable domain</title></path>`).join('')}${dnsPairs.map((p) => `<path data-dns-link stroke-dasharray="5 5" d="M 335 ${at(rootNames, p.root)} C 420 ${at(rootNames, p.root)}, 455 ${at(ipNames, p.ip)}, 535 ${at(ipNames, p.ip)}"><title>${esc(p.root)} → ${esc(p.ip)} · current public DNS answer</title></path>`).join('')}</g><g class="dossier-host-nodes"><text x="20" y="22">Associated hostname</text><text x="260" y="22">Root domain</text><text x="535" y="22">DNS address</text>${hostNames.map((v) => `<g><circle cx="150" cy="${at(hostNames, v)}" r="4"/><text x="140" y="${at(hostNames, v) - 9}" text-anchor="end">${esc(short(v))}</text><title>${esc(v)}</title></g>`).join('')}${rootNames.map((v) => `<g><circle cx="335" cy="${at(rootNames, v)}" r="5"/><text x="335" y="${at(rootNames, v) - 12}" text-anchor="middle">${esc(short(v))}</text><title>${esc(v)}</title></g>`).join('')}${ipNames.map((v) => `<g><circle cx="535" cy="${at(ipNames, v)}" r="4"/><text x="545" y="${at(ipNames, v) + 4}">${esc(short(v))}</text><title>${esc(v)}</title></g>`).join('')}</g></svg></div>`;
    const evidence = roots
      .map((r) => {
        const lookup = r.lookup,
          answers = list(lookup?.answers),
          ips = answers.flatMap((a) => list(a.addresses));
        return `<tr><td><strong>${esc(r.root_domain)}</strong><small>${list(
          r.associated_hostnames || r.reported_hostnames,
        )
          .map(esc)
          .join(
            ', ',
          )}</small></td><td>${ips.length ? ips.map(esc).join('<br>') : lookup ? 'No public address returned' : 'Not retrieved'}${lookup?.stale ? '<small>Previous answer · refresh due</small>' : ''}${lookup?.comparison ? `<small>${esc({ agreement: 'Resolvers agree', disagreement: 'Resolver answers differ', incomplete: 'Resolver comparison incomplete' }[lookup.comparison.status] || 'Resolver comparison incomplete')}</small>` : ''}${list(lookup?.warnings).length ? '<small>Lookup incomplete</small>' : ''}</td><td>${lookup ? ctx.actions.stamp(lookup.checked_at) : '—'}${answers.map((a) => `<details><summary>${esc(a.record_type)} · ${esc(a.source?.resolver || 'Resolver not recorded')}</summary><p>${list(a.addresses).map(esc).join(', ') || esc(a.status || 'No answer')}</p><p>${esc(a.source?.retrieved_at)}${a.source?.from_cache ? ' · cached response' : ''}</p>${list(a.cname_chain).length ? `<p>Aliases: ${list(a.cname_chain).map(esc).join(' → ')}</p>` : ''}<p>SHA-256 <code>${esc(a.source?.body_sha256)}</code></p><pre>${esc(JSON.stringify(a.source, null, 2))}</pre></details>`).join('')}</td></tr>`;
      })
      .join('');
    return `<section class="dossier-root-dns"><div class="dossier-section-head"><h3>${title}</h3>${state.disabled ? '<span class="dossier-quiet">Demonstration · offline</span>' : `<button class="button small" data-action="entity-dns-refresh" ${state.running ? 'disabled' : ''}>Refresh root DNS</button>`}</div>${graph}<div class="dossier-graph-caption"><span>Solid = registrable root / dashed = current DNS</span><span>Google Public DNS + Cloudflare DNS · public recursive resolvers</span></div><p class="dossier-quiet">DNS connections do not establish common ownership or add reported exposures.</p>${job.error ? `<p role="status">${esc(job.error)}</p>` : ''}${!state.running && state.roots_remaining ? `<p class="dossier-quiet">${ctx.actions.num(state.roots_remaining)} roots awaiting DNS.</p>` : ''}<details class="dossier-connection-evidence"><summary>Root DNS evidence · ${ctx.actions.num(state.total_roots)} domains${state.truncated ? ' · first 128 shown' : ''}</summary><div class="table-wrap"><table><thead><tr><th>Root / associated hostnames</th><th>DNS addresses</th><th>Retrieved / evidence</th></tr></thead><tbody>${evidence}</tbody></table></div></details></section>`;
  }

  async function refreshEntityDns(refresh = false) {
    const entity = ctx.state.entities.current;
    if (!entity?.dns_connections?.total_roots || entity.dns_connections.disabled) return;
    const id = entity.id,
      renderId = ctx.state.navigation.renderId,
      active = () =>
        ctx.state.entities.current?.id === id && ctx.state.navigation.renderId === renderId,
      paint = (value) => {
        if (!active()) return;
        ctx.state.entities.current.dns_connections = value;
        const region = ctx.actions.$('[data-entity-dns]');
        if (region) region.innerHTML = entityDnsMarkup(ctx.state.entities.current);
      },
      url = '/api/entities/' + encode(id) + '/connections/dns';
    try {
      let value = await ctx.actions.api(url, { method: 'POST', body: { refresh } });
      paint(value);
      let polls = 0,
        batches = 0;
      while (active() && polls++ < 100) {
        if (!value.running) {
          if (
            !value.needs_lookup ||
            value.job?.status !== 'complete' ||
            !value.job?.completed ||
            batches++ >= 4
          )
            break;
          value = await ctx.actions.api(url, { method: 'POST', body: { refresh: false } });
          paint(value);
          continue;
        }
        await new Promise((resolve) => setTimeout(resolve, 1200));
        if (!active()) return;
        value = await ctx.actions.api(url);
        paint(value);
      }
    } catch {
      if (!active()) return;
      paint({
        ...entity.dns_connections,
        running: false,
        job: { status: 'error', error: 'Root DNS could not refresh. Try again when connected.' },
      });
    }
  }

  function entityConstellationMarkup(entity, model = entityDossierModel(entity)) {
    const height = Math.max(
      250,
      Math.max(model.graph.hosts.length, model.graph.ips.length) * 52 + 42,
    );
    const y = (index, length) => (height / (length + 1)) * (index + 1);
    const hostPositions = new Map(
      model.graph.hosts.map((item, index) => [item.value, y(index, model.graph.hosts.length)]),
    );
    const ipPositions = new Map(
      model.graph.ips.map((item, index) => [item.value, y(index, model.graph.ips.length)]),
    );
    const short = (value, length = 29) =>
      value.length > length ? value.slice(0, length - 1) + '…' : value;
    const graphId = 'dossier-network-' + encode(entity.id).replaceAll('%', '-');
    return `<section class="dossier-connections"><div class="dossier-section-head"><div><span class="dossier-kicker">Observed infrastructure</span><h2>Connections.</h2></div><a class="dossier-link" href="#eclipse?entity=${encode(entity.id)}">Explore in Eclipse ${ctx.actions.icon('arrow')}</a></div>${model.hostCount || model.ipCount ? `<div class="dossier-graph-viewport" role="region" aria-label="Observed hostname and IP connections" tabindex="0"><svg class="dossier-constellation" data-dossier-graph role="img" aria-labelledby="${esc(graphId)}-title ${esc(graphId)}-desc" viewBox="0 0 680 ${height}"><title id="${esc(graphId)}-title">Reported hostname and IP connections for ${esc(entityName(entity))}</title><desc id="${esc(graphId)}-desc">Lines connect hostnames and IP addresses recorded together in a source observation. ${model.graph.edges.length} of ${model.connectionCount} recorded pairs shown. Shared infrastructure does not establish ownership. Source pairs and observation links follow.</desc><g class="dossier-links">${model.graph.edges.map((pair) => `<path data-dossier-edge data-host="${esc(pair.host)}" data-ip="${esc(pair.ip)}" data-count="${pair.count}" ${pair.approved_count === 0 ? 'stroke-dasharray="4 5" opacity="0.45"' : ''} d="M 248 ${hostPositions.get(pair.host)} C 334 ${hostPositions.get(pair.host)}, 346 ${ipPositions.get(pair.ip)}, 432 ${ipPositions.get(pair.ip)}" stroke-width="${Math.min(3, 1 + Math.log2(pair.count + 1) / 2)}"><title>${esc(pair.host)} → ${esc(pair.ip)} · ${pair.approved_count !== undefined ? `${pair.approved_count} admitted / ${pair.dark_matter_count} dark matter observations` : `${pair.count} source observations`}</title></path>`).join('')}</g><g class="dossier-host-nodes">${model.graph.hosts.map((item) => `<g data-dossier-host="${esc(item.value)}"><circle cx="248" cy="${hostPositions.get(item.value)}" r="5"/><text x="230" y="${hostPositions.get(item.value) + 4}" text-anchor="end">${esc(short(item.value))}</text><title>${esc(item.value)} · ${item.count} observations</title></g>`).join('')}</g><g class="dossier-ip-nodes">${model.graph.ips.map((item) => `<g data-dossier-ip="${esc(item.value)}"><circle cx="432" cy="${ipPositions.get(item.value)}" r="5"/><text x="450" y="${ipPositions.get(item.value) + 4}">${esc(short(item.value, 25))}</text><title>${esc(item.value)} · ${item.count} observations</title></g>`).join('')}</g></svg></div>` : '<div class="dossier-empty-network">No hostname or IP recorded.</div>'}<div class="dossier-graph-caption"><span>${ctx.actions.num(model.hostCount)} hostnames / ${ctx.actions.num(model.ipCount)} IPs</span><span>Lines = co-reported source values</span></div><details class="dossier-connection-evidence"><summary>Connection evidence · ${ctx.actions.num(model.connectionCount)} pairs${model.graph.edges.length < model.connectionCount ? ' · graph is a selection' : ''}</summary>${model.edges.length ? `<div class="table-wrap"><table><thead><tr><th>Hostname</th><th>IP</th><th>Source rows</th></tr></thead><tbody>${model.edges.map((pair) => `<tr><td>${esc(pair.host)}</td><td>${esc(pair.ip)}</td><td>${ctx.actions.num(pair.count)}${pair.approved_count !== undefined ? `<small>${ctx.actions.num(pair.approved_count)} admitted / ${ctx.actions.num(pair.dark_matter_count)} dark matter</small>` : ''}${pair.entry_ids.map((id, index) => `<a class="dossier-source-link" href="/api/eclipse/observations/${encode(id)}" target="_blank" rel="noopener noreferrer" aria-label="Source observation ${index + 1} for ${esc(pair.host)} and ${esc(pair.ip)}">${index + 1}</a>`).join('')}</td></tr>`).join('')}</tbody></table></div>` : '<p>No complete hostname/IP pair occurs in the saved observations.</p>'}</details>${sharedIpMarkup(entity.shared_ip_associations)}<div data-entity-dns>${entityDnsMarkup(entity)}</div></section>`;
  }

  function dossierCaseRows(cases) {
    return list(cases).length
      ? `<ol class="dossier-history">${list(cases)
          .map(
            (item) =>
              `<li><span class="dossier-history-mark" aria-hidden="true"></span><div><a href="#workspace/notifications/${encode(item.id)}">${esc(item.title || 'Notification')}</a><small>${ctx.actions.date(item.updated_at || item.created_at)}</small></div>${ctx.actions.statusBadge(item.stage)}</li>`,
          )
          .join('')}</ol>`
      : '<p class="dossier-quiet">No notifications opened.</p>';
  }

  function directoryContact(entity) {
    const saved = ctx.state.entities.contactOverviews?.get(entity.id);
    if (saved) return saved;
    const profile = entity.entity_profile || {};
    return {
      name: profile.contact_name,
      email: profile.contact_email,
      phone: profile.contact_phone,
      loading: true,
    };
  }

  function contactValues(contact) {
    return `${contact.name ? `<strong>${esc(contact.name)}</strong>` : ''}${contact.email ? `<span class="dossier-contact-value">${esc(contact.email)}</span>` : ''}${contact.phone ? `<span class="dossier-contact-value">${esc(contact.phone)}</span>` : ''}${contact.form && /^https?:\/\//i.test(contact.form) ? `<a class="dossier-contact-value" href="${esc(contact.form)}" target="_blank" rel="noopener noreferrer">Company contact form</a>` : ''}${!contact.email && !contact.phone && !contact.form ? `<span class="dossier-quiet">${contact.loading ? 'Loading saved contacts…' : ['partial', 'failed'].includes(contact.status) ? 'Search incomplete' : contact.status === 'not_checked' ? 'Contacts not checked' : 'No contacts found'}</span>` : ''}`;
  }

  function directoryContactMarkup(entity) {
    const contact = directoryContact(entity);
    const busy = ['pending', 'running'].includes(contact.queue_status);
    return `${contactValues(contact)}<button class="button small" data-action="refresh-entity-contact" data-entity-id="${esc(entity.id)}" aria-label="Refresh contacts for ${esc(entityName(entity))}" ${busy ? 'disabled' : ''}>${busy ? 'Finding contacts…' : 'Refresh contacts'}</button>`;
  }

  function entityGapsMarkup(entity) {
    const profile = entity.entity_profile || {},
      contact = directoryContact(entity);
    const missing = [];
    if (
      !entity.company ||
      entity.company === entity.domain ||
      entity.company.endsWith('.' + entity.domain)
    )
      missing.push('Business name missing');
    if (!profile.address) missing.push('Address missing');
    if (!contact.loading && !contact.email && !contact.phone) missing.push('No email or phone');
    return missing.length
      ? missing.map((label) => `<small class="dossier-quiet">${label}</small>`).join('')
      : `<span class="dossier-quiet">${contact.loading ? 'Checking saved contacts…' : 'Details available'}</span>`;
  }

  function entityBrief(entity, model) {
    const profile = entity.entity_profile || {};
    const first = entity.observation_dates?.first_seen || model.observedFrom;
    const last = entity.observation_dates?.last_seen || model.observedTo;
    const website = entity.website?.final_url;
    const domain = /^https?:\/\//i.test(website || '')
      ? `<a href="${esc(website)}" target="_blank" rel="noopener noreferrer">${esc(entity.domain)}</a>`
      : esc(entity.domain);
    return `<div class="entity-brief"><section><span class="dossier-kicker">Primary domain</span><h2 class="entity-root">${domain}</h2>${profile.address ? `<address>${esc(profile.address)}</address>` : '<p class="dossier-quiet">Address not found</p>'}<dl><dt>Record created</dt><dd>${ctx.actions.date(entity.created_at)}</dd><dt>First observed</dt><dd>${first ? ctx.actions.date(first) : 'Not recorded'}</dd><dt>Last observed</dt><dd>${last ? ctx.actions.date(last) : 'Not recorded'}</dd></dl></section><section><div class="dossier-section-head"><h2>Contact</h2><a class="dossier-link" href="#entity/${encode(entity.id)}?tab=contacts">Details ${ctx.actions.icon('arrow')}</a></div><div data-entity-contact="${esc(entity.id)}">${directoryContactMarkup(entity)}</div><div data-entity-completeness="${esc(entity.id)}">${entityGapsMarkup(entity)}</div></section></div>`;
  }

  async function loadEntityContactOverviews() {
    const state = ctx.state.entities,
      generation = ctx.state.navigation.renderId;
    if (state.contactLoading === generation) return;
    const route = ctx.state.navigation.currentRoute.split('?')[0];
    const rows =
      route === 'entities'
        ? state.directoryRows || []
        : route.startsWith('entity/') && state.current
          ? [state.current]
          : [];
    if (!rows.length) return;
    state.contactLoading = generation;
    state.contactOverviews ||= new Map();
    const batches = [];
    for (let i = 0; i < rows.length; i += 50) batches.push(rows.slice(i, i + 50));
    const current = () => generation === ctx.state.navigation.renderId;
    const worker = async () => {
      while (batches.length && current()) {
        const batch = batches.shift();
        try {
          const query = new URLSearchParams();
          for (const row of batch) query.append('entity_ids', row.id);
          const result = await ctx.actions.api('/api/contact-discovery/overviews?' + query);
          if (!current()) return;
          for (const row of batch) {
            if (!result[row.id]) continue;
            state.contactOverviews.set(row.id, result[row.id]);
            const card = ctx.actions.$(`[data-entity-contact="${row.id}"]`);
            // Keep the focused refresh control in place until the user leaves it.
            if (card && !card.contains?.(document.activeElement))
              card.innerHTML = directoryContactMarkup(row);
            const gaps = ctx.actions.$(`[data-entity-completeness="${row.id}"]`);
            if (gaps) gaps.innerHTML = entityGapsMarkup(row);
          }
        } catch {
          if (current())
            for (const row of batch) {
              const card = ctx.actions.$(`[data-entity-contact="${row.id}"]`);
              if (card && !state.contactOverviews.has(row.id))
                card.innerHTML =
                  '<span class="dossier-quiet">Saved contacts unavailable · retrying</span>';
            }
        }
      }
    };
    try {
      await Promise.all([worker(), worker()]);
      if (!current()) return;
      const status = await ctx.actions.api('/api/contact-discovery/directory-status');
      if (!current()) return;
      const label = ctx.actions.$('#entity-directory-status');
      if (label)
        label.textContent =
          status.pending || status.running
            ? `${status.pending} queued · ${status.running} searching`
            : '';
    } catch {
      // Saved details remain usable; the next scheduled poll retries.
    } finally {
      if (state.contactLoading === generation) state.contactLoading = null;
    }
  }

  async function findAllEntityContacts(button) {
    button.disabled = true;
    try {
      const result = await ctx.actions.api('/api/contact-discovery/find-all', { method: 'POST' });
      ctx.actions.toast(`${result.queued} entities queued for contact search`);
      await loadEntityContactOverviews();
    } finally {
      button.disabled = false;
    }
  }

  async function refreshDirectoryContact(button) {
    button.disabled = true;
    try {
      await ctx.actions.api(`/api/entities/${encode(button.dataset.entityId)}/contacts/refresh`, {
        method: 'POST',
      });
      button.textContent = 'Finding contacts…';
      await loadEntityContactOverviews();
    } catch (error) {
      button.disabled = false;
      throw error;
    }
  }

  function dossierOverview(entity, model) {
    const profile = entity.entity_profile || {};
    const open = list(entity.cases).filter((item) =>
      ['in_progress', 'pending_notification'].includes(item.stage),
    ).length;
    return `${entityBrief(entity, model)}<div class="dossier-overview"><div class="dossier-overview-main">${entityConstellationMarkup(entity, model)}<section class="dossier-findings"><div class="dossier-section-head"><div><span class="dossier-kicker">Admitted evidence</span><h2>Findings.</h2></div><a class="dossier-link" href="#entity/${encode(entity.id)}?tab=assets">All assets ${ctx.actions.icon('arrow')}</a></div>${
      model.findings.length
        ? `<ol class="dossier-finding-list">${model.findings
            .slice(0, 6)
            .map(
              (item, index) =>
                `<li><span class="dossier-row-number">${String(index + 1).padStart(2, '0')}</span><div><strong>${esc(item.label)}</strong>${item.riskChanged ? `<span class="badge warning" title="${esc(list(item.riskReasons).join(' '))}">Risk changed</span>` : ''}<small>${esc([item.hostname, item.service, item.version || 'Version not reported'].filter(Boolean).join(' · '))}</small></div><span>${ctx.actions.num(item.count)}<small>${entity.awareness ? 'approved observations' : 'observations'}</small>${item.unknownCount ? `<small>${ctx.actions.num(item.unknownCount)} legacy qualification unavailable</small>` : ''}</span></li>`,
            )
            .join(
              '',
            )}</ol>${(model.findingCount ?? model.findings.length) > 6 ? `<a class="dossier-link" href="#eclipse?entity=${encode(entity.id)}">${ctx.actions.num((model.findingCount ?? model.findings.length) - 6)} more findings</a>` : ''}`
        : '<p class="dossier-quiet">No findings recorded.</p>'
    }</section></div><aside class="dossier-overview-side"><section class="dossier-notifications"><div class="dossier-section-head"><div><span class="dossier-kicker">Outreach history</span><h2>Notifications<span class="dossier-inline-count">${list(entity.cases).length}</span></h2></div></div>${open ? `<p class="dossier-quiet">${open} active</p>` : ''}${dossierCaseRows(list(entity.cases).slice(0, 4))}${list(entity.cases).length > 4 ? `<a class="dossier-link" href="#entity/${encode(entity.id)}?tab=history">All notification history ${ctx.actions.icon('arrow')}</a>` : ''}</section>${profile.notes ? `<section class="dossier-note"><span class="dossier-kicker">Entity notes</span><p>${esc(profile.notes.length > 350 ? profile.notes.slice(0, 350) + '…' : profile.notes)}</p><a class="dossier-link" href="#entity/${encode(entity.id)}?tab=details">View details ${ctx.actions.icon('arrow')}</a></section>` : ''}</aside></div>`;
  }

  function entityUpdateMarkup() {
    const lead = ctx.state.editor.currentLead,
      current = lead?.current_entity;
    if (!current || lead.case?.stage !== 'in_progress') return '';
    const previous = lead.entity_profile || {},
      latest = current.entity_profile || {};
    const changed =
      (current.company || current.domain) !== (lead.company || lead.domain) ||
      current.domain !== lead.domain ||
      ['address', 'city', 'state'].some((key) => (previous[key] || '') !== (latest[key] || ''));
    return changed
      ? '<div class="notice"><span>Entity details have changed. This report retains its reviewed business details until you adopt the update. Review the changes and reopen only affected sections in one step.</span><button class="button small" data-action="use-entity-details">Review entity update</button></div>'
      : '';
  }

  function entityAttributionMarkup(entity) {
    return `<section class="panel"><div class="panel-head"><h2>Attribution</h2></div><div class="panel-body">${
      list(entity.attribution_summaries)
        .map(
          (record) =>
            `<article><h3>${esc(record.root_domain)}</h3><p><strong>${esc(record.reported_ip)} → ${esc(record.validated_ip)}</strong> · ${esc(record.source_name)}</p><p>${esc(record.match_summary)}</p><small>${ctx.actions.stamp(record.validated_at)}</small><details><summary>Source details</summary><pre>${esc(JSON.stringify(record.details, null, 2))}</pre></details></article>`,
        )
        .join('') || '<p class="muted">No attribution recorded.</p>'
    }</div></section><details class="panel"><summary>Saved IP associations (${list(entity.ip_associations).length})</summary><div class="panel-body"><div class="key-value">${list(
      entity.ip_associations,
    )
      .map(
        (record) =>
          `<span>${esc(record.ip)}</span><strong>${ctx.actions.stamp(record.recorded_at)}</strong>`,
      )
      .join(
        '',
      )}</div><form id="entity-ip-form" data-entity="${esc(entity.id)}" class="actions"><label for="entity-associated-ip">IP</label><input id="entity-associated-ip" name="ip" required aria-label="IP associated with this entity"><button class="button" type="submit">Save association</button></form></div></details>`;
  }

  async function entitiesPage(params = new URLSearchParams()) {
    const renderId = ctx.state.navigation.renderId;
    const q = params.get('q') || '',
      review = params.get('review_required') === 'true';
    const rows = await ctx.actions.api(
      '/api/entities?' + new URLSearchParams({ q, ...(review ? { review_required: 'true' } : {}) }),
    );
    if (renderId !== ctx.state.navigation.renderId) return '';
    ctx.state.contacts.batchEntityIds = rows.map((r) => r.id);
    for (const row of rows) ctx.state.contacts.entityNames.set(row.id, entityName(row));
    ctx.state.entities.directoryRows = rows;
    return `<section class="dossier-index entity-index"><header class="dossier-index-head"><div><h1>Entities</h1></div><div class="dossier-index-count"><strong>${ctx.actions.num(rows.length)}</strong><span>in this view</span></div></header><div class="dossier-index-tools"><form id="entity-search" class="dossier-filter-form">${ctx.actions.icon('search')}<input name="q" value="${esc(q)}" aria-label="Search entities" placeholder="Name or hostname"><select name="review_required" aria-label="Entity information filter" data-submit-filter><option value="" ${!review ? 'selected' : ''}>All entities</option><option value="true" ${review ? 'selected' : ''}>Information gaps</option></select><button class="button" type="submit">Search</button></form><div class="entity-contact-tools"><button class="button" data-action="find-all-entity-contacts">Find missing contacts</button><p id="entity-directory-status" role="status"></p></div></div>${rows.length ? `<div class="table-wrap dossier-directory"><table><thead><tr><th scope="col">Entity</th><th scope="col">Address</th><th scope="col">Contact</th><th scope="col">Awareness</th><th scope="col">Information</th></tr></thead><tbody>${rows.map((r) => `<tr data-entity-row="${esc(r.id)}"><td class="dossier-directory-identity"><div><a href="#entity/${encode(r.id)}">${esc(entityName(r))}</a>${r.company && r.company !== r.domain ? `<small>${esc(r.domain)}</small>` : ''}<small>${ctx.actions.num(r.open_cases || 0)} active notifications</small></div></td><td class="entity-directory-address">${esc(r.entity_profile?.address || 'Address not found')}</td><td class="entity-directory-contacts" data-entity-contact="${esc(r.id)}">${directoryContactMarkup(r)}</td><td><strong>${ctx.actions.num(r.finding_count || 0)}<span> findings</span></strong><small>${ctx.actions.num(r.assets || 0)} IPs · ${ctx.actions.num(r.hostname_count || 0)} hostnames</small><small>${ctx.actions.num(r.approved_observations || 0)} admitted observations · ${ctx.actions.num(r.dark_matter_observations || 0)} dark matter${r.legacy_unknown_observation_count ? ` · ${ctx.actions.num(r.legacy_unknown_observation_count)} legacy qualification unavailable` : ''}</small></td><td data-entity-completeness="${esc(r.id)}">${entityGapsMarkup(r)}</td></tr>`).join('')}</tbody></table></div>` : ctx.actions.empty('No entities match', '', ctx.actions.linkButton('#entities', 'Clear filters'))}</section>`;
  }

  async function entityPage(id, params = new URLSearchParams()) {
    const renderId = ctx.state.navigation.renderId;
    const entity = await ctx.actions.api('/api/entities/' + encode(id));
    if (params.get('tab') === 'details') {
      try {
        entity.location_choices = await ctx.actions.api(
          '/api/entity-locations?state=' +
            encode(entity.entity_profile?.state || '') +
            '&q=' +
            encode(entity.entity_profile?.city || ''),
        );
      } catch (error) {
        if (error.name === 'AbortError') throw error;
        entity.location_choices = { states: [], cities: [], unavailable: true };
      }
    }
    if (renderId !== ctx.state.navigation.renderId) return '';
    ctx.state.entities.current = entity;
    ctx.state.entities.dirty = false;
    ctx.state.entities.changedForms.clear();
    ctx.state.entities.tab = ['overview', 'details', 'contacts', 'assets', 'history'].includes(
      params.get('tab'),
    )
      ? params.get('tab')
      : 'overview';
    if (
      ['overview', 'assets'].includes(ctx.state.entities.tab) &&
      (entity.dns_connections?.needs_lookup || entity.dns_connections?.running)
    ) {
      setTimeout(() => {
        if (
          renderId === ctx.state.navigation.renderId &&
          ctx.state.entities.current?.id === entity.id
        )
          void refreshEntityDns(false);
      }, 0);
    }
    return independentEntityMarkup();
  }

  function entityAssetsMarkup(entity) {
    return `<section class="panel"><div class="panel-head"><h2>Associated domains and hostnames</h2></div><div class="panel-body"><div class="key-value">${list(
      entity.associated_assets,
    )
      .map(
        (a) =>
          `<span>${esc(a.hostname)}</span><small>${esc(a.association_basis === 'manual' ? 'Manually associated' : a.association_basis || 'Observed asset')} <button class="button small" data-action="transfer-entity-asset" data-hostname="${esc(a.hostname)}">Transfer ownership</button></small>`,
      )
      .join('')}</div>${list(entity.domain_groups)
      .filter((g) => g.current_association !== 0)
      .map(
        (g) =>
          `<p><strong>${esc(g.root_domain)}</strong> <button class="button small" data-action="transfer-entity-asset" data-hostname="${esc(g.root_domain)}">Transfer entire domain</button></p>`,
      )
      .join(
        '',
      )}<form id="entity-asset-form" data-entity="${esc(entity.id)}" class="actions"><label for="entity-associated-hostname">Domain / hostname</label><input id="entity-associated-hostname" name="hostname" required maxlength="253" placeholder="example.com" aria-label="Domain or hostname to associate"><button class="button" type="submit">Associate asset</button></form><p class="section-note">Old and new domains can belong to this entity. An association does not create a vulnerability finding. Transfers preserve earlier business evidence and notification history.</p>${
      list(entity.awareness_findings).some((f) => f.workflow === 'ignored' && f.can_reactivate)
        ? `<section><h3>Dismissed findings</h3><ul>${list(entity.awareness_findings)
            .filter((f) => f.workflow === 'ignored' && f.can_reactivate)
            .map(
              (f) =>
                `<li>${esc(f.condition)} · ${esc(f.hostname)} <button class="button small" data-action="reactivate-entity-finding" data-finding="${esc(f.id)}">Review restoration</button></li>`,
            )
            .join('')}</ul></section>`
        : ''
    }</div></section>`;
  }

  function independentEntityMarkup() {
    const e = ctx.state.entities.current,
      tab = ctx.state.entities.tab,
      profile = e.entity_profile || {};
    const model = entityDossierModel(e);
    const back = ctx.state.navigation.returns.get('entities') || 'entities';
    const location = [profile.city, profile.state].filter(Boolean).join(', ');
    const head = `<header class="dossier-masthead"><div class="dossier-topline"><a class="page-back" href="#${esc(back)}">${ctx.actions.icon('back')}Entities</a><span class="dossier-kicker">Entity profile</span><a class="dossier-link" href="#eclipse?entity=${encode(e.id)}">Explore ${ctx.actions.icon('arrow')}</a></div><div class="dossier-identity"><div><h1>${esc(entityName(e))}</h1><p>${esc(e.domain)}${location ? `<span aria-hidden="true">/</span>${esc(location)}` : ''}</p></div><div class="dossier-identity-meta">${e.entity_review?.required ? `<a href="#entity/${encode(e.id)}?tab=details" class="dossier-review-link">Review details ${ctx.actions.icon('arrow')}</a>` : ''}${model.observedTo ? `<span>Last observed <strong>${esc(model.observedTo)}</strong></span>` : ''}</div></div><div class="dossier-numbers"><span><strong>${ctx.actions.num(model.hostCount)}</strong> hostnames</span><span><strong>${ctx.actions.num(model.ipCount)}</strong> IPs</span><span><strong>${ctx.actions.num(model.entryCount)}</strong> observations</span>${e.awareness ? `<span>${ctx.actions.num(model.approvedCount)} admitted / ${ctx.actions.num(model.darkMatterCount)} dark matter${model.unknownCount ? ` / ${ctx.actions.num(model.unknownCount)} legacy qualification unavailable` : ''}</span>` : ''}<a href="#leads?q=${encode(e.domain)}">Incoming leads ${ctx.actions.icon('arrow')}</a></div></header>`;
    const tabs = `<nav class="dossier-tabs record-tabs" aria-label="Entity views">${[
      ['overview', 'Overview'],
      ['contacts', 'Contacts'],
      ['assets', 'Assets'],
      ['history', 'History'],
      ['details', 'Details / edit'],
    ]
      .map(
        ([key, label]) =>
          `<a href="#entity/${encode(e.id)}?tab=${key}" ${tab === key ? 'class="active" aria-current="page"' : ''}>${label}</a>`,
      )
      .join('')}</nav>`;
    let content;
    if (tab === 'overview') content = dossierOverview(e, model);
    else if (tab === 'contacts')
      content = `<div class="dossier-contact-layout">${ctx.actions.contactDiscoveryMarkup(e)}<aside class="dossier-contact-editor"><span class="dossier-kicker">Entity record</span><h2>Saved contact.</h2><form id="entity-contact-form" data-entity="${esc(e.id)}" class="form-grid">${ctx.actions.field('Name / team', 'contact_name', profile.contact_name, { draft: false, full: true })}${ctx.actions.field('Role', 'contact_title', profile.contact_title, { draft: false, full: true })}${ctx.actions.field('Email', 'contact_email', profile.contact_email, { draft: false, type: 'email', full: true })}${ctx.actions.field('Phone', 'contact_phone', profile.contact_phone, { draft: false, full: true })}<div class="full actions"><button class="button primary" type="submit">Save contact</button><span id="entity-save-state" class="save-note" role="status">Saved</span></div></form></aside></div>`;
    else if (tab === 'assets')
      content = `<div class="dossier-assets">${entityAssetsMarkup(e)}${entityConstellationMarkup(e, model)}<section class="dossier-findings"><div class="dossier-section-head"><h2>Source observations</h2><span>${ctx.actions.num(list(e.entries).length)} rows</span></div><div class="table-wrap"><table><thead><tr><th>Hostname / IP</th><th>Finding</th><th>Version</th><th>Observed</th><th>Source</th></tr></thead><tbody>${list(
        e.entries,
      )
        .map((entry) => {
          const f = entry.source?.fields || entry;
          return `<tr><td><strong>${esc(entry.hostname || f.hostname || 'Hostname not reported')}</strong><small>${esc(entry.ip || f.ip)}</small></td><td>${esc(entry.tag || f.tag || 'Not reported')}</td><td>${esc(observedVersion(entry) || 'Not reported')}</td><td>${esc(String(f.timestamp || '').slice(0, 10))}</td><td>${entry.id ? `<a class="dossier-link" href="/api/eclipse/observations/${encode(entry.id)}" target="_blank" rel="noopener noreferrer">${esc(entry.source?.sheet || 'Source')} · ${esc(entry.source?.row ?? '')}${ctx.actions.icon('arrow')}</a>` : esc(entry.source?.workbook || '')}</td></tr>`;
        })
        .join(
          '',
        )}</tbody></table></div></section><div class="dossier-attribution">${entityAttributionMarkup(e)}</div></div>`;
    else if (tab === 'history')
      content = `<div class="dossier-history-layout"><section><div class="dossier-section-head"><h2>Notifications.</h2><a class="dossier-link" href="#workspace/notifications?q=${encode(e.domain)}">Open workspace ${ctx.actions.icon('arrow')}</a></div>${dossierCaseRows(e.cases)}</section><section><div class="dossier-section-head"><h2>Activity.</h2></div>${ctx.actions.activities(list(e.history))}</section></div>`;
    else {
      const f = (label, name, value, options = {}) =>
        ctx.actions.entityReviewField(label, name, value, { draft: false, ...options });
      content = `<div class="dossier-edit-layout"><section><span class="dossier-kicker">Entity record</span><h2>Edit details.</h2><form id="entity-details-form" data-entity="${esc(e.id)}" class="form-grid">${f('Name', 'name', entityName(e), { required: true, full: true })}${f('Mailing address', 'address', profile.address, { area: true, full: true })}${f('City', 'city', profile.city).replace('name="city"', 'name="city" list="entity-city-options" autocomplete="address-level2"')}${f('State', 'state', profile.state).replace('name="state"', 'name="state" list="entity-state-options" autocomplete="address-level1"')}${e.location_choices?.unavailable ? '<p class="section-note">Location suggestions are unavailable. Enter the city and state; they will be checked when saved.</p>' : ''}<datalist id="entity-state-options">${list(
        e.location_choices?.states,
      )
        .map((r) => `<option value="${esc(r.code)}">${esc(r.name)}</option>`)
        .join('')}</datalist><datalist id="entity-city-options">${list(e.location_choices?.cities)
        .map((r) => `<option value="${esc(r.city)}">${esc(r.state)}</option>`)
        .join(
          '',
        )}</datalist>${ctx.actions.field('Notes', 'notes', profile.notes, { draft: false, area: true, full: true })}<div class="full actions"><button class="button primary" type="submit">Save details</button><span id="entity-save-state" class="save-note" role="status">Saved</span></div></form></section><aside><span class="dossier-kicker">Record management</span><p>${esc(e.domain)}</p><details class="dossier-tools"><summary>Combine entities</summary><p>Retain these observations and history under another entity.</p><button class="button" data-action="combine-entity">Combine with another entity</button></details></aside></div>`;
    }
    return `<section class="entity-dossier" data-entity-id="${esc(e.id)}" data-dossier-tab="${esc(tab)}">${head}${tabs}${content}</section>`;
  }
  const actions = {
    loadEntityContactOverviews,
    findAllEntityContacts,
    refreshDirectoryContact,
    directoryContactMarkup,
    entityGapsMarkup,
    entitiesPage,
    entityPage,
    independentEntityMarkup,
    entityUpdateMarkup,
    entityDossierModel,
    entityConstellationMarkup,
    entityDnsMarkup,
    refreshEntityDns,
    sharedIpMarkup,
    leadTable,
    leadsPage,
  };
  Object.assign(ctx.actions, actions);
  return actions;
}
