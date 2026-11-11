import React, { useEffect, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import { ChoiceCombobox, Empty, Icon, IconButton } from '../components/ui';
import ServiceDialog from '../components/ServiceDialog';
import { NavContext, placeHref } from './nav';
import InquiryPage, { InquiryMetrics } from '../inquiry/InquiryPage';
import InquiryBoard from '../inquiry/InquiryBoard';
import NoticePage from '../notice/NoticePage';
import NoticeTicker from '../notice/NoticeTicker';
import AdminPreview from '../admin/AdminPreview';
import ServicePreviewV2 from '../preview/ServicePreviewV2';
import { api, featureLabels, hasFeature, modeLabels, query } from './api.js';
import ResourceBrowser from './ResourceBrowser';
import MyBookings from './MyBookings';
import BookingReview from './BookingReview';
import AdminSchedule from './AdminSchedule';
import ResourceAdmin from './ResourceAdmin';
import SlotAdmin from './SlotAdmin';
import BookingRules from './BookingRules';
import BookingStats from './BookingStats';
import './booking.css';

// everyone but the public works in the staff layout (sidebar, tables)
const roleOf = (persona) => (persona === 'booker' || persona === 'viewer' ? 'user' : 'admin');
// the overview lives inside a role: reviewers open on it; a payment desk gets its own summary on 결제 확인 instead
const hasHome = (persona) => hasFeature(persona, 'dashboard') && (hasFeature(persona, 'review_reservations') || !hasFeature(persona, 'manage_payments'));

/** Menu entries a persona gets, in the order they appear. Data management expands into three screens. */
function menuFor(persona, service, counts = {}) {
  const items = [];
  const add = (key, label, icon) => items.push({ key, label, icon });
  const reviewer = hasFeature(persona, 'review_reservations');
  if (reviewer && hasHome(persona)) add('dashboard', '홈', 'dashboard');
  if (hasFeature(persona, 'browse_resources')) add('browse', hasFeature(persona, 'make_reservation') ? '예약하기' : '둘러보기', 'table');
  if (hasFeature(persona, 'my_reservations')) add('mine', '내 예약', 'reservation');
  if (hasFeature(persona, 'review_reservations')) { add('review', '예약 관리', 'request'); add('schedule', '일정표', 'schedule'); }
  // the field's own screen; where there is no field role, check-in sits in 예약 관리 instead
  if (hasFeature(persona, 'run_sessions') && !hasFeature(persona, 'review_reservations')) add('today', '오늘 이용', 'reservation');
  // setting up reads top to bottom: what is booked, then how it is booked
  if (hasFeature(persona, 'manage_resources')) add('resources', '항목 관리', 'table');
  // 회차 belong to sheets of dated sessions, and to items whose records settled into a fixed schedule
  if (hasFeature(persona, 'manage_schedule') && (service.sheetKind === 'schedule_slots' || counts.slots > 0)) add('slots', '회차·정원', 'schedule');
  if (service.booking.acceptsNew && hasFeature(persona, 'manage_schedule', 'manage_resources')) add('rules', '예약 규칙', 'rules');
  if (hasFeature(persona, 'inquiry')) add('inquiry', '문의', 'inquiry');
  if (hasFeature(persona, 'reply_inquiries')) add('inquiries', '문의 답변', 'inquiry');
  if (hasFeature(persona, 'notices')) add('notices', '공지', 'notice');
  if (hasFeature(persona, 'manage_payments')) add('payments', '결제 확인', 'payment');
  if (hasFeature(persona, 'manage_notices')) add('notices_admin', '공지 관리', 'notice');
  if (!reviewer && hasHome(persona)) add('dashboard', '현황', 'dashboard');
  if (hasFeature(persona, 'manage_data') && service.dashboard?.preview) add('stats', '데이터 통계', 'analysis');
  if (hasFeature(persona, 'manage_data')) { add('fields', '필드 구성', 'fields'); add('choices', '선택지 관리', 'choices'); add('data', '데이터 관리', 'data'); }
  return items;
}

function ScopeBar({ uploadId, persona, scope, onChange }) {
  const [scopes, setScopes] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    api(`/api/uploads/${uploadId}/bookings/scopes/${query({ persona: persona.id })}`)
      .then((data) => setScopes(data))
      .catch((caught) => setError(caught.message));
  }, [uploadId, persona.id]);
  return <div className="scope-bar">
    <span className="field-label">{scopes?.label || '담당 범위'}</span>
    <div className="scope-choice"><ChoiceCombobox label={scopes?.label || '담당 범위'} options={scopes?.values || []} value={scope} onChange={onChange} placeholder="전체" /></div>
    {scope && <IconButton icon="close" label="전체 보기" onClick={() => onChange('')} />}
    {error && <span className="error">{error}</span>}
  </div>;
}

