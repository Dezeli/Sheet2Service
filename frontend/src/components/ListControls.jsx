import React, { useState } from 'react';

export function listQuery(filters = {}) {
  const params = new URLSearchParams();
  if (filters.q?.trim()) params.set('q', filters.q.trim());
  if (filters.column && filters.value) {
    params.set('filter_column', filters.column);
    params.set('filter_value', filters.value);
  }
  return params.toString();
}

export default function ListControls({ columns, disabled, onApply }) {
  const [query, setQuery] = useState('');
  const [column, setColumn] = useState('');
  const [value, setValue] = useState('');
  return <form className="list-controls" onSubmit={(event) => {
    event.preventDefault(); onApply({ q: query, column, value });
  }}>
    <label className="list-search"><span>검색</span><input type="search" value={query} maxLength={200} placeholder="검색어를 입력하세요" disabled={disabled} onChange={(event) => setQuery(event.target.value)} /></label>
    <label><span>필터</span><select value={column} disabled={disabled} onChange={(event) => { setColumn(event.target.value); setValue(''); }}>
      <option value="">전체</option>{columns.map((item) => <option key={item.number} value={item.number}>{item.label}</option>)}
    </select></label>
    {column && <label><span>값</span><input type="text" value={value} placeholder="일치하는 값" disabled={disabled} onChange={(event) => setValue(event.target.value)} /></label>}
    <button type="submit" disabled={disabled}>검색</button>
    <button type="button" className="service-back-button" disabled={disabled} onClick={() => {
      setQuery(''); setColumn(''); setValue(''); onApply({});
    }}>초기화</button>
  </form>;
}
