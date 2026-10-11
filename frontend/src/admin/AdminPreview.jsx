import React, { useCallback, useEffect, useRef, useState } from 'react';
import ListControls, { listQuery } from '../components/ListControls';
import ServiceDialog from '../components/ServiceDialog';
import InquiryPage from '../inquiry/InquiryPage';
import RequestManagement from '../requests/RequestManagement';
import { createAdminConfig } from './config.js';
import './admin.css';
import { rowSummary } from './rowSummary.js';
import RowEditor from './RowEditor';
import FieldNameEditor, { FieldActionIcon } from './FieldNameEditor';
import ChoiceManagement from './ChoiceManagement';

const labels = { records: '데이터 관리', fields: '필드 구성', choices: '선택지 관리', requests: '신청 관리' };
const typeLabels = { text: '텍스트', number: '숫자', date: '날짜', datetime: '날짜·시간', time: '시간', boolean: '참·거짓', formula: '수식 형태', mixed: '혼합', unknown: '알 수 없음', empty: '빈 값', url: 'URL', email: '이메일' };

async function request(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.detail || '요청을 처리하지 못했습니다.');
  return data;
}

export default function AdminPreview({ uploadId, report, dashboardConfig, workflowConfig, viewTemplate, embedded = false, titleColumns = [], onFieldLabelsChange }) {
  const [selected, setSelected] = useState(0);
  const [fieldSort, setFieldSort] = useState(null);
  const [fieldEditing, setFieldEditing] = useState(null);
  const [rows, setRows] = useState([]);
  const [page, setPage] = useState(1);
  const [rowCount, setRowCount] = useState(report.row_count);
  const [column, setColumn] = useState(1);
  const [choices, setChoices] = useState({});
  const [editor, setEditor] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const deleting = useRef(false);
  const saving = useRef(false);
  const [csrf, setCsrf] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [filters, setFilters] = useState({});
  const [loadingRows, setLoadingRows] = useState(false);
  const rowRequest = useRef(0);
  let config;
  try { config = createAdminConfig(report, dashboardConfig, workflowConfig); }
  catch (caught) { config = null; }

  const loadRows = useCallback(async (nextPage = page, criteria = filters) => {
    const sequence = ++rowRequest.current;
    setLoadingRows(true);
    try {
    const result = await request(`/api/uploads/${uploadId}/managed-rows/?page=${nextPage}&${listQuery(criteria)}`);
    if (sequence !== rowRequest.current) return;
    setRows(result.rows);
    setRowCount(result.row_count);
    setPage(result.page); setFilters(criteria);
    } finally { if (sequence === rowRequest.current) setLoadingRows(false); }
  }, [uploadId, page, filters]);

  const loadChoices = useCallback(async (number) => {
    const result = await request(`/api/uploads/${uploadId}/choices/?column=${number}`);
    setChoices((current) => ({ ...current, [number]: result.choices }));
    return result.choices;
  }, [uploadId]);


  useEffect(() => {
    request('/api/session/').then((result) => setCsrf(result.csrf_token)).catch((caught) => setError(caught.message));
    loadRows(1).catch((caught) => setError(caught.message));
  }, [uploadId]);

  useEffect(() => {
    if (viewTemplate === 'choices' || (!viewTemplate && selected === 2)) loadChoices(column).catch((caught) => setError(caught.message));
  }, [viewTemplate, selected, column, loadChoices]);


  if (!config) return <p className="error" role="alert">관리자 화면 설정이 올바르지 않습니다.</p>;
  const view = config.views.find((item) => item.template === viewTemplate) || config.views[selected];
  const fieldColumns = fieldSort ? [...view.columns].sort((a, b) => {
    const left = report.columns[a - 1];
    const right = report.columns[b - 1];
    const order = fieldSort.key === 'number' ? a - b
      : fieldSort.key === 'count' ? left.unique_count - right.unique_count
      : (fieldSort.key === 'type' ? typeLabels[left.candidate] || left.candidate : left.label)
        .localeCompare(fieldSort.key === 'type' ? typeLabels[right.candidate] || right.candidate : right.label, 'ko', { numeric: true });
    return (fieldSort.direction === 'asc' ? order : -order) || a - b;
  }) : view.columns;
  const choiceList = choices[column] || [];
  const deleteSummary = deleteTarget && rowSummary(deleteTarget, report.columns,
    [workflowConfig?.user?.subjectColumn, ...titleColumns, ...dashboardConfig.views.map((item) => item.titleColumn)]);

  async function mutate(url, method, body) {
    setBusy(true); setError(''); setMessage('');
    try {
      return await request(url, { method, headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: body === undefined ? undefined : JSON.stringify(body) });
    } catch (caught) {
      setError(caught.message);
      throw caught;
    } finally { setBusy(false); }
  }

  async function openEditor(row = null) {
    setBusy(true); setError('');
    try {
      const needed = report.columns.map((_, index) => index + 1);
      const loaded = await Promise.all(needed.map((number) => loadChoices(number)));
      setChoices(Object.fromEntries(needed.map((number, index) => [number, loaded[index]])));
      setEditor({ id: row?.id || null, values: row
        ? row.values.map((value) => typeof value === 'string' && !value.trim() ? null : value)
        : Array(report.column_count).fill(null) });
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  async function saveRow(values) {
    if (!editor || !csrf || saving.current) return;
    saving.current = true;
    const url = editor.id ? `/api/uploads/${uploadId}/managed-rows/${editor.id}/`
      : `/api/uploads/${uploadId}/managed-rows/`;
    try {
      await mutate(url, editor.id ? 'PATCH' : 'POST', { values });
      setEditor(null);
      await loadRows(1);
      setMessage('데이터를 저장했습니다.');
    } catch { /* mutate displays the error */ }
    finally { saving.current = false; }
  }

  async function deleteRow(row) {
    if (deleting.current || busy || !csrf) return;
    deleting.current = true;
    try {
      await mutate(`/api/uploads/${uploadId}/managed-rows/${row.id}/`, 'DELETE');
      setDeleteTarget(null);
      await loadRows(Math.min(page, Math.max(1, Math.ceil((rowCount - 1) / 20))));
      setMessage('데이터를 삭제했습니다.');
    } catch { /* mutate displays the error */ }
    finally { deleting.current = false; }
  }

  async function addChoice(value) {
    if (!value.trim() || !csrf || busy) return false;
    try {
      await mutate(`/api/uploads/${uploadId}/choices/`, 'POST', { column, value });
      await loadChoices(column);
      setMessage('선택지를 추가했습니다.');
      return true;
    } catch { return false; }
  }

  async function saveFieldName(number, label) {
    if (busy || !csrf || saving.current) return;
    saving.current = true;
    try {
      const result = await mutate(`/api/uploads/${uploadId}/fields/${number}/`, 'PATCH', { label });
      onFieldLabelsChange?.(result.field_labels);
      setFieldEditing(null);
      setMessage('필드명을 저장했습니다.');
    } catch { /* Keep the draft visible when saving fails. */ }
    finally { saving.current = false; }
  }

  async function updateChoice(choice, changes) {
    if (!csrf || busy) return false;
    try {
      await mutate(`/api/uploads/${uploadId}/choices/${choice.id}/`, 'PATCH', changes);
      await loadChoices(column);
      await loadRows(page);
      setMessage('선택지를 변경했습니다.');
      return true;
    } catch { return false; }
  }


  return <section className={embedded ? 'admin-data-view' : 'admin-shell'} aria-label="관리자 화면">
    {!embedded && <aside className="admin-sidebar">
      <p className="admin-sidebar-title">관리 메뉴</p>
      <nav aria-label="관리자 화면 선택">
        {config.views.map((item, index) => <button key={item.template} type="button"
          aria-current={selected === index ? 'page' : undefined} onClick={() => { setSelected(index); setEditor(null); setError(''); }}>
          {item.template === 'requests' && workflowConfig?.admin?.template === 'reply_inquiries' ? '문의 관리' : labels[item.template]}
        </button>)}
      </nav>
    </aside>}
    <div className={embedded ? undefined : 'admin-content'}>
      <div className="admin-heading">
        <div><h2>{view.template === 'requests' && workflowConfig?.admin?.template === 'reply_inquiries' ? '문의 관리' : labels[view.template]}</h2></div>
        <span>{view.template === 'choices' ? `${choiceList.length.toLocaleString()}개 선택지`
          : view.template === 'fields' ? `${report.column_count.toLocaleString()}개 필드`
          : `${rowCount.toLocaleString()}개 데이터 · ${report.column_count.toLocaleString()}개 필드`}</span>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {view.template === 'records' && <>
        <ListControls uploadId={uploadId} columns={report.columns.map((item, index) => ({ ...item, number: index + 1 }))} disabled={busy || loadingRows}
          actions={<button type="button" data-intent="primary" disabled={busy || !csrf} onClick={() => openEditor()}>데이터 추가</button>}
          onApply={(criteria) => { setError(''); loadRows(1, criteria).catch((caught) => setError(caught.message)); }} />
        {deleteTarget && <ServiceDialog title="데이터를 삭제할까요?" className="admin-delete-dialog" busy={busy} error={error} onClose={() => setDeleteTarget(null)}>
          <div className="delete-target"><span className="muted">{deleteTarget.displayNumber}번 데이터</span>
            {deleteSummary.title && <div className="delete-target-title"><small>{deleteSummary.title.label}</small><p>{deleteSummary.title.value}</p></div>}
            <dl className="delete-target-fields">{deleteSummary.supporting.map((field) => <div key={field.number}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}</dl>
            {!deleteSummary.title && !deleteSummary.supporting.length && <p>모든 값이 비어 있는 데이터</p>}
          </div>
          <p className="muted">삭제한 데이터는 되돌릴 수 없습니다.</p>
          <div className="dialog-form-actions"><button type="button" className="service-back-button" disabled={busy} onClick={() => setDeleteTarget(null)}>취소</button>
            <button type="button" data-intent="danger" disabled={busy || !csrf} onClick={() => deleteRow(deleteTarget)}>{busy ? '삭제 중…' : '삭제'}</button></div>
        </ServiceDialog>}
        {editor && <RowEditor row={editor} columns={report.columns} choices={choices}
          titleColumns={[workflowConfig?.user?.subjectColumn, ...titleColumns, ...dashboardConfig.views.map((item) => item.titleColumn)]}
          busy={busy} error={error} canSave={!!csrf} onSave={saveRow} onClose={() => setEditor(null)} />}
        <div className="table-scroll" role="region" aria-label="관리 데이터 목록" tabIndex={0}>
          <table className="admin-record-table"><thead><tr><th scope="col" className="admin-record-tools">번호 · 관리</th>{view.columns.map((number) => <th key={number} scope="col">{report.columns[number - 1].label}</th>)}</tr></thead>
            <tbody>{rows.map((row, index) => <tr key={row.id}>
              <td className="admin-record-tools"><div className="admin-record-actions"><span className="admin-record-number">{(page - 1) * 20 + index + 1}</span>
                <button type="button" className="record-icon-action" title="수정" aria-label={`${(page - 1) * 20 + index + 1}행 수정`} disabled={busy} onClick={() => openEditor(row)}>
                  <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="m15 5 4 4M4 20l4-1 12-12a2.8 2.8 0 0 0-4-4L4 15z" /></svg>
                </button>
                <button type="button" className="record-icon-action record-delete-action" title="삭제" aria-label={`${(page - 1) * 20 + index + 1}행 삭제`} disabled={busy || !csrf} onClick={() => { setError(''); setDeleteTarget({ ...row, displayNumber: (page - 1) * 20 + index + 1 }); }}>
                  <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="m6 6 12 12M18 6 6 18" /></svg>
                </button></div></td>
              {view.columns.map((number) => <td key={number}><span className="service-table-value" title={String(row.values[number - 1] ?? '')}>{row.values[number - 1] || '—'}</span></td>)}
            </tr>)}</tbody>
          </table>
        </div>
        {!rows.length && !loadingRows && <p className="muted">조건에 맞는 데이터가 없습니다.</p>}
        {message && <p className="notice" role="status">{message}</p>}
        <nav className="service-pagination" aria-label="관리 데이터 페이지">
          <button type="button" disabled={busy || loadingRows || page === 1} onClick={() => loadRows(page - 1).catch((caught) => setError(caught.message))}>이전</button>
          <span>{page} / {Math.max(1, Math.ceil(rowCount / 20))}</span>
          <button type="button" disabled={busy || loadingRows || page * 20 >= rowCount} onClick={() => loadRows(page + 1).catch((caught) => setError(caught.message))}>다음</button>
        </nav>
      </>}
      {view.template === 'fields' && <div className="table-scroll admin-fields-scroll" role="region" aria-label="필드 구성 목록" tabIndex={0}>
        <table className="admin-fields-table"><thead><tr>{[
          { key: 'number', label: '번호' }, { key: 'name', label: '필드명' }, { key: 'type', label: '값 형식' }, { key: 'count', label: '고유 값 수' },
        ].map((item) => <th key={item.key} scope="col" aria-sort={fieldSort?.key === item.key ? fieldSort.direction === 'asc' ? 'ascending' : 'descending' : 'none'}>
          <button type="button" className="field-sort-button" onClick={() => setFieldSort((current) => ({ key: item.key, direction: current?.key === item.key && current.direction === 'asc' ? 'desc' : 'asc' }))}>
            {item.label}{fieldSort?.key === item.key && <span aria-hidden="true"> {fieldSort.direction === 'asc' ? '↑' : '↓'}</span>}
          </button>
        </th>)}</tr></thead>
          <tbody>{fieldColumns.map((number) => {
        const field = report.columns[number - 1];
        return <tr key={field.id}><td>{number}</td><th scope="row">
          {fieldEditing === number ? <FieldNameEditor label={field.label} number={number} busy={busy} onSave={(label) => saveFieldName(number, label)} onCancel={() => setFieldEditing(null)} />
            : <div className="field-name-display"><span>{field.label}</span><button type="button" className="field-name-icon" title="필드명 수정" aria-label={`${field.label} 필드명 수정`} disabled={busy || !csrf}
              onClick={() => { setFieldEditing(number); setError(''); setMessage(''); }}><FieldActionIcon kind="edit" /></button></div>}
        </th><td>{typeLabels[field.candidate] || field.candidate}</td><td>{field.unique_count.toLocaleString()}개</td></tr>;
      })}</tbody></table></div>}
      {view.template === 'choices' && <ChoiceManagement key={column} uploadId={uploadId} columns={report.columns} column={column}
        choices={choiceList} loaded={Object.hasOwn(choices, column)} busy={busy} canSave={!!csrf} message={message} error={error}
        onClearError={() => setError('')}
        onColumn={(number) => { setColumn(number); setMessage(''); setError(''); }} onAdd={addChoice} onUpdate={updateChoice} />}
      {view.template === 'requests' && workflowConfig?.admin?.template === 'reply_inquiries' &&
        <InquiryPage uploadId={uploadId} config={workflowConfig} admin />}
      {view.template === 'requests' && workflowConfig?.admin?.template !== 'reply_inquiries' &&
        <RequestManagement uploadId={uploadId} />}
      {!['records', 'choices'].includes(view.template) && message && <p className="notice" role="status">{message}</p>}
    </div>
  </section>;
}
