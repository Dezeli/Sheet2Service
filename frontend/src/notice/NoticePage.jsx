import React, { useEffect, useRef, useState } from 'react';
import ServiceDialog from '../components/ServiceDialog';
import SectionIcon from '../components/SectionIcon';
import { Empty, Icon, IconButton, Pager, Segmented } from '../components/ui';
import '../inquiry/inquiry.css';

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) throw new Error(data?.detail || '공지를 처리하지 못했습니다.');
  return data;
}

const dateText = (value) => new Date(value).toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' });

/** Published notices for everyone; drafts, editing and publishing for admins. */
export default function NoticePage({ uploadId, title, admin = false, focus = '' }) {
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

  // a notice named in the address opens on arrival, even when it is not on the first page
  const [focused, setFocused] = useState(null);
  useEffect(() => {
    setFocused(null);
    if (!focus || admin) return;
    api(`${base}${focus}/`).then(setFocused).catch(() => setFocused(null));
  }, [uploadId, focus, admin]);
  useEffect(() => { if (focused) document.getElementById(`notice-${focused.id}`)?.scrollIntoView({ block: 'center' }); }, [focused]);
  const shown = focused && !list.notices.some((item) => item.id === focused.id) ? [focused, ...list.notices] : list.notices;
  const load = (page = 1) => api(listUrl(page)).then(setList).catch((caught) => setError(caught.message));
  async function save(event) {
    event.preventDefault();
    if (working.current || !csrf || !editor) return;
    working.current = true; setBusy(true); setError(''); setMessage('');
    try {
      await api(editor.id ? `${base}${editor.id}/` : base, {
        method: editor.id ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ title: editor.title, body: editor.body, is_published: editor.is_published }),
      });
      setMessage(editor.is_published ? '공지를 게시했습니다.' : '숨김으로 저장했습니다.');
      setEditor(null); await load(1);
    } catch (caught) { setError(caught.message); }
    finally { working.current = false; setBusy(false); }
  }
  async function quick(item, method, body, text) {
    if (working.current || !csrf) return;
    working.current = true; setBusy(true); setError(''); setMessage('');
    try {
      const response = await fetch(`${base}${item.id}/`, { method, credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: body ? JSON.stringify(body) : undefined });
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || '공지를 처리하지 못했습니다.');
      setMessage(text); await load(list.page);
    } catch (caught) { setError(caught.message); }
    finally { working.current = false; setBusy(false); }
  }
  const togglePublished = (item) => quick(item, 'PATCH', { is_published: !item.is_published }, item.is_published ? '공지를 숨겼습니다.' : '공지를 게시했습니다.');
  const remove = (item) => { if (window.confirm(`"${item.title}" 공지를 삭제할까요? 되돌릴 수 없습니다.`)) quick(item, 'DELETE', null, '공지를 삭제했습니다.'); };
  const open = (item) => { setEditor(item ? { id: item.id, title: item.title, body: item.body, is_published: item.is_published } : { title: '', body: '', is_published: true }); setError(''); setMessage(''); };

  return <div className="inquiry-page">
    <section className="panel">
      <div className="section-title"><h2 className="icon-heading"><SectionIcon name="notice" />{title || (admin ? '공지 관리' : '공지')}</h2>
        <span className="section-tools">
          <IconButton icon="refresh" label="새로고침" disabled={busy} onClick={() => load(list.page)} />
          {admin && <button type="button" data-intent="primary" className="with-icon" disabled={busy} onClick={() => open(null)}><Icon name="plus" size={16} />공지 작성</button>}
        </span>
      </div>
      {!editor && error && <p className="error" role="alert">{error}</p>}
      {message && <p className="notice" role="status">{message}</p>}
      {!list.notices.length && <Empty>{admin ? '작성한 공지가 없습니다.' : '공지가 없습니다.'}</Empty>}
      {admin && list.notices.length > 0 && <div className="table-scroll" role="region" aria-label="공지 목록" tabIndex={0}>
        <table className="resource-table notice-table">
          <thead><tr><th scope="col">제목</th><th scope="col">상태</th><th scope="col">날짜</th><th scope="col"><span className="visually-hidden">관리</span></th></tr></thead>
          <tbody>{list.notices.map((item) => <tr key={item.id} className={item.is_published ? undefined : 'is-inactive'}>
            <td className="notice-title"><button type="button" className="service-title-button" onClick={() => open(item)}>{item.title}</button>
              <small className="cell-sub">{item.body.slice(0, 60)}{item.body.length > 60 ? '…' : ''}</small></td>
            <td><span className={`service-badge tone-${item.is_published ? 'ok' : 'muted'}`}>{item.is_published ? '게시 중' : '숨김'}</span></td>
            <td className="cell-when">{dateText(item.published_at || item.updated_at)}</td>
            <td className="cell-actions"><div className="ui-actions">
              <IconButton icon="edit" tone="info" label="수정" disabled={busy} onClick={() => open(item)} />
              <IconButton icon={item.is_published ? 'eyeOff' : 'eye'} tone={item.is_published ? 'warn' : 'approve'} label={item.is_published ? '숨기기' : '게시하기'} disabled={busy} onClick={() => togglePublished(item)} />
              <IconButton icon="trash" tone="danger" label="삭제" disabled={busy} onClick={() => remove(item)} />
            </div></td>
          </tr>)}</tbody>
        </table>
      </div>}
      {!admin && <div className="inquiry-list">{shown.map((item) => <details key={`${item.id}-${focused?.id === item.id}`} id={`notice-${item.id}`}
        className={`inquiry-item${focused?.id === item.id ? ' is-focused' : ''}`} open={focused?.id === item.id || undefined}>
        <summary><strong>{item.title}</strong>
          <span className="summary-meta"><small className="muted">{dateText(item.published_at || item.updated_at)}</small></span>
        </summary>
        <p className="inquiry-text">{item.body}</p>
      </details>)}</div>}
      <Pager page={list.page} count={list.count} disabled={busy} onPage={load} />
    </section>
    {admin && editor && <ServiceDialog title={editor.id ? '공지 수정' : '공지 작성'} busy={busy} error={error} onClose={() => setEditor(null)}>
      <form onSubmit={save}><fieldset disabled={busy} className="form-grid">
        <label>제목<input required maxLength={120} value={editor.title} onChange={(event) => setEditor({ ...editor, title: event.target.value })} /></label>
        <label>내용<textarea required rows={8} maxLength={10000} value={editor.body} onChange={(event) => setEditor({ ...editor, body: event.target.value })} /></label>
        <div className="dialog-actions dialog-actions-split">
          <Segmented label="게시 상태" value={editor.is_published} onChange={(value) => setEditor({ ...editor, is_published: value })}
            options={[{ value: true, label: '게시' }, { value: false, label: '숨김' }]} />
          <button type="submit" disabled={!csrf || !editor.title.trim() || !editor.body.trim()}>저장</button>
        </div>
      </fieldset></form>
    </ServiceDialog>}
  </div>;
}
