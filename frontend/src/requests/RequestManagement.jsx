import React, { useEffect, useRef, useState } from 'react';

const labels = { pending: '검토 대기', approved: '승인', rejected: '거절', submitted: '접수 완료', in_progress: '처리 중', completed: '완료', cancelled: '취소' };
const actions = { approved: '승인', rejected: '거절', in_progress: '처리 시작', completed: '처리 완료' };
async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) throw new Error(data?.detail || '신청을 처리하지 못했습니다.');
  return data;
}

export default function RequestManagement({ uploadId, title }) {
  const [list, setList] = useState({ requests: [], page: 1, count: 0, has_next: false });
  const [csrf, setCsrf] = useState('');
  const [editor, setEditor] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const working = useRef(false);
  const base = `/api/uploads/${uploadId}/service-requests/`;
  async function load(page = 1) { setList(await api(`${base}?page=${page}`)); }
  useEffect(() => {
    let active = true;
    Promise.all([api('/api/session/'), api(base)]).then(([session, result]) => {
      if (active) { setCsrf(session.csrf_token); setList(result); }
    }).catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId]);
  async function save(event) {
    event.preventDefault(); if (working.current || !editor || !csrf) return;
    working.current = true; setBusy(true); setError(''); setMessage('');
    let saved = false;
    try {
      await api(`${base}${editor.id}/`, { method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ status: editor.status, processing_note: editor.note }),
      });
      saved = true; setEditor(null); setMessage('처리했습니다.'); await load(list.page);
    } catch (caught) { setError(saved ? '처리됐지만 목록을 불러오지 못했습니다. 새로고침해 주세요.' : caught.message); }
    finally { working.current = false; setBusy(false); }
  }
  return <section className="panel">
    <div className="section-title"><h2>{title || '신청 관리'}</h2><button type="button" className="service-back-button" disabled={busy}
      onClick={() => load(list.page).catch((caught) => setError(caught.message))}>새로고침</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p className="notice" role="status">{message}</p>}
    {!list.requests.length && <p className="muted">접수된 신청이 없습니다.</p>}
    <div className="inquiry-list">{list.requests.map((item) => <details className="inquiry-item" key={item.id}>
      <summary><strong>{item.subject}</strong><span className="service-badge">{labels[item.status]}</span></summary>
      {item.content && <p className="inquiry-text">{item.content}</p>}
      {item.processing_note && <p className="inquiry-answer inquiry-text">{item.processing_note}</p>}
      <div className="admin-row-actions">{item.admin_actions.map((status) =>
        <button type="button" key={status} className={status === 'rejected' ? 'admin-danger' : ''} disabled={busy || !csrf}
          onClick={() => setEditor({ id: item.id, subject: item.subject, status, note: item.processing_note })}>{actions[status]}</button>)}</div>
    </details>)}</div>
    {editor && <form className="admin-editor" onSubmit={save}><h3>{editor.subject} · {actions[editor.status]}</h3>
      <fieldset className="inquiry-form" disabled={busy}><label>처리 사유{editor.status === 'rejected' ? ' (필수)' : ' (선택)'}
        <textarea required={editor.status === 'rejected'} maxLength={5000} value={editor.note}
          onChange={(event) => setEditor({ ...editor, note: event.target.value })} /></label>
        <div className="admin-row-actions"><button type="submit" disabled={!csrf || (editor.status === 'rejected' && !editor.note.trim())}>확인</button>
          <button type="button" className="service-back-button" onClick={() => setEditor(null)}>닫기</button></div>
      </fieldset></form>}
    <nav className="service-pagination" aria-label="접수 목록 페이지">
      <button type="button" disabled={busy || list.page === 1} onClick={() => load(list.page - 1).catch((caught) => setError(caught.message))}>이전</button>
      <span>{list.page} / {Math.max(1, Math.ceil(list.count / 20))}</span>
      <button type="button" disabled={busy || !list.has_next} onClick={() => load(list.page + 1).catch((caught) => setError(caught.message))}>다음</button>
    </nav>
  </section>;
}
