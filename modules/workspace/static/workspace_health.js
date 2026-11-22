/** Workspace diagnostics remain separate from unsaved Settings preferences. */
export function install(ctx) {
  let pollRevision = 0;
  const esc = (value) => ctx.actions.esc(String(value ?? ''));
  const bytes = (value) => `${(Number(value || 0) / 1024 / 1024).toFixed(2)} MiB`;

  function workspaceHealthPanel(pending) {
    return `<section class="panel"><div class="panel-head"><div><h2>Workspace health &amp; storage</h2><p>Check databases, retained evidence, report ownership and reference freshness.</p></div></div><div class="panel-body"><div class="settings-data-actions"><button class="button full-width" type="button" data-action="check-workspace" ${pending ? 'disabled' : ''}>Check workspace</button><button class="button full-width" type="button" data-action="review-workspace-cleanup" ${pending ? 'disabled' : ''}>Review safe cleanup</button><button class="button full-width" type="button" data-action="export-diagnostics">Export diagnostic summary</button></div><div id="workspace-health-result" role="status" aria-live="polite"></div><p class="help">Checks run in the background. The diagnostic export excludes report contents, contacts, credentials and logs.</p><details class="settings-help"><summary>Recovery when the app cannot open</summary><p>Close the app and use the workspace recovery command from its installation folder. It checks a selected backup before replacement and keeps the entire previous workspace.</p><code class="code-path">runtime\\python.exe -m modules.workspace.components.workspace_recovery --data-dir "WORKSPACE" check</code><p class="help">Use restore BACKUP.zip --confirm RESTORE to restore, or compact --confirm COMPACT to reclaim unused database pages after a verified restore point is saved.</p></details></div></section>`;
  }

  function healthMarkup(job) {
    if (job.status === 'running')
      return `<p>${esc(job.phase || 'Checking workspace…')}</p><button class="button" type="button" data-action="cancel-workspace-health">Cancel check</button>`;
    if (job.status !== 'completed')
      return `<p>${esc(job.message || 'No workspace check recorded this session.')}</p>`;
    const health = job.result;
    const core = health.stores.find((item) => item.store === 'workspace');
    const index = core?.counts?.analytical_index;
    const incompatibleIndex = Object.values(index?.differences || {}).some(
      (difference) => difference.schema_mismatch,
    );
    const stores = health.stores
      .map(
        (item) =>
          `<li><strong>${esc(item.store)}</strong>: ${esc(item.status.replaceAll('_', ' '))}${item.schema === null ? '' : ` · schema ${esc(item.schema)} / ${esc(item.supported_schema)}`}<br>${bytes(item.database_bytes)} database · ${bytes(item.wal_bytes)} WAL${item.message ? `<p>${esc(item.message)}</p>` : ''}${
            item.feeds
              ? `<ul>${Object.entries(item.feeds)
                  .map(
                    ([name, feed]) =>
                      `<li>${esc(name.toUpperCase())}: ${feed.stale ? 'stale or unavailable' : 'current'} · ${esc(feed.last_success_at || 'never updated')}</li>`,
                  )
                  .join('')}</ul>`
              : ''
          }</li>`,
      )
      .join('');
    const storage = Object.entries(health.storage)
      .map(
        ([name, item]) =>
          `<li>${esc(name.replaceAll('_', ' '))}: ${item.status === 'error' ? esc(item.message) : `${bytes(item.bytes)} · ${esc(item.files)} files`}</li>`,
      )
      .join('');
    return `<h3>${health.ok ? 'Workspace checks passed' : 'Workspace needs attention'}</h3><p class="help">Checked ${esc(ctx.actions.stamp(health.checked_at))}. Each database uses its own committed read snapshot.</p><ul>${stores}</ul>${health.warnings?.length ? `<ul>${health.warnings.map((message) => `<li>${esc(message)}</li>`).join('')}</ul>` : ''}<details class="settings-help"><summary>Storage usage</summary><ul>${storage}</ul><p>Free disk: ${bytes(health.free_disk_bytes)}</p></details><p>Last verified backup: ${esc(ctx.actions.stamp(health.last_verified_backup?.verified_at))}</p>${health.query_planner ? `<p>Query planner maintenance: ${esc(health.query_planner.state || 'not recorded')}</p>` : ''}${index?.available ? `<p>Analytical counters: ${incompatibleIndex ? 'incompatible table layout' : index.healthy ? 'verified' : 'need rebuilding'}</p>${index.healthy || incompatibleIndex ? '' : '<button type="button" class="button" data-action="rebuild-workspace-index">Rebuild analytical counters</button>'}` : ''}`;
  }

  async function checkWorkspaceHealth() {
    const target = ctx.actions.$('#workspace-health-result');
    if (!target) return;
    const revision = ++pollRevision;
    target.innerHTML = '<p>Starting workspace check…</p>';
    const render = async (job) => {
      if (revision !== pollRevision || ctx.actions.$('#workspace-health-result') !== target) return;
      target.innerHTML = healthMarkup(job);
      if (job.status === 'running') {
        setTimeout(async () => {
          if (revision !== pollRevision || ctx.actions.$('#workspace-health-result') !== target)
            return;
          try {
            await render(await ctx.actions.api('/api/data/health'));
          } catch (error) {
            if (ctx.actions.$('#workspace-health-result') === target)
              target.textContent = error.message;
          }
        }, 700);
      }
    };
    await render(await ctx.actions.api('/api/data/health', { method: 'POST' }));
  }

  async function cancelWorkspaceHealth() {
    await ctx.actions.api('/api/data/health', { method: 'DELETE' });
    ctx.actions.toast('Workspace check is stopping. Saved data is unchanged.');
  }

  async function reviewWorkspaceCleanup() {
    const target = ctx.actions.$('#workspace-health-result');
    const plan = await ctx.actions.api('/api/data/maintenance');
    if (ctx.actions.$('#workspace-health-result') !== target) return;
    ctx.actions.modal(
      'Review safe cleanup',
      `<form id="workspace-cleanup-form" class="form-grid"><p class="full">${esc(plan.lookup_pointers)} expired lookup pointers can be removed (${esc(plan.estimated_payload_bytes)} bytes of row payload). No files will be deleted.</p><p class="full">${esc(plan.policy)}</p><p class="help full">${esc(plan.disk_space_note)}</p><input type="hidden" name="cutoff" value="${esc(plan.cutoff)}"><input type="hidden" name="token" value="${esc(plan.token)}"><div class="field full"><label for="cleanup-confirmation">Type CLEAN to apply this reviewed plan</label><input id="cleanup-confirmation" name="confirmation" pattern="CLEAN" required autocomplete="off"></div><button type="submit" class="button primary" ${plan.lookup_pointers ? '' : 'disabled'}>Remove expired pointers</button></form>`,
    );
  }

  async function applyWorkspaceCleanup(values) {
    const result = await ctx.actions.api('/api/data/maintenance', {
      method: 'POST',
      body: {
        confirmation: values.confirmation,
        cutoff: Number(values.cutoff),
        token: values.token,
      },
    });
    ctx.actions.closeModal();
    ctx.actions.toast(
      `${result.removed} expired lookup pointers removed. Retained evidence and files are unchanged.`,
    );
    await checkWorkspaceHealth();
  }

  function reviewIndexRebuild() {
    ctx.actions.modal(
      'Rebuild analytical counters',
      '<form id="workspace-index-form" class="form-grid"><p class="full">Recreate Observatory counters from saved observations, ownership and admission decisions. Source evidence and historical decisions are retained.</p><div class="field full"><label for="index-confirmation">Type REBUILD to confirm</label><input id="index-confirmation" name="confirmation" pattern="REBUILD" required autocomplete="off"></div><button type="submit" class="button primary">Rebuild counters</button></form>',
    );
  }

  async function rebuildWorkspaceIndex(values) {
    await ctx.actions.api('/api/data/analytical-index/rebuild', {
      method: 'POST',
      body: { confirmation: values.confirmation },
    });
    ctx.actions.closeModal();
    ctx.actions.toast('Analytical counters rebuilt and verified.');
    await checkWorkspaceHealth();
  }

  Object.assign(ctx.actions, {
    workspaceHealthPanel,
    healthMarkup,
    checkWorkspaceHealth,
    cancelWorkspaceHealth,
    reviewWorkspaceCleanup,
    applyWorkspaceCleanup,
    reviewIndexRebuild,
    rebuildWorkspaceIndex,
  });
}
