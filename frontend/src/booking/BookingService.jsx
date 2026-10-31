import React, { useEffect, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import InquiryPage, { InquiryMetrics } from '../inquiry/InquiryPage';
import NoticePage from '../notice/NoticePage';
import AdminPreview from '../admin/AdminPreview';
import ServicePreviewV2 from '../preview/ServicePreviewV2';
import { api, featureLabels, hasFeature, modeLabels, personaIcons, query } from './api.js';
import ResourceBrowser from './ResourceBrowser';
import MyBookings from './MyBookings';
import BookingReview from './BookingReview';
import ResourceAdmin from './ResourceAdmin';
import SlotAdmin from './SlotAdmin';
import BookingStats from './BookingStats';
import './booking.css';

const REVIEWERS = ['admin', 'staff', 'org_manager', 'finance'];
const roleOf = (persona) => persona === 'dashboard' ? 'dashboard' : REVIEWERS.includes(persona) ? 'admin' : 'user';

/** Menu entries a persona gets, in the order they appear. Data management expands into three screens. */
function menuFor(persona, service) {
  const subject = service.subject;
  const items = [];
  const add = (key, label, icon) => items.push({ key, label, icon });
  if (hasFeature(persona, 'browse_resources')) add('browse', `${subject} ${hasFeature(persona, 'make_reservation') ? '찾기·예약' : '둘러보기'}`, 'table');
  if (hasFeature(persona, 'my_reservations')) add('mine', '내 예약', 'reservation');
  if (hasFeature(persona, 'review_reservations')) add('review', '예약 관리', 'request');
  if (hasFeature(persona, 'manage_schedule')) add('slots', '일정·정원', 'reservation');
  if (hasFeature(persona, 'manage_resources')) add('resources', `${subject} 관리`, 'table');
  if (hasFeature(persona, 'inquiry')) add('inquiry', '문의', 'inquiry');
  if (hasFeature(persona, 'reply_inquiries')) add('inquiries', '문의 답변', 'inquiry');
  if (hasFeature(persona, 'notices')) add('notices', '공지', 'notice');
  if (hasFeature(persona, 'manage_payments')) add('payments', '결제 확인', 'analysis');
  if (hasFeature(persona, 'manage_notices')) add('notices_admin', '공지 관리', 'notice');
  // the dashboard is a top-level screen, not a menu entry of a role
  if (hasFeature(persona, 'manage_data')) { add('fields', '필드 구성', 'features'); add('choices', '선택지 관리', 'features'); add('data', '데이터 관리', 'table'); }
  return items;
}

function ScopeBar({ uploadId, persona, scope, onChange }) {
  const [scopes, setScopes] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    api(`/api/uploads/${uploadId}/bookings/scopes/${query({ persona: persona.id })}`)
      .then((data) => { setScopes(data); if (!scope && data.values.length === 1) onChange(data.values[0]); })
      .catch((caught) => setError(caught.message));
  }, [uploadId, persona.id]);
  return <div className="scope-bar">
    <label>{scopes?.label || '담당 범위'}
      <select value={scope} onChange={(event) => onChange(event.target.value)}>
        <option value="">선택해 주세요</option>
        {(scopes?.values || []).map((value) => <option key={value} value={value}>{value}</option>)}
      </select></label>
    <span className="muted">{persona.evidence || '이 역할은 선택한 범위의 예약만 봅니다.'}</span>
    {error && <span className="error">{error}</span>}
  </div>;
}

function Dashboard({ uploadId, service, upload, persona, scope }) {
  const report = { ...upload.analysis, columns: upload.analysis.columns.map((column, index) => ({
    ...column, original_label: column.label, label: upload.field_labels?.[String(index + 1)] || column.label })) };
  return <div className="dashboard-workspace">
    {service.booking.mode !== 'none' && <BookingStats uploadId={uploadId} persona={persona} scope={scope} />}
    {hasFeature(persona, 'reply_inquiries') && <InquiryMetrics uploadId={uploadId} />}
    <div className="dashboard-data"><ServicePreviewV2 uploadId={uploadId} report={report} config={service.dashboard.preview} usedFallback={false} /></div>
  </div>;
}

