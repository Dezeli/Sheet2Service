// Initial catalog: these seven IDs are the only supported template choices.
// Each binding points to a source column ID; no executable expressions are allowed.
export const templates = Object.freeze({
  cards: { label: '카드 목록', ready: true, required: ['title'], optional: ['subtitle', 'image', 'badge'], lists: ['fields'] },
  detail: { label: '상세 화면', ready: true, required: ['title'], optional: ['image', 'badge', 'link', 'phone'], lists: ['fields'] },
  table: { label: '표 목록', ready: true, required: [], optional: [], lists: ['fields'] },
  map: { label: '지도 목록', ready: false, required: ['title', 'latitude', 'longitude'], optional: [], lists: ['fields'] },
  calendar: { label: '달력', ready: false, required: ['title', 'start'], optional: ['end'], lists: ['fields'] },
  grouped: { label: '그룹 목록', ready: true, required: ['title', 'group'], optional: ['subtitle', 'image', 'badge'], lists: ['fields'] },
  form: { label: '입력 양식', ready: false, required: [], optional: [], lists: ['fields'] },
});

const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
function keys(value, allowed) {
  if (!object(value) || Object.keys(value).some((key) => !allowed.includes(key))) throw new Error('지원하지 않는 미리보기 설정입니다.');
}

// Configuration and data remain separate from React and from model responses.
export function validateConfig(config, columns) {
  keys(config, ['version', 'title', 'pages']);
  if (config.version !== 1 || typeof config.title !== 'string' || !config.title.trim() || config.title.length > 120) throw new Error('미리보기 제목 또는 버전이 올바르지 않습니다.');
  if (!Array.isArray(config.pages) || !config.pages.length || config.pages.length > 7) throw new Error('미리보기 화면은 1~7개여야 합니다.');
  const columnIds = new Set(columns.map((column) => column.id));
  const pages = new Map();
  for (const page of config.pages) {
    keys(page, ['id', 'template', 'title', 'bindings', 'detailPage', 'charts']);
    if (typeof page.id !== 'string' || !/^[a-z][a-z0-9_]{0,63}$/.test(page.id) || pages.has(page.id)) throw new Error('화면 ID가 올바르지 않거나 중복되었습니다.');
    if (!Object.hasOwn(templates, page.template)) throw new Error('지원하지 않는 화면 형식입니다.');
    if (typeof page.title !== 'string' || !page.title.trim() || page.title.length > 120) throw new Error('화면 제목이 필요합니다.');
    const spec = templates[page.template];
    keys(page.bindings, [...spec.required, ...spec.optional, ...spec.lists]);
    for (const slot of spec.required) if (!Object.hasOwn(page.bindings, slot)) throw new Error('필수 열 연결이 누락되었습니다.');
    for (const [slot, value] of Object.entries(page.bindings)) {
      const refs = spec.lists.includes(slot) ? value : [value];
      if (!Array.isArray(refs) || !refs.length || refs.length > 200 || new Set(refs).size !== refs.length || refs.some((id) => !columnIds.has(id))) throw new Error('열 연결이 비어 있거나 올바르지 않습니다.');
    }
    if (['table', 'form'].includes(page.template) && !page.bindings.fields?.length) throw new Error('표시할 열이 필요합니다.');
    if (page.detailPage !== undefined && !['cards', 'grouped'].includes(page.template)) throw new Error('상세 화면 연결은 카드·그룹 목록에서만 사용할 수 있습니다.');
    if (page.charts !== undefined) {
      if (!['cards', 'table', 'grouped'].includes(page.template) || !Array.isArray(page.charts) || page.charts.length > 4) throw new Error('그래프는 목록 화면에 최대 4개까지 설정할 수 있습니다.');
      for (const chart of page.charts) {
        keys(chart, ['type', 'title', 'groupBy', 'aggregate']);
        if (!['bar', 'donut'].includes(chart.type) || chart.aggregate !== 'count' || !columnIds.has(chart.groupBy)) throw new Error('그래프 종류·집계·열 설정이 올바르지 않습니다.');
        if (typeof chart.title !== 'string' || !chart.title.trim() || chart.title.length > 120) throw new Error('그래프 제목이 필요합니다.');
      }
    }
    pages.set(page.id, page);
  }
  for (const page of config.pages) {
    if (page.detailPage !== undefined && pages.get(page.detailPage)?.template !== 'detail') throw new Error('상세 화면 연결이 올바르지 않습니다.');
  }
  return config;
}

export function previewRecords(report) {
  return recordsFromRows(report.preview, report.columns);
}

export function recordsFromRows(rows, columns) {
  return rows.map((row) => ({
    id: String(row.row_number),
    values: Object.fromEntries(columns.map((column, index) => [column.id, row.values[index] ?? null])),
  }));
}

export function safeWebUrl(value) {
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}
