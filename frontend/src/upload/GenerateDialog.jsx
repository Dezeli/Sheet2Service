import React, { useEffect, useRef } from 'react';

export default function GenerateDialog({ file, summary, busy, error, canRetry, onRetry, onConfirm, onClose }) {
  const dialog = useRef(null);
  useEffect(() => {
    const element = dialog.current;
    element.showModal();
    return () => element.close();
  }, []);
  return <dialog ref={dialog} className="generate-dialog" aria-labelledby="generate-title" aria-describedby="generate-purpose"
    onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
    <h2 id="generate-title">서비스를 생성하시겠습니까?</h2>
    <div className="generate-file">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
        <path d="M14 3v6h6M8 14h8M8 17h5" />
      </svg>
      <div><span className="generate-file-label">업로드된 파일</span><p className="upload-file-name">{file.name}</p></div>
      {busy && <span className="generate-file-loading" role="status" aria-live="polite">
        <span className="loading-spinner" aria-hidden="true" />
        <span className="visually-hidden">파일을 처리하고 있습니다.</span>
      </span>}
    </div>
    <p id="generate-purpose">시트를 읽어 무엇이 예약되고 누가 관리하는지 파악한 뒤 예약 서비스를 바로 만듭니다. 컬럼 분석과 예시 행만 보내며 Claude를 1회 호출합니다.</p>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="generate-actions">
      <button type="button" className="generate-cancel" disabled={busy} onClick={onClose}>취소</button>
      {canRetry && <button type="button" data-intent="secondary" disabled={busy} onClick={onRetry}>다시 시도</button>}
      <button type="button" disabled={busy || !summary} onClick={onConfirm}>서비스 생성</button>
    </div>
  </dialog>;
}