/** Shown once, right after generation: what was read from the sheet and what was built from it. */
function SummaryPage({ uploadId, data }) {
  const service = data.service;
  const counts = data.counts || {};
  const built = [counts.resources ? `${service.resources.levels.at(-1) || '항목'} ${counts.resources.toLocaleString()}개` : null,
    counts.slots ? `회차 ${counts.slots.toLocaleString()}개` : null,
    counts.bookings ? `예약 기록 ${counts.bookings.toLocaleString()}건` : null].filter(Boolean);
  return <main className="service-page summary-page" data-role="dashboard">
    <header className="service-page-header">
      <div className="service-topline"><a className="service-brand" href="/">Sheet2Service</a></div>
      <div className="service-heading-row"><h1 className="icon-heading"><SectionIcon name="help" />시트 분석 결과</h1>
        <a className="service-source" href={`/api/uploads/${uploadId}/original/`} download>{data.upload.name}</a></div>
    </header>
    <section className="panel service-summary">
      {service.summary.split('\n').filter(Boolean).map((line, index) => <p key={index}>{line}</p>)}
      <dl className="metrics">
        <div><dt>예약 대상</dt><dd className="metric-text">{service.resources.levels.join(' › ') || '없음'}</dd></div>
        <div><dt>예약 방식</dt><dd className="metric-text">{modeLabels[service.booking.mode]}</dd></div>
        <div><dt>시트에서 만든 것</dt><dd className="metric-text">{built.join(' · ') || '없음'}</dd></div>
      </dl>
    </section>
    <section className="panel">
      <div className="section-title"><h2>역할과 기능</h2></div>
      <ul className="persona-list">{service.personas.map((item) => <li key={item.id}>
        <strong>{item.title}</strong>
        <span className="muted">{menuFor(item, service).map((entry) => entry.label).join(' · ')}</span>
        {item.evidence && <small className="muted">{item.evidence}</small>}
      </li>)}</ul>
    </section>
    {data.understanding?.questions?.length > 0 && <section className="panel">
      <div className="section-title"><h2>확인이 필요한 점</h2></div>
      <ul className="question-list">{data.understanding.questions.map((question, index) => <li key={index}>{question}</li>)}</ul>
      <p className="muted">가장 근거 있는 쪽으로 서비스를 만들었습니다. 다르면 관리자 화면에서 항목·일정을 고쳐 쓰면 됩니다.</p>
    </section>}
    <div className="summary-actions">
      <a className="button-link" href={`/${uploadId}/${data.landing}`}>서비스 시작</a>
      {service.personas.map((item) => <a key={item.id} className="button-link secondary" href={`/${uploadId}/${item.id}`}>{item.title}로 보기</a>)}
    </div>
  </main>;
}

