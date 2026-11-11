import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { csvFile } from '../upload/files';
import { api } from '../booking/api.js';

const OFFLINE = '서버에 연결할 수 없습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.';

/** The approval step before the one Claude call: what is sent, how often, then the button that sends it. */
function GenerateDialog({ file, summary, busy, error, canRetry, onRetry, onConfirm, onClose }) {
  const dialog = useRef(null);
  useEffect(() => {
    const element = dialog.current;
    element.showModal();
    return () => element.close();
  }, []);
  return <dialog ref={dialog} className="lp-dialog" aria-labelledby="generate-title" aria-describedby="generate-purpose"
    onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
    <div className="lp-dialog__head">
      <h2 id="generate-title">이 시트로 서비스를 만들까요?</h2>
      <button type="button" className="lp-dialog__close" aria-label="닫기" disabled={busy} onClick={onClose}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
      </button>
    </div>
    <div className="lp-dialog__file">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6" /></svg>
      <span>{file.name}</span>
      {busy && <span className="lp-dialog__spin" role="status" aria-label="처리 중" />}
    </div>
    <p id="generate-purpose">컬럼 분석과 예시 행만 Claude에 보내 무엇을 누가 예약하는지 읽고, 예약자 화면과 관리자 화면을 만듭니다. Claude는 한 번 호출합니다.</p>
    {error && <p className="lp-dialog__error" role="alert">{error}</p>}
    <div className="lp-dialog__actions">
      {canRetry && <button type="button" className="btn btn--secondary" disabled={busy} onClick={onRetry}>다시 시도</button>}
      <button type="button" className="btn btn--primary" disabled={busy || !summary} onClick={onConfirm}>{busy && summary ? '만드는 중…' : '서비스 만들기'}</button>
    </div>
  </dialog>;
}

/** Every [data-upload] button opens the file picker, and a CSV dropped anywhere on the page starts the same flow. */
export default function UploadFlow() {
  const input = useRef(null); // a detached file input: the page's <body> keeps only its header, main and footer
  const working = useRef(false);
  const [file, setFile] = useState(null);
  const [upload, setUpload] = useState(null);
  const [csrf, setCsrf] = useState('');
  const [summary, setSummary] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [dragging, setDragging] = useState(false);

  async function start(files) {
    if (working.current) return;
    let selected;
    try { selected = csvFile(files); } catch (caught) { setFile(null); setError(caught.message); return; }
    working.current = true;
    setFile(selected); setError(''); setUpload(null); setSummary(null); setBusy(true);
    try {
      const { csrf_token: token } = await api('/api/session/');
      setCsrf(token);
      const body = new FormData();
      body.append('file', selected); body.append('encoding', 'auto');
      const uploaded = await api('/api/uploads/', { method: 'POST', body, headers: { 'X-CSRFToken': token } });
      setUpload(uploaded);
      setSummary(await api(`/api/uploads/${uploaded.id}/generate/`));
    } catch (caught) { setError(caught instanceof TypeError ? OFFLINE : caught.message); }
    finally { working.current = false; setBusy(false); }
  }

  async function retry() {
    if (!upload || working.current) return;
    working.current = true; setBusy(true); setError('');
    try { setSummary(await api(`/api/uploads/${upload.id}/generate/`)); }
    catch (caught) { setError(caught.message); }
    finally { working.current = false; setBusy(false); }
  }

  async function generate() {
    if (!upload || !summary || working.current) return;
    working.current = true; setBusy(true); setError('');
    try {
      await api(`/api/uploads/${upload.id}/generate/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ approved: true, request_fingerprint: summary.request_fingerprint,
          approval_note: `생성 확인 창의 서비스 만들기 버튼으로 ${summary.model} 1회 호출 승인` }),
      });
      window.location.assign(`/${upload.id}/summary`);
    } catch (caught) { setError(caught instanceof TypeError ? OFFLINE : caught.message); working.current = false; setBusy(false); }
  }

  function close() {
    if (working.current) return;
    setFile(null); setUpload(null); setSummary(null); setError('');
  }

  useEffect(() => {
    const picker = Object.assign(document.createElement('input'), { type: 'file', accept: '.csv,text/csv' });
    picker.addEventListener('change', () => { if (picker.files.length) start(picker.files); picker.value = ''; });
    input.current = picker;
    const open = (event) => { if (event.target.closest('[data-upload]')) { event.preventDefault(); input.current?.click(); } };
    let depth = 0;
    const enter = (event) => { if ([...(event.dataTransfer?.types || [])].includes('Files')) { event.preventDefault(); depth += 1; setDragging(true); } };
    const over = (event) => { if ([...(event.dataTransfer?.types || [])].includes('Files')) event.preventDefault(); };
    const leave = () => { depth = Math.max(0, depth - 1); if (!depth) setDragging(false); };
    const drop = (event) => { if (!event.dataTransfer?.files?.length) return; event.preventDefault(); depth = 0; setDragging(false); start(event.dataTransfer.files); };
    document.addEventListener('click', open);
    window.addEventListener('dragenter', enter); window.addEventListener('dragover', over);
    window.addEventListener('dragleave', leave); window.addEventListener('drop', drop);
    return () => {
      document.removeEventListener('click', open);
      window.removeEventListener('dragenter', enter); window.removeEventListener('dragover', over);
      window.removeEventListener('dragleave', leave); window.removeEventListener('drop', drop);
    };
  }, []);

  return createPortal(<>
    {dragging && <div className="lp-drop" aria-hidden="true"><span>CSV를 놓으면 올립니다</span></div>}
    {!file && error && <p className="lp-toast" role="alert">{error}</p>}
    {file && <GenerateDialog file={file} summary={summary} busy={busy} error={error} canRetry={Boolean(upload) && !summary}
      onRetry={retry} onConfirm={generate} onClose={close} />}
  </>, document.body);
}