/** The role's home: today's bookings first, then where inquiries stand. Sheet charts have their own screen. */
function Dashboard({ uploadId, service, persona, scope }) {
  return <div className="home-workspace">
    {service.booking.mode !== 'none' && <BookingStats uploadId={uploadId} persona={persona} scope={scope} />}
    {hasFeature(persona, 'reply_inquiries') && <InquiryMetrics uploadId={uploadId} />}
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
        <a className="service-source" href={`/api/uploads/${uploadId}/original/`} download title="원본 시트 내려받기"><Icon name="download" size={16} />{data.upload.name}</a></div>
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
        <span className="muted">{menuFor(item, service, data.counts).map((entry) => entry.label).join(' · ')}</span>
        {item.evidence && <small className="muted">{item.evidence}</small>}
      </li>)}</ul>
    </section>
    {data.understanding?.questions?.length > 0 && <section className="panel">
      <div className="section-title"><h2>확인이 필요한 점</h2></div>
      <ul className="question-list">{data.understanding.questions.map((question, index) => <li key={index}>{question}</li>)}</ul>
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
  const [menu, setMenu] = useState(() => new URLSearchParams(window.location.search).get('menu') || '');
  const [focus, setFocus] = useState(() => new URLSearchParams(window.location.search).get('item') || '');
  const [view, setView] = useState(() => new URLSearchParams(window.location.search).get('view') || '');
  const [scope, setScope] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [fieldLabels, setFieldLabels] = useState({});
  const [badges, setBadges] = useState({}); // menu key → things waiting for staff
  const [renaming, setRenaming] = useState(null); // the draft service name while an admin renames it
  const [renameError, setRenameError] = useState('');
  useEffect(() => {
    let active = true;
    Promise.all([api(`/api/uploads/${uploadId}/service/`), api('/api/session/')])
      .then(([service, session]) => { if (active) { setData(service); setCsrf(session.csrf_token); setFieldLabels(service.upload.field_labels || {}); } })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId]);
  useEffect(() => {
    const restore = () => { const params = new URLSearchParams(window.location.search); setMenu(params.get('menu') || ''); setFocus(params.get('item') || ''); setView(params.get('view') || ''); };
    window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, []);
  // a move inside this page: the address changes too, so Back returns and the place can be shared
  const go = (nextMenu, item = '', nextView = '') => {
    window.history.pushState(null, '', placeHref(uploadId, page, nextMenu, item, nextView));
    setMenu(nextMenu || ''); setFocus(item || ''); setView(nextView || ''); window.scrollTo(0, 0);
  };

  const service = data?.service;
  const personas = service?.personas || [];
  // the old top-level dashboard address now opens the home of the first role that has one
  useEffect(() => {
    if (page !== 'DashBoard' || !service) return;
    const home = service.personas.find((item) => hasHome(item) && hasFeature(item, 'review_reservations')) || service.personas.find(hasHome);
    if (home) window.location.replace(placeHref(uploadId, home.id, 'dashboard'));
  }, [page, service]);
  // what is waiting for staff, as numbers beside the menu: re-read when the screen changes and every minute
  useEffect(() => {
    const me = service?.personas?.find((item) => item.id === page);
    if (!me || roleOf(me.id) !== 'admin') { setBadges({}); return undefined; }
    let active = true;
    const refresh = async () => {
      const next = {};
      const asks = [];
      if (hasFeature(me, 'review_reservations', 'manage_payments')) {
        asks.push(api(`/api/uploads/${uploadId}/bookings/stats/${query({ persona: me.id, scope })}`).then((stats) => {
          if (hasFeature(me, 'review_reservations')) next.review = stats.counts.requested; // the same 승인 대기 the dashboard and the quick filter show
          if (hasFeature(me, 'manage_payments')) next.payments = stats.payments?.unpaid || 0;
        }).catch(() => {}));
      }
      if (hasFeature(me, 'reply_inquiries')) {
        asks.push(api(`/api/uploads/${uploadId}/inquiries/stats/`).then((stats) => { next.inquiries = stats.counts.received; }).catch(() => {}));
      }
      await Promise.all(asks);
      if (active) setBadges(next);
    };
    refresh();
    const timer = setInterval(refresh, 60000);
    return () => { active = false; clearInterval(timer); };
  }, [uploadId, page, service, scope, menu]);
  // the browser tab carries the service's own name
  useEffect(() => { const name = service?.title || service?.subject; if (name && page !== 'summary') document.title = name; }, [service?.title, service?.subject, page]);
  if (page === 'summary') {
    if (error) return <main className="service-page"><p className="error" role="alert">{error}</p></main>;
    if (!data) return <main className="service-page"><p role="status">분석 결과를 불러오는 중입니다.</p></main>;
    return <SummaryPage uploadId={uploadId} data={data} />;
  }
  const persona = personas.find((item) => item.id === page);
  const items = service && persona ? menuFor(persona, service, data.counts) : [];
  const active = items.some((item) => item.key === menu) ? menu : items[0]?.key;
  const hasScope = Boolean(persona?.scopeColumn); // the desk's work splits by a column: an optional narrowing
  const role = roleOf(persona?.id);
  const siteTitle = service?.title || service?.subject || '예약 서비스';
  const canRename = role === 'admin' && hasFeature(persona, 'review_reservations', 'manage_resources', 'manage_data');
  async function rename(event) {
    event.preventDefault();
    try {
      const response = await fetch(`/api/uploads/${uploadId}/service/`, { method: 'PATCH', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify({ persona: persona.id, title: renaming }) });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(result?.detail || '이름을 바꾸지 못했습니다.');
      setData((current) => ({ ...current, service: { ...current.service, title: result.service.title } })); setRenaming(null);
    } catch (caught) { setRenameError(caught.message); }
  }
  const report = data ? { ...data.upload.analysis, columns: data.upload.analysis.columns.map((column, index) => ({
    ...column, original_label: column.label, label: fieldLabels[String(index + 1)] || column.label })) } : null;

  const nav = { uploadId, page, go, has: (key) => items.some((item) => item.key === key) };
  return <NavContext.Provider value={nav}><main className="service-page" data-role={role}>
    <header className="service-page-header">
      <div className="service-topline">
        <span className="service-title-line">
          <a className="service-site-title" href={data ? `/${uploadId}/${persona?.id || data.landing}` : '/'}>{data ? siteTitle : ''}</a>
          {data && canRename && <IconButton icon="edit" label="서비스 이름 바꾸기" onClick={() => { setRenameError(''); setRenaming(siteTitle); }} />}
          {data && role !== 'user' && <a className="service-source-file" href={`/api/uploads/${uploadId}/original/`} download title={`원본 시트 내려받기 · ${data.upload.name.normalize('NFC')}`}>
            <Icon name="download" size={16} /><span>{data.upload.name.normalize('NFC')}</span></a>}
        </span>
        <nav className="service-switch" aria-label="역할 이동">
          {personas.map((item) => <a key={item.id} href={`/${uploadId}/${item.id}`} aria-current={page === item.id ? 'page' : undefined}>{item.title}</a>)}
        </nav>
      </div>
    </header>
    {renaming !== null && <ServiceDialog title="서비스 이름" error={renameError} onClose={() => setRenaming(null)} className="rename-dialog">
      <form onSubmit={rename} className="form-grid">
        <label>이용자에게 보이는 이름<input autoFocus required maxLength={40} value={renaming} onChange={(event) => setRenaming(event.target.value)} /></label>
        <div className="dialog-actions"><button type="submit" data-intent="primary" disabled={!csrf || !renaming.trim()}>저장</button></div>
      </form>
    </ServiceDialog>}
    {error && <p className="error" role="alert">{error}</p>}
    {!error && !data && <p role="status">서비스 화면을 불러오는 중입니다.</p>}
    {data && !persona && <p className="error" role="alert">이 서비스에 없는 역할입니다. <a href={`/${uploadId}/${data.landing}`}>처음 화면으로</a></p>}
    {data && persona && <>
      {hasScope && <ScopeBar uploadId={uploadId} persona={persona} scope={scope} onChange={setScope} />}
      <div className={role === 'admin' && items.length > 1 ? 'admin-shell' : undefined}>
        {role === 'admin' && items.length > 1 && <aside className="admin-sidebar">
          <nav aria-label="관리 메뉴">{items.map((item) => <button type="button" key={item.key} aria-current={item.key === active ? 'page' : undefined} onClick={() => go(item.key)}>
            <SectionIcon name={item.icon} />{item.label}
            {badges[item.key] > 0 && <span className="menu-badge" aria-label={`처리할 것 ${badges[item.key]}건`}>{badges[item.key] > 99 ? '99+' : badges[item.key]}</span>}</button>)}</nav></aside>}
        {role !== 'admin' && items.length > 1 && <nav className="feature-tabs" aria-label="서비스 기능">
          {items.map((item) => <button type="button" key={item.key} aria-pressed={item.key === active} onClick={() => go(item.key)}><SectionIcon name={item.icon} />{item.label}</button>)}</nav>}
        {role !== 'admin' && active !== 'notices' && items.some((item) => item.key === 'notices') && <NoticeTicker uploadId={uploadId} />}
        <div className={role === 'admin' && items.length > 1 ? 'admin-content' : undefined}>
          {active === 'browse' && <ResourceBrowser uploadId={uploadId} service={service} persona={persona} csrf={csrf} focus={focus} onReserved={() => setRefresh((n) => n + 1)} />}
          {active === 'mine' && <MyBookings uploadId={uploadId} service={service} persona={persona} csrf={csrf} refreshKey={refresh} />}
          {active === 'review' && <BookingReview uploadId={uploadId} service={service} persona={persona} csrf={csrf} scope={scope} focus={focus} view={view} />}
          {active === 'schedule' && <AdminSchedule uploadId={uploadId} service={service} persona={persona} csrf={csrf} scope={scope} focus={focus} />}
          {active === 'today' && <BookingReview uploadId={uploadId} service={service} persona={persona} csrf={csrf} scope={scope} focus={focus} mode="field" />}
          {active === 'payments' && <BookingReview uploadId={uploadId} service={service} persona={persona} csrf={csrf} scope={scope} focus={focus} mode="payments" />}
          {active === 'slots' && <SlotAdmin uploadId={uploadId} service={service} persona={persona} csrf={csrf} />}
          {active === 'rules' && <BookingRules uploadId={uploadId} service={service} persona={persona} csrf={csrf}
            onSaved={(rules) => setData((current) => ({ ...current, service: { ...current.service,
              booking: { ...current.service.booking, rules, unit: rules.timeMode } } }))} />}
          {active === 'resources' && <ResourceAdmin uploadId={uploadId} service={service} persona={persona} csrf={csrf} />}
          {active === 'inquiry' && <InquiryBoard uploadId={uploadId} withResource={!service.resources.implicit} />}
          {active === 'inquiries' && <InquiryPage uploadId={uploadId} admin />}
          {active === 'notices' && <NoticePage uploadId={uploadId} focus={focus} />}
          {active === 'notices_admin' && <NoticePage uploadId={uploadId} admin />}
          {active === 'dashboard' && <Dashboard uploadId={uploadId} service={service} persona={persona} scope={scope} />}
          {active === 'stats' && <div className="dashboard-data"><ServicePreviewV2 uploadId={uploadId} report={report} config={service.dashboard.preview} usedFallback={false} /></div>}
          {['fields', 'choices', 'data'].includes(active) && <AdminPreview key={active} uploadId={uploadId} report={report} dashboardConfig={service.dashboard.preview}
            workflowConfig={null} embedded onFieldLabelsChange={setFieldLabels} titleColumns={service.resources.columns}
            viewTemplate={active === 'data' ? 'records' : active} />}
          {!items.length && <Empty>이 역할에 배정된 기능이 없습니다.</Empty>}
        </div>
      </div>
    </>}
  </main></NavContext.Provider>;
}
