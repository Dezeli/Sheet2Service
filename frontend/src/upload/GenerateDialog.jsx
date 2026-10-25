import React, { useEffect, useRef } from 'react';

export default function GenerateDialog({ file, summary, understandSummary, busy, error, canRetry, onRetry, onUnderstand, onLegacy, onClose }) {
  const dialog = useRef(null);
  useEffect(() => {
    const element = dialog.current;
    element.showModal();
    return () => element.close();
  }, []);
  return <dialog ref={dialog} className="generate-dialog" aria-labelledby="generate-title" aria-describedby="generate-purpose"
    onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
    <h2 id="generate-title">이 시트를 이해해 볼까요?</h2>
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
    <p id="generate-purpose">이 시트가 무엇이고, 왜 존재하며, 어떤 업무 흐름으로 운영되는지 AI가 읽어 냅니다. 결과를 확인한 뒤 서비스를 만듭니다.</p>
    {understandSummary && <p className="muted">전송 범위: 파일 이름, CSV 컬럼 분석과 최대 10개 예시 행, 컬럼 간 운영 신호입니다. 원본 파일 전체는 보내지 않습니다. 시트 이해하기 버튼을 누르면 {understandSummary.model} API를 1회 호출하며 자동 재시도하지 않습니다.</p>}
    {error && <p className="error" role="alert">{error}</p>}
    <div className="generate-actions">
      <button type="button" className="generate-cancel" disabled={busy} onClick={onClose}>취소</button>
      {canRetry && <button type="button" data-intent="secondary" disabled={busy} onClick={onRetry}>다시 시도</button>}
      <button type="button" disabled={busy || !understandSummary} onClick={onUnderstand}>시트 이해하기</button>
    </div>
    <details className="generate-legacy"><summary>기존 템플릿 방식 사용</summary>
      <p>예약·대여·견적 등 미리 만든 템플릿에서 고르는 이전 방식입니다. CSV 컬럼 분석과 최대 10개 예시 행을 Claude에 보내며, 버튼을 누르면 API를 1회 호출합니다. 자동 재시도는 하지 않습니다.</p>
      <button type="button" className="service-back-button" disabled={busy || !summary} onClick={onLegacy}>기존 템플릿 생성 · Claude 1회</button>
    </details>
  </dialog>;
}
