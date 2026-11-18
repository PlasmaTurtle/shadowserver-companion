/** Editor interactions. No browser listeners or startup side effects. */
export function createHandlers(ctx) {
  return {
    input(e) {
      if (e.target.matches('[data-draft]')) {
        ctx.state.editor.draft[e.target.name] =
          e.target.type === 'checkbox' ? e.target.checked : e.target.value;
        if (e.target.name !== 'reviewed') ctx.state.editor.draft.reviewed = false;
        ctx.actions.markDirty();
      }
      const el = e.target;
      if (el.matches('[data-draft]') && el.name === 'report_date') ctx.actions.scheduleNarrative();
      if (el.dataset.finding) {
        ctx.state.editor.draft.narrative_values ??= {};
        ctx.state.editor.draft.narrative_values[el.dataset.finding] ??= {};
        ctx.state.editor.draft.narrative_values[el.dataset.finding][el.dataset.findingField] =
          el.value;
        ctx.state.editor.draft.reviewed = false;
        ctx.actions.markDirty();
        ctx.actions.scheduleNarrative();
      }
      if (el.dataset.cveField) {
        const value = ctx.state.editor.draft.cve_dispositions[el.dataset.cveId];
        value[el.dataset.cveField] = el.value;
        if (el.dataset.cveField === 'description') value.evidence_text = el.value;
        ctx.state.editor.draft.reviewed = false;
        ctx.actions.markDirty();
      }
      if (el.dataset.blockEdit) {
        ctx.state.editor.draft.explainer_overrides ??= {};
        ctx.state.editor.draft.explainer_overrides[el.dataset.blockEdit] ??= {};
        ctx.state.editor.draft.explainer_overrides[el.dataset.blockEdit][el.dataset.blockField] =
          el.value;
        ctx.state.editor.draft.reviewed = false;
        ctx.actions.markDirty();
      }
      if (el.dataset.template) {
        ctx.state.editor.draft.report_template ??= {
          id: 'standard',
          version: 1,
          marking: 'For Informational Purposes Only',
          font_size: 9.5,
        };
        ctx.state.editor.draft.report_template[el.dataset.template] =
          el.dataset.template === 'font_size' ? Number(el.value) : el.value;
        ctx.state.editor.draft.reviewed = false;
        ctx.actions.markDirty();
      }
    },
    change: [
      {
        matches: (el, e) => el.id === 'outreach-template',
        run: async (el, e) => {
          ctx.state.editor.draft.outreach_template = el.value;
          ctx.state.editor.draft.reviewed = false;
          ctx.actions.markDirty();
          ctx.actions.scheduleNarrative();
        },
      },
      {
        matches: (el, e) => el.id === 'cve-signal-filter',
        run: async (el, e) => {
          ctx.state.editor.cveSignalFilter = el.value;
          ctx.actions.$('#editor-content').innerHTML = ctx.actions.editorContent();
          return;
        },
      },
      {
        matches: (el, e) => el.dataset.ssvcId,
        run: async (el, e) => {
          if (ctx.actions.sectionLocked('vulnerabilities')) return;
          ctx.state.editor.draft.selected_ssvc_assessments ??= {};
          if (el.value)
            ctx.state.editor.draft.selected_ssvc_assessments[el.dataset.ssvcId] = el.value;
          else delete ctx.state.editor.draft.selected_ssvc_assessments[el.dataset.ssvcId];
          ctx.state.editor.draft.reviewed = false;
          ctx.actions.markDirty();
          ctx.actions.$('#editor-content').innerHTML = ctx.actions.editorContent();
          return;
        },
      },
      {
        matches: (el, e) => el.dataset.block,
        run: async (el, e) => {
          ctx.state.editor.draft.selected_explainers = el.checked
            ? [...new Set([...ctx.state.editor.draft.selected_explainers, el.dataset.block])]
            : ctx.state.editor.draft.selected_explainers.filter((id) => id !== el.dataset.block);
          ctx.state.editor.draft.explainer_snapshots ??= [];
          if (
            el.checked &&
            !ctx.state.editor.draft.explainer_snapshots.some((b) => b.id === el.dataset.block)
          ) {
            const block = ctx.state.navigation.boot.explainers.find(
              (b) => b.id === el.dataset.block,
            );
            if (block) ctx.state.editor.draft.explainer_snapshots.push(structuredClone(block));
          }
          ctx.state.editor.draft.reviewed = false;
          ctx.actions.markDirty();
          ctx.actions.$('#editor-content').innerHTML = ctx.actions.editorContent();
        },
      },
      {
        matches: (el, e) => el.dataset.cveDisposition,
        run: async (el, e) => {
          ctx.state.editor.draft.cve_dispositions ??= {};
          if (el.value === 'source')
            delete ctx.state.editor.draft.cve_dispositions[el.dataset.cveDisposition];
          else
            ctx.state.editor.draft.cve_dispositions[el.dataset.cveDisposition] = {
              ...(ctx.state.editor.draft.cve_dispositions[el.dataset.cveDisposition] || {}),
              action: el.value,
              ...(el.value === 'fallback'
                ? {
                    retrieved_at:
                      ctx.state.editor.draft.cve_dispositions[el.dataset.cveDisposition]
                        ?.retrieved_at || new Date().toISOString(),
                  }
                : {}),
            };
          ctx.state.editor.draft.reviewed = false;
          ctx.actions.markDirty();
          ctx.actions.$('#editor-content').innerHTML = ctx.actions.editorContent();
        },
      },
      {
        matches: (el, e) => el.dataset.evidence,
        run: async (el, e) => {
          if (ctx.actions.sectionLocked('attribution') || el.disabled) return;
          const context = ctx.actions.notificationContext();
          const item = ctx.state.editor.currentLead.evidence.find(
            (x) => x.id === el.dataset.evidence,
          );
          if (!item) return;
          const included = el.checked;
          el.disabled = true;
          try {
            if (ctx.state.editor.dirty) await ctx.actions.saveDraft();
            if (!ctx.actions.notificationContextCurrent(context)) return;
            const saved = ctx.actions.notificationContext();
            const url = ctx.actions.leadURL('');
            await ctx.actions.api('/api/evidence/' + item.id, {
              method: 'PUT',
              body: {
                included,
                caption: item.caption,
                source_url: item.source_url,
                captured_at: item.captured_at,
              },
            });
            if (!ctx.actions.notificationContextCurrent(saved)) return;
            const value = await ctx.actions.api(url);
            ctx.actions.applyNotificationMutation(value, saved);
          } catch (err) {
            el.checked = item.included;
            ctx.actions.toast(err.message, true);
          } finally {
            el.disabled = false;
          }
        },
      },
    ],
    click: [
      {
        matches: (el, e) =>
          el.dataset.openLead && !e.target.closest('a,input,select,textarea,button,label'),
        run: async (el, e) => {
          location.hash = 'entity/' + el.dataset.openLead;
          return;
        },
      },
      {
        matches: (el, e) => el.dataset.tab,
        run: async (el, e) => {
          if (el.dataset.tab === 'entity') {
            location.hash = 'entity/' + encodeURIComponent(ctx.state.editor.currentLead.id);
            return;
          }
          if (ctx.state.workflow.workflowDirty && !confirm('Leave this form without saving?'))
            return;
          ctx.state.workflow.workflowDirty = false;
          ctx.state.workflow.changedCaseForms.clear();
          ctx.actions.stopContactDiscoveryPolling();
          ctx.state.editor.tab = el.dataset.tab;
          if (ctx.state.editor.currentLead?.case_id) {
            const route =
              'workspace/notifications/' +
              encodeURIComponent(ctx.state.editor.currentLead.case_id) +
              '?tab=' +
              encodeURIComponent(el.dataset.tab);
            globalThis.history?.pushState?.(null, '', '#' + route);
            ctx.state.navigation.currentRoute = route;
          }
          ctx.actions.$('#main').innerHTML = ctx.actions.leadMarkup();
          ctx.actions.$('#editor-tab-' + ctx.state.editor.tab)?.focus?.();
          if (ctx.state.editor.tab === 'assets') void ctx.actions.loadAssetAttribution();
          if (ctx.state.editor.tab === 'contact') void ctx.actions.loadContactDiscovery();
          return;
        },
      },
      {
        matches: (el, e) => el.dataset.reportSection,
        run: async (el, e) => {
          ctx.state.editor.reportSection = el.dataset.reportSection;
          ctx.actions.$('#editor-content').innerHTML = ctx.actions.editorContent();
          ctx.actions.$(`[data-report-section="${ctx.state.editor.reportSection}"]`)?.focus();
          if (ctx.state.editor.reportSection === 'Vulnerabilities') ctx.actions.scheduleNarrative();
          return;
        },
      },
      {
        matches: (el, e) => el.dataset.entry !== undefined,
        run: async (el, e) => {
          const item = ctx.state.editor.currentLead.entries[Number(el.dataset.entry)];
          ctx.actions.modal(
            'Original row · ' + item.ip,
            `<p class="muted">${ctx.actions.esc(item.source.workbook)} · ${ctx.actions.esc(item.source.sheet)} · row ${item.source.row}</p><pre>${ctx.actions.esc(JSON.stringify(item.source.fields, null, 2))}</pre>`,
          );
          return;
        },
      },
    ],
    actions: {
      'capture-website': () => ctx.actions.captureWebsite(),
      'cancel-website-capture': () => ctx.actions.cancelWebsiteCapture(),
      'open-contact-activity': () => {
        const disclosure = ctx.actions.$('#contact-activity-compose');
        if (!disclosure) return;
        disclosure.open = true;
        disclosure.scrollIntoView?.({ block: 'nearest', behavior: 'auto' });
        ctx.actions.$('#attempt-outcome')?.focus?.({ preventScroll: true });
      },
      'report-activity': async () => ctx.actions.showReportActivity(),
      save: async (el) => {
        await ctx.actions.saveDraft();
        ctx.actions.toast('Draft saved.');
      },
      'validate-section': async (el) => {
        await ctx.actions.validateSection(el.dataset.section);
      },
      'reopen-section': async (el) => {
        ctx.actions.openSectionReason(el.dataset.section);
      },
      preview: async () => {
        await ctx.actions.previewReport();
      },
      finalize: async (el) => {
        return ctx.actions.reportOperation(
          'Certifying notification report',
          async (options, isCurrent) => {
            if (ctx.state.editor.dirty || ctx.state.editor.currentLead.status === 'new')
              await ctx.actions.saveDraft(options);
            if (!isCurrent()) return;
            const missing = ctx.state.editor.currentLead.readiness.filter((c) => !c.ok);
            if (missing.length) {
              ctx.actions.toast(
                'Finish these checks: ' + missing.map((c) => c.label).join('; '),
                true,
              );
              return;
            }
            const r = await ctx.actions.api(ctx.actions.leadURL('/finalize'), {
              ...options,
              method: 'POST',
            });
            if (!isCurrent() || ctx.state.editor.dirty) {
              ctx.actions.toast(
                'Report certified. Refresh that notification to view its saved revision.',
              );
              return;
            }
            ctx.state.editor.dirty = false;
            await ctx.actions.route(true);
            if (!isCurrent()) return;
            ctx.actions.modal(
              'Report certified',
              `<div class="notice">${ctx.actions.icon('check')}Revision ${ctx.actions.esc(r.revision)} is certified and ready for delivery. Record outreach in Contact &amp; delivery.</div><div class="modal-actions"><a class="button primary" href="/api/reports/${r.id}/docx">${ctx.actions.icon('download')}Download DOCX</a><a class="button" href="/api/reports/${r.id}/pdf" target="_blank" rel="noopener">Open PDF</a><a class="button primary" href="/api/reports/${r.id}/recipient-zip">Recipient package</a><a class="button" href="/api/reports/${r.id}/zip">Evidence & records</a>${r.supporting_appendix_available ? `<a class="button" href="/api/reports/${r.id}/appendix-pdf" target="_blank" rel="noopener">Supporting appendix PDF</a><a class="button" href="/api/reports/${r.id}/appendix-docx">Supporting appendix DOCX</a>` : ''}</div>`,
            );
          },
        );
      },

      cves: async (el) => {
        await ctx.actions.retrieveCveSources();
      },
      'refresh-cves': async () => {
        await ctx.actions.retrieveCveSources({ refresh: true });
      },
      'search-report-catalog': () => ctx.actions.openReportCatalog(),
      'retrieve-catalog-cve': async (el) => {
        if (ctx.actions.sectionLocked('vulnerabilities')) return;
        await ctx.actions.retrieveCveSources({ cveIds: [el.dataset.cveId] });
      },
      'review-cves': async (el) => {
        ctx.actions.showCveRefreshReview();
      },
      'cancel-cve-refresh': async (el) => {
        if (ctx.state.editor.pendingCveRefresh) {
          ctx.state.editor.pendingCveRefresh.cancelled = true;
          if (ctx.state.editor.pendingCveRefresh.jobId)
            await ctx.actions.api(
              '/api/source-jobs/' + ctx.state.editor.pendingCveRefresh.jobId + '/cancel',
              { method: 'POST' },
            );
        }
        ctx.actions.toast('Retrieval will stop after the current request.');
      },
      'adopt-cves': async (el) => {
        ctx.actions.adoptCveSources();
      },
      'adopt-presentation': async (el) => {
        if (ctx.state.editor.dirty) await ctx.actions.saveDraft();
        ctx.actions.modal(
          'Adopt current report format',
          `<p>Update this draft to the current report format and sender identity from Settings. Reopen affected frozen sections first. Certified reports remain unchanged.</p><form id="presentation-adopt-form"><div class="field"><label for="presentation-reason">Reason</label><textarea id="presentation-reason" name="reason" required rows="3"></textarea></div><div class="modal-actions"><button class="button primary" type="submit">Adopt report format</button></div></form>`,
        );
      },
      'adopt-blocks': async (el) => {
        if (ctx.actions.sectionLocked('information')) return;
        const context = ctx.actions.notificationContext();
        const latest = await ctx.actions.api('/api/explainers');
        if (
          !ctx.actions.notificationContextCurrent(context) ||
          ctx.actions.sectionLocked('information')
        )
          return;
        ctx.state.navigation.boot.explainers = latest;
        const snapshots = new Map(
          (ctx.state.editor.draft.explainer_snapshots || []).map((b) => [b.id, b]),
        );
        for (const b of latest)
          if (ctx.state.editor.draft.selected_explainers.includes(b.id))
            snapshots.set(b.id, structuredClone(b));
        ctx.state.editor.draft.explainer_snapshots = [...snapshots.values()];
        ctx.state.editor.draft.reviewed = false;
        ctx.actions.markDirty();
        ctx.actions.$('#editor-content').innerHTML = ctx.actions.editorContent();
        ctx.actions.toast(
          'Latest library text added to this notification. Review before certifying.',
        );
      },
    },
    forms: {
      'report-catalog-search-form': (_form, obj) =>
        ctx.actions.searchReportCatalog(obj.query || ''),
      'evidence-form': async (form, obj, data, reviewDecision) => {
        if (ctx.actions.sectionLocked('attribution')) return;
        const context = ctx.actions.notificationContext();
        if (ctx.state.editor.dirty) await ctx.actions.saveDraft();
        if (!ctx.actions.notificationContextCurrent(context)) return;
        const saved = ctx.actions.notificationContext();
        data.set('captured_at', obj.captured_at + ':00Z');
        const value = await ctx.actions.api(ctx.actions.leadURL('/evidence'), {
          method: 'POST',
          body: data,
        });
        if (ctx.actions.applyNotificationMutation(value, saved))
          ctx.actions.toast('Evidence attached.');
      },
      'delivery-form': async (form, obj, data, reviewDecision) => {
        await ctx.actions.api('/api/reports/' + form.dataset.report + '/delivery', {
          method: 'POST',
          body: { ...obj, sent_at: obj.sent_at + ':00Z' },
        });
        ctx.actions.closeModal();
        ctx.actions.toast('Delivery recorded.');
        await ctx.actions.route(true);
      },
    },
  };
}
