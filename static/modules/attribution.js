/** Attribution feature. Dependencies and mutable state are provided by the application context. */
export function install(ctx) {
  function highlighted(value, words) {
    const text = String(value ?? ''),
      lower = text.toLowerCase(),
      spans = [];
    for (const word of words) {
      const needle = String(word).toLowerCase();
      if (!needle) continue;
      for (let at = lower.indexOf(needle); at !== -1; at = lower.indexOf(needle, at + 1))
        spans.push([at, at + needle.length]);
    }
    spans.sort((a, b) => a[0] - b[0]);
    const merged = [];
    for (const span of spans) {
      const last = merged[merged.length - 1];
      if (last && span[0] <= last[1]) last[1] = Math.max(last[1], span[1]);
      else merged.push([...span]);
    }
    let end = 0,
      html = '';
    for (const [start, stop] of merged) {
      html +=
        ctx.actions.esc(text.slice(end, start)) +
        '<mark>' +
        ctx.actions.esc(text.slice(start, stop)) +
        '</mark>';
      end = stop;
    }
    return html + ctx.actions.esc(text.slice(end));
  }

  async function reviewsPage() {
    const rows = await ctx.actions.api('/api/reviews');
    ctx.actions.$('#review-count').textContent = rows.length;
    return (
      ctx.actions.heading(
        'Attribution',
        '',
        ctx.actions.linkButton('#data', 'Shadowserver Data', '', 'upload'),
      ) +
      `<section class="panel"><div class="panel-head"><div><h2><span data-review-total>${ctx.actions.num(rows.length)}</span> groups to review</h2></div><span class="badge amber">Analyst decision</span></div>${
        rows.length
          ? `<div class="table-wrap"><table><thead><tr><th>Reported root</th><th>Registration name</th><th>Matching words</th><th>Assets</th><th></th></tr></thead><tbody>${rows
              .map((g) => {
                const best = [...g.matches].sort(
                  (a, b) =>
                    b.details.matched_words.join('').length -
                    a.details.matched_words.join('').length,
                )[0];
                const bestIndex = g.matches.indexOf(best);
                return `<tr data-attribution-review-row="${ctx.actions.esc(g.id)}"><td><button class="text-button" data-group="${g.id}">${ctx.actions.esc(g.domain)}</button><small>${ctx.actions.esc(g.import_name)}</small></td><td>${best ? ctx.actions.highlighted(best.match.value, best.details.matched_words) : 'Saved partial match'}<small>${ctx.actions.esc(best?.source_name || '')} · ${ctx.actions.esc(best?.ip || '')} ${g.lookup_incomplete ? '· Retry also available' : ''}</small></td><td>${best?.details.matched_words.map((w) => `<span class="badge amber">${ctx.actions.esc(w)}</span>`).join(' ') || ''}</td><td><strong>${ctx.actions.num(g.assets)}</strong><small>${ctx.actions.num(g.observations)} observations</small></td><td><div class="actions attribution-quick-actions"><button class="button small primary" data-attribution-decision="accept" data-attribution-group="${ctx.actions.esc(g.id)}" data-result="${ctx.actions.esc(g.attribution_result_id || '')}" data-evidence-index="${bestIndex}" ${bestIndex < 0 || !g.attribution_result_id ? 'disabled' : ''}>Accept</button><button class="button small" data-attribution-decision="dismiss" data-attribution-group="${ctx.actions.esc(g.id)}" data-result="${ctx.actions.esc(g.attribution_result_id || '')}" ${!g.attribution_result_id ? 'disabled' : ''}>Reject</button><button class="button small" data-group="${ctx.actions.esc(g.id)}">Review ${ctx.actions.icon('arrow')}</button></div></td></tr>`;
              })
              .join('')}</tbody></table></div>`
          : ctx.actions.empty(
              'No partial matches awaiting review',
              'New name matches appear here as reports are processed.',
              ctx.actions.linkButton('#data', 'Open imports'),
            )
      }</section>`
    );
  }

  async function showGroup(id) {
    const g = await ctx.actions.api('/api/groups/' + id),
      result = g.attribution_result,
      partials = result?.partial_evidence || [],
      canReview = g.status === 'review';
    const cards = partials
      .map(
        (e, index) =>
          `<article class="match-card"><div class="match-heading">${canReview ? `<input type="radio" name="evidence_index" id="match-${index}" value="${index}" ${index === 0 ? 'checked' : ''}><label for="match-${index}">Use this supporting record</label>` : `<strong>Saved partial match</strong>`}<span class="badge amber">${ctx.actions.esc(e.match.field_type.replaceAll('_', ' '))}</span></div><p class="match-value">${ctx.actions.highlighted(e.match.value, e.details.matched_words)}</p><p><strong>${ctx.actions.highlighted(g.domain, e.details.matched_words)}</strong> · ${ctx.actions.esc(e.ip)}</p><p class="match-words">${e.details.matched_words.map((w) => `<span class="badge amber">${ctx.actions.esc(w)}</span>`).join(' ')}</p><small>${ctx.actions.esc(e.source_name)} · retrieved ${ctx.actions.stamp(e.retrieved_at)}</small><p class="source-path">${ctx.actions.esc(e.match.field_path)} · ${ctx.actions.esc(e.source_url)}</p>${e.details.network_start ? `<small>Registered range: ${ctx.actions.esc(e.details.network_start)} – ${ctx.actions.esc(e.details.network_end)}</small>` : ''}<details><summary>Inspect saved registration response</summary><pre>${ctx.actions.esc(JSON.stringify(g.partial_records?.[e.snapshot_id], null, 2))}</pre></details></article>`,
      )
      .join('');
    ctx.actions.modal(
      g.domain,
      `<div class="inline-stats">${ctx.actions.statusBadge(g.status)}<span>${g.entries.length} retained rows</span></div>${canReview ? '<p>Review the highlighted name and its source. Accepting qualifies this hostname group using the selected original observation.</p>' : ''}${partials.length ? `<form id="attribution-review-form" data-group="${g.id}" data-result="${result.result_id}">${cards}${canReview ? `<div class="field"><label for="review-note">Decision note (optional)</label><textarea id="review-note" name="note" maxlength="2000" rows="2"></textarea></div><div class="modal-actions"><button class="button primary" type="submit" name="decision" value="accept">${ctx.actions.icon('check')}Accept attribution</button><button class="button" type="submit" name="decision" value="dismiss">Dismiss match</button></div>` : ''}</form>` : ''}${g.reviews.map((r) => `<div class="notice"><div><strong>${ctx.actions.esc(r.decision === 'accept' ? 'Accepted' : 'Dismissed')} by ${ctx.actions.esc(r.reviewer)}</strong><small>${ctx.actions.stamp(r.reviewed_at)} · lookup ${ctx.actions.esc(r.result_id.slice(0, 8))}</small><p>${ctx.actions.esc(r.note)}</p>${r.lead_id ? `<a class="text-link" href="#entity/${r.lead_id}" data-close-modal>Open entity</a>` : ''}</div></div>`).join('')}<details ${partials.length ? '' : 'open'}><summary>Lookup history</summary>${g.attempts.map((a) => `<div class="notice"><div><strong>${ctx.actions.esc(a.ip)} · ${ctx.actions.esc(a.method || 'RDAP')} · ${ctx.actions.esc(a.status)}</strong><p>${ctx.actions.esc(a.message || a.reason || a.error || '')}</p>${a.warnings?.length ? `<small>${a.warnings.map(ctx.actions.esc).join('; ')}</small>` : ''}</div></div>`).join('')}</details><div class="modal-actions">${result ? `<a class="button" href="/api/groups/${g.id}/attribution.zip">${ctx.actions.icon('download')}Download evidence</a>` : ''}${g.can_retry ? `<button class="button" data-retry-group="${g.id}" data-result="${ctx.actions.esc(result?.result_id || '')}">${ctx.actions.icon('refresh')}Retry lookups</button>` : ''}</div><details><summary>Original report fields</summary><pre>${ctx.actions.esc(JSON.stringify(g.entries, null, 2))}</pre></details>`,
    );
  }

  function attributionMarkup() {
    const summaries = ctx.state.editor.currentLead.attribution_summaries || [];
    return `<section class="panel"><div class="panel-head"><div><h2>Qualified attribution</h2><p>The reported asset, the supporting match, and where it was validated.</p></div><a class="button small" href="${ctx.actions.leadURL('/attribution.zip')}">${ctx.actions.icon('download')}Evidence bundle</a></div><div class="panel-body">${summaries.length ? summaries.map(ctx.actions.attributionCard).join('') : '<div class="notice warn">A readable attribution summary is not available for this record. Open the preserved evidence bundle to review its support.</div>'}</div></section>`;
  }

  function attributionCard(a) {
    const d = a.details || {},
      supported = a.supported === true,
      network =
        a.covering_network ||
        (d.network_start ? [d.network_start, d.network_end].filter(Boolean).join(' – ') : ''),
      valid = supported && !!(a.validated_ip || network),
      method =
        {
          registration: 'Registration match',
          dns: 'DNS match',
          analyst_review: 'Analyst accepted',
          registrant_approval_reuse: 'Prior approval reused',
        }[a.method] || 'Support not established';
    const facts = [
      ['Matched field', d.matched_field],
      ['Matched value', d.matched_value],
      ['Matched domain', d.matched_domain],
      [
        'Registered network',
        d.network_start ? [d.network_start, d.network_end].filter(Boolean).join(' – ') : '',
      ],
      ['Resolved hostname', d.resolved_hostname],
      ['DNS basis', d.dns_basis],
      ['Resolver results', d.resolver_results],
      ['Lookup result', d.result_id],
      ['Snapshot', d.snapshot_id],
      ['SHA-256', d.body_sha256],
      ['Review note', d.review_note],
      ['Original approval by', d.prior_approval_by],
      ['Original approval at', d.prior_approval_at],
      ['Original approval result', d.approval_source_result_id],
      ['Timing note', d.timestamp_note],
      ['Association reused', a.reuse?.fresh_lookup === false ? a.reuse.recognized_at : ''],
    ].filter(([, value]) => value);
    const source =
      a.source_url && /^https?:\/\//i.test(a.source_url)
        ? `<a class="text-link" href="${ctx.actions.safeHref(a.source_url)}" target="_blank" rel="noopener">${ctx.actions.esc(a.source_name || 'Source record')}${ctx.actions.icon('external')}</a>`
        : `<strong>${ctx.actions.esc(a.source_name || 'Source not recorded')}</strong>`;
    return `<article class="attribution-card ${valid ? 'supported' : 'unresolved'}"><div class="attribution-card-heading"><h3>${ctx.actions.esc(a.root_domain)}</h3><span class="badge ${valid ? 'green' : 'amber'}">${ctx.actions.icon(valid ? 'check' : 'search')}${ctx.actions.esc(valid ? method : 'Support needs review')}</span></div><p class="section-note">${ctx.actions.num(a.supporting_ip_count)} IP used for attribution · ${ctx.actions.num(a.reported_ip_count)} reported IPs included</p><div class="attribution-proof"><div><span class="proof-label">Reported IP</span><strong class="proof-ip">${ctx.actions.esc(a.reported_ip || 'Not recorded')}</strong></div>${ctx.actions.icon('arrow', 'proof-arrow')}<div><span class="proof-label">${network ? 'Covering network' : 'Validated IP'}</span><strong class="proof-ip">${ctx.actions.esc(valid ? network || a.validated_ip : 'Not established')}</strong></div><div class="proof-source"><span class="proof-label">Validated using</span>${source}</div></div><p class="attribution-match">${ctx.actions.icon(valid ? 'check' : 'search')}<span>${ctx.actions.esc(a.match_summary || 'Review the saved source to establish the association.')}</span></p>${d.resolver_comparison ? `<p class="notice ${d.resolver_comparison.status === 'disagreement' ? 'warn' : ''}">${ctx.actions.esc({ agreement: 'Google and Cloudflare DNS agree', disagreement: 'Google and Cloudflare returned different DNS answers', incomplete: 'DNS comparison incomplete — one resolver did not return a comparable answer' }[d.resolver_comparison.status] || 'DNS comparison unavailable')}</p>` : ''}${d.integrity_warning ? `<div class="notice warn">${ctx.actions.esc(d.integrity_warning)}</div>` : ''}<div class="attribution-times"><div><span class="proof-label">${a.validation_kind === 'automatic' ? 'Automatically validated' : a.validation_kind === 'analyst' ? 'Validated by analyst' : 'Validation'}</span><strong>${ctx.actions.timeMarkup(a.validated_at)}</strong><span>${ctx.actions.esc(a.validated_by || 'Author not recorded')}</span></div><div><span class="proof-label">Source retrieved</span><strong>${ctx.actions.timeMarkup(a.retrieved_at)}</strong><span>${a.reuse?.fresh_lookup === false ? 'Historical association reused · no fresh lookup' : a.from_cache ? 'Preserved response · retrieved previously' : 'Preserved source response'}</span></div></div><details class="supporting-details"><summary>View supporting details</summary><dl>${facts.map(([label, value]) => `<dt>${label}</dt><dd>${ctx.actions.esc(typeof value === 'object' ? JSON.stringify(value) : value)}</dd>`).join('')}${a.source_url ? `<dt>Source reference</dt><dd>${ctx.actions.esc(a.source_url)}</dd>` : ''}</dl>${d.raw_record ? `<details><summary>Preserved source response</summary><pre>${ctx.actions.esc(JSON.stringify(d.raw_record, null, 2))}</pre></details>` : ''}</details></article>`;
  }
  Object.assign(ctx.actions, {
    highlighted,
    reviewsPage,
    showGroup,
    attributionMarkup,
    attributionCard,
  });
}
