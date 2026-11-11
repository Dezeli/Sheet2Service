import React, { useState } from 'react';
import { IconButton } from '../components/ui';

export default function FieldNameEditor({ label, number, busy, onSave, onCancel }) {
  const [draft, setDraft] = useState(label);
  const valid = draft.trim() && draft.trim() !== label;
  return <form className="field-name-edit" onSubmit={(event) => { event.preventDefault(); if (!busy && valid) onSave(draft.trim()); }}>
    <input autoFocus type="text" aria-label={`${number}번 필드 표시 이름`} maxLength={120} value={draft} disabled={busy}
      onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Escape' && !busy) { event.preventDefault(); onCancel(); } }} />
    <IconButton icon="close" label="필드명 변경 취소" disabled={busy} onClick={onCancel} />
    <IconButton type="submit" icon="check" tone="approve" label="필드명 저장" disabled={busy || !valid} />
  </form>;
}
