// Initial catalog: these seven IDs are the only supported template choices.
// Each binding points to a source column ID; no executable expressions are allowed.
export const templates = Object.freeze({
  cards: { label: '카드 목록', ready: true, required: ['title'], optional: ['subtitle', 'image', 'badge'], lists: ['fields'] },
  detail: { label: '상세 페이지', ready: true, required: ['title'], optional: ['image', 'badge', 'link', 'phone'], lists: ['fields'] },
  table: { label: '테이블 목록', ready: false, required: [], optional: [], lists: ['fields'] },
  map: { label: '지도 목록', ready: false, required: ['title', 'latitude', 'longitude'], optional: [], lists: ['fields'] },
  calendar: { label: '캘린더', ready: false, required: ['title', 'start'], optional: ['end'], lists: ['fields'] },
  grouped: { label: '그룹별 목록', ready: false, required: ['title', 'group'], optional: [], lists: ['fields'] },
  form: { label: '입력·수정 폼', ready: false, required: [], optional: [], lists: ['fields'] },
});

const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
function keys(value, allowed) {
  if (!object(value) || Object.keys(value).some((key) => !allowed.includes(key))) throw new Error('지원하지 않는 설정입니다.');
}

// Configuration and data remain separate from React and from model responses.
export function validateConfig(config, columns) {
  keys(config, ['version', 'title', 'pages']);
  if (config.version !== 1 || typeof config.title !== 'string' || !config.title.trim() || config.title.length > 120) throw new Error('Preview 이름 또는 버전이 올바르지 않습니다.');
  if (!Array.isArray(config.pages) || !config.pages.length || config.pages.length > 7) throw new Error('페이지는 1~7개여야 합니다.');
  const columnIds = new Set(columns.map((column) => column.id));
  const pages = new Map();
  for (const page of config.pages) {
    keys(page, ['id', 'template', 'title', 'bindings', 'detailPage', 'charts']);
    if (typeof page.id !== 'string' || !/^[a-z][a-z0-9_]{0,63}$/.test(page.id) || pages.has(page.id)) throw new Error('페이지 ID가 잘못되었거나 중복되었습니다.');
    if (!Object.hasOwn(templates, page.template)) throw new Error('지원하지 않는 템플릿입니다.');
    if (typeof page.title !== 'string' || !page.title.trim() || page.title.length > 120) throw new Error('페이지 이름이 필요합니다.');
    const spec = templates[page.template];
    keys(page.bindings, [...spec.required, ...spec.optional, ...spec.lists]);
    for (const slot of spec.required) if (!Object.hasOwn(page.bindings, slot)) throw new Error(`${slot} 컬럼 연결이 필요합니다.`);
    for (const [slot, value] of Object.entries(page.bindings)) {
      const refs = spec.lists.includes(slot) ? value : [value];
      if (!Array.isArray(refs) || !refs.length || refs.length > 200 || new Set(refs).size !== refs.length || refs.some((id) => !columnIds.has(id))) throw new Error('컬럼 연결이 비어 있거나 잘못되었습니다.');
    }
    if (['table', 'form'].includes(page.template) && !page.bindings.fields?.length) throw new Error('표시할 필드가 필요합니다.');
    if (page.detailPage !== undefined && page.template !== 'cards') throw new Error('상세 연결은 카드 목록에서만 지원합니다.');
    if (page.charts !== undefined) {
      if (!['cards', 'table', 'grouped'].includes(page.template) || !Array.isArray(page.charts) || page.charts.length > 4) throw new Error('그래프는 목록 페이지에 최대 4개까지 설정할 수 있습니다.');
      for (const chart of page.charts) {
        keys(chart, ['type', 'title', 'groupBy', 'aggregate']);
        if (!['bar', 'donut'].includes(chart.type) || chart.aggregate !== 'count' || !columnIds.has(chart.groupBy)) throw new Error('그래프 종류·집계·컬럼 설정이 올바르지 않습니다.');
        if (typeof chart.title !== 'string' || !chart.title.trim() || chart.title.length > 120) throw new Error('그래프 제목이 필요합니다.');
      }
    }
    pages.set(page.id, page);
  }
  for (const page of config.pages) {
    if (page.detailPage !== undefined && pages.get(page.detailPage)?.template !== 'detail') throw new Error('상세 페이지 연결이 올바르지 않습니다.');
  }
  return config;
}

// Explicit example mapping, not semantic inference. Never guess for other headers.
export function reservationConfig(columns) {
  const find = (name) => {
    const found = columns.filter((column) => column.name === name);
    if (found.length !== 1) throw new Error(`예시 설정에 필요한 컬럼: ${name}`);
    return found[0].id;
  };
  const title = find('서비스명');
  const badge = find('서비스상태');
  const image = find('이미지경로');
  return validateConfig({ version: 1, title: '시설·서비스 둘러보기', pages: [
    { id: 'services', template: 'cards', title: '서비스 목록', detailPage: 'service_detail', bindings: {
      title, badge, image, subtitle: find('장소명'), fields: [find('소분류명'), find('결제방법')],
    }, charts: [
      { type: 'bar', title: '종목별 서비스 수', groupBy: find('소분류명'), aggregate: 'count' },
      { type: 'donut', title: '결제방법 비율', groupBy: find('결제방법'), aggregate: 'count' },
    ] },
    { id: 'service_detail', template: 'detail', title: '서비스 상세', bindings: {
      title, badge, image, link: find('바로가기URL'), phone: find('전화번호'),
      fields: columns.filter((column) => ![title, badge, image, find('바로가기URL'), find('전화번호')].includes(column.id)).map((column) => column.id),
    } },
  ] }, columns);
}

export function previewRecords(report) {
  return report.preview.slice(0, 5).map((row) => ({
    id: String(row.row_number),
    values: Object.fromEntries(report.columns.map((column, index) => [column.id, row.values[index] ?? null])),
  }));
}

export function safeWebUrl(value) {
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}
