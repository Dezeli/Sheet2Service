import React, { useId, useRef, useState } from 'react';

export default function SearchableChoice({ label, value, choices, disabled, onChange }) {
  const [query, setQuery] = useState('');
  const control = useRef(null);
  const summary = useRef(null);
  const labelId = useId();
  const selected = String(value ?? '');
  const options = choices.filter((choice) => choice.value === selected || choice.value.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const existing = selected && !choices.some((choice) => choice.value === selected);
  function close() { control.current.open = false; summary.current.focus(); }
  return <details className="searchable-choice" ref={control} onToggle={(event) => { if (event.currentTarget.open) setQuery(''); }}>
    <summary ref={summary} aria-label={`${label}: ${selected || '선택 안 함'}`} aria-disabled={disabled} onClick={(event) => { if (disabled) event.preventDefault(); }}>
      <span className="choice-current">{selected || '선택 안 함'}</span>
      <svg className="choice-dropdown-mark" aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="m7 10 5 5 5-5" /></svg>
    </summary>
    <div className="choice-picker" onKeyDown={(event) => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); }
      if (event.key === 'Enter') { event.preventDefault(); if (event.target.tagName === 'SELECT') close(); }
    }}>
      <label id={labelId} className="visually-hidden">{label} 선택지 검색</label>
      <input aria-labelledby={labelId} type="search" value={query} disabled={disabled} placeholder="선택지 검색" onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => { if (event.key === 'Enter') event.preventDefault(); }} />
      <select aria-label={`${label} 선택지`} size={Math.min(6, Math.max(3, options.length + 1))} value={selected} disabled={disabled}
        onChange={(event) => { onChange(event.target.value || null); close(); }}>
        <option value="">선택 안 함</option>
        {existing && <option value={selected}>{selected} (기존 값)</option>}
        {options.map((choice) => <option key={choice.id} value={choice.value} disabled={!choice.active && choice.value !== selected}>
          {choice.value}{choice.active ? '' : ' (사용 중지)'}</option>)}
      </select>
      {!options.length && <span className="muted">일치하는 선택지가 없습니다.</span>}
    </div>
  </details>;
}
