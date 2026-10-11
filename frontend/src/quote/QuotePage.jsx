import React, { useEffect, useRef, useState } from 'react';
import '../inquiry/inquiry.css';

const statuses = { pending: '견적 대기', quoted: '견적 도착', accepted: '수락', declined: '견적 거절',
  unavailable: '요청 거절', in_progress: '진행 중', completed: '완료', cancelled: '취소' };
const actions = { accept: '견적 수락', decline: '견적 거절', cancel: '요청 취소', start: '진행 시작', complete: '완료 처리' };
const messages = { save: '견적 초안을 저장했습니다.', send: '견적을 전달했습니다.', reject: '요청을 거절했습니다.',
  accept: '견적을 수락했습니다.', decline: '견적을 거절했습니다.', cancel: '요청을 취소했습니다.', start: '진행을 시작했습니다.', complete: '완료 처리했습니다.' };
async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) throw new Error(data?.detail || '견적을 처리하지 못했습니다.');
  return data;
}

export default function QuotePage({ uploadId, config, admin = false }) {
  const [list, setList] = useState({ quotes: [], page: 1, count: 0, has_next: false });
  const [rows, setRows] = useState({ rows: [], page: 1, row_count: 0 });
  const [rowId, setRowId] = useState('');
  const [content, setContent] = useState('');
  const [editor, setEditor] = useState(null);
  const [csrf, setCsrf] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const working = useRef(false);
  const base = `/api/uploads/${uploadId}/quote-requests/`;
  const listUrl = (page) => `${base}?page=${page}${admin ? '&admin=1' : ''}`;

  useEffect(() => {
    let active = true;
    Promise.all([api('/api/session/'), api(listUrl(1)),
      admin ? Promise.resolve(null) : api(`/api/uploads/${uploadId}/managed-rows/?page=1`)])
      .then(([session, result, candidates]) => {
        if (!active) return;
        setCsrf(session.csrf_token); setList(result); if (candidates) setRows(candidates);
      }).catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId, admin]);

  function load(page = 1) { return api(listUrl(page)).then(setList); }
  function loadRows(page) { api(`/api/uploads/${uploadId}/managed-rows/?page=${page}`).then(setRows).catch((caught) => setError(caught.message)); }
  async function mutate(id, body) {
    if (working.current || !csrf) return;
    working.current = true; setBusy(true); setError(''); setMessage('');
    let saved = false;
    try {
      await api(id ? `${base}${id}/` : base, { method: id ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify(body) });
      saved = true; setMessage(id ? messages[body.action] : '견적 요청을 접수했습니다.');
      setEditor(null); if (!id) { setRowId(''); setContent(''); }
      await load(1);
    } catch (caught) { setError(saved ? '저장됐지만 목록을 불러오지 못했습니다. 새로고침해 주세요.' : caught.message); }
    finally { working.current = false; setBusy(false); }
  }
  function saveOffer(event) {
    event.preventDefault();
    const action = event.nativeEvent.submitter?.value || 'save';
    mutate(editor.id, action === 'reject' ? { action, processing_note: editor.processing_note }
      : { action, amount: editor.amount, currency: editor.currency, proposal: editor.proposal });
  }

  return <div className="inquiry-page">
    <h2>{config[admin ? 'admin' : 'user'].title || (admin ? '견적 관리' : '견적 요청')}</h2>
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p className="notice" role="status">{message}</p>}
    {!admin && <section className="panel"><h3>견적 요청</h3>
      <form onSubmit={(event) => { event.preventDefault(); mutate(null, { row_id: rowId, content }); }}>
        <fieldset disabled={busy} className="inquiry-form">
          <label>항목<select required value={rowId} onChange={(event) => setRowId(event.target.value)}>
            <option value="">선택해 주세요</option>
            {rowId && !rows.rows.some((row) => row.id === rowId) && <option value={rowId}>선택한 항목</option>}
            {rows.rows.map((row) => <option key={row.id} value={row.id}>{row.values[config.user.subjectColumn - 1] || `항목 ${row.row_number}`}</option>)}
          </select></label>
          <nav className="service-pagination" aria-label="견적 항목 페이지">
            <button type="button" disabled={rows.page === 1} onClick={() => loadRows(rows.page - 1)}>이전</button>
            <span>{rows.page} / {Math.max(1, Math.ceil(rows.row_count / 20))}</span>
            <button type="button" disabled={rows.page * 20 >= rows.row_count} onClick={() => loadRows(rows.page + 1)}>다음</button>
          </nav>
          <label>요청 조건<textarea required maxLength={5000} value={content} onChange={(event) => setContent(event.target.value)} /></label>
          <button type="submit" disabled={!csrf || !rowId || !content.trim()}>요청</button>
        </fieldset>
      </form>
    </section>}
    <section className="panel"><div className="section-title"><h3>{admin ? '견적 요청 내역' : '내 견적 요청'}</h3>
      <button type="button" className="service-back-button" disabled={busy} onClick={() => load(list.page).catch((caught) => setError(caught.message))}>새로고침</button></div>
      {!list.quotes.length && <p className="muted">견적 요청이 없습니다.</p>}
      <div className="inquiry-list">{list.quotes.map((item) => <details key={item.id} className="inquiry-item">
        <summary><strong>{item.subject}</strong><span className="service-badge">{statuses[item.status]}</span></summary>
        <h4>요청 조건</h4><p className="inquiry-text">{item.content}</p>
        {item.amount !== null && <div className="inquiry-answer"><h4>{item.sent_at ? '전달된 견적' : '견적 초안'}</h4>
          <strong>{item.amount} {item.currency}</strong><p className="inquiry-text">{item.proposal}</p>
        </div>}
        {item.processing_note && <p className="inquiry-text">{item.processing_note}</p>}
        {admin && item.admin_actions.length > 0 && <button type="button" disabled={busy} onClick={() => setEditor({
          id: item.id, subject: item.subject, status: item.status, amount: item.amount || '', currency: item.currency || 'KRW',
          proposal: item.proposal, processing_note: item.processing_note, action: item.admin_actions[0],
        })}>{item.status === 'pending' ? '견적 작성·전달' : '진행 관리'}</button>}
        {!admin && item.user_actions.map((action) => <button type="button" key={action} disabled={busy || !csrf}
          onClick={() => mutate(item.id, { action })}>{actions[action]}</button>)}
      </details>)}</div>
      <nav className="service-pagination" aria-label="견적 요청 페이지">
        <button type="button" disabled={busy || list.page === 1} onClick={() => load(list.page - 1).catch((caught) => setError(caught.message))}>이전</button>
        <span>{list.page} / {Math.max(1, Math.ceil(list.count / 20))}</span>
        <button type="button" disabled={busy || !list.has_next} onClick={() => load(list.page + 1).catch((caught) => setError(caught.message))}>다음</button>
      </nav>
    </section>
    {admin && editor && <section className="panel"><h3>{editor.subject}</h3>
      <form onSubmit={editor.status === 'pending' ? saveOffer : (event) => { event.preventDefault();
        mutate(editor.id, { action: editor.action, processing_note: editor.processing_note }); }}>
        <fieldset disabled={busy} className="inquiry-form">
          {editor.status === 'pending' ? <>
            <label>금액<input required type="number" min="0" max="999999999999.99" step="0.01" value={editor.amount} onChange={(event) => setEditor({ ...editor, amount: event.target.value })} /></label>
            <label>통화<select value={editor.currency} onChange={(event) => setEditor({ ...editor, currency: event.target.value })}>
              {['KRW', 'USD', 'EUR', 'JPY'].map((currency) => <option key={currency} value={currency}>{currency}</option>)}
            </select></label>
            <label>제안 내용<textarea required maxLength={5000} value={editor.proposal} onChange={(event) => setEditor({ ...editor, proposal: event.target.value })} /></label>
            <p className="muted">전달 후 금액·제안은 변경할 수 없습니다.</p>
            <button type="submit" value="save" disabled={!csrf}>초안 저장</button>
            <button type="submit" value="send" disabled={!csrf}>견적 전달</button>
            <label>요청 거절 사유 (선택)<textarea maxLength={5000} value={editor.processing_note} onChange={(event) => setEditor({ ...editor, processing_note: event.target.value })} /></label>
            <button type="submit" value="reject" formNoValidate disabled={!csrf}>요청 거절</button>
          </> : <>
            <label>처리 메모 (선택)<textarea maxLength={5000} value={editor.processing_note} onChange={(event) => setEditor({ ...editor, processing_note: event.target.value })} /></label>
            <button type="submit" disabled={!csrf}>{actions[editor.action]}</button>
          </>}
          <button type="button" onClick={() => setEditor(null)}>닫기</button>
        </fieldset>
      </form>
    </section>}
  </div>;
}