export default function BookingService({ uploadId, page }) {
  const [data, setData] = useState(null);
  const [csrf, setCsrf] = useState('');
  const [error, setError] = useState('');
  const [menu, setMenu] = useState('');
  const [scope, setScope] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [fieldLabels, setFieldLabels] = useState({});
  useEffect(() => {
    let active = true;
    Promise.all([api(`/api/uploads/${uploadId}/service/`), api('/api/session/')])
      .then(([service, session]) => { if (active) { setData(service); setCsrf(session.csrf_token); setFieldLabels(service.upload.field_labels || {}); } })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId]);

  const service = data?.service;
  const personas = service?.personas || [];
  if (page === 'summary') {
    if (error) return <main className="service-page"><p className="error" role="alert">{error}</p></main>;
    if (!data) return <main className="service-page"><p role="status">분석 결과를 불러오는 중입니다.</p></main>;
    return <SummaryPage uploadId={uploadId} data={data} />;
  }
  const isDashboard = page === 'DashBoard';
  const persona = isDashboard
    ? (personas.find((item) => item.id === 'admin') || personas.find((item) => hasFeature(item, 'dashboard')) || personas[0])
    : personas.find((item) => item.id === page);
  const items = service && persona && !isDashboard ? menuFor(persona, service) : [];
  const active = items.some((item) => item.key === menu) ? menu : items[0]?.key;
  const needsScope = persona && ['staff', 'org_manager'].includes(persona.id);
  const role = roleOf(isDashboard ? 'dashboard' : persona?.id);
  const title = isDashboard ? '대시보드' : persona?.title || '서비스';
  const report = data ? { ...data.upload.analysis, columns: data.upload.analysis.columns.map((column, index) => ({
    ...column, original_label: column.label, label: fieldLabels[String(index + 1)] || column.label })) } : null;

  return <main className="service-page" data-role={role}>
    <header className="service-page-header">
      <div className="service-topline"><a className="service-brand" href="/">Sheet2Service</a>
        <nav className="service-switch" aria-label="역할 이동">
          {personas.some((item) => hasFeature(item, 'dashboard')) && <a href={`/${uploadId}/DashBoard`} aria-current={isDashboard ? 'page' : undefined}>대시보드</a>}
          {personas.map((item) => <a key={item.id} href={`/${uploadId}/${item.id}`} aria-current={page === item.id ? 'page' : undefined}>{item.title}</a>)}
        </nav>
      </div>
      <div className="service-heading-row"><h1 className="icon-heading"><SectionIcon name={isDashboard ? 'dashboard' : personaIcons[persona?.id] || 'user'} />{title}</h1>
        {data && <a className="service-source" href={`/api/uploads/${uploadId}/original/`} download>{data.upload.name}</a>}
      </div>
      {service && !isDashboard && <p className="service-subject muted">{service.subject} · {modeLabels[service.booking.mode]}</p>}
    </header>
    {error && <p className="error" role="alert">{error}</p>}
    {!error && !data && <p role="status">서비스 화면을 불러오는 중입니다.</p>}
    {data && !persona && <p className="error" role="alert">이 서비스에 없는 역할입니다. <a href={`/${uploadId}/${data.landing}`}>처음 화면으로</a></p>}
    {data && persona && isDashboard && <Dashboard uploadId={uploadId} service={service} upload={data.upload} persona={persona} scope={scope} />}
    {data && persona && !isDashboard && <>
      {needsScope && <ScopeBar uploadId={uploadId} persona={persona} scope={scope} onChange={setScope} />}
      <div className={role === 'admin' ? 'admin-shell' : undefined}>
        {role === 'admin' && <aside className="admin-sidebar"><p className="admin-sidebar-title">관리 메뉴</p>
          <nav aria-label="관리 메뉴">{items.map((item) => <button type="button" key={item.key} aria-current={item.key === active ? 'page' : undefined} onClick={() => setMenu(item.key)}>{item.label}</button>)}</nav></aside>}
        {role !== 'admin' && items.length > 1 && <nav className="feature-tabs" aria-label="서비스 기능">
          {items.map((item) => <button type="button" key={item.key} aria-pressed={item.key === active} onClick={() => setMenu(item.key)}><SectionIcon name={item.icon} />{item.label}</button>)}</nav>}
        <div className={role === 'admin' ? 'admin-content' : undefined}>
          {active === 'browse' && <ResourceBrowser uploadId={uploadId} service={service} persona={persona} csrf={csrf} onReserved={() => setRefresh((n) => n + 1)} />}
          {active === 'mine' && <MyBookings uploadId={uploadId} service={service} persona={persona} csrf={csrf} refreshKey={refresh} />}
          {active === 'review' && <BookingReview uploadId={uploadId} service={service} persona={persona} csrf={csrf} scope={scope} />}
          {active === 'payments' && <BookingReview uploadId={uploadId} service={service} persona={persona} csrf={csrf} scope={scope} mode="payments" />}
          {active === 'slots' && <SlotAdmin uploadId={uploadId} service={service} persona={persona} csrf={csrf} />}
          {active === 'resources' && <ResourceAdmin uploadId={uploadId} service={service} persona={persona} csrf={csrf} />}
          {active === 'inquiry' && <InquiryPage uploadId={uploadId} subjectColumn={service.resources.columns.at(-1) || 0} />}
          {active === 'inquiries' && <InquiryPage uploadId={uploadId} subjectColumn={service.resources.columns.at(-1) || 0} admin />}
          {active === 'notices' && <NoticePage uploadId={uploadId} title="공지" />}
          {active === 'notices_admin' && <NoticePage uploadId={uploadId} title="공지 관리" admin />}
          {active === 'dashboard' && <Dashboard uploadId={uploadId} service={service} upload={data.upload} persona={persona} scope={scope} />}
          {['fields', 'choices', 'data'].includes(active) && <AdminPreview key={active} uploadId={uploadId} report={report} dashboardConfig={service.dashboard.preview}
            workflowConfig={null} embedded onFieldLabelsChange={setFieldLabels} titleColumns={service.resources.columns}
            viewTemplate={active === 'data' ? 'records' : active} />}
          {!items.length && <p className="muted">이 역할에 배정된 기능이 없습니다.</p>}
        </div>
      </div>
    </>}
  </main>;
}
