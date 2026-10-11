import React, { useEffect, useRef, useState } from 'react';
import './inquiry.css';

const labels = { received: '접수', in_progress: '처리 중', resolved: '완료' };
async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) throw new Error(data?.detail || '문의를 처리하지 못했습니다.');
  return data;
}

export default function InquiryPage({ uploadId, config, admin = false }) {
  const [list, setList] = useState({ inquiries: [], page: 1, count: 0, has_next: false });
  const [csrf, setCsrf] = useState('');
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [rowId, setRowId] = useState('');
  const [rows, setRows] = useState({ rows: [], page: 1, row_count: 0 });
  const [editor, setEditor] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const working = useRef(false);
  const column = config.user.subjectColumn;
  const base = `/api/uploads/${uploadId}/inquiries/`;
  async function load(page = 1) {
    const result = await api(`${base}?page=${page}${admin ? '' : '&mine=1'}`);
    setList(result);
  }
  async function loadRows(page = 1) {
    setRows(await api(`/api/uploads/${uploadId}/managed-rows/?page=${page}`));
  }
  useEffect(() => {
    let active = true;
    Promise.all([
      api('/api/session/'), api(`${base}?page=1${admin ? '' : '&mine=1'}`),
      !admin && column > 0 ? api(`/api/uploads/${uploadId}/managed-rows/?page=1`) : Promise.resolve(null),
    ]).then(([session, result, items]) => {
      if (!active) return;
      setCsrf(session.csrf_token); setList(result); if (items) setRows(items);
    }).catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId, admin, column]);

  async function save(event) {
    event.preventDefault();
    if (working.current || !csrf) return;
    working.current = true; setBusy(true); setError(''); setMessage('');
    let saved = false;
    try {
      await api(admin ? `${base}${editor.id}/` : base, {
        method: admin ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify(admin ? { answer: editor.answer, status: editor.status }
          : { title, body, ...(rowId ? { row_id: rowId } : {}) }),
      });
      saved = true;
      if (admin) setEditor(null);
      else { setTitle(''); setBody(''); setRowId(''); }
      setMessage(admin ? '저장했습니다.' : '문의가 접수됐습니다.');
      await load(admin ? list.page : 1);
    } catch (caught) {
      setError(saved ? '저장됐지만 목록을 불러오지 못했습니다. 새로고침해 주세요.' : caught.message);
    } finally { working.current = false; setBusy(false); }
  }

  return <div className="inquiry-page">
    {!admin && <section className="panel"><h2>문의하기</h2>
      <form onSubmit={save}><fieldset disabled={busy} className="inquiry-form">
        {column > 0 && <div>
          <label>관련 항목 (선택)<select value={rowId} onChange={(event) => setRowId(event.target.value)}>
            <option value="">일반 문의</option>
            {rowId && !rows.rows.some((row) => row.id === rowId) && <option value={rowId}>선택한 항목</option>}
            {rows.rows.map((row) => <option key={row.id} value={row.id}>{row.values[column - 1] || `항목 ${row.row_number}`}</option>)}
          </select></label>
          <nav className="service-pagination" aria-label="관련 항목 페이지">
            <button type="button" disabled={rows.page === 1} onClick={() => loadRows(rows.page - 1).catch((caught) => setError(caught.message))}>이전</button>
            <span>{rows.page} / {Math.max(1, Math.ceil(rows.row_count / 20))}</span>
            <button type="button" disabled={rows.page * 20 >= rows.row_count} onClick={() => loadRows(rows.page + 1).catch((caught) => setError(caught.message))}>다음</button>
          </nav>
        </div>}
        <label>제목<input type="text" required maxLength={120} value={title} onChange={(event) => setTitle(event.target.value)} /></label>
        <label>내용<textarea required maxLength={5000} value={body} onChange={(event) => setBody(event.target.value)} /></label>
        <button type="submit" disabled={!csrf || !title.trim() || !body.trim()}>{busy ? '접수 중...' : '문의 접수'}</button>
      </fieldset></form>
    </section>}
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p className="notice" role="status">{message}</p>}
    <section className={admin ? '' : 'panel'}>
      <div className="section-title"><h2>{admin ? '문의 관리' : '내 문의'}</h2>
        <button type="button" className="service-back-button" disabled={busy} onClick={() => load(list.page).catch((caught) => setError(caught.message))}>새로고침</button></div>
      {!list.inquiries.length && <p className="muted">문의가 없습니다.</p>}
      <div className="inquiry-list">{list.inquiries.map((item) => <details key={item.id} className="inquiry-item">
        <summary><strong>{item.title}</strong><span className="service-badge">{labels[item.status]}</span></summary>
        {item.subject && <p className="muted">{item.subject}</p>}
        <p className="inquiry-text">{item.body}</p>
        {item.answer && <div className="inquiry-answer"><h3>답변</h3><p className="inquiry-text">{item.answer}</p></div>}
        {admin && <button type="button" disabled={busy} onClick={() => setEditor({ id: item.id, title: item.title, answer: item.answer, status: item.status })}>답변·상태 수정</button>}
      </details>)}</div>
      <nav className="service-pagination" aria-label="문의 페이지">
        <button type="button" disabled={busy || list.page === 1} onClick={() => load(list.page - 1).catch((caught) => setError(caught.message))}>이전</button>
        <span>{list.page} / {Math.max(1, Math.ceil(list.count / 20))}</span>
        <button type="button" disabled={busy || !list.has_next} onClick={() => load(list.page + 1).catch((caught) => setError(caught.message))}>다음</button>
      </nav>
    </section>
    {admin && editor && <form className="admin-editor" onSubmit={save}>
      <h3>{editor.title}</h3><fieldset className="inquiry-form" disabled={busy}>
        <label>답변<textarea value={editor.answer} required={editor.status === 'resolved'} maxLength={5000}
          onChange={(event) => setEditor({ ...editor, answer: event.target.value })} /></label>
        <label>처리 상태<select value={editor.status} onChange={(event) => setEditor({ ...editor, status: event.target.value })}>
          {Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <div className="admin-row-actions"><button type="submit" disabled={!csrf || (editor.status === 'resolved' && !editor.answer.trim())}>저장</button>
          <button type="button" className="service-back-button" onClick={() => setEditor(null)}>취소</button></div>
      </fieldset>
    </form>}
  </div>;
}

export function InquiryMetrics({ uploadId }) {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState('');
  async function load() {
    try { setStats(await api(`/api/uploads/${uploadId}/inquiries/stats/`)); setError(''); }
    catch (caught) { setError(caught.message); }
  }
  useEffect(() => { load(); }, [uploadId]);
  return <section className="panel"><div className="section-title"><h2>문의 현황</h2>
    <button type="button" className="service-back-button" onClick={load}>새로고침</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    {stats && <dl className="metrics">{Object.entries(labels).map(([status, label]) =>
      <div key={status}><dt>{label}</dt><dd>{stats.counts[status].toLocaleString()}</dd></div>)}</dl>}
  </section>;
}
