/** Portable DOM regression runner; no installed browser or running API required. */
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const suites = [
  '../modules/ui/tests/test_shared_frontend_helpers.cjs',
  'test_api_poll.cjs',
  '../modules/investigations/tests/test_cases_ui.cjs',
  '../modules/investigations/tests/test_review_ui.cjs',
  '../modules/investigations/tests/test_template_ui_041.cjs',
  '../modules/ui/tests/test_companion_ui_050.cjs',
  '../modules/investigations/tests/test_report_ui_040.cjs',
  '../modules/ui/tests/test_frontend_070.cjs',
  '../modules/ui/tests/test_frontend_modules_071.cjs',
  '../modules/ui/tests/test_frontend_lifecycle_075.cjs',
  '../modules/investigations/tests/test_report_operations_ui_080.cjs',
  '../modules/investigations/tests/test_report_operations_ui_095.cjs',
  '../modules/entities/tests/test_entity_review_080.cjs',
  '../modules/attribution/tests/test_assets_ui_080.cjs',
  '../modules/workspace/tests/test_workspace_data_ui_080.cjs',
  '../modules/entities/tests/test_contacts_ui_090.cjs',
  '../modules/entities/tests/test_contacts_ui_095.cjs',
  '../modules/entities/tests/test_entities_interface.cjs',
  '../modules/leads/tests/test_website_thumbnail_ui.cjs',
  '../modules/investigations/tests/test_outreach_preparation_ui.cjs',
  '../modules/investigations/tests/test_observation_scope_ui.cjs',
  '../modules/entities/tests/test_contacts_ui_0981.cjs',
  '../modules/workspace/tests/test_queue_polish_095.cjs',
  '../modules/workspace/tests/test_workday_guidance_ui.cjs',
  '../modules/settings/tests/test_settings_ui_095.cjs',
  '../modules/library/tests/test_resources_ui.cjs',
  '../modules/library/tests/test_cve_catalog_ui_0983.cjs',
  '../modules/library/tests/test_catalog_library_ui_0984.cjs',
  '../modules/library/tests/test_library_selection_lifecycle.cjs',
  '../modules/library/tests/test_catalog_observatory_0984.cjs',
  '../modules/entities/tests/test_entity_dns_ui_0984.cjs',
  '../modules/ui/tests/test_interaction_ui_095.cjs',
  '../modules/ui/tests/test_navigation_ui_098.cjs',
  '../modules/ui/tests/test_command_palette_ui_0981.cjs',
  '../modules/observatory/tests/test_eclipse_model_0981.cjs',
  '../modules/observatory/tests/test_eclipse_space_0982.cjs',
  '../modules/investigations/tests/test_dossiers_ui_0982.cjs',
  '../modules/investigations/tests/test_investigations_ui_0982.cjs',
  '../modules/ui/tests/test_cosmic_background_0985.cjs',
  '../modules/investigations/tests/test_website_capture_ui_0985.cjs',
  '../modules/accretion/tests/test_accretion_ui_0987.cjs',
  '../modules/accretion/tests/test_dark_matter_ui_0987.cjs',
  '../modules/accretion/tests/test_intake_ui_0990.cjs',
  '../modules/accretion/tests/test_intake_interface.cjs',
  '../modules/workspace/tests/test_queue_loading_0991.cjs',
  '../modules/accretion/tests/test_intake_entity_ui_0992.cjs',
  '../modules/accretion/tests/test_api_setup_ui_0992.cjs',
  '../modules/accretion/tests/test_data_route_0993.cjs',
  '../modules/ui/tests/test_navigation_cancellation_0994.cjs',
  '../modules/entities/tests/test_entity_fields_0994.cjs',
  '../modules/investigations/tests/test_notification_workflow_0994.cjs',
  '../modules/investigations/tests/test_notification_review_ui_0997.cjs',
  '../modules/settings/tests/test_sender_identity_ui_0101.cjs',
  '../modules/observatory/tests/test_observatory_canonical_0994.cjs',
  '../modules/observatory/tests/test_observatory_controller_0995.cjs',
  '../modules/observatory/tests/test_observatory_scene_0995.cjs',
  '../modules/observatory/tests/test_observatory_scene_0998.cjs',
  '../modules/observatory/tests/test_observatory_entity_map.cjs',
  '../modules/observatory/tests/test_observatory_entity_controller.cjs',
  '../modules/observatory/tests/test_observatory_recency_layout.cjs',
  '../modules/observatory/tests/test_observatory_field_navigation.cjs',
  '../modules/observatory/tests/test_observatory_state_0995.cjs',
  '../modules/observatory/tests/test_observatory_shell_0995.cjs',
  '../modules/accretion/tests/test_schedule_ui_0994.cjs',
  '../modules/entities/tests/test_entity_lifecycle_ui_0110.cjs',
  '../modules/workspace/tests/test_workspace_health_ui_0110.cjs',
  '../modules/accretion/tests/test_admission_ui_0110.cjs',
  '../modules/accretion/tests/test_api_jurisdiction_ui_0120.cjs',
  '../modules/settings/tests/test_onboarding_ui_0120.cjs',
  '../modules/settings/tests/test_software_updates_ui_0120.cjs',
];

// Browser suites use *_browser*.cjs; these two predate that naming convention.
const legacyBrowserSuites = new Set([
  'modules/ui/tests/test_frontend_accessibility_070.cjs',
  'modules/workspace/tests/test_frontend_workspace_080.cjs',
]);

function validateSuites(root, registered = suites) {
  const portable = new Set();
  const relative = (file) => path.relative(root, file).split(path.sep).join('/');
  function discover(directory) {
    if (!fs.existsSync(directory)) return;
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const file = path.join(directory, entry.name);
      if (entry.isDirectory()) discover(file);
      else if (
        entry.isFile() &&
        /^test_.*\.cjs$/.test(entry.name) &&
        !entry.name.includes('_browser') &&
        !legacyBrowserSuites.has(relative(file))
      ) {
        portable.add(file);
      }
    }
  }
  root = path.resolve(root);
  discover(path.join(root, 'tests'));
  const modules = path.join(root, 'modules');
  if (fs.existsSync(modules)) {
    for (const entry of fs.readdirSync(modules, { withFileTypes: true })) {
      if (entry.isDirectory()) discover(path.join(modules, entry.name, 'tests'));
    }
  }
  const registeredPaths = registered.map((suite) => path.resolve(root, 'tests', suite));
  const seen = new Set();
  for (const file of registeredPaths) {
    if (seen.has(file)) throw new Error(`Duplicate DOM suite registration: ${relative(file)}`);
    if (!portable.has(file)) {
      throw new Error(`Registered DOM suite is missing or browser-only: ${relative(file)}`);
    }
    seen.add(file);
  }
  const missing = [...portable].filter((file) => !seen.has(file));
  if (missing.length) {
    throw new Error(`Unregistered DOM suites: ${missing.map(relative).sort().join(', ')}`);
  }
}

if (require.main === module) {
  validateSuites(path.resolve(__dirname, '..'));
  for (const suite of suites) {
    const result = spawnSync(
      process.execPath,
      ['--experimental-vm-modules', path.join(__dirname, suite)],
      {
        stdio: 'inherit',
      },
    );
    if (result.error) throw result.error;
    if (result.status !== 0) process.exit(result.status || 1);
  }
}

module.exports = { validateSuites };
