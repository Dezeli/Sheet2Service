export const featureLabels = {
  request_review: '신청·승인', request_auto: '즉시 접수', inquiry: '문의 접수', browse_only: '목록 조회',
  reservation: '시간 예약',
  notice: '공지',
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
