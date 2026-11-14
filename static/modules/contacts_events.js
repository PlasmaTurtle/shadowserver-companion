/** Contact actions are explicit; rendering and polling never start new discovery. */
export function createHandlers(ctx) {
  return {
    input: (event) => ctx.actions.outreachPreparationInput?.(event),
    change: [
      {
        matches: (el) => el.id === 'contact-root',
        run: (el) => {
          ctx.state.contacts.selectedRoots.set(ctx.actions.contactEntityId(), el.value);
          ctx.state.contacts.includeWww.delete(ctx.actions.contactEntityId());
          ctx.actions.$('#contact-discovery-panel').outerHTML =
            ctx.actions.contactDiscoveryMarkup();
        },
      },
      {
        matches: (el) => el.id === 'contact-source-url',
        run: (el) => ctx.state.contacts.sourceUrls.set(ctx.actions.contactEntityId(), el.value),
      },
    ],
    click: [
      {
        matches: (el) => el.dataset.contactValueCopy,
        run: (el) =>
          ctx.actions.busy(el, () => ctx.actions.copyContactValue(el.dataset.contactValueCopy)),
      },
      {
        matches: (el) => el.dataset.contactRoute,
        run: (el) =>
          ctx.actions.openContactRouteDecision(el.dataset.contactRoute, el.dataset.routeAction),
      },
      {
        matches: (el) => el.dataset.contactReview,
        run: (el) =>
          ctx.actions.busy(el, () =>
            ctx.actions.reviewContactCandidate(el.dataset.contactReview, el.dataset.decision),
          ),
      },
      {
        matches: (el) => el.dataset.contactUse,
        run: (el) =>
          ctx.actions.busy(el, () => ctx.actions.useContactCandidate(el.dataset.contactUse)),
      },
      {
        matches: (el) => el.dataset.contactCopy,
        run: (el) =>
          ctx.actions.busy(el, () => ctx.actions.copyContactProvenance(el.dataset.contactCopy)),
      },
    ],
    forms: {
      'contact-route-decision': (_form, values) => ctx.actions.saveContactRouteDecision(values),
      'outreach-verification': (_form, values) => ctx.actions.saveOutreachVerification(values),
    },
    actions: {
      'find-all-entity-contacts': (button) => ctx.actions.findAllEntityContacts(button),
      'refresh-entity-contact': (button) => ctx.actions.refreshDirectoryContact(button),
      'load-contact-discovery': () => ctx.actions.loadContactDiscovery(),
      'start-contact-discovery': () => ctx.actions.startContactDiscovery(false),
      'refresh-contact-discovery': () => ctx.actions.startContactDiscovery(true),
      'inspect-contact-source': () => ctx.actions.inspectContactSource(),
      'cancel-contact-discovery': () => ctx.actions.cancelContactDiscovery(),
      'start-contact-batch': () => ctx.actions.startContactBatch(),
      'clear-contact-selection': () => ctx.actions.clearContactSelection(),
      'refresh-contact-batch': () => ctx.actions.resumeContactBatch(),
      'outreach-handoff': () => ctx.actions.showOutreachHandoff(),
      'copy-outreach-message': () => ctx.actions.copyOutreachMessage(),
      'save-outreach-preparation': () => ctx.actions.saveOutreachPreparation(),
      'reset-outreach-preparation': () => ctx.actions.saveOutreachPreparation(true),
      'refresh-outreach-context': () => ctx.actions.refreshOutreachContext(),
      'reload-outreach-preparation': () => ctx.actions.reloadOutreachPreparation(),
    },
  };
}
