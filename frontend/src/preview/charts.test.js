import test from 'node:test';
import assert from 'node:assert/strict';
import { countGroups } from './charts.js';
import { validateConfigV2 } from './configV2.js';

const records = (values) => values.map((value, index) => ({ id: String(index), values: { category: value } }));

test('counts actual values and missing records without merging literal labels', () => {
  const input = records(['테니스장', '테니스장', '다목적구장', null, ' ', '값 없음']);
  const before = structuredClone(input);
  const result = countGroups(input, 'category');
  assert.equal(result.find((g) => g.key === '테니스장').count, 2);
  assert.equal(result.find((g) => g.key === null).count, 2);
  assert.equal(result.find((g) => g.key === '값 없음').count, 1);
  assert.equal(result.reduce((sum, g) => sum + g.count, 0), 6);
  assert.deepEqual(input, before);
  assert.deepEqual(countGroups([], 'category'), []);
});

test('many categories are combined without losing counts and retain stable ordering', () => {
  const result = countGroups(records(Array.from({ length: 12 }, (_, i) => `cat${i}`)), 'category');
  assert.equal(result.length, 8);
  assert.equal(result[0].label, 'cat0');
  assert.equal(result[7].count, 5);
  assert.equal(result.reduce((sum, g) => sum + g.count, 0), 12);
});

test('v2 chart config only accepts supported types, aggregation and existing columns', () => {
  const config = { version: 2, views: [{ template: 'table', columns: [1], charts: [{ type: 'bar', groupColumn: 1, aggregate: 'count' }] }] };
  const columns = [{ id: 'category' }];
  assert.equal(validateConfigV2(config, columns), config);
  for (const change of [{ type: 'script' }, { aggregate: 'sum' }, { groupColumn: 9 }, { code: 'run()' }]) {
    const bad = structuredClone(config);
    Object.assign(bad.views[0].charts[0], change);
    assert.throws(() => validateConfigV2(bad, columns));
  }
});
