import { validateConfigV2 } from '../preview/configV2.js';

const TEMPLATES = Object.freeze(['records', 'fields', 'choices', 'requests']);

export function createAdminConfig(report, dashboardConfig, workflowConfig = null) {
  validateConfigV2(dashboardConfig, report.columns);
  const columns = report.columns.map((_, index) => index + 1);
  const preferred = dashboardConfig.views.find((view) => view.template === 'table');
  const listColumns = preferred ? preferred.columns : columns.slice(0, Math.min(6, columns.length));
  const views = [
    { template: 'records', columns: listColumns },
    { template: 'fields', columns },
    { template: 'choices', columns },
  ];
  if (['review_requests', 'monitor_requests'].includes(workflowConfig?.admin?.template)) {
    views.push({ template: 'requests', columns: [workflowConfig.admin.subjectColumn] });
  }
  return validateAdminConfig({
    version: 1,
    views,
  }, report.columns);
}

export function validateAdminConfig(config, columns) {
  if (!config || config.version !== 1 || !Array.isArray(config.views)
      || ![3, 4].includes(config.views.length)
      || config.views.some((view) => !view || !TEMPLATES.includes(view.template))
      || config.views.some((view, index) => !view || view.template !== TEMPLATES[index]
        || Object.keys(view).some((key) => !['template', 'columns'].includes(key))
        || !Array.isArray(view.columns) || !view.columns.length
        || new Set(view.columns).size !== view.columns.length
        || view.columns.some((number) => !Number.isInteger(number) || number < 1 || number > columns.length))) {
    throw new Error('관리자 화면 설정이 올바르지 않습니다.');
  }
  return config;
}
