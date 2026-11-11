import React, { useRef, useState } from 'react';
import DisableChoiceDialog from './DisableChoiceDialog';
import { Empty, IconButton, Pager, SearchField, Segmented } from '../components/ui';

export default function ChoiceManagement({ uploadId, columns, column, choices, loaded, busy, canSave, message, error, onClearError, onColumn, onAdd, onUpdate }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const [sort, setSort] = useState({ key: 'value', direction: 'asc' });
  const [page, setPage] = useState(1);
  const [draft, setDraft] = useState('');
  const [editor, setEditor] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [stopping, setStopping] = useState(null);
  const working = useRef(false);
  const filtered = choices.filter((item) => item.value.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
    && (status === 'all' || item.active === (status === 'active'))).sort((a, b) => {
      const order = sort.key === 'active' ? Number(a.active) - Number(b.active)
        : sort.key === 'usage' ? (a.usage_count || 0) - (b.usage_count || 0) : a.value.localeCompare(b.value, 'ko', { numeric: true });
      return (sort.direction === 'asc' ? order : -order) || a.value.localeCompare(b.value, 'ko', { numeric: true });
    });
  const pages = Math.max(1, Math.ceil(filtered.length / 10));
  const currentPage = Math.min(page, pages);
  const visible = filtered.slice((currentPage - 1) * 10, currentPage * 10);
  async function run(action) {
    if (working.current || busy || !canSave) return false;
    working.current = true;
    try { return await action(); } finally { working.current = false; }
  }
  function changeSort(key) { setSort((current) => ({ key, direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc' })); setPage(1); setEditor(null); }
  return <div className="choice-management">
    <div className="ui-toolbar">
      <select aria-label="관리할 필드" value={column} disabled={busy} onChange={(event) => onColumn(Number(event.target.value))}>
        {columns.map((field, index) => <option key={field.id} value={index + 1}>{field.label}</option>)}
      </select>
      <SearchField value={query} placeholder="선택지 찾기" delay={0} onSearch={(text) => { setQuery(text); setPage(1); setEditor(null); }} />
      <Segmented label="사용 상태" size="small" value={status} onChange={(value) => { setStatus(value); setPage(1); setEditor(null); }}
        options={[{ value: 'all', label: '전체' }, { value: 'active', label: '사용 중' }, { value: 'inactive', label: '중지' }]} />
    </div>
    <div className="table-scroll" role="region" aria-label="선택지 목록" tabIndex={0}>
      <table className="choice-table"><thead><tr><th scope="col">번호</th>{[{ key: 'value', label: '선택지' }, { key: 'usage', label: '사용 건수' }, { key: 'active', label: '사용 상태' }].map((item) =>
        <th key={item.key} scope="col" aria-sort={sort.key === item.key ? sort.direction === 'asc' ? 'ascending' : 'descending' : 'none'}>
          <button type="button" className="choice-sort" disabled={busy} onClick={() => changeSort(item.key)}>{item.label}{sort.key === item.key && <span aria-hidden="true"> {sort.direction === 'asc' ? '↑' : '↓'}</span>}</button>
        </th>)}</tr></thead>
        <tbody>{visible.map((choice, index) => <tr key={choice.id}>
          <td>{(currentPage - 1) * 10 + index + 1}</td>
          <td><div className="choice-value-cell">{editor?.id === choice.id ? <input className="choice-edit-input" aria-label="선택지 이름 수정" autoFocus type="text" maxLength={100000} value={editor.value} disabled={busy}
            onChange={(event) => setEditor({ ...editor, value: event.target.value })} onKeyDown={async (event) => {
              if (event.key === 'Escape' && !busy) setEditor(null);
              if (event.key === 'Enter') { event.preventDefault(); if (editor.value.trim() && editor.value !== choice.value && await run(() => onUpdate(choice, { value: editor.value }))) setEditor(null); }
            }} /> : <button type="button" className="choice-value-button" aria-expanded={expanded === choice.id} title={expanded === choice.id ? '접기' : '전체 내용 보기'}
              onClick={() => setExpanded((current) => current === choice.id ? null : choice.id)}><span className={`choice-value ${expanded === choice.id ? 'is-expanded' : ''}`}>{choice.value}</span></button>}
          <div className="choice-row-actions">{editor?.id === choice.id ? <>
            <IconButton icon="close" label="선택지 변경 취소" disabled={busy} onClick={() => setEditor(null)} />
            <IconButton icon="check" tone="approve" label="선택지 저장" disabled={busy || !canSave || !editor.value.trim() || editor.value === choice.value}
              onClick={async () => { if (await run(() => onUpdate(choice, { value: editor.value }))) setEditor(null); }} />
          </> : <IconButton icon="edit" tone="info" label={`${choice.value} 수정`} disabled={busy || !canSave} onClick={() => setEditor({ id: choice.id, value: choice.value })} />}</div></div></td>
          <td className="choice-usage-count">{(choice.usage_count || 0).toLocaleString()}개</td>
          <td><button type="button" className={`choice-toggle ${choice.active ? 'is-active' : ''}`} role="switch" aria-checked={choice.active}
            aria-label={`${choice.value} 사용 여부`} title={choice.active ? '사용 중지' : '사용 재개'} disabled={busy || !canSave} onClick={async () => {
              onClearError();
              if (!choice.active) await run(() => onUpdate(choice, { active: true }));
              else if (choice.usage_count === 0) {
                const stopped = await run(() => onUpdate(choice, { active: false, expected_usage: 0, expected_value: choice.value }));
                if (!stopped) setStopping(choice);
              } else setStopping(choice);
            }}>
            <span className="choice-toggle-track" aria-hidden="true"><span /></span><span>{choice.active ? '사용 중' : '사용 중지'}</span>
          </button></td>
        </tr>)}</tbody>
      </table>
    </div>
    {stopping && <DisableChoiceDialog uploadId={uploadId} column={column} choice={stopping} busy={busy} error={error} onClearError={onClearError} onClose={() => setStopping(null)} onUpdate={(choice, changes) => run(() => onUpdate(choice, changes))} />}
    {!loaded ? <p className="muted" role="status">불러오는 중…</p> : !filtered.length && <Empty>조건에 맞는 선택지가 없습니다.</Empty>}
    <form className="choice-add-row" onSubmit={async (event) => {
      event.preventDefault(); if (draft.trim() && await run(() => onAdd(draft))) { setDraft(''); setPage(1); }
    }}><input type="text" aria-label="새 선택지 추가" placeholder="새 선택지 추가" maxLength={100000} value={draft} disabled={busy || !loaded} onChange={(event) => setDraft(event.target.value)} />
      <IconButton type="submit" icon="plus" data-intent="primary" label="선택지 추가" disabled={busy || !loaded || !canSave || !draft.trim()} />
    </form>
    {message && <p className="notice" role="status">{message}</p>}
    <Pager page={currentPage} count={filtered.length} size={10} disabled={busy} onPage={(next) => { setPage(next); setEditor(null); }} />
  </div>;
}
