import React, { useCallback, useEffect, useState } from 'react';
import { createAdminConfig } from './config.js';
import './admin.css';

const labels = { records: '데이터 관리', fields: '필드 구성', choices: '선택지 관리', requests: '신청 관리' };
const statusLabels = { pending: '검토 대기', approved: '승인', rejected: '거절', submitted: '접수 완료' };

async function request(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.detail || '요청을 처리하지 못했습니다.');
  return data;
}

export default function AdminPreview({ uploadId, report, dashboardConfig, workflowConfig }) {
  const [selected, setSelected] = useState(0);
  const [rows, setRows] = useState([]);
  const [page, setPage] = useState(1);
  const [rowCount, setRowCount] = useState(report.row_count);
  const [column, setColumn] = useState(1);
  const [choices, setChoices] = useState({});
  const [editor, setEditor] = useState(null);
  const [newChoice, setNewChoice] = useState('');
  const [choiceQuery, setChoiceQuery] = useState('');
  const [editingChoice, setEditingChoice] = useState(null);
  const [csrf, setCsrf] = useState('');
  const [requests, setRequests] = useState([]);
  const [requestPage, setRequestPage] = useState(1);
  const [requestCount, setRequestCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  let config;
  try { config = createAdminConfig(report, dashboardConfig, workflowConfig); }
  catch (caught) { config = null; }

  const loadRows = useCallback(async (nextPage = page) => {
    const result = await request(`/api/uploads/${uploadId}/managed-rows/?page=${nextPage}`);
    setRows(result.rows);
    setRowCount(result.row_count);
    setPage(result.page);
  }, [uploadId, page]);

  const loadChoices = useCallback(async (number) => {
    const result = await request(`/api/uploads/${uploadId}/choices/?column=${number}`);
    setChoices((current) => ({ ...current, [number]: result.choices }));
    return result.choices;
  }, [uploadId]);

  const loadRequests = useCallback(async (nextPage = 1) => {
    const result = await request(`/api/uploads/${uploadId}/service-requests/?page=${nextPage}`);
    setRequests(result.requests); setRequestPage(result.page); setRequestCount(result.count);
  }, [uploadId]);

  useEffect(() => {
    request('/api/session/').then((result) => setCsrf(result.csrf_token)).catch((caught) => setError(caught.message));
    loadRows(1).catch((caught) => setError(caught.message));
  }, [uploadId]);

  useEffect(() => {
    if (selected === 2) loadChoices(column).catch((caught) => setError(caught.message));
  }, [selected, column, loadChoices]);

  useEffect(() => {
    if (config?.views[selected]?.template === 'requests') loadRequests().catch((caught) => setError(caught.message));
  }, [selected, loadRequests]);

  if (!config) return <p className="error" role="alert">관리자 화면 설정이 올바르지 않습니다.</p>;
  const view = config.views[selected];
  const choiceList = choices[column] || [];
  const filteredChoices = choiceList.filter((choice) => choice.value.toLocaleLowerCase().includes(choiceQuery.toLocaleLowerCase()));

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

  async function saveRow(event) {
    event.preventDefault();
    if (!editor || !csrf) return;
    const url = editor.id ? `/api/uploads/${uploadId}/managed-rows/${editor.id}/`
      : `/api/uploads/${uploadId}/managed-rows/`;
    try {
      await mutate(url, editor.id ? 'PATCH' : 'POST', { values: editor.values });
      setEditor(null);
      await loadRows(editor.id ? page : Math.max(1, Math.ceil((rowCount + 1) / 20)));
      setMessage('데이터를 저장했습니다.');
    } catch { /* mutate displays the error */ }
  }

  async function deleteRow(row) {
    if (!window.confirm('이 데이터를 삭제할까요?')) return;
    try {
      await mutate(`/api/uploads/${uploadId}/managed-rows/${row.id}/`, 'DELETE');
      await loadRows(Math.min(page, Math.max(1, Math.ceil((rowCount - 1) / 20))));
      setMessage('데이터를 삭제했습니다.');
    } catch { /* mutate displays the error */ }
  }

  async function addChoice(event) {
    event.preventDefault();
    if (!newChoice.trim() || !csrf) return;
    try {
      await mutate(`/api/uploads/${uploadId}/choices/`, 'POST', { column, value: newChoice });
      setNewChoice('');
      await loadChoices(column);
      setMessage('선택지를 추가했습니다.');
    } catch { /* mutate displays the error */ }
  }

  async function updateChoice(choice, changes) {
    try {
      await mutate(`/api/uploads/${uploadId}/choices/${choice.id}/`, 'PATCH', changes);
      setEditingChoice(null);
      await loadChoices(column);
      await loadRows(page);
      setMessage('선택지를 변경했습니다.');
    } catch { /* mutate displays the error */ }
  }

  async function processRequest(item, status) {
    try {
      await mutate(`/api/uploads/${uploadId}/service-requests/${item.id}/`, 'PATCH', { status });
      await loadRequests(requestPage);
      setMessage(`신청을 ${statusLabels[status]} 처리했습니다.`);
    } catch { /* mutate displays the error */ }
  }

  return <section className="admin-shell" aria-label="관리자 화면">
    <aside className="admin-sidebar">
      <p className="admin-sidebar-title">관리 메뉴</p>
      <nav aria-label="관리자 화면 선택">
        {config.views.map((item, index) => <button key={item.template} type="button"
          aria-current={selected === index ? 'page' : undefined} onClick={() => { setSelected(index); setEditor(null); setError(''); }}>
          {labels[item.template]}
        </button>)}
      </nav>
    </aside>
    <div className="admin-content">
      <div className="admin-heading">
        <div><p className="eyebrow">ADMIN</p><h2>{labels[view.template]}</h2></div>
        <span>{rowCount.toLocaleString()}개 데이터 · {report.column_count.toLocaleString()}개 필드</span>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {message && <p className="notice" role="status">{message}</p>}
      {view.template === 'records' && <>
        <div className="admin-toolbar"><p className="muted">등록된 선택지만 골라 데이터를 추가하거나 수정합니다.</p>
          <button type="button" disabled={busy || !csrf} onClick={() => openEditor()}>데이터 추가</button></div>
        {editor && <form className="admin-editor" onSubmit={saveRow}>
          <div className="admin-toolbar"><h3>{editor.id ? '데이터 수정' : '새 데이터'}</h3>
            <button type="button" className="service-back-button" onClick={() => setEditor(null)}>닫기</button></div>
          <div className="admin-editor-grid">{report.columns.map((field, index) => {
            const number = index + 1;
            const current = editor.values[index] ?? '';
            const available = choices[number] || [];
            return <label key={field.id}>{field.label}
              <select value={current} onChange={(event) => setEditor((before) => ({ ...before,
                values: before.values.map((value, at) => at === index ? event.target.value || null : value) }))}>
                <option value="">선택 안 함</option>
                {current && !available.some((choice) => choice.value === current) && <option value={current}>{current} (기존 값)</option>}
                {available.map((choice) => <option key={choice.id} value={choice.value}
                  disabled={!choice.active && current !== choice.value}>{choice.value}{choice.active ? '' : ' (사용 중지)'}</option>)}
              </select>
            </label>;
          })}</div>
          <button type="submit" disabled={busy || !csrf}>저장</button>
        </form>}
        <div className="table-scroll" role="region" aria-label="관리 데이터 목록" tabIndex={0}>
          <table><thead><tr>{view.columns.map((number) => <th key={number} scope="col">{report.columns[number - 1].label}</th>)}<th scope="col">관리</th></tr></thead>
            <tbody>{rows.map((row) => <tr key={row.id}>{view.columns.map((number) => <td key={number}>{row.values[number - 1] || '—'}</td>)}
              <td><div className="admin-row-actions"><button type="button" disabled={busy} onClick={() => openEditor(row)}>수정</button>
                <button type="button" className="admin-danger" disabled={busy || !csrf} onClick={() => deleteRow(row)}>삭제</button></div></td>
            </tr>)}</tbody>
          </table>
        </div>
        <nav className="service-pagination" aria-label="관리 데이터 페이지">
          <button type="button" disabled={busy || page === 1} onClick={() => loadRows(page - 1).catch((caught) => setError(caught.message))}>이전</button>
          <span>{page} / {Math.max(1, Math.ceil(rowCount / 20))}</span>
          <button type="button" disabled={busy || page * 20 >= rowCount} onClick={() => loadRows(page + 1).catch((caught) => setError(caught.message))}>다음</button>
        </nav>
      </>}
      {view.template === 'fields' && <div className="admin-field-grid">{view.columns.map((number) => {
        const field = report.columns[number - 1];
        return <article key={field.id} className="admin-field-card"><small>필드 {number}</small><h3>{field.label}</h3>
          <p>분석 유형: {field.candidate}</p><p>최초 CSV 고유 값: {field.unique_count.toLocaleString()}개</p></article>;
      })}</div>}
      {view.template === 'choices' && <>
        <p className="muted">이 화면에서 후보를 관리합니다. 데이터 편집 화면에서는 활성 후보만 선택할 수 있습니다.</p>
        <div className="admin-choice-controls"><label>관리할 필드
          <select value={column} onChange={(event) => { setColumn(Number(event.target.value)); setChoiceQuery(''); }}>
            {report.columns.map((field, index) => <option key={field.id} value={index + 1}>{field.label}</option>)}
          </select></label>
          <label>후보 찾기<input type="search" value={choiceQuery} onChange={(event) => setChoiceQuery(event.target.value)} /></label></div>
        <form className="admin-choice-add" onSubmit={addChoice}><label>새 후보 등록
          <input value={newChoice} onChange={(event) => setNewChoice(event.target.value)} maxLength={100000} required /></label>
          <button type="submit" disabled={busy || !csrf || !newChoice.trim()}>후보 추가</button></form>
        <div className="admin-choice-list">{filteredChoices.map((choice) => <div key={choice.id} className="admin-choice-item">
          {editingChoice?.id === choice.id ? <>
            <input value={editingChoice.value} onChange={(event) => setEditingChoice({ ...editingChoice, value: event.target.value })} />
            <button type="button" disabled={busy || !editingChoice.value.trim()} onClick={() => updateChoice(choice, { value: editingChoice.value })}>저장</button>
            <button type="button" className="service-back-button" onClick={() => setEditingChoice(null)}>취소</button>
          </> : <>
            <span>{choice.value}</span><span className={choice.active ? 'template-ready' : 'template-planned'}>{choice.active ? '사용 중' : '사용 중지'}</span>
            <button type="button" disabled={busy} onClick={() => setEditingChoice({ id: choice.id, value: choice.value })}>이름 변경</button>
            <button type="button" className="service-back-button" disabled={busy} onClick={() => updateChoice(choice, { active: !choice.active })}>
              {choice.active ? '사용 중지' : '다시 사용'}</button>
          </>}
        </div>)}</div>
      </>}
      {view.template === 'requests' && <>
        <p className="muted">유저 페이지에서 접수된 신청을 확인합니다.</p>
        {workflowConfig?.admin?.steps?.length > 0 && <ol className="admin-flow-steps">
          {workflowConfig.admin.steps.map((step, index) => <li key={index}>{step}</li>)}
        </ol>}
        <div className="table-scroll" role="region" aria-label="신청 목록" tabIndex={0}>
          <table><thead><tr><th scope="col">신청 항목</th><th scope="col">상태</th><th scope="col">신청 시각</th><th scope="col">처리</th></tr></thead>
            <tbody>{requests.map((item) => <tr key={item.id}><td>{item.subject}</td>
              <td>{statusLabels[item.status]}</td><td>{new Date(item.created_at).toLocaleString()}</td><td>
                {item.status === 'pending' && workflowConfig?.admin?.template === 'review_requests'
                  ? <div className="admin-row-actions"><button type="button" disabled={busy || !csrf}
                      onClick={() => processRequest(item, 'approved')}>승인</button>
                      <button type="button" className="admin-danger" disabled={busy || !csrf}
                        onClick={() => processRequest(item, 'rejected')}>거절</button></div> : '—'}
              </td></tr>)}</tbody>
          </table>
        </div>
        <nav className="service-pagination" aria-label="신청 페이지"><button type="button" disabled={busy || requestPage === 1}
          onClick={() => loadRequests(requestPage - 1).catch((caught) => setError(caught.message))}>이전</button>
          <span>{requestPage} / {Math.max(1, Math.ceil(requestCount / 20))}</span>
          <button type="button" disabled={busy || requestPage * 20 >= requestCount}
            onClick={() => loadRequests(requestPage + 1).catch((caught) => setError(caught.message))}>다음</button></nav>
      </>}
    </div>
  </section>;
}
