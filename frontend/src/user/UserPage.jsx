import React, { useEffect, useRef, useState } from 'react';
import './user.css';
import ListControls, { listQuery } from '../components/ListControls';
import { publicColumns, summaryColumns } from './catalog';
import ServiceDialog from '../components/ServiceDialog';
import ReadableText from '../components/ReadableText';

const statusLabels = { pending: '검토 대기', approved: '승인', rejected: '거절', submitted: '접수 완료', in_progress: '처리 중', completed: '완료', cancelled: '취소' };

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.detail || '요청을 처리하지 못했습니다.');
  return data;
}

export default function UserPage({ uploadId, report, config }) {
  const [rows, setRows] = useState([]);
  const [page, setPage] = useState(1);
  const [rowCount, setRowCount] = useState(report.row_count);
  const [requests, setRequests] = useState([]);
  const [requestPage, setRequestPage] = useState(1);
  const [requestCount, setRequestCount] = useState(0);
  const [editor, setEditor] = useState(null);
  const [content, setContent] = useState('');
  const working = useRef(false);
  const [csrf, setCsrf] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [filters, setFilters] = useState({});
  const [loadingRows, setLoadingRows] = useState(false);
  const [detail, setDetail] = useState(null);
  const rowRequest = useRef(0);
  const user = config.user;
  const titleIndex = user.subjectColumn - 1;

  async function loadRows(nextPage, criteria = filters) {
    const sequence = ++rowRequest.current;
    setLoadingRows(true);
    try {
      const result = await api(`/api/uploads/${uploadId}/managed-rows/?page=${nextPage}&${listQuery(criteria)}`);
      if (sequence !== rowRequest.current) return;
      setRows(result.rows); setPage(result.page); setRowCount(result.row_count); setFilters(criteria); setDetail(null);
    } finally { if (sequence === rowRequest.current) setLoadingRows(false); }
  }

  async function loadRequests(nextPage = 1) {
    const result = await api(`/api/uploads/${uploadId}/service-requests/?mine=1&page=${nextPage}`);
    setRequests(result.requests); setRequestPage(result.page); setRequestCount(result.count);
  }

  useEffect(() => {
    Promise.all([loadRows(1), loadRequests(), api('/api/session/').then((result) => setCsrf(result.csrf_token))])
      .catch((caught) => setError(caught.message));
  }, [uploadId]);

  async function submit(event) {
    event.preventDefault();
    if (working.current || !editor || !csrf || user.template === 'browse_only') return;
    working.current = true;
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await api(`/api/uploads/${uploadId}/service-requests/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ row_id: editor.id, content }),
      });
      setEditor(null); setContent('');
      setMessage(`${result.subject}: ${statusLabels[result.status]} 상태로 신청했습니다.`);
      await loadRequests();
    } catch (caught) { setError(caught.message); }
    finally { working.current = false; setBusy(false); }
  }

  async function cancel(item) {
    if (working.current || !csrf) return;
    working.current = true; setBusy(true); setError(''); setMessage('');
    try {
      await api(`/api/uploads/${uploadId}/service-requests/${item.id}/`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ status: 'cancelled' }),
      });
      setMessage('취소했습니다.'); await loadRequests(requestPage);
    } catch (caught) { setError(caught.message); }
    finally { working.current = false; setBusy(false); }
  }

  return <div className="user-page template-workspace">
    {error && <p className="error" role="alert">{error}</p>}
    <section className="panel workspace-main"><div className="section-title"><h2>{user.title || '이용 가능한 항목'}</h2><span className="muted">{rowCount.toLocaleString()}개</span></div>
      <ListControls uploadId={uploadId} columns={publicColumns(report.columns)} disabled={busy || loadingRows}
        onApply={(criteria) => { setError(''); loadRows(1, criteria).catch((caught) => setError(caught.message)); }} />
      {!rows.length && !loadingRows && <p className="muted">조건에 맞는 항목이 없습니다.</p>}
      <div className="catalog-list" aria-busy={loadingRows}>{rows.map((row) => <article key={row.id} className="catalog-row">
        <div className="catalog-row-content"><h3><button type="button" className="service-title-button" onClick={() => setDetail(row)}>{row.values[titleIndex] || `항목 ${row.row_number}`}</button></h3>
        <dl className="catalog-summary">{summaryColumns(report.columns, user.subjectColumn).map((column) => !row.values[column.number - 1] ? null :
          <div key={column.id}><dt>{column.label}</dt><dd title={String(row.values[column.number - 1])}>{row.values[column.number - 1]}</dd></div>)}</dl></div>
        <div className="admin-row-actions"><button type="button" className="service-back-button" onClick={() => setDetail(row)}>상세 보기</button>
          {user.template !== 'browse_only' && <button type="button" data-intent="primary" disabled={busy || !csrf}
            onClick={() => { setEditor(row); setContent(''); }}>{user.template === 'request_review' ? '신청하기' : '접수하기'}</button>}</div>
      </article>)}</div>
      <nav className="service-pagination" aria-label="항목 페이지">
        <button type="button" disabled={busy || loadingRows || page === 1} onClick={() => loadRows(page - 1).catch((caught) => setError(caught.message))}>이전</button>
        <span>{page} / {Math.max(1, Math.ceil(rowCount / 20))}</span>
        <button type="button" disabled={busy || loadingRows || page * 20 >= rowCount} onClick={() => loadRows(page + 1).catch((caught) => setError(caught.message))}>다음</button>
      </nav>
    </section>
    {detail && <ServiceDialog title={detail.values[titleIndex] || '항목 상세'} onClose={() => setDetail(null)}>
      <dl className="catalog-detail">{publicColumns(report.columns).map((column) => <div key={column.id} className={String(detail.values[column.number - 1] ?? '').length > 80 || /[\r\n]/.test(String(detail.values[column.number - 1] ?? '')) ? 'field-wide' : undefined}><dt>{column.label}</dt><dd>{detail.values[column.number - 1] || '—'}</dd></div>)}</dl>
    </ServiceDialog>}
    {editor && <ServiceDialog title={editor.values[titleIndex] || `항목 ${editor.row_number}`} busy={busy} error={error} onClose={() => setEditor(null)}>
      <form onSubmit={submit}><fieldset className="inquiry-form" disabled={busy}>
        <label>신청 내용 (선택)<textarea maxLength={5000} value={content} onChange={(event) => setContent(event.target.value)} /></label>
        <div className="admin-row-actions"><button type="submit" disabled={!csrf}>{busy ? '제출 중...' : user.template === 'request_review' ? '신청 제출' : '접수 제출'}</button>
          <button type="button" className="service-back-button" onClick={() => setEditor(null)}>닫기</button></div>
      </fieldset></form>
    </ServiceDialog>}
    {user.template !== 'browse_only' && <section className="panel workspace-side"><div className="section-title"><h2>내 신청 현황</h2>
      <button type="button" className="service-back-button" disabled={busy} onClick={() => loadRequests(requestPage).catch((caught) => setError(caught.message))}>새로고침</button></div>
      {!requests.length ? <p className="muted">아직 신청한 항목이 없습니다.</p> :
        <ul className="user-request-list">{requests.map((item) => <li key={item.id}>
          <div><strong>{item.subject}</strong>
            {item.content && <ReadableText>{item.content}</ReadableText>}
            {item.processing_note && <ReadableText className="inquiry-answer">{item.processing_note}</ReadableText>}</div>
          <div><span className="service-badge">{statusLabels[item.status]}</span>
            {item.can_cancel && <button type="button" className="service-back-button" disabled={busy} onClick={() => cancel(item)}>신청 취소</button>}</div>
        </li>)}</ul>}
      {message && <p className="notice" role="status">{message}</p>}
      <nav className="service-pagination" aria-label="내 신청 페이지">
        <button type="button" disabled={busy || requestPage === 1} onClick={() => loadRequests(requestPage - 1).catch((caught) => setError(caught.message))}>이전</button>
        <span>{requestPage} / {Math.max(1, Math.ceil(requestCount / 20))}</span>
        <button type="button" disabled={busy || requestPage * 20 >= requestCount} onClick={() => loadRequests(requestPage + 1).catch((caught) => setError(caught.message))}>다음</button>
      </nav>
    </section>}
  </div>;
}
