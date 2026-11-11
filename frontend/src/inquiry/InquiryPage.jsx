import React, { useEffect, useRef, useState } from 'react';
import './inquiry.css';
import ServiceDialog from '../components/ServiceDialog';
import SectionIcon from '../components/SectionIcon';
import { Empty, Icon, IconButton, Pager, Segmented } from '../components/ui';

const labels = { received: '접수', in_progress: '처리 중', resolved: '완료' };
const tones = { received: 'pending', in_progress: 'pending', resolved: 'ok' };
const dateText = (value) => new Date(value).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' });
const openEditor = (item) => ({ id: item.id, title: item.title, body: item.body, subject: item.subject, answer: item.answer,
  author: item.author, phone: item.phone, isPrivate: item.is_private,
  status: item.status === 'received' ? 'resolved' : item.status });
async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) throw new Error(data?.detail || '문의를 처리하지 못했습니다.');
  return data;
}

/** Staff answer inquiries here; bookers ask and read them on the board (InquiryBoard). */
export default function InquiryPage({ uploadId, admin = true }) {
  const [list, setList] = useState({ inquiries: [], page: 1, count: 0, has_next: false });
  const [csrf, setCsrf] = useState('');
  const [editor, setEditor] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [status, setStatus] = useState('');
  const working = useRef(false);
  const base = `/api/uploads/${uploadId}/inquiries/`;
  const listUrl = (page, only = status) => `${base}?page=${page}${only ? `&status=${only}` : ''}`;
  const load = (page = 1, only = status) => api(listUrl(page, only)).then(setList).catch((caught) => setError(caught.message));
  useEffect(() => {
    let active = true;
    Promise.all([api('/api/session/'), api(listUrl(1))])
      .then(([session, result]) => { if (active) { setCsrf(session.csrf_token); setList(result); } })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId, admin]);

  async function save(event) {
    event.preventDefault();
    if (working.current || !csrf) return;
    working.current = true; setBusy(true); setError(''); setMessage('');
    try {
      await api(`${base}${editor.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ answer: editor.answer, status: editor.status }),
      });
      setEditor(null);
      setMessage('저장했습니다.');
      await load(list.page);
    } catch (caught) { setError(caught.message); }
    finally { working.current = false; setBusy(false); }
  }
  async function remove(item) {
    if (working.current || !csrf || !window.confirm(`"${item.title}" 문의를 삭제할까요? 되돌릴 수 없습니다.`)) return;
    working.current = true; setBusy(true); setError(''); setMessage('');
    try {
      const response = await fetch(`${base}${item.id}/`, { method: 'DELETE', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf } });
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || '문의를 삭제하지 못했습니다.');
      setMessage('문의를 삭제했습니다.'); await load(list.page > 1 && list.inquiries.length === 1 ? list.page - 1 : list.page);
    } catch (caught) { setError(caught.message); }
    finally { working.current = false; setBusy(false); }
  }

  return <div className="inquiry-page">
    <section className="panel">
      <div className="section-title"><h2 className="icon-heading"><SectionIcon name="inquiry" />문의 답변</h2>
        <span className="section-tools">{admin && <span className="section-count">{list.count.toLocaleString()}건</span>}
          <IconButton icon="refresh" label="새로고침" disabled={busy} onClick={() => load(list.page)} /></span></div>
      {admin && error && <p className="error" role="alert">{error}</p>}
      {message && <p className="notice" role="status">{message}</p>}
      {admin && <div className="ui-toolbar"><Segmented label="처리 상태" value={status} onChange={(next) => { setStatus(next); load(1, next); }}
        options={[{ value: '', label: '전체' }, ...Object.entries(labels).map(([value, label]) => ({ value, label }))]} /></div>}
      {!list.inquiries.length && <Empty>{status ? `${labels[status]} 상태인 문의가 없습니다.` : '문의가 없습니다.'}</Empty>}
      {admin && list.inquiries.length > 0 && <div className="table-scroll" role="region" aria-label="문의 목록" tabIndex={0}>
        <table className="resource-table notice-table inquiry-table">
          <thead><tr><th scope="col">문의</th><th scope="col">작성자</th><th scope="col">관련 항목</th><th scope="col">상태</th><th scope="col">날짜</th><th scope="col"><span className="visually-hidden">관리</span></th></tr></thead>
          <tbody>{list.inquiries.map((item) => <tr key={item.id} className={item.status === 'resolved' ? 'is-inactive' : undefined}>
            <td className="notice-title"><button type="button" className="service-title-button with-icon" onClick={() => setEditor(openEditor(item))}>
              {item.is_private && <Icon name="lock" size={13} />}{item.title}</button>
              <small className="cell-sub">{item.body.slice(0, 60)}{item.body.length > 60 ? '…' : ''}</small></td>
            <td>{item.author || <span className="muted">-</span>}{item.phone && <small className="cell-sub">{item.phone}</small>}</td>
            <td title={item.subject ? item.subject.split(' / ').join(' › ') : undefined}>{item.subject ? item.subject.split(' / ').at(-1) : <span className="muted">일반</span>}</td>
            <td><span className={`service-badge tone-${tones[item.status]}`}>{labels[item.status]}</span></td>
            <td className="cell-when">{dateText(item.created_at)}</td>
            <td className="cell-actions"><div className="ui-actions">
              <IconButton icon={item.answer ? 'edit' : 'reply'} tone="info" label={item.answer ? '답변 수정' : '답변하기'} disabled={busy} onClick={() => setEditor(openEditor(item))} />
              <IconButton icon="trash" tone="danger" label="삭제" disabled={busy} onClick={() => remove(item)} />
            </div></td>
          </tr>)}</tbody>
        </table>
      </div>}
      <Pager page={list.page} count={list.count} disabled={busy} onPage={load} />
    </section>
    {admin && editor && <ServiceDialog title={editor.title} busy={busy} error={error} onClose={() => setEditor(null)}><form onSubmit={save}>
      <fieldset className="form-grid" disabled={busy}>
        <p className="muted">{[editor.author, editor.phone, editor.isPrivate ? '비공개' : '공개'].filter(Boolean).join(' · ')}</p>
        {editor.subject && <p className="muted" title={editor.subject.split(' / ').join(' › ')}>{editor.subject.split(' / ').at(-1)}</p>}
        <p className="inquiry-text">{editor.body}</p>
        <label>답변<textarea rows={5} value={editor.answer} required={editor.status === 'resolved'} maxLength={5000}
          onChange={(event) => setEditor({ ...editor, answer: event.target.value })} /></label>
        <div className="dialog-actions dialog-actions-split">
          <Segmented label="처리 상태" value={editor.status} onChange={(status) => setEditor({ ...editor, status })}
            options={Object.entries(labels).map(([value, label]) => ({ value, label }))} />
          <button type="submit" disabled={!csrf || (editor.status === 'resolved' && !editor.answer.trim())}>저장</button>
        </div>
      </fieldset>
    </form></ServiceDialog>}
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
  return <section className="panel"><div className="section-title"><h2 className="icon-heading"><SectionIcon name="inquiry" />문의 현황</h2>
    <IconButton icon="refresh" label="새로고침" onClick={load} /></div>
    {error && <p className="error" role="alert">{error}</p>}
    {stats && <div className="ledger-focus">{Object.entries(labels).map(([status, label], index) =>
      <div key={status} className={index ? 'is-quiet' : undefined}><span className="ledger-focus__label">{label}</span><strong>{stats.counts[status].toLocaleString()}</strong><span className="ledger-focus__unit">건</span></div>)}</div>}
  </section>;
}
