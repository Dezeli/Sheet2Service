import test from 'node:test';
import assert from 'node:assert/strict';
import { recordsFromRows, safeWebUrl } from './config.js';

test('rows become records keyed by column id, with missing cells as null', () => {
  const columns = [{ id: 'column_1' }, { id: 'column_2' }];
  const records = recordsFromRows([{ row_number: 2, values: ['A'] }, { row_number: 3, values: ['B', 'x'] }], columns);
  assert.deepEqual(records, [
    { id: '2', values: { column_1: 'A', column_2: null } },
    { id: '3', values: { column_1: 'B', column_2: 'x' } },
  ]);
});

test('only plain http(s) urls without credentials are shown as links or images', () => {
  assert.equal(safeWebUrl('https://example.com/a.png'), 'https://example.com/a.png');
  assert.equal(safeWebUrl('javascript:alert(1)'), null);
  assert.equal(safeWebUrl('https://user:pw@example.com/'), null);
  assert.equal(safeWebUrl(42), null);
});
