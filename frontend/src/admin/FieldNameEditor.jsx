import React, { useState } from 'react';

export function FieldActionIcon({ kind }) {
  return <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
    {kind === 'edit' ? <path d="m15 5 4 4M4 20l4-1 12-12a2.8 2.8 0 0 0-4-4L4 15z" />
      : kind === 'save' ? <path d="m5 12 4 4L19 6" /> : <path d="m9 5-5 5 5 5M4 10h10a6 6 0 0 1 0 12" />}
  </svg>;
}

export default function FieldNameEditor({ label, number, busy, onSave, onCancel }) {
  const [draft, setDraft] = useState(label);
  const valid = draft.trim() && draft.trim() !== label;
  return <form className="field-name-edit" onSubmit={(event) => { event.preventDefault(); if (!busy && valid) onSave(draft.trim()); }}>
    <input autoFocus type="text" aria-label={`${number}번 필드 표시 이름`} maxLength={120} value={draft} disabled={busy}
      onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Escape' && !busy) { event.preventDefault(); onCancel(); } }} />
    <button type="button" className="field-name-icon field-name-cancel" title="변경 취소" aria-label="필드명 변경 취소" disabled={busy} onClick={onCancel}><FieldActionIcon kind="cancel" /></button>
    <button type="submit" className="field-name-icon field-name-save" title="저장" aria-label="필드명 저장" disabled={busy || !valid}><FieldActionIcon kind="save" /></button>
  </form>;
}
