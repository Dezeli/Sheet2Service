export const featureLabels = {
  request_review: '신청·승인', request_auto: '즉시 접수', inquiry: '문의 접수', browse_only: '목록 조회',
  reservation: '시간 예약',
  notice: '공지',
  rental: '대여·반납',
  quote: '견적 요청',
};

export function modulesOf(config) {
  return config ? config.modules || [config] : [];
}

export function rolesOf(config) {
  if (config?.role_selection) return config.role_selection;
  const modules = modulesOf(config);
  return {
    user: modules.map((module) => module.user.template),
    admin: ['manage_catalog', ...modules.filter((module) => module.user.template !== 'browse_only').map((module) => module.admin.template)],
    dashboard: ['csv_statistics',
      ...(modules.some((module) => ['request_review', 'request_auto'].includes(module.user.template)) ? ['request_statistics'] : []),
      ...(modules.some((module) => module.user.template === 'inquiry') ? ['inquiry_statistics'] : [])],
  };
}

export function selectedFirst(options, isSelected) {
  return [...options.filter(isSelected), ...options.filter((option) => !isSelected(option))];
}

export function featureGroup(template) {
  return ['request_review', 'request_auto'].includes(template) ? 'reception' : template;
}

export function recommendedSelection(options) {
  const groups = new Set();
  return options.filter((option) => {
    const group = featureGroup(option.template);
    if (!option.implemented || groups.has(group)) return false;
    groups.add(group);
    return true;
  });
}

export function toggleFeature(current, option) {
  if (current.some((item) => item.template === option.template)) {
    return current.filter((item) => item.template !== option.template);
  }
  return [...current.filter((item) => featureGroup(item.template) !== featureGroup(option.template)), option];
}

export function restoreFeatures(config, options) {
  return modulesOf(config).map((module) => {
    const template = module.user.template;
    const option = options.find((item) => item.template === template);
    return module.selection
      ? { ...option, template, user: module.user, admin: module.admin,
          user_title: module.user.title || option?.user_title,
          admin_title: module.admin.title || option?.admin_title, reference: module.selection }
      : option;
  }).filter(Boolean);
}
