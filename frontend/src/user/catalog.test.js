import test from 'node:test';
import assert from 'node:assert/strict';
import { publicColumns, summaryColumns } from './catalog.js';

test('public catalog hides identifier columns without renumbering data references', () => {
  assert.deepEqual(publicColumns([{ label: '서비스 ID' }, { label: '이름' }, { label: 'record_id' }, { label: '구분' }]).map((item) => item.number), [2, 4]);
});

test('summary keeps at most three public fields and excludes the title', () => {
  const columns = ['이름', '서비스 ID', '구분', '기간', '가격', '설명'].map((label) => ({ label, candidate: 'text', unique_count: 2, non_empty_count: 20 }));
  assert.deepEqual(summaryColumns(columns, 1).map((item) => item.number), [3, 4, 5]);
});

test('renaming an identifier does not expose it in the public catalog', () => {
  assert.deepEqual(publicColumns([
    { original_label: 'record_id', label: 'Reference' },
    { original_label: 'name', label: 'Display name' },
  ]).map((item) => item.number), [2]);
});
