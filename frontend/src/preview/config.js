// Initial catalog: these seven IDs are the only supported template choices.
// Each binding points to a source column ID; no executable expressions are allowed.
export const templates = Object.freeze({
  cards: { label: 'Card list', ready: true, required: ['title'], optional: ['subtitle', 'image', 'badge'], lists: ['fields'] },
  detail: { label: 'Detail page', ready: true, required: ['title'], optional: ['image', 'badge', 'link', 'phone'], lists: ['fields'] },
  table: { label: 'Table list', ready: true, required: [], optional: [], lists: ['fields'] },
  map: { label: 'Map list', ready: false, required: ['title', 'latitude', 'longitude'], optional: [], lists: ['fields'] },
  calendar: { label: 'Calendar', ready: false, required: ['title', 'start'], optional: ['end'], lists: ['fields'] },
  grouped: { label: 'Grouped list', ready: true, required: ['title', 'group'], optional: ['subtitle', 'image', 'badge'], lists: ['fields'] },
  form: { label: 'Input form', ready: false, required: [], optional: [], lists: ['fields'] },
});

const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
function keys(value, allowed) {
  if (!object(value) || Object.keys(value).some((key) => !allowed.includes(key))) throw new Error('Unsupported config.');
}

// Configuration and data remain separate from React and from model responses.
export function validateConfig(config, columns) {
  keys(config, ['version', 'title', 'pages']);
  if (config.version !== 1 || typeof config.title !== 'string' || !config.title.trim() || config.title.length > 120) throw new Error('Preview title or version is invalid.');
  if (!Array.isArray(config.pages) || !config.pages.length || config.pages.length > 7) throw new Error('Preview must contain 1 to 7 pages.');
  const columnIds = new Set(columns.map((column) => column.id));
  const pages = new Map();
  for (const page of config.pages) {
    keys(page, ['id', 'template', 'title', 'bindings', 'detailPage', 'charts']);
    if (typeof page.id !== 'string' || !/^[a-z][a-z0-9_]{0,63}$/.test(page.id) || pages.has(page.id)) throw new Error('Page ID is invalid or duplicated.');
    if (!Object.hasOwn(templates, page.template)) throw new Error('Unsupported template.');
    if (typeof page.title !== 'string' || !page.title.trim() || page.title.length > 120) throw new Error('Page title is required.');
    const spec = templates[page.template];
    keys(page.bindings, [...spec.required, ...spec.optional, ...spec.lists]);
    for (const slot of spec.required) if (!Object.hasOwn(page.bindings, slot)) throw new Error(`${slot} column binding is required.`);
    for (const [slot, value] of Object.entries(page.bindings)) {
      const refs = spec.lists.includes(slot) ? value : [value];
      if (!Array.isArray(refs) || !refs.length || refs.length > 200 || new Set(refs).size !== refs.length || refs.some((id) => !columnIds.has(id))) throw new Error('Column binding is empty or invalid.');
    }
    if (['table', 'form'].includes(page.template) && !page.bindings.fields?.length) throw new Error('Display fields are required.');
    if (page.detailPage !== undefined && !['cards', 'grouped'].includes(page.template)) throw new Error('Detail links are supported only from card or grouped lists.');
    if (page.charts !== undefined) {
      if (!['cards', 'table', 'grouped'].includes(page.template) || !Array.isArray(page.charts) || page.charts.length > 4) throw new Error('Charts are supported only on list pages, up to 4 charts.');
      for (const chart of page.charts) {
        keys(chart, ['type', 'title', 'groupBy', 'aggregate']);
        if (!['bar', 'donut'].includes(chart.type) || chart.aggregate !== 'count' || !columnIds.has(chart.groupBy)) throw new Error('Chart type, aggregation, or column setting is invalid.');
        if (typeof chart.title !== 'string' || !chart.title.trim() || chart.title.length > 120) throw new Error('Chart title is required.');
      }
    }
    pages.set(page.id, page);
  }
  for (const page of config.pages) {
    if (page.detailPage !== undefined && pages.get(page.detailPage)?.template !== 'detail') throw new Error('Detail page link is invalid.');
  }
  return config;
}

// Development-only fallback mapping for quickly checking the Preview UI.
// Runtime API flow must use Claude-generated config instead.
export function reservationConfig(columns) {
  if (!Array.isArray(columns) || columns.length < 8) throw new Error('Development example config requires at least 8 columns.');
  const id = (index) => columns[index]?.id;
  const title = id(0);
  const badge = id(1);
  const image = id(2);
  const place = id(3);
  const category = id(4);
  const payment = id(5);
  const link = id(6);
  const phone = id(7);
  return validateConfig({ version: 1, title: 'Development service Preview', pages: [
    { id: 'dev_services', template: 'cards', title: 'Development list', detailPage: 'dev_service_detail', bindings: {
      title, badge, image, subtitle: place, fields: [category, payment],
    }, charts: [
      { type: 'bar', title: 'Items by category', groupBy: category, aggregate: 'count' },
      { type: 'donut', title: 'Items by status', groupBy: badge, aggregate: 'count' },
    ] },
    { id: 'dev_service_table', template: 'table', title: 'Development table', bindings: {
      fields: [title, badge, place, category, payment, phone, link],
    } },
    { id: 'dev_service_groups', template: 'grouped', title: 'Development groups', detailPage: 'dev_service_detail', bindings: {
      group: category, title, badge, image, subtitle: place, fields: [badge, payment],
    } },
    { id: 'dev_service_detail', template: 'detail', title: 'Development detail', bindings: {
      title, badge, image, link, phone,
      fields: columns.filter((column) => ![title, badge, image, link, phone].includes(column.id)).map((column) => column.id),
    } },
  ] }, columns);
}

export function previewRecords(report) {
  return report.preview.map((row) => ({
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
