import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import './fonts.css';
import TemplateExamples from './preview/TemplateExamples';
import WorkflowReview from './workflow/WorkflowReview';
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

function Cell({ value, expanded }) {
  if (value === null || value === '') return <span className="empty">빈 값</span>;
  const text = String(value);
  return <span className={expanded ? 'cell-value is-expanded' : 'cell-value'} title={expanded ? undefined : text}>{text}</span>;
}

function Preview({ upload }) {
  const [expandedRow, setExpandedRow] = useState(null);
  function toggleRow(number) {
    setExpandedRow((current) => current === number ? null : number);
  }
  const report = upload.analysis;
  const widths = report.columns.map((column, index) => {
    const visualLength = (value) => [...String(value)].reduce((sum, char) => sum + (char.charCodeAt(0) > 255 ? 2 : 1), 0);
    const lengths = report.preview.map((row) => visualLength(row.values[index] ?? '')).sort((a, b) => a - b);
    const typical = lengths[Math.floor((lengths.length - 1) * .75)] || 0;
    const label = Math.min(10, visualLength(column.label));
    return Math.min(260, Math.max(72, Math.max(label, typical) * 7 + 24));
  });
  return <section className="panel data-panel" aria-labelledby="preview-title">
    <div className="section-title preview-heading">
      <div><h2 id="preview-title" className="icon-heading"><SectionIcon name="table" />CSV 미리보기 <span className="preview-encoding">({upload.encoding === 'utf-8-sig' ? 'UTF-8' : upload.encoding.toUpperCase()})</span></h2>
        <p className="preview-note">미리보기는 20행까지만 지원합니다.</p>
      </div>
      <div className="preview-counts"><span>데이터 행 <strong>{report.row_count.toLocaleString()}</strong></span><span>열 <strong>{report.column_count}</strong></span></div>
    </div>
    <div className="table-scroll" role="region" aria-label="업로드한 CSV 미리보기" tabIndex={0}>
      <table className="csv-preview-table" style={{ width: widths.reduce((sum, width) => sum + width, 64) }}>
        <colgroup><col style={{ width: 64 }} />{widths.map((width, index) => <col key={report.columns[index].id} style={{ width }} />)}</colgroup>
        <thead><tr><th scope="col">행</th>{report.columns.map((column) => <th scope="col" key={column.id}>{column.label}</th>)}</tr></thead>
        <tbody>{report.preview.map((row) => {
          const expanded = expandedRow === row.row_number;
          return <tr key={row.row_number} className={expanded ? 'is-expanded' : ''} onClick={() => toggleRow(row.row_number)}>
            <th scope="row"><button type="button" className="preview-row-toggle" aria-expanded={expanded}
              aria-label={`${row.row_number - 1}행 ${expanded ? '접기' : '자세히 보기'}`}
              onClick={(event) => { event.stopPropagation(); toggleRow(row.row_number); }}>
              {row.row_number - 1}
            </button></th>
            {row.values.map((value, index) => <td key={index}><Cell value={value} expanded={expanded} /></td>)}
          </tr>;
        })}</tbody>
      </table>
    </div>
    {!report.row_count && <p>헤더는 있지만 데이터 행이 없습니다.</p>}
    {report.warnings.length > 0 && <aside className="data-warnings" aria-label="데이터 확인 사항"><h3>확인이 필요한 데이터</h3><ul>{report.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></aside>}
  </section>;
}

const typeLabels = {
  text: '텍스트', number: '숫자', date: '날짜', datetime: '날짜·시간',
  time: '시간', boolean: '참·거짓', formula: '수식 형태', mixed: '혼합', unknown: '알 수 없음',
};
const percent = (value) => `${(value * 100).toFixed(1)}%`;

function ColumnAnalysis({ report }) {
  return <section className="panel data-panel" aria-labelledby="analysis-title">
    <div className="section-title preview-heading">
      <div><h2 id="analysis-title" className="icon-heading"><SectionIcon name="analysis" />열별 분석</h2><p className="preview-note">전체 데이터의 형식과 빈 값을 확인하세요.</p></div>
      <div className="preview-counts"><span>데이터 행 <strong>{report.row_count.toLocaleString()}</strong></span><span>열 <strong>{report.column_count}</strong></span></div>
    </div>
    <div className="table-scroll" role="region" aria-label="열별 분석 결과" tabIndex={0}>
      <table className="analysis-table">
        <colgroup>{[56, 190, 110, 120, 100, 100, 100, 300].map((width, index) => <col key={index} style={{ width: `${width / 1076 * 100}%` }} />)}</colgroup>
        <thead><tr>{['번호', '컬럼명', '추정 형식', '빈 값', '고유값', '숫자 비율', '날짜 비율', '값 형식·확인 사항'].map((label) => <th scope="col" key={label}>{label}</th>)}</tr></thead>
        <tbody>{report.columns.map((column, index) => <tr key={column.id}>
          <td className="analysis-column-number">{index + 1}</td>
          <th scope="row">{column.label}</th>
          <td><span className={`type-badge ${column.candidate === 'mixed' ? 'type-mixed' : ''}`}>{typeLabels[column.candidate] || column.candidate}</span></td>
          <td>{column.missing_count.toLocaleString()} <span className="analysis-ratio">({report.row_count ? percent(column.missing_ratio) : '-'})</span></td>
          <td>{column.unique_count.toLocaleString()}</td>
          <td>{column.non_empty_count ? percent(column.number_ratio) : '-'}</td>
          <td>{column.non_empty_count ? percent(column.date_ratio) : '-'}</td>
          <td><div className="analysis-detail">{Object.entries(column.type_counts).map(([kind, count]) => `${typeLabels[kind] || kind} ${count.toLocaleString()}개`).join(' · ') || '값이 없는 열'}</div>
            {column.issues.length > 0 && <div className="analysis-detail analysis-issues">{column.issues.join(' · ')}</div>}
          </td>
        </tr>)}</tbody>
      </table>
    </div>
    <details className="help analysis-help"><summary>분석 기준</summary>
      <ul>
        <li>원본 값은 변경하지 않으며, 표시된 형식은 값에서 추정한 결과입니다.</li>
        <li>빈 값은 비어 있거나 공백만 있는 셀입니다. 완전히 빈 행은 분석에서 제외합니다.</li>
        <li>고유값은 빈 값을 제외한 서로 다른 원본 문자열의 수입니다.</li>
        <li>숫자·날짜 비율은 빈 값을 제외한 데이터 중 해당 형식으로 읽을 수 있는 비율입니다.</li>
      </ul>
    </details>
  </section>;
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
      await api(`/api/uploads/${upload.id}/inference/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ approved: true, approval_note: `생성 확인 모달의 서비스 생성 버튼으로 ${callSummary.model} 1회 호출 승인` }),
      });
      window.location.assign(`/select?upload=${upload.id}`);
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

function SelectPage() {
  const uploadId = new URLSearchParams(window.location.search).get('upload');
  const [upload, setUpload] = useState(null);
  const [csrfToken, setCsrfToken] = useState('');
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');
  const titles = ['CSV 미리보기', '열별 분석', '서비스 기능 선택'];
  useEffect(() => {
    let active = true;
    if (!uploadId || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(uploadId)) {
      setError('파일을 먼저 업로드해 주세요.');
      return;
    }
    Promise.all([api(`/api/uploads/${uploadId}/`), api('/api/session/')])
      .then(([data, session]) => { if (active) { setUpload(data); setCsrfToken(session.csrf_token); } })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId]);
  function move(next) {
    setStep(next);
    window.scrollTo({ top: 0, behavior: 'instant' });
  }
  return <main className="select-page">
    <header className="upload-header"><h1>Sheet2Service</h1></header>
    <div className="selection-toolbar">
    <a className="selection-back" href="/">← 파일 업로드로 돌아가기</a>
    <ol className="selection-steps" aria-label="서비스 생성 단계">
      {titles.map((title, index) => <li key={title} aria-current={step === index ? 'step' : undefined}
        className={index < step ? 'is-complete' : ''}>
        <span className="selection-step-number">{index < step ? '✓' : index + 1}</span>{title}
      </li>)}
    </ol>
    </div>
    {upload && <div className="selection-file"><a className="selection-file-name" href={`/api/uploads/${upload.id}/original/`} download>{upload.name}</a></div>}
    {error && <div className="error" role="alert">{error} <a href="/">파일 업로드로 돌아가기</a></div>}
    {!upload && !error && <div className="selection-loading" role="status"><span className="loading-spinner" aria-hidden="true" /><span className="visually-hidden">불러오는 중입니다.</span></div>}
    {upload && <>
      {step === 0 && <Preview upload={upload} />}
      {step === 1 && <ColumnAnalysis report={upload.analysis} />}
      <div hidden={step !== 2}>
        <WorkflowReview uploadId={upload.id} csrfToken={csrfToken}
          onBack={() => move(1)}
          onApplied={(page) => window.location.assign(`/${upload.id}/${page}`)} />
      </div>
      <nav className="selection-navigation" aria-label="단계 이동">
        {step === 1 && <button type="button" className="service-back-button" onClick={() => move(step - 1)}>이전</button>}
        {step < 2 && <button type="button" onClick={() => move(step + 1)}>다음</button>}
      </nav>
    </>}
  </main>;
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
      사용할 기능을 먼저 선택해 주세요.
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
    : path === '/select' ? <SelectPage />
    : serviceMatch ? <ServicePage uploadId={serviceMatch[1]} page={serviceMatch[2].toLowerCase() === 'admin' ? 'Admin'
      : serviceMatch[2].toLowerCase() === 'user' ? 'User' : 'DashBoard'} />
      : <App />}
  <SiteFooter />
</React.StrictMode>);
