import { install as installWebsiteCapture } from './modules/website_capture.js';
import { mountCosmicBackground } from './cosmic_background.js';
/** Application composition root. Importing this module does not start network requests or attach events. */
import { createState } from './modules/state.js';
import { install as installShared } from './modules/shared.js';
import { install as installQueues } from './modules/queues.js';
import { install as installEntityLeads } from './modules/entity_leads.js';
import { install as installShadowserverData } from './modules/shadowserver_data.js';
import { install as installAssets } from './modules/assets.js';
import { install as installActivity } from './modules/activity.js';
import { install as installContacts } from './modules/contacts.js';
import { install as installAttribution } from './modules/attribution.js';
import { install as installIntelligence } from './modules/intelligence.js';
import { install as installSettings } from './modules/settings.js';
import { install as installOnboarding } from './modules/onboarding.js';
import { install as installSoftwareUpdates } from './modules/software_updates.js';
import { install as installWorkflow } from './modules/workflow.js';
import { install as installNavigation } from './modules/navigation.js';
import { install as installEditor } from './modules/editor.js';
import { install as installObservationScope } from './modules/observation_scope.js';
import { install as installReportOperations } from './modules/report_operations.js';
import { install as installCommandPalette } from './modules/command_palette.js';
import { start } from './modules/navigation.js';
import { bindEvents } from './modules/events.js';

export function createApplication({ overrides = {} } = {}) {
  const context = { state: createState(), actions: {}, constants: {} };
  installShared(context);
  installQueues(context);
  installActivity(context);
  installAttribution(context);
  installAssets(context);
  installContacts(context);
  installIntelligence(context);
  installSettings(context);
  installOnboarding(context);
  installSoftwareUpdates(context);
  installWorkflow(context);
  installNavigation(context);
  installEditor(context);
  installObservationScope(context);
  installWebsiteCapture(context);
  installEntityLeads(context);
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
      detach?.();
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
    },
  };
}
