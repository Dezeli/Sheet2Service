import test from 'node:test';
import assert from 'node:assert/strict';
import { chartConfigsV2, columnId, validateConfigV2 } from './configV2.js';

const columns = [
  { id: 'column_1', label: '시설명' },
  { id: 'column_2', label: '분류' },
  { id: 'column_3', label: '안내' },
];

test('v2 integer references resolve against header order and chart labels use CSV names', () => {
  const config = { version: 2, views: [
    { template: 'cards', titleColumn: 1, fields: [3], charts: [
      { type: 'bar', groupColumn: 2, aggregate: 'count' },
    ] },
    { template: 'table', columns: [3, 1, 2] },
  ] };
  assert.equal(validateConfigV2(config, columns), config);
  assert.equal(columnId(columns, 3), 'column_3');
  assert.deepEqual(chartConfigsV2(config.views[0].charts, columns), [
    { type: 'bar', groupBy: 'column_2', aggregate: 'count', title: '분류별 항목 수' },
  ]);
});

test('v2 runtime rejects arbitrary code, missing table columns and invalid references', () => {
  for (const view of [
    { template: 'table', columns: [] },
    { template: 'table', columns: [4] },
    { template: 'cards', titleColumn: 1, fields: [], script: 'alert(1)' },
    { template: 'cards', titleColumn: true, fields: [] },
  ]) {
    assert.throws(() => validateConfigV2({ version: 2, views: [view] }, columns));
  }
});
