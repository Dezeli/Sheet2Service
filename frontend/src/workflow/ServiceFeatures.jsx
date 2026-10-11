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
  const [selected, setSelected] = useState(modules[0]?.user.template || 'data');
  const report = service.upload.analysis;
  const catalog = modules.find((item) => item.user.template === 'browse_only');

  if (page === 'DashBoard') return <>
    {roles.dashboard.includes('request_statistics') && requestMetrics}
    {roles.dashboard.includes('inquiry_statistics') && <InquiryMetrics uploadId={uploadId} />}
    {roles.dashboard.includes('csv_statistics') && <ServicePreviewV2 uploadId={uploadId} report={report} config={service.result.preview} usedFallback={service.result.used_fallback} />}
    {!roles.dashboard.length && <p className="muted">선택한 대시보드 기능이 없습니다.</p>}
  </>;

  if (!modules.length && page === 'User') return <p className="muted">선택한 사용자 기능이 없습니다.</p>;
  if (!roles.admin.length && page === 'Admin') return <p className="muted">선택한 관리자 기능이 없습니다.</p>;
  const choices = page === 'Admin'
    ? [...(roles.admin.includes('manage_catalog') ? [{ template: 'data', label: '데이터 관리' }] : []), ...modules.filter((item) => item.user.template !== 'browse_only')
      .map((item) => ({ template: item.user.template, label: item.admin.title || featureLabels[item.user.template] }))]
    : modules.map((item) => ({ template: item.user.template, label: item.user.title || featureLabels[item.user.template] }));
  const activeTemplate = choices.some((item) => item.template === selected) ? selected : choices[0]?.template;
  const module = modules.find((item) => item.user.template === activeTemplate);
  const dataSelected = page === 'Admin' && activeTemplate === 'data';
  return <>
    {choices.length > 1 && <nav className="feature-tabs" aria-label="서비스 기능">
      {choices.map((item) => <button type="button" key={item.template}
        aria-pressed={item.template === activeTemplate}
        onClick={() => setSelected(item.template)}><SectionIcon name={item.template === 'data' || item.template === 'browse_only' ? 'table'
          : ['request_review', 'request_auto'].includes(item.template) ? 'request' : item.template} />{item.label}</button>)}
    </nav>}
    {page === 'Admin'
      ? dataSelected
        ? <AdminPreview key="data" uploadId={uploadId} report={report} dashboardConfig={service.result.preview} workflowConfig={catalog || null} />
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
  </>;
}
