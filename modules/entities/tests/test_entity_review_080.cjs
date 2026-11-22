/** Reminder actions preserve draft edits and use exact saved-field snapshots. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { loadApplication } = require('../../../tests/frontend_harness.cjs');
(async () => {
  const context = vm.createContext({ console });
  const { application } = await loadApplication(context, { attach: false });
  const ctx = application;
  ctx.state.editor.currentLead = {
    id: 'entity',
    entity_revision: 3,
    entity_profile: {},
    entity_review: {
      required: true,
      fields: [
        {
          field: 'name',
          label: 'Entity / business name',
          value: 'mail.example.com',
          value_hash: 'a'.repeat(64),
          status: 'pending',
          can_confirm: true,
          reason: 'Using the reported hostname',
        },
        {
          field: 'address',
          label: 'Mailing address',
          value: '',
          value_hash: 'b'.repeat(64),
          status: 'pending',
          can_confirm: false,
          reason: 'Missing business detail',
        },
      ],
    },
  };
  ctx.state.editor.draft = { narrative: 'Unsaved narrative' };
  ctx.state.editor.dirty = true;
  ctx.state.workflow.workflowDirty = true;
  assert.match(ctx.actions.entityReviewSummary(), /Review required: business details/);
  assert.match(ctx.actions.entityFieldReview('name'), /data-review="confirm"/);
  assert.doesNotMatch(ctx.actions.entityFieldReview('address'), /data-review="confirm"/);
  const profile = ctx.actions.entityProfileMarkup();
  assert.match(profile, /aria-describedby="entity-review-address"/);
  assert.match(profile, /data-entity-review-field="address"/);
  assert.doesNotMatch(profile, /data-entity-review-field="contact_email"/);
  const module = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, '../static/entity_review.js'), 'utf8'),
    { context },
  );
  await module.link(() => {
    throw Error('Unexpected dependency');
  });
  await module.evaluate();
  const handler = module.namespace.createHandlers(ctx).actions['entity-field-review'];
  const input = { value: 'Unsaved replacement' };
  ctx.actions.$ = () => input;
  const summaryNode = { outerHTML: '' };
  const fieldNode = { dataset: { entityReviewField: 'name' }, outerHTML: '' };
  ctx.actions.$$ = (selector) => (selector.includes('summary') ? [summaryNode] : [fieldNode]);
  ctx.actions.refreshNavigationCounts = async () => {};
  let requests = 0;
  ctx.actions.api = async (url, options) => {
    requests++;
    assert.equal(url, '/api/entities/entity/field-review');
    assert.equal(options.body.expected_revision, 3);
    assert.equal(options.body.value_hash, 'a'.repeat(64));
    return {
      entity_revision: 3,
      entity_review: {
        required: false,
        fields: [{ ...ctx.state.editor.currentLead.entity_review.fields[0], status: 'confirmed' }],
      },
    };
  };
  const button = { dataset: { field: 'name', review: 'confirm' } };
  await assert.rejects(handler(button), /Save this business detail/);
  assert.equal(requests, 0);
  input.value = 'mail.example.com';
  await handler(button);
  assert.equal(requests, 1);
  assert.equal(ctx.state.editor.draft.narrative, 'Unsaved narrative');
  assert.equal(ctx.state.editor.dirty, true);
  assert.equal(ctx.state.workflow.workflowDirty, true);
  assert.match(fieldNode.outerHTML, /Confirmed/);
  assert.match(summaryNode.outerHTML, /hidden/);
  ctx.state.editor.currentLead.entity_review.fields = [
    {
      field: 'address',
      label: 'Mailing address',
      value: '24 Main Street\r\nAsheville',
      value_hash: 'c'.repeat(64),
      status: 'pending',
      can_confirm: true,
    },
  ];
  input.value = '24 Main Street\nAsheville';
  ctx.actions.api = async (url, options) => {
    assert.equal(options.body.value_hash, 'c'.repeat(64));
    return { entity_review: { required: false, fields: [] } };
  };
  await handler({ dataset: { field: 'address', review: 'confirm' } });
  console.log('Entity reminders, saved-value guards, and independent draft preservation passed.');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
