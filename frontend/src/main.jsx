import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import './fonts.css';
import TemplateExamples from './preview/TemplateExamples';
import ServiceFeatures from './workflow/ServiceFeatures';
import './theme.css';
import UploadDropzone from './upload/UploadDropzone';
import GenerateDialog from './upload/GenerateDialog';
import { csvFile } from './upload/files';
import SiteFooter from './components/SiteFooter';
import SectionIcon from './components/SectionIcon';
import './service.css';
import './hierarchy.css';

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof data?.detail === 'string' ? data.detail : '요청을 처리하지 못했습니다. 다시 시도해 주세요.');
  }
  if (!data) throw new Error('서버 응답을 읽지 못했습니다.');
  return data;
}

function App() {
  const [file, setFile] = useState(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [upload, setUpload] = useState(null);
  const [csrfToken, setCsrfToken] = useState('');
  const [callSummary, setCallSummary] = useState(null);
  const submitting = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function selectFile(files) {
    if (busy || submitting.current) return;
    setError('');
    let selected;
    try { selected = csvFile(files); }
    catch (caught) { setError(caught.message); return; }
    submitting.current = true;
    setFile(selected); setConfirmOpen(true);
    setBusy(true); setUpload(null); setCallSummary(null);
    try {
      const { csrf_token } = await api('/api/session/');
      setCsrfToken(csrf_token);
      const body = new FormData();
      body.append('file', selected); body.append('encoding', 'auto');
      const uploaded = await api('/api/uploads/', { method: 'POST', body, headers: { 'X-CSRFToken': csrf_token } });
      setUpload(uploaded);
      const summary = await api(`/api/uploads/${uploaded.id}/inference/`);
      setCallSummary(summary);
    } catch (err) {
      setError(err instanceof TypeError ? '서버에 연결할 수 없습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.' : err.message);
    } finally { submitting.current = false; setBusy(false); }
  }

  async function retrySummary() {
    if (!upload || busy || submitting.current) return;
    submitting.current = true; setBusy(true); setError('');
    try { setCallSummary(await api(`/api/uploads/${upload.id}/inference/`)); }
    catch (caught) { setError(caught.message); }
    finally { submitting.current = false; setBusy(false); }
  }

  async function generate() {
    if (!upload || !callSummary || busy || submitting.current) return;
    submitting.current = true; setBusy(true); setError('');
    try {
      const generated = await api(`/api/uploads/${upload.id}/inference/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ approved: true, approval_note: `생성 확인 모달의 서비스 생성 버튼으로 ${callSummary.model} 1회 호출 승인` }),
      });
      window.location.assign(`/${upload.id}/${generated.landing || 'DashBoard'}`);
    } catch (err) {
      setError(err instanceof TypeError ? '서버에 연결할 수 없습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.' : err.message);
    } finally { submitting.current = false; setBusy(false); }
  }

  function cancelUpload() {
    if (busy || submitting.current) return;
    setConfirmOpen(false); setFile(null); setUpload(null);
    setCallSummary(null); setError('');
  }

  return (
    <main className="upload-home">
      <header className="upload-header"><h1>Sheet2Service</h1></header>
      <div className="upload-hero">
      <div className="upload-intro">
      <h2 className="upload-headline"><span className="upload-headline-line">복잡한 스프레드시트를</span><br /><span className="upload-headline-accent">서비스로.</span></h2>
      <p className="upload-description">파일을 올리고, 필요한 서비스와 기능을 골라보세요.</p>
      <figure className="upload-visual">
        <img src="/images/sheet2service-workspace.png" alt="스프레드시트가 열린 노트북 작업 공간" width="1024" height="768" fetchPriority="high" />
      </figure>
      </div>
      <div className="upload-column">
      <section className="panel upload-card" aria-labelledby="upload-title">
        <h2 id="upload-title" className="visually-hidden">파일 업로드</h2>
        <UploadDropzone disabled={busy} onFiles={selectFile} />
      </section>
      <p className="upload-policy">CSV를 업로드하면 서비스 약관에 동의한 것으로 간주합니다. Sheet2Service가 개인 데이터를 처리하는 방법에 대한 자세한 정보는 개인정보 보호정책에서 확인하세요.</p>
      </div>
      </div>
      {confirmOpen && file && <GenerateDialog file={file} summary={callSummary} busy={busy} error={error}
        canRetry={!!upload && !callSummary} onRetry={retrySummary} onConfirm={generate} onClose={cancelUpload} />}
      {!confirmOpen && error && <div className="error" role="alert">{error}</div>}
    </main>
  );
}

function ServicePage({ uploadId, page }) {
  const [service, setService] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    api(`/api/uploads/${uploadId}/service/`)
      .then((data) => { if (active) setService(data); })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId]);
  const roleTitle = page === 'DashBoard' ? '대시보드' : page === 'Admin' ? '관리자' : '사용자';
  return <main className="service-page" data-role={page === 'DashBoard' ? 'dashboard' : page === 'Admin' ? 'admin' : 'user'}>
    <header className="service-page-header">
      <div className="service-topline"><a className="service-brand" href="/">Sheet2Service</a>
      <nav className="service-switch" aria-label="서비스 화면 이동">
        <a href={`/${uploadId}/DashBoard`} aria-current={page === 'DashBoard' ? 'page' : undefined}>대시보드</a>
        {service?.workflow_config && <a href={`/${uploadId}/User`} aria-current={page === 'User' ? 'page' : undefined}>사용자</a>}
        <a href={`/${uploadId}/Admin`} aria-current={page === 'Admin' ? 'page' : undefined}>관리자</a>
      </nav>
      </div>
      <div className="service-heading-row"><h1 className="icon-heading"><SectionIcon name={page === 'DashBoard' ? 'dashboard' : page === 'Admin' ? 'admin' : 'user'} />{roleTitle}</h1>
        {service && <a className="service-source" href={`/api/uploads/${uploadId}/original/`} download>{service.upload.name}</a>}
      </div>
    </header>
    {error && <p className="error" role="alert">{error}</p>}
    {!error && !service && <p role="status">서비스 화면을 불러오는 중입니다.</p>}
    {service?.workflow_required && !service.workflow_config && <p className="notice">
      서비스 구성이 아직 없습니다. 파일을 다시 업로드해 생성해 주세요.
    </p>}
    {service && (!service.workflow_required || service.workflow_config) &&
      <ServiceFeatures uploadId={uploadId} page={page} service={service}
        requestMetrics={<RequestMetrics uploadId={uploadId} enabled />} />}
  </main>;
}

function RequestMetrics({ uploadId, enabled }) {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState('');
  async function load() {
    try { setStats(await api(`/api/uploads/${uploadId}/service-requests/stats/`)); setError(''); }
    catch (caught) { setError(caught.message); }
  }
  useEffect(() => {
    if (!enabled) return;
    load();
  }, [uploadId, enabled]);
  if (!enabled) return null;
  return <section className="panel" aria-labelledby="request-metrics-title">
    <div className="section-title"><h2 id="request-metrics-title" className="icon-heading"><SectionIcon name="analysis" />신청 현황</h2><button type="button" className="service-back-button" onClick={load}>새로고침</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    {stats && <dl className="metrics">
      <div><dt>전체 신청</dt><dd>{stats.total.toLocaleString()}</dd></div>
      <div><dt>검토 대기</dt><dd>{stats.counts.pending.toLocaleString()}</dd></div>
      <div><dt>승인</dt><dd>{stats.counts.approved.toLocaleString()}</dd></div>
      <div><dt>거절</dt><dd>{stats.counts.rejected.toLocaleString()}</dd></div>
      <div><dt>접수 완료</dt><dd>{stats.counts.submitted.toLocaleString()}</dd></div>
      <div><dt>처리 중</dt><dd>{stats.counts.in_progress.toLocaleString()}</dd></div>
      <div><dt>완료</dt><dd>{stats.counts.completed.toLocaleString()}</dd></div>
      <div><dt>취소</dt><dd>{stats.counts.cancelled.toLocaleString()}</dd></div>
    </dl>}
  </section>;
}

const path = window.location.pathname.replace(/\/+$/, '');
const serviceMatch = path.match(/^\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/(User|DashBoard|Admin)$/i);
createRoot(document.getElementById('root')).render(<React.StrictMode>
  {path === '/templates' ? <TemplateExamples />
    : serviceMatch ? <ServicePage uploadId={serviceMatch[1]} page={serviceMatch[2].toLowerCase() === 'admin' ? 'Admin'
      : serviceMatch[2].toLowerCase() === 'user' ? 'User' : 'DashBoard'} />
      : <App />}
  <SiteFooter />
</React.StrictMode>);
