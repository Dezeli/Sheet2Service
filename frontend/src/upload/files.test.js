import test from 'node:test';
import assert from 'node:assert/strict';
import { csvFile } from './files.js';

test('file picker and dropped files share CSV validation including size boundaries', () => {
  const file = { name: 'DATA.CSV', size: 10 * 1024 * 1024 };
  assert.equal(csvFile([file]), file);
  for (const invalid of [{ name: 'data.xlsx', size: 1 }, { name: 'data.csv', size: 0 },
    { name: 'data.csv', size: 10 * 1024 * 1024 + 1 }]) {
    assert.throws(() => csvFile([invalid]));
  }
});

test('multiple or missing dropped files cannot initiate upload', () => {
  const file = { name: 'data.csv', size: 1 };
  assert.throws(() => csvFile([]));
  assert.throws(() => csvFile([file, file]));
});
