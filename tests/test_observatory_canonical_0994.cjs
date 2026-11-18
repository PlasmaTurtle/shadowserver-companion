const assert = require('node:assert/strict');
(async () => {
  const { densityBand, densityStats, findingCount, findingRows, atlasLayout, priorityMark } =
    await import('../static/eclipse_model.js');
  const { clusterLocations } = await import('../static/eclipse_space.js');
  assert.deepEqual(
    [0, 50, 51, 200, 201, 1000, 1001].map((n) => densityBand(n).id),
    ['normal', 'normal', 'yellow', 'yellow', 'red', 'red', 'purple'],
  );
  const rows = Array.from({ length: 1001 }, (_, i) => ({
    id: 'o' + i,
    observation_id: 'o' + i,
    asset_id: 'a1',
    entity_id: 'e1',
    entity_name: 'Example',
    hostname: 'mail.example.com',
    ip: '8.8.8.8',
    tag: 'CVE-2026-10001;CVE-2026-10002',
    finding_ids: ['f1', 'f2'],
    observed_day: '2026-11-12',
    observed_at: '2026-11-12T' + String(i).padStart(5, '0'),
    latitude: 35.2,
    longitude: -80.8,
    admitted: true,
    dark_matter: false,
    temperature: 'cool',
  }));
  const repeatedDelivery = [...rows, { ...rows[0] }];
  assert.equal(densityStats(repeatedDelivery).observation_count, 1001);
  assert.equal(findingCount(repeatedDelivery), 2);
  const definitions = [
    { id: 'f1', finding_id: 'f1', tag: 'CVE-2026-10001', admitted: true },
    { id: 'f2', finding_id: 'f2', tag: 'CVE-2026-10002', admitted: true },
  ];
  const records = findingRows(repeatedDelivery, definitions);
  assert.equal(records.length, 2);
  assert(records.every((r) => r.observation_count === 1001 && r.sightings === 1));
  const atlas = atlasLayout(rows);
  assert.equal(atlas.nodes.length, 1);
  assert.equal(atlas.nodes[0].finding_count, 2);
  assert.equal(atlas.nodes[0].density_count, 1001);
  assert.equal(rows[0].temperature, 'cool');
  assert.match(priorityMark('cool'), /data-temperature="cool"/);
  assert.equal(priorityMark('<script>'), '');
  const clusters = clusterLocations(atlas.nodes, { x: 0, y: 0, k: 1 });
  assert.equal(clusters[0].finding_count, 2);
  assert.equal(clusters[0].observation_count, 1001);
  const failed = {
    ...rows[0],
    id: 'failed',
    observation_id: 'failed',
    ip: '1.1.1.1',
    observed_at: '2026-11-13',
    admitted: false,
    dark_matter: true,
  };
  const withFailure = findingRows([rows[0], failed], definitions);
  assert.equal(withFailure.filter((r) => r.admitted).length, 2);
  assert.equal(withFailure.find((r) => !r.admitted).ip, '1.1.1.1');
  assert(withFailure.filter((r) => r.admitted).every((r) => r.ip === '8.8.8.8'));
  const mixed = {
    ...rows[0],
    source: { workbook: 'pending.csv' },
    condition_admissions: {
      'CVE-2026-10001': true,
      'CVE-2026-10002': false,
    },
  };
  const mixedDefinitions = [
    { ...definitions[0], source: { workbook: 'approved.csv' } },
    {
      ...definitions[1],
      admitted: false,
      intake_reason: 'pending',
      disposition_reason: 'Pending',
      source: { workbook: 'pending.csv' },
    },
  ];
  const mixedRecords = findingRows([mixed], mixedDefinitions);
  assert.equal(
    mixedRecords.find((r) => r.id === 'f1').source.workbook,
    'pending.csv',
    'A finding retains the selected observation source; a global representative cannot replace its provenance',
  );
  assert.equal(mixedRecords.find((r) => r.id === 'f2').admitted, false);
  assert.equal(mixedRecords.find((r) => r.id === 'f2').intake_reason, 'pending');
  console.log(
    'Canonical Observatory findings, distinct-event density, exact bands, entity nodes, and admission/priority separation passed.',
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
