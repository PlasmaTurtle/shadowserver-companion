import { install as installWebsiteCapture } from '../../investigations/static/website_capture.js';
import { mountCosmicBackground } from './cosmic_background.js';
/** Application composition root. Importing this module does not start network requests or attach events. */
import { createState } from './state.js';
import { install as installShared } from './shared.js';
import { install as installIntake } from '../../accretion/static/intake.js';
import { install as installEntities } from '../../entities/static/entities.js';
import { install as installResources } from '../../library/static/resources.js';
import { install as installCatalog } from '../../library/static/cve_catalog.js';
import { install as installWorkspaceHealth } from '../../workspace/static/workspace_health.js';
import { install as installQueues } from '../../workspace/static/queues.js';
import { install as installLeads } from '../../leads/static/entity_leads.js';
import { install as installShadowserverData } from '../../accretion/static/shadowserver_data.js';
import { install as installAssets } from '../../attribution/static/assets.js';
import { install as installActivity } from '../../activity/static/activity.js';
import { install as installContacts } from '../../entities/static/contacts.js';
import { install as installAttribution } from '../../attribution/static/attribution.js';
import { install as installIntelligence } from '../../investigations/static/source_intelligence.js';
import { install as installSettings } from '../../settings/static/settings.js';
import { install as installOnboarding } from '../../settings/static/onboarding.js';
import { install as installSoftwareUpdates } from '../../settings/static/software_updates.js';
import { install as installWorkflow } from '../../investigations/static/workflow.js';
import { install as installNavigation } from './navigation.js';
import { install as installEditor } from '../../investigations/static/editor.js';
import { install as installObservationScope } from '../../investigations/static/observation_scope.js';
import { install as installReportOperations } from '../../investigations/static/report_operations.js';
import { install as installCommandPalette } from './command_palette.js';
import { start } from './navigation.js';
import { bindEvents } from './events.js';

export function createApplication({ overrides = {} } = {}) {
  const context = { state: createState(), actions: {}, constants: {} };
  installShared(context);
  installQueues(context);
  installIntake(context);
  installActivity(context);
  installAttribution(context);
  installAssets(context);
  installContacts(context);
  installEntities(context);
  installIntelligence(context);
  installCatalog(context);
  installResources(context);
  installWorkspaceHealth(context);
  installSettings(context);
  installOnboarding(context);
  installSoftwareUpdates(context);
  installWorkflow(context);
  installNavigation(context);
  installEditor(context);
  installObservationScope(context);
  installWebsiteCapture(context);
  installLeads(context);
  installShadowserverData(context);
  installReportOperations(context);
  installCommandPalette(context);
  Object.assign(context.actions, overrides);
  let detach = null;
  let startup = null;
  let background = null;
  let generation = 0;
  return {
    state: context.state,
    actions: context.actions,
    constants: context.constants,
    attach() {
      if (!detach) detach = bindEvents(context);
    },
    start() {
      this.attach();
      if (!background) background = mountCosmicBackground();
      if (!startup) {
        context.actions.resumeSetup?.();
        context.actions.resumeSoftwareUpdates?.();
        const current = generation;
        startup = start(context, () => current === generation);
      }
      return startup;
    },
    destroy() {
      background?.destroy();
      background = null;
      try {
        detach?.();
      } finally {
        detach = null;
        generation++;
        startup = null;
        context.state.navigation.renderId++;
        context.actions.stopViewRequests();
        context.actions.stopCatalogPolling?.();
        clearInterval(context.state.navigation.poll);
        context.state.navigation.poll = null;
        clearTimeout(context.state.editor.narrativeRefreshTimer);
        context.state.editor.narrativeRefreshId++;
        if (context.state.editor.pendingCveRefresh) {
          context.state.editor.pendingCveRefresh.detached = true;
          context.state.editor.pendingCveRefresh.running = false;
        }
        context.actions.disposeReportPreview();
        context.actions.stopAssetAttributionPolling();
        context.actions.stopContactDiscoveryPolling();
        context.actions.stopWebsiteCapturePolling();
        context.actions.stopApiAcquisitionPolling();
        context.actions.disposeCommandPalette();
        context.actions.disposeSoftwareUpdates?.();
        context.actions.disposeSetup?.();
        window.Eclipse?.destroy();
      }
    },
  };
}
