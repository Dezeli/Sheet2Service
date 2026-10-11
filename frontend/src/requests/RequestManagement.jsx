import React, { useEffect, useRef, useState } from 'react';
import ServiceDialog from '../components/ServiceDialog';

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
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sort, setSort] = useState('-created_at');
  const [expanded, setExpanded] = useState(null);
  const [loading, setLoading] = useState(false);
  const sequence = useRef(0);
  const working = useRef(false);
  const base = `/api/uploads/${uploadId}/service-requests/`;
  async function load(page = 1) {
    const current = ++sequence.current;
    setLoading(true);
    try {
      const params = new URLSearchParams({ page, q: query, status: statusFilter, sort });
      const result = await api(`${base}?${params}`);
      if (current === sequence.current) { setList(result); setExpanded(null); }
    } finally { if (current === sequence.current) setLoading(false); }
  }
  useEffect(() => {
    let active = true;
    api('/api/session/').then((session) => { if (active) setCsrf(session.csrf_token); })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId]);
  useEffect(() => {
    const timer = setTimeout(() => { setError(''); load(1).catch((caught) => setError(caught.message)); }, query ? 300 : 0);
    return () => { clearTimeout(timer); sequence.current += 1; };
  }, [uploadId, query, statusFilter, sort]);
  async function save(event) {
    event.preventDefault(); if (working.current || !editor || !csrf) return;
    working.current = true; setBusy(true); setError(''); setMessage('');
    let saved = false;
    try {
      await api(`${base}${editor.id}/`, { method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ status: editor.status, processing_note: editor.note }),
      });
      saved = true; setEditor(null); setMessage('처리했습니다.'); await load(1);
    } catch (caught) { setError(saved ? '처리됐지만 목록을 불러오지 못했습니다. 새로고침해 주세요.' : caught.message); }
    finally { working.current = false; setBusy(false); }
  }
  return <section className="panel">
    <div className="section-title"><h2>{title || '신청 관리'}</h2><button type="button" className="service-back-button" disabled={busy}
      onClick={() => load(list.page).catch((caught) => setError(caught.message))}>새로고침</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="request-tools"><div className="request-search">
      <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg>
      <input type="search" aria-label="신청 검색" placeholder="신청 검색" maxLength={200} value={query} disabled={busy} onChange={(event) => setQuery(event.target.value)} /></div>
      <div className="request-filter">
        <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 5h18l-7 8v6l-4 2v-8z" /></svg>
        <select aria-label="신청 상태 필터" value={statusFilter} disabled={busy} onChange={(event) => setStatusFilter(event.target.value)}><option value="">전체 상태</option>{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
        <span className="muted">{list.count.toLocaleString()}개</span></div>
    </div>
    <div className="table-scroll" role="region" aria-label="신청 목록" aria-busy={loading} tabIndex={0}>
      <table className="request-management-table"><thead><tr><th scope="col">번호</th>{[
        { key: 'subject', label: '신청 항목' }, { key: 'status', label: '상태' }, { key: 'created_at', label: '신청일' },
      ].map((item) => <th key={item.key} scope="col" aria-sort={sort.replace('-', '') === item.key ? sort.startsWith('-') ? 'descending' : 'ascending' : 'none'}>
        <button type="button" className="request-sort" disabled={busy || loading} onClick={() => setSort((current) => current === item.key ? `-${item.key}` : item.key)}>{item.label}{sort.replace('-', '') === item.key && <span aria-hidden="true"> {sort.startsWith('-') ? '↓' : '↑'}</span>}</button>
      </th>)}</tr></thead><tbody>{list.requests.map((item, index) => <React.Fragment key={item.id}>
        <tr><td>{(list.page - 1) * 20 + index + 1}</td><td><div className="request-subject-cell">
          <button type="button" className="request-subject" aria-expanded={expanded === item.id} title={expanded === item.id ? '접기' : '신청 내용 보기'} onClick={() => setExpanded((current) => current === item.id ? null : item.id)}>{item.subject}</button>
          <div className="request-actions">{item.admin_actions.map((status) => <button type="button" key={status} className={`request-action ${status === 'rejected' ? 'is-danger' : ''}`} title={actions[status]} aria-label={`${item.subject} ${actions[status]}`} disabled={busy || loading || !csrf}
            onClick={() => { setError(''); setEditor({ id: item.id, subject: item.subject, status, note: item.processing_note }); }}>
            <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              {status === 'rejected' ? <path d="m6 6 12 12M18 6 6 18" /> : status === 'in_progress' ? <path d="m8 4 12 8-12 8z" /> : status === 'completed' ? <><circle cx="12" cy="12" r="9" /><path d="m7 12 3 3 7-7" /></> : <path d="m5 12 4 4L19 6" />}
            </svg></button>)}</div></div></td>
          <td><span className="request-status" data-status={item.status}>{labels[item.status]}</span></td>
          <td className="request-date"><time dateTime={item.created_at} title={new Date(item.created_at).toLocaleString('ko-KR')}>{new Date(item.created_at).toLocaleDateString('ko-KR')}</time></td></tr>
        {expanded === item.id && <tr className="request-detail-row"><td colSpan={4}><dl>
          <div><dt>신청 내용</dt><dd>{item.content || '작성된 내용이 없습니다.'}</dd></div>
          {item.processing_note && <div><dt>처리 사유</dt><dd>{item.processing_note}</dd></div>}
        </dl></td></tr>}
      </React.Fragment>)}</tbody></table>
    </div>
    {!list.requests.length && !loading && <p className="muted">조건에 맞는 신청이 없습니다.</p>}
    {editor && <ServiceDialog title={`신청 ${actions[editor.status]}`} busy={busy} error={error} onClose={() => setEditor(null)}>
      <div className="editor-subject"><p>{editor.subject}</p></div><form onSubmit={save}>
      <fieldset className="inquiry-form" disabled={busy}><label>처리 사유{editor.status === 'rejected' ? ' (필수)' : ' (선택)'}
        <textarea required={editor.status === 'rejected'} maxLength={5000} value={editor.note}
          onChange={(event) => setEditor({ ...editor, note: event.target.value })} /></label>
        <div className="dialog-form-actions"><button type="button" className="service-back-button" onClick={() => setEditor(null)}>취소</button>
          <button type="submit" data-intent={editor.status === 'rejected' ? 'danger' : 'primary'} disabled={!csrf || (editor.status === 'rejected' && !editor.note.trim())}>{actions[editor.status]}</button></div>
      </fieldset></form></ServiceDialog>}
    {message && <p className="notice" role="status">{message}</p>}
    <nav className="service-pagination" aria-label="접수 목록 페이지">
      <button type="button" disabled={busy || loading || list.page === 1} onClick={() => load(list.page - 1).catch((caught) => setError(caught.message))}>이전</button>
      <span>{list.page} / {Math.max(1, Math.ceil(list.count / 20))}</span>
      <button type="button" disabled={busy || loading || !list.has_next} onClick={() => load(list.page + 1).catch((caught) => setError(caught.message))}>다음</button>
    </nav>
  </section>;
}
