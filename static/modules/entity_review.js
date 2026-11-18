/** Business-detail reminders; resolving one never saves or rerenders a report draft. */
export function install(ctx) {
  function entityReviewSummary() {
    const required = ctx.state.editor.currentLead?.entity_review?.required;
    return `<p data-entity-review-summary ${required ? '' : 'hidden'}><a class="text-link entity-review-required" href="#entity/${encodeURIComponent(ctx.state.editor.currentLead?.id || '')}?tab=details">Review required: business details</a></p>`;
  }

  function entityFieldReview(name) {
    const entity = ctx.state.entities?.current || ctx.state.editor.currentLead;
    const field = (
      ctx.state.entities?.current || ctx.state.editor.currentLead
    )?.entity_review?.fields.find((item) => item.field === name);
    const button = (action, label) =>
      `<button type="button" class="text-link" data-action="entity-field-review" data-field="${name}" data-review="${action}" aria-label="${label} ${ctx.actions.esc(field?.label || name)}">${label}</button>`;
    let content = '';
    const source = entity?.registry_profile_sources?.[name];
    const sourceURL = /^https?:\/\//i.test(source?.source_url || '') ? source.source_url : '';
    const provenance =
      source && source.value_hash === field?.value_hash
        ? `<span class="entity-registry-source">From registration record${sourceURL ? ` · <a href="${ctx.actions.esc(sourceURL)}" target="_blank" rel="noopener noreferrer">Source</a>` : ''}</span>`
        : '';
    if (entity?.entity_review?.complete) content = '';
    else if (field?.status === 'pending')
      content = `<span class="entity-review-required">Review required · ${ctx.actions.esc(field.reason)}</span>${field.can_confirm ? button('confirm', 'Confirm') : ''}${button('ignore', 'Ignore')}`;
    else if (['confirmed', 'ignored'].includes(field?.status))
      content = `<span>${field.status === 'confirmed' ? 'Confirmed' : 'Ignored'}</span>${button('pending', 'Review again')}`;
    return `<div id="entity-review-${name}" data-entity-review-field="${name}" class="entity-field-review" aria-live="polite">${provenance}${content}</div>`;
  }

  function entityReviewField(label, name, value, options = {}) {
    return ctx.actions
      .field(label, name, value, options)
      .replace(`name="${name}"`, `name="${name}" aria-describedby="entity-review-${name}"`)
      .replace(/<\/div>$/, entityFieldReview(name) + '</div>');
  }

  Object.assign(ctx.actions, { entityReviewSummary, entityFieldReview, entityReviewField });
}

export function createHandlers(ctx) {
  return {
    actions: {
      'entity-field-review': async (button) => {
        const independent = !!ctx.state.entities?.current;
        const lead = independent ? ctx.state.entities.current : ctx.state.editor.currentLead;
        const field = lead.entity_review.fields.find((item) => item.field === button.dataset.field);
        const form = independent
          ? 'entity-details-form'
          : field.field === 'name'
            ? 'entity-name-form'
            : 'entity-profile-form';
        const input = ctx.actions.$(`#${form} [name="${field.field}"]`);
        // Textareas normalize saved CRLF line endings when the browser loads them.
        const displayed = (value) => value.replace(/\r\n?/g, '\n');
        if (input && displayed(input.value) !== displayed(field.value))
          throw Error('Save this business detail before reviewing it.');
        const response = await ctx.actions.api(`/api/entities/${lead.id}/field-review`, {
          method: 'POST',
          body: {
            field: field.field,
            action: button.dataset.review,
            expected_revision: lead.entity_revision ?? lead.draft_revision,
            value_hash: field.value_hash,
          },
        });
        const current = independent ? ctx.state.entities.current : ctx.state.editor.currentLead;
        if (current?.id !== lead.id) return;
        current.entity_review = response.entity_review;
        void ctx.actions.refreshNavigationCounts?.();
        ctx.actions.$$('[data-entity-review-summary]').forEach((node) => {
          node.outerHTML = ctx.actions.entityReviewSummary();
        });
        ctx.actions.$$('[data-entity-review-field]').forEach((node) => {
          node.outerHTML = ctx.actions.entityFieldReview(node.dataset.entityReviewField);
        });
      },
    },
    forms: {},
    change: [],
    click: [],
  };
}
