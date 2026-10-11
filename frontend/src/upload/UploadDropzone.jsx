import React, { useRef, useState } from 'react';

export default function UploadDropzone({ disabled, onFiles }) {
  const input = useRef(null);
  const depth = useRef(0);
  const [dragging, setDragging] = useState(false);
  return <>
    <input ref={input} type="file" accept=".csv,text/csv" hidden disabled={disabled}
      onChange={(event) => {
        if (event.target.files.length) onFiles(event.target.files);
        event.target.value = '';
      }} />
    <button type="button" className={`upload-dropzone${dragging ? ' is-dragging' : ''}`} disabled={disabled}
      aria-label="CSV 파일 선택 또는 드래그하여 업로드" onClick={() => input.current.click()}
      onDragEnter={(event) => { event.preventDefault(); if (!disabled) { depth.current += 1; setDragging(true); } }}
      onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = disabled ? 'none' : 'copy'; }}
      onDragLeave={(event) => { event.preventDefault(); depth.current = Math.max(0, depth.current - 1); if (!depth.current) setDragging(false); }}
      onDrop={(event) => {
        event.preventDefault(); depth.current = 0; setDragging(false);
        if (!disabled) onFiles(event.dataTransfer.files);
      }}>
      <svg width="56" height="56" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M28 5H12a3 3 0 0 0-3 3v32a3 3 0 0 0 3 3h24a3 3 0 0 0 3-3V16L28 5Z" />
        <path d="M28 5v11h11M24 35V22m-6 6 6-6 6 6" />
      </svg>
      <span className="upload-instruction">클릭하여 파일을 업로드하거나<br />파일을 드래그하여 주세요</span>
      <span className="upload-formats">
        <span>지원 포맷 <b>CSV</b></span><span className="upload-format-planned">XLSX · 지원 예정</span>
      </span>
    </button>
  </>;
}
