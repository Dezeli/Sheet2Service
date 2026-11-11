import React, { useEffect, useState } from 'react';
import { ChoiceCombobox, SearchField } from './ui';

export function listQuery(filters = {}) {
  const params = new URLSearchParams();
  if (filters.q?.trim()) params.set('q', filters.q.trim());
  if (filters.column && filters.value) {
    params.set('filter_column', filters.column);
    params.set('filter_value', filters.value);
  }
  return params.toString();
}

/** Search as you type, plus one field = value filter whose values come from the sheet; every change applies at once. */
export default function ListControls({ uploadId, columns, disabled, onApply, actions }) {
  const [criteria, setCriteria] = useState({ q: '', column: '', value: '' });
  const [choices, setChoices] = useState([]);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!criteria.column) { setChoices([]); setError(''); return undefined; }
    const controller = new AbortController();
    setChoices([]); setError('');
    fetch(`/api/uploads/${uploadId}/choices/?column=${criteria.column}`, { credentials: 'same-origin', signal: controller.signal })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok || !Array.isArray(data.choices)) throw new Error();
        if (!controller.signal.aborted) setChoices(data.choices.map((choice) => choice.value));
      })
      .catch(() => { if (!controller.signal.aborted) setError('값 목록을 불러오지 못했습니다.'); });
    return () => controller.abort();
  }, [uploadId, criteria.column]);

  function apply(changes) {
    const next = { ...criteria, ...changes };
    setCriteria(next);
    if (!next.column || next.value || 'value' in changes || 'q' in changes) onApply(next);
  }
  const filtered = Boolean(criteria.q || criteria.value);
  return <div className="ui-toolbar list-controls-bar">
    <SearchField value={criteria.q} placeholder="검색" onSearch={(q) => apply({ q })} />
    <select aria-label="필터할 필드" value={criteria.column} disabled={disabled} onChange={(event) => apply({ column: event.target.value, value: '' })}>
      <option value="">필드로 거르기</option>{columns.map((item) => <option key={item.number} value={item.number}>{item.label}</option>)}
    </select>
    {criteria.column && <div className="list-value-filter"><ChoiceCombobox label="필터 값" options={choices} value={criteria.value} emptyLabel="전체"
      placeholder={error || '값 찾기'} disabled={disabled || Boolean(error)} onChange={(value) => apply({ value })} /></div>}
    {filtered && <button type="button" className="text-button" disabled={disabled} onClick={() => { const empty = { q: '', column: '', value: '' }; setCriteria(empty); onApply(empty); }}>조건 지우기</button>}
    {actions && <div className="toolbar-end">{actions}</div>}
  </div>;
}
