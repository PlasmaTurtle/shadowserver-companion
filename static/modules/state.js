/** Each application instance owns its state; feature modules never use page globals. */
export function createState() {
  return {
    navigation: {
      boot: undefined,
      currentRoute: '',
      renderId: 0,
      poll: null,
      positions: new Map(),
      returns: new Map(),
    },
    entities: { current: null, dirty: false, changedForms: new Set(), tab: 'details' },
    intakeLeads: { current: null },
    editor: {
      currentLead: null,
      draft: null,
      dirty: false,
      tab: 'notification',
      pendingCveRefresh: null,
      cveSignalFilter: 'all',
      reportSection: 'Introduction',
      narrativeRefreshTimer: undefined,
      narrativeRefreshId: 0,
    },
    workflow: { workflowDirty: false, changedCaseForms: new Set() },
    resources: { resources: [], resourceId: null },
    contacts: {
      entities: new Map(),
      selectedRoots: new Map(),
      includeWww: new Set(),
      generation: 0,
      timer: null,
      watch: null,
      pending: null,
      batch: null,
      batchEntityIds: [],
      entityNames: new Map(),
    },
  };
}
