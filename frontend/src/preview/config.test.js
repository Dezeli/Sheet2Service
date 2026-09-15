import test from 'node:test';
import assert from 'node:assert/strict';
import { templates, validateConfig, previewRecords, safeWebUrl, reservationConfig } from './config.js';

const columns = [{ id: 'column_1', name: 'title', label: '제목' }];
const config = () => ({ version: 1, title: '테스트', pages: [
  { id: 'list', title: '목록', template: 'cards', detailPage: 'detail', bindings: { title: 'column_1' } },
  { id: 'detail', title: '상세', template: 'detail', bindings: { title: 'column_1', fields: ['column_1'] } },
] });

test('catalog has seven templates and the card/detail pair validates', () => {
  assert.equal(Object.keys(templates).length, 7);
  assert.equal(Object.values(templates).filter((t) => t.ready).length, 2);
  assert.deepEqual(validateConfig(config(), columns), config());
});

test('reject unknown templates, missing bindings, dangling links and extra code', () => {
  for (const change of [
    (c) => { c.pages[0].template = 'custom_code'; },
    (c) => { c.pages[0].bindings.title = 'column_99'; },
    (c) => { delete c.pages[0].bindings.title; },
    (c) => { c.pages[0].detailPage = 'missing'; },
    (c) => { c.pages[1].id = 'list'; },
    (c) => { c.pages[1].bindings.fields = ['column_1', 'column_1']; },
    (c) => { c.pages[0].script = 'alert(1)'; },
    (c) => { c.pages[0].bindings.html = 'column_1'; },
  ]) {
    const value = config(); change(value);
    assert.throws(() => validateConfig(value, columns));
  }
});

test('record adapter preserves values and limits records without changing the report', () => {
  const report = { columns, preview: Array.from({ length: 7 }, (_, i) => ({ row_number: i + 2, values: [i === 0 ? '001' : '<script>text</script>'] })) };
  const before = structuredClone(report);
  const records = previewRecords(report);
  assert.equal(records.length, 5);
  assert.equal(records[0].values.column_1, '001');
  assert.equal(records[1].values.column_1, '<script>text</script>');
  assert.deepEqual(report, before);
});

test('URLs permit only explicit http(s) addresses without credentials', () => {
  for (const url of ['javascript:alert(1)', 'data:text/html,test', '//example.com', '/local', 'https://user:pass@example.com']) assert.equal(safeWebUrl(url), null);
  assert.equal(safeWebUrl('https://example.com/info'), 'https://example.com/info');
});

test('example mapping requires unique matching headers', () => {
  assert.throws(() => reservationConfig(columns));
  const names = ['서비스명', '서비스상태', '이미지경로', '장소명', '소분류명', '결제방법', '바로가기URL', '전화번호', '상세정보'];
  const source = names.map((name, i) => ({ id: `column_${i + 1}`, name }));
  assert.equal(reservationConfig(source).pages[0].bindings.title, 'column_1');
  assert.throws(() => reservationConfig([...source, { id: 'extra', name: '서비스명' }]));
});
