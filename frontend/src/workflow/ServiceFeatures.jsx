import React, { useState } from 'react';
import { featureLabels, modulesOf, rolesOf } from './features';
import UserPage from '../user/UserPage';
import InquiryPage, { InquiryMetrics } from '../inquiry/InquiryPage';
import RequestManagement from '../requests/RequestManagement';
import AdminPreview from '../admin/AdminPreview';
import ServicePreviewV2 from '../preview/ServicePreviewV2';
import ReservationPage from '../reservation/ReservationPage';
import NoticePage from '../notice/NoticePage';
import RentalPage from '../rental/RentalPage';
import QuotePage from '../quote/QuotePage';
import SectionIcon from '../components/SectionIcon';

export default function ServiceFeatures({ uploadId, page, service, requestMetrics }) {
  const modules = modulesOf(service.workflow_config);
  const roles = rolesOf(service.workflow_config);
  const [selected, setSelected] = useState(page === 'Admin' && roles.admin.includes('manage_catalog') ? 'fields' : modules[0]?.user.template || 'data');
  const [fieldLabels, setFieldLabels] = useState(service.upload.field_labels || {});
  const report = { ...service.upload.analysis, columns: service.upload.analysis.columns.map((column, index) => ({
    ...column, original_label: column.label, label: fieldLabels[String(index + 1)] || column.label,
  })) };
  const catalog = modules.find((item) => item.user.template === 'browse_only');

  if (page === 'DashBoard') return <div className="dashboard-workspace">
    {roles.dashboard.includes('request_statistics') && requestMetrics}
    {roles.dashboard.includes('inquiry_statistics') && <InquiryMetrics uploadId={uploadId} />}
    {roles.dashboard.includes('csv_statistics') && <div className="dashboard-data"><ServicePreviewV2 uploadId={uploadId} report={report} config={service.result.preview} usedFallback={service.result.used_fallback} /></div>}
    {!roles.dashboard.length && <p className="muted">선택한 대시보드 기능이 없습니다.</p>}
  </div>;

  if (!modules.length && page === 'User') return <p className="muted">선택한 사용자 기능이 없습니다.</p>;
  if (!roles.admin.length && page === 'Admin') return <p className="muted">선택한 관리자 기능이 없습니다.</p>;
  const choices = page === 'Admin'
    ? [...(roles.admin.includes('manage_catalog') ? [{ template: 'fields', label: '필드 구성' }, { template: 'choices', label: '선택지 관리' }, { template: 'data', label: '데이터 관리' }] : []), ...modules.filter((item) => item.user.template !== 'browse_only')
      .map((item) => ({ template: item.user.template, label: item.admin.title || featureLabels[item.user.template] }))]
    : modules.map((item) => ({ template: item.user.template, label: item.user.title || featureLabels[item.user.template] }));
  const activeTemplate = choices.some((item) => item.template === selected) ? selected : choices[0]?.template;
  const module = modules.find((item) => item.user.template === activeTemplate);
  const dataSelected = page === 'Admin' && ['data', 'fields', 'choices'].includes(activeTemplate);
  return <div className={page === 'Admin' ? 'admin-shell' : undefined}>
    {page === 'Admin' && <aside className="admin-sidebar">
      <p className="admin-sidebar-title">관리 메뉴</p>
      <nav aria-label="관리 메뉴">{choices.map((item) => <button type="button" key={item.template}
        aria-current={item.template === activeTemplate ? 'page' : undefined}
        onClick={() => setSelected(item.template)}>{item.label}</button>)}</nav>
    </aside>}
    {page !== 'Admin' && choices.length > 1 && <nav className="feature-tabs" aria-label="서비스 기능">
      {choices.map((item) => <button type="button" key={item.template}
        aria-pressed={item.template === activeTemplate}
        onClick={() => setSelected(item.template)}><SectionIcon name={item.template === 'data' || item.template === 'browse_only' ? 'table'
          : ['request_review', 'request_auto'].includes(item.template) ? 'request' : item.template} />{item.label}</button>)}
    </nav>}
    <div className={page === 'Admin' ? 'admin-content' : undefined}>
    {page === 'Admin'
      ? dataSelected
        ? <AdminPreview key={activeTemplate} uploadId={uploadId} report={report} dashboardConfig={service.result.preview} workflowConfig={catalog || null}
            embedded onFieldLabelsChange={setFieldLabels} titleColumns={modules.map((item) => item.user.subjectColumn)} viewTemplate={activeTemplate === 'data' ? 'records' : activeTemplate} />
        : module.user.template === 'quote'
          ? <QuotePage key="quote" uploadId={uploadId} config={module} admin />
        : module.user.template === 'rental'
          ? <RentalPage key="rental" uploadId={uploadId} config={module} admin />
        : module.user.template === 'notice'
          ? <NoticePage key="notice" uploadId={uploadId} config={module} admin />
        : module.user.template === 'reservation'
          ? <ReservationPage key="reservation" uploadId={uploadId} config={module} admin />
        : module.user.template === 'inquiry'
          ? <InquiryPage key="inquiry" uploadId={uploadId} config={module} admin />
          : <RequestManagement key={module.user.template} uploadId={uploadId} title={module.admin.title} />
      : module.user.template === 'quote'
        ? <QuotePage key="quote" uploadId={uploadId} config={module} />
      : module.user.template === 'rental'
        ? <RentalPage key="rental" uploadId={uploadId} config={module} />
      : module.user.template === 'notice'
        ? <NoticePage key="notice" uploadId={uploadId} config={module} />
      : module.user.template === 'reservation'
        ? <ReservationPage key="reservation" uploadId={uploadId} config={module} />
      : module.user.template === 'inquiry'
        ? <InquiryPage key="inquiry" uploadId={uploadId} config={module} />
        : <UserPage key={module.user.template} uploadId={uploadId} report={report} config={module} />}
    </div>
  </div>;
}
