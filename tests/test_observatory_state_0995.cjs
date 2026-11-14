const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
(async () => {
  const {
    initialState,
    selectionScope,
    drillOptions,
    scopeLabels,
    queryFor,
    scopedURL,
    persistentState,
  } = await import(pathToFileURL(path.join(__dirname, '../static/eclipse_navigation_state.js')));
  assert.equal(initialState(null).view, 'field');
  assert.equal(initialState([]).lens, 'organization');
  let state = initialState({ view: 'atlas' }, new URLSearchParams());
  assert.equal(state.view, 'field');
  assert.equal(state.lens, 'organization');
  assert.equal(state.inspectorOpen, false);
  state = initialState({ defaultView: 'records', intake: 'dark_matter' }, new URLSearchParams());
  assert.equal(state.view, 'records');
  assert.equal(state.intake, 'dark_matter');
  state = initialState(
    {
      search: 'CVE-2026-99999',
      entity: 'other',
      network: '15169',
      status: 'delivered',
      intake: 'dark_matter',
      unplaced: true,
      defaultView: 'atlas',
    },
    new URLSearchParams('entity=one'),
  );
  assert.equal(state.entity, 'one');
  assert.equal(state.search, '');
  assert.equal(state.status, '');
  assert.equal(state.network, '');
  assert.equal(state.intake, '');
  assert.equal(state.unplaced, false);
  assert.equal(state.view, 'atlas');
  state = initialState({ search: { unexpected: 1 }, cutoff: 'bad' }, new URLSearchParams());
  assert.equal(state.search, '');
  assert.equal(state.cutoff, '');
  assert.doesNotThrow(() => queryFor(state));
  const scope = selectionScope({
    type: 'product',
    scope: {
      product_name: 'Mail Server',
      entity_id: 'one',
      version: '2.1',
      location_key: 'area:x',
    },
  });
  assert.deepEqual(scope, {
    productName: 'Mail Server',
    entity: 'one',
    version: '2.1',
    locationKey: 'area:x',
  });
  Object.assign(state, scope);
  const query = queryFor(state);
  assert.equal(query.get('product_name'), 'Mail Server');
  assert.equal(query.get('entity_id'), 'one');
  assert.equal(query.get('version'), '2.1');
  assert.equal(query.get('location_key'), 'area:x');
  const roundtrip = initialState({}, new URLSearchParams(scopedURL(state).split('?')[1]));
  assert.equal(roundtrip.productName, 'Mail Server');
  assert.equal(roundtrip.locationKey, 'area:x');
  assert.equal(roundtrip.version, '2.1');
  state.search = 'CVE-2026-12345';
  assert.equal(queryFor(state).get('cve'), 'CVE-2026-12345');
  assert.equal(queryFor(state).has('q'), false);
  state.search = '';
  state.page = 3;
  assert.equal(queryFor(state).get('offset'), '60');
  assert.equal(
    drillOptions({ type: 'entity', scope: { entity_id: 'one' } }).find((x) => x.id === 'products')
      .recordsMode,
    'products',
  );
  const eolNode = {
    type: 'finding',
    label: 'PHP 7.3 end of life',
    scope: { condition: 'eol-php:7.3' },
  };
  assert.ok(drillOptions(eolNode).some((option) => option.id === 'locations'));
  const eolState = {
    ...initialState({}, new URLSearchParams('entity=one')),
    ...selectionScope(eolNode),
  };
  assert.equal(queryFor(eolState).get('condition'), 'eol-php:7.3');
  assert.equal(queryFor(eolState).get('entity_id'), 'one');
  assert.equal(
    initialState({}, new URLSearchParams(scopedURL(eolState).split('?')[1])).condition,
    'eol-php:7.3',
  );
  assert.equal(persistentState(eolState).condition, 'eol-php:7.3');
  assert.ok(scopeLabels(eolState).includes('Finding: End of life · php · 7.3'));
  const refinedEol = {
    ...eolState,
    ...selectionScope({ type: 'product', scope: { product_name: 'PHP' } }),
  };
  assert.equal(queryFor(refinedEol).get('condition'), 'eol-php:7.3');
  assert.equal(queryFor(refinedEol).get('product_name'), 'PHP');
  assert.equal(
    initialState({ condition: 'eol-php:7.3' }, new URLSearchParams('entity=two')).condition,
    '',
  );
  assert.equal(drillOptions({ type: 'mystery', label: 'Unknown' }).length, 0);
  assert.deepEqual(
    selectionScope({ type: 'cluster' }, [
      { city: 'Asheville', region: 'NC' },
      { city: 'Charlotte', region: 'NC' },
    ]),
    {},
  );
  assert.deepEqual(selectionScope({ type: 'cluster' }, [{ city: 'Asheville', region: 'NC' }]), {
    city: 'Asheville',
    region: 'NC',
  });
  assert.ok(
    scopeLabels(state, [{ id: 'one', name: 'One Company' }]).includes('Organization: One Company'),
  );
  assert.equal(persistentState({ ...state, defaultView: 'pulse' }).defaultView, 'pulse');
  assert.equal('page' in persistentState(state), false);
  console.log('Observatory 0.9.95 navigation state tests passed');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
