import React, { useEffect, useRef, useState } from 'react';
import '../inquiry/inquiry.css';

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) throw new Error(data?.detail || '공지를 처리하지 못했습니다.');
  return data;
}

export default function NoticePage({ uploadId, config, admin = false }) {
  const [list, setList] = useState({ notices: [], page: 1, count: 0, has_next: false });
  const [csrf, setCsrf] = useState('');
  const [editor, setEditor] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const working = useRef(false);
  const base = `/api/uploads/${uploadId}/notices/`;
  const listUrl = (page) => `${base}?page=${page}${admin ? '&admin=1' : ''}`;

  useEffect(() => {
    let active = true;
    Promise.all([api('/api/session/'), api(listUrl(1))])
      .then(([session, result]) => { if (active) { setCsrf(session.csrf_token); setList(result); } })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId, admin]);

  function load(page = 1) { return api(listUrl(page)).then(setList); }
  async function save(event) {
    event.preventDefault();
    if (working.current || !csrf || !editor) return;
    working.current = true; setBusy(true); setError(''); setMessage('');
    let saved = false;
    try {
      await api(editor.id ? `${base}${editor.id}/` : base, {
        method: editor.id ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ title: editor.title, body: editor.body, is_published: editor.is_published }),
      });
      saved = true; setMessage(editor.is_published ? '공지를 게시했습니다.' : '미게시 상태로 저장했습니다.');
      setEditor(null); await load(1);
    } catch (caught) { setError(saved ? '저장됐지만 목록을 불러오지 못했습니다. 새로고침해 주세요.' : caught.message); }
    finally { working.current = false; setBusy(false); }
  }

  return <div className="inquiry-page">
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p className="notice" role="status">{message}</p>}
    <section className="panel">
      <div className="section-title"><h2>{config[admin ? 'admin' : 'user'].title || (admin ? '공지 관리' : '공지')}</h2>
        {admin && <button type="button" disabled={busy} onClick={() => {
          setEditor({ title: '', body: '', is_published: false }); setError(''); setMessage('');
        }}>공지 작성</button>}
        <button type="button" disabled={busy} className="service-back-button"
          onClick={() => load(list.page).catch((caught) => setError(caught.message))}>새로고침</button>
      </div>
      {!list.notices.length && <p className="muted">{admin ? '작성한 공지가 없습니다.' : '게시된 공지가 없습니다.'}</p>}
      <div className="inquiry-list">{list.notices.map((item) => <details key={item.id} className="inquiry-item">
        <summary><strong>{item.title}</strong>
          {admin && <span className="service-badge">{item.is_published ? '게시 중' : '미게시'}</span>}
        </summary>
        <p className="muted">{new Date(item.published_at || item.updated_at).toLocaleString('ko-KR')}</p>
        <p className="inquiry-text">{item.body}</p>
        {admin && <button type="button" disabled={busy} onClick={() => {
          setEditor({ id: item.id, title: item.title, body: item.body, is_published: item.is_published });
          setError(''); setMessage('');
        }}>수정·게시 관리</button>}
      </details>)}</div>
      <nav className="service-pagination" aria-label="공지 페이지">
        <button type="button" disabled={busy || list.page === 1} onClick={() => load(list.page - 1).catch((caught) => setError(caught.message))}>이전</button>
        <span>{list.page} / {Math.max(1, Math.ceil(list.count / 20))}</span>
        <button type="button" disabled={busy || !list.has_next} onClick={() => load(list.page + 1).catch((caught) => setError(caught.message))}>다음</button>
      </nav>
    </section>
    {admin && editor && <section className="panel"><h3>{editor.id ? '공지 수정' : '공지 작성'}</h3>
      <form onSubmit={save}><fieldset disabled={busy} className="inquiry-form">
        <label>제목<input required maxLength={120} value={editor.title} onChange={(event) => setEditor({ ...editor, title: event.target.value })} /></label>
        <label>내용<textarea required maxLength={10000} value={editor.body} onChange={(event) => setEditor({ ...editor, body: event.target.value })} /></label>
        <label>게시 상태<select value={editor.is_published ? 'published' : 'draft'} onChange={(event) => setEditor({ ...editor, is_published: event.target.value === 'published' })}>
          <option value="draft">미게시</option><option value="published">게시 중</option>
        </select></label>
        <button type="submit" disabled={!csrf || !editor.title.trim() || !editor.body.trim()}>저장</button>
        <button type="button" onClick={() => setEditor(null)}>닫기</button>
      </fieldset></form>
    </section>}
  </div>;
}
