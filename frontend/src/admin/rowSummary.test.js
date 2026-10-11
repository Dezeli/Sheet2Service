import test from 'node:test';
import assert from 'node:assert/strict';
import { rowSummary } from './rowSummary.js';

const columns = [
  { label: 'Category', unique_count: 2, non_empty_count: 10 },
  { label: 'Product', unique_count: 10, non_empty_count: 10 },
  { label: 'Location', unique_count: 5, non_empty_count: 10 },
];
test('configured title takes priority over the first value and always includes labeled context', () => {
  const result = rowSummary({ values: ['Internal', 'Camera', 'Room A'] }, columns, [2]);
  assert.equal(result.title.value, 'Camera');
  assert.deepEqual(result.supporting.map((field) => field.label), ['Location', 'Category']);
});
test('missing and invalid title columns fall back to labeled distinguishing fields', () => {
  const result = rowSummary({ values: ['Internal', '', 'Room A'] }, columns, [99, 2]);
  assert.equal(result.title, undefined);
  assert.deepEqual(result.supporting.map((field) => field.label), ['Location', 'Category']);
});
test('empty rows have no invented title and numeric zero is preserved', () => {
  assert.deepEqual(rowSummary({ values: [null, '', ' '] }, columns), { title: undefined, supporting: [] });
  assert.equal(rowSummary({ values: [0] }, columns, [1]).title.value, '0');
});
