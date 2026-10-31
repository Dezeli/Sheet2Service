import React, { useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import './fonts.css';
import './theme.css';
import UploadDropzone from './upload/UploadDropzone';
import GenerateDialog from './upload/GenerateDialog';
import { csvFile } from './upload/files';
import SiteFooter from './components/SiteFooter';
import BookingService from './booking/BookingService';
import { api } from './booking/api.js';
import './service.css';
import './hierarchy.css';

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
      setCallSummary(await api(`/api/uploads/${uploaded.id}/generate/`));
    } catch (err) {
      setError(err instanceof TypeError ? '서버에 연결할 수 없습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.' : err.message);
    } finally { submitting.current = false; setBusy(false); }
  }

  async function retrySummary() {
    if (!upload || busy || submitting.current) return;
    submitting.current = true; setBusy(true); setError('');
    try { setCallSummary(await api(`/api/uploads/${upload.id}/generate/`)); }
    catch (caught) { setError(caught.message); }
    finally { submitting.current = false; setBusy(false); }
  }

  async function generate() {
    if (!upload || !callSummary || busy || submitting.current) return;
    submitting.current = true; setBusy(true); setError('');
    try {
      const generated = await api(`/api/uploads/${upload.id}/generate/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ approved: true, request_fingerprint: callSummary.request_fingerprint,
          approval_note: `생성 확인 모달의 서비스 생성 버튼으로 ${callSummary.model} 1회 호출 승인` }),
      });
      window.location.assign(`/${upload.id}/summary`);
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
      <h2 className="upload-headline"><span className="upload-headline-line">예약 스프레드시트를</span><br /><span className="upload-headline-accent">예약 서비스로.</span></h2>
      <p className="upload-description">예약 대장, 시설 목록, 회차표 등 예약 관련 CSV를 올리면 시트를 읽어 예약자·관리자 화면을 바로 만듭니다.</p>
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

const path = window.location.pathname.replace(/\/+$/, '');
const serviceMatch = path.match(/^\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/([A-Za-z_]+)$/);
createRoot(document.getElementById('root')).render(<React.StrictMode>
  {serviceMatch ? <BookingService uploadId={serviceMatch[1]} page={serviceMatch[2] === 'DashBoard' ? 'DashBoard' : serviceMatch[2]} />
    : <App />}
  <SiteFooter />
</React.StrictMode>);
