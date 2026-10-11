import React, { useState } from 'react';
import ServiceDialog from '../components/ServiceDialog';
import SearchableChoice from './SearchableChoice';
import { rowSummary } from './rowSummary.js';

const display = (value) => value === null || value === undefined || value === '' ? '빈 값' : String(value);

export default function RowEditor({ row, columns, choices, titleColumns, busy, error, canSave, onSave, onClose }) {
  const [values, setValues] = useState([...row.values]);
  const [query, setQuery] = useState('');
  const [review, setReview] = useState(false);
  const summary = row.id && rowSummary(row, columns, titleColumns);
  const changed = columns.map((column, index) => ({ column, index, before: row.values[index], after: values[index] }))
    .filter((field) => String(field.before ?? '') !== String(field.after ?? ''));
  const shown = columns.map((column, index) => ({ column, index }))
    .filter(({ column, index }) => `${index + 1} ${column.label}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  return <ServiceDialog title={review ? '변경 내용 확인' : row.id ? '데이터 수정' : '데이터 추가'} className="admin-edit-dialog" busy={busy} error={error} onClose={onClose}>
    {summary && <div className="editor-subject"><small>{summary.title?.label || summary.supporting[0]?.label}</small>
      <p>{summary.title?.value || summary.supporting[0]?.value || '선택한 데이터'}</p></div>}
    <form className="admin-edit-form" onSubmit={(event) => {
      event.preventDefault();
      if (busy || !canSave || (row.id && !changed.length)) return;
      if (!review) setReview(true); else onSave(values);
    }}>
      {!review ? <>
        <div className="editor-search"><input type="search" aria-label="필드 검색" placeholder="필드 이름 또는 번호로 검색" value={query} disabled={busy}
          onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') event.preventDefault(); }} />
          <span className="muted" aria-live="polite">{changed.length}개 변경</span></div>
        <fieldset disabled={busy} className="admin-editor-grid">{shown.map(({ column, index }) => {
          const isChanged = changed.some((field) => field.index === index);
          const wide = Math.max(String(values[index] ?? '').length, String(row.values[index] ?? '').length) > 80;
          return <div key={column.id} className={`editor-field ${wide ? 'editor-field-wide' : ''} ${isChanged ? 'editor-field-changed' : ''}`}>
            <div className="editor-field-label"><span className="editor-field-number">{index + 1}</span>{column.label}
              {isChanged && <button type="button" className="editor-revert" title="변경 취소" aria-label={`${column.label} 변경 취소`} disabled={busy}
                onClick={() => setValues((current) => current.map((item, at) => at === index ? row.values[index] : item))}>
                <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="m9 5-5 5 5 5M4 10h10a6 6 0 0 1 0 12" /></svg>
              </button>}</div>
            <SearchableChoice label={column.label} value={values[index]} choices={choices[index + 1] || []} disabled={busy}
              onChange={(value) => setValues((current) => current.map((item, at) => at === index ? value : item))} />
          </div>;
        })}
          {!shown.length && <p className="muted">일치하는 필드가 없습니다.</p>}
        </fieldset>
      </> : <div className="editor-review" tabIndex={0} role="region" aria-label="변경 내용">
        {!changed.length && <p className="muted">모든 필드를 빈 값으로 추가합니다.</p>}
        {changed.map((field) => <section key={field.index} className="editor-change"><h3>{field.column.label}</h3>
          <dl><div><dt>변경 전</dt><dd>{display(field.before)}</dd></div><div><dt>변경 후</dt><dd>{display(field.after)}</dd></div></dl></section>)}
      </div>}
      <div className="dialog-form-actions">
        <button type="button" className="service-back-button" disabled={busy} onClick={review ? () => setReview(false) : onClose}>{review ? '계속 수정' : '취소'}</button>
        <button type="submit" disabled={busy || !canSave || (row.id && !changed.length)}>{busy ? '저장 중…' : review ? '저장' : '변경 내용 확인'}</button>
      </div>
    </form>
  </ServiceDialog>;
}
