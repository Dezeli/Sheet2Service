const viewKeys = {
  cards: ['template', 'titleColumn', 'subtitleColumn', 'imageColumn', 'badgeColumn', 'fields', 'charts'],
  table: ['template', 'columns', 'charts'],
  grouped: ['template', 'groupColumn', 'titleColumn', 'subtitleColumn', 'badgeColumn', 'fields', 'charts'],
};

const required = {
  cards: ['template', 'titleColumn', 'fields'],
  table: ['template', 'columns'],
  grouped: ['template', 'groupColumn', 'titleColumn', 'fields'],
};

const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const exactKeys = (value, allowed, needed) => object(value)
  && Object.keys(value).every((key) => allowed.includes(key))
  && needed.every((key) => Object.hasOwn(value, key));

export function validateConfigV2(config, columns) {
  if (!exactKeys(config, ['version', 'views'], ['version', 'views']) || config.version !== 2
    || !Array.isArray(config.views) || !config.views.length || config.views.length > 7) {
    throw new Error('미리보기 설정 형식이 올바르지 않습니다.');
  }
  const exists = (number) => Number.isInteger(number) && number >= 1 && number <= columns.length;
  const numbers = (value, nonempty) => Array.isArray(value) && (!nonempty || value.length > 0)
    && value.length <= columns.length && value.every(exists) && new Set(value).size === value.length;
  for (const view of config.views) {
    const kind = view?.template;
    if (!Object.hasOwn(viewKeys, kind) || !exactKeys(view, viewKeys[kind], required[kind])) {
      throw new Error('지원하지 않는 목록 설정입니다.');
    }
    for (const [key, value] of Object.entries(view)) {
      if (key.endsWith('Column') && !exists(value)) throw new Error('컬럼 번호가 올바르지 않습니다.');
    }
    if (kind === 'table' ? !numbers(view.columns, true) : !numbers(view.fields, false)) {
      throw new Error('표시할 컬럼이 올바르지 않습니다.');
    }
    if (view.charts !== undefined) {
      if (!Array.isArray(view.charts) || view.charts.length > 4) throw new Error('차트 수가 올바르지 않습니다.');
      for (const chart of view.charts) {
        if (!exactKeys(chart, ['type', 'groupColumn', 'aggregate'], ['type', 'groupColumn', 'aggregate'])
          || !['bar', 'donut'].includes(chart.type) || chart.aggregate !== 'count' || !exists(chart.groupColumn)) {
          throw new Error('차트 설정이 올바르지 않습니다.');
        }
      }
    }
  }
  return config;
}

export const columnId = (columns, number) => columns[number - 1].id;
export const columnLabel = (columns, number) => columns[number - 1].label || `컬럼 ${number}`;

export function chartConfigsV2(charts = [], columns) {
  return charts.map((chart) => ({
    type: chart.type,
    groupBy: columnId(columns, chart.groupColumn),
    aggregate: chart.aggregate,
    title: `${columnLabel(columns, chart.groupColumn)}별 항목 수`,
  }));
}
