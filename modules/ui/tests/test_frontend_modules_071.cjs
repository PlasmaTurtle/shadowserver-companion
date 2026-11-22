const assert = require('node:assert/strict');
const vm = require('node:vm');
const { loadApplication } = require('../../../tests/frontend_harness.cjs');
(async () => {
  let listeners = 0;
  const context = vm.createContext({
    document: {
      addEventListener() {
        listeners++;
      },
    },
    window: {
      addEventListener() {
        listeners++;
      },
    },
    console,
  });
  const { application, createApplication } = await loadApplication(context, { attach: false });
  assert.equal(listeners, 0, 'Module imports do not attach browser listeners');
  const second = createApplication();
  application.state.editor.currentLead = { id: 'first', case_id: 'case-first' };
  second.state.editor.currentLead = { id: 'second', case_id: 'case-second' };
  application.state.editor.draft = { narrative: 'First draft' };
  application.state.workflow.changedCaseForms.add('case-plan');
  assert.equal(second.state.editor.draft, null);
  assert.equal(second.state.workflow.changedCaseForms.size, 0);
  assert.equal(application.actions.leadURL('/draft'), '/api/leads/first/draft?case_id=case-first');
  assert.equal(second.actions.leadURL('/draft'), '/api/leads/second/draft?case_id=case-second');
  assert.notEqual(application.state.editor, second.state.editor);
  assert.notEqual(application.actions, second.actions);
  console.log('Native feature imports, explicit instance state, and case URL isolation passed.');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
