import React, { useEffect, useState } from 'react';

export function listQuery(filters = {}) {
  const params = new URLSearchParams();
  if (filters.q?.trim()) params.set('q', filters.q.trim());
  if (filters.column && filters.value) {
    params.set('filter_column', filters.column);
    params.set('filter_value', filters.value);
  }
  return params.toString();
}

export default function ListControls({ uploadId, columns, disabled, onApply, actions }) {
  const [query, setQuery] = useState('');
  const [column, setColumn] = useState('');
  const [value, setValue] = useState('');
  const [choices, setChoices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!column) { setChoices([]); setLoading(false); setError(''); return; }
    const controller = new AbortController();
    setChoices([]); setLoading(true); setError('');
    fetch(`/api/uploads/${uploadId}/choices/?column=${column}`, { credentials: 'same-origin', signal: controller.signal })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok || !Array.isArray(data.choices)) throw new Error('필터 값을 불러오지 못했습니다.');
        if (!controller.signal.aborted) setChoices(data.choices);
      })
      .catch((caught) => { if (!controller.signal.aborted) setError('필터 값을 불러오지 못했습니다. 다시 시도해 주세요.'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [uploadId, column, retry]);
  return <form className="list-controls" onSubmit={(event) => {
    event.preventDefault(); onApply({ q: query, column, value });
  }}>
    <div className="list-search-row"><label className="list-search"><svg className="list-search-icon" aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg><input aria-label="검색어" type="search" value={query} maxLength={200} placeholder="검색어를 입력하세요" disabled={disabled} onChange={(event) => setQuery(event.target.value)} /></label>
      {actions && <div className="list-extra-actions">{actions}</div>}
    </div>
    <div className="list-filter-row">
    <svg className="list-filter-icon" aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 5h18l-7 8v6l-4 2v-8z" /></svg>
    <label><select aria-label="필터 컬럼" value={column} disabled={disabled} onChange={(event) => { setColumn(event.target.value); setValue(''); }}>
      <option value="">전체</option>{columns.map((item) => <option key={item.number} value={item.number}>{item.label}</option>)}
    </select></label>
    <label><select aria-label="필터 값" value={value} disabled={!column || disabled || loading || !!error} onChange={(event) => setValue(event.target.value)}>
      <option value="">{!column ? '필터를 선택하세요' : loading ? '불러오는 중…' : error ? '조회 실패' : '전체'}</option>
      {choices.map((choice) => <option key={choice.id} value={choice.value}>{choice.value}</option>)}
    </select></label>
    <div className="list-filter-actions">
    <button type="submit" disabled={disabled || loading || !!error}>검색</button>
    <button type="button" className="service-back-button" disabled={disabled} onClick={() => {
      setQuery(''); setColumn(''); setValue(''); onApply({});
    }}>초기화</button>
    </div></div>
    {error && <div className="list-filter-error" role="alert">{error} <button type="button" className="service-back-button" disabled={disabled || loading} onClick={() => setRetry((current) => current + 1)}>다시 시도</button></div>}
  </form>;
}
