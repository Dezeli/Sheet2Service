import React, { useEffect, useState } from 'react';
import './user.css';

const statusLabels = { pending: '검토 대기', approved: '승인', rejected: '거절', submitted: '접수 완료' };

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
  const [csrf, setCsrf] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const user = config.user;
  const titleIndex = user.subjectColumn - 1;

  async function loadRows(nextPage) {
    const result = await api(`/api/uploads/${uploadId}/managed-rows/?page=${nextPage}`);
    setRows(result.rows); setPage(result.page); setRowCount(result.row_count);
  }

  async function loadRequests() {
    const result = await api(`/api/uploads/${uploadId}/service-requests/?mine=1`);
    setRequests(result.requests);
  }

  useEffect(() => {
    Promise.all([loadRows(1), loadRequests(), api('/api/session/').then((result) => setCsrf(result.csrf_token))])
      .catch((caught) => setError(caught.message));
  }, [uploadId]);

  async function submit(row) {
    if (busy || !csrf || user.template === 'browse_only') return;
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await api(`/api/uploads/${uploadId}/service-requests/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ row_id: row.id }),
      });
      setMessage(`${result.subject}: ${statusLabels[result.status]} 상태로 신청했습니다.`);
      await loadRequests();
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  return <div className="user-page">
    <section className="user-intro">
      <p className="eyebrow">USER PREVIEW</p><h2>서비스 이용</h2>
      <p>목록에서 원하는 항목을 선택해 주세요.</p>
      {user.steps?.length > 0 && <ol>{user.steps.map((step, index) => <li key={index}>{step}</li>)}</ol>}
    </section>
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p className="notice" role="status">{message}</p>}
    <section className="panel"><div className="section-title"><h2>이용 가능한 항목</h2><span className="muted">{rowCount.toLocaleString()}개</span></div>
      <div className="user-item-grid">{rows.map((row) => <article key={row.id} className="user-item">
        <small>항목 {row.row_number}</small><h3>{row.values[titleIndex] || `항목 ${row.row_number}`}</h3>
        <dl>{report.columns.slice(0, 6).map((column, index) => index === titleIndex || !row.values[index] ? null :
          <div key={column.id}><dt>{column.label}</dt><dd>{row.values[index]}</dd></div>)}</dl>
        {user.template !== 'browse_only' && <button type="button" disabled={busy || !csrf}
          onClick={() => submit(row)}>{user.template === 'request_review' ? '신청하기' : '접수하기'}</button>}
      </article>)}</div>
      <nav className="service-pagination" aria-label="항목 페이지">
        <button type="button" disabled={busy || page === 1} onClick={() => loadRows(page - 1).catch((caught) => setError(caught.message))}>이전</button>
        <span>{page} / {Math.max(1, Math.ceil(rowCount / 20))}</span>
        <button type="button" disabled={busy || page * 20 >= rowCount} onClick={() => loadRows(page + 1).catch((caught) => setError(caught.message))}>다음</button>
      </nav>
    </section>
    {user.template !== 'browse_only' && <section className="panel"><h2>내 신청 현황</h2>
      {!requests.length ? <p className="muted">아직 신청한 항목이 없습니다.</p> :
        <ul className="user-request-list">{requests.map((item) => <li key={item.id}>
          <strong>{item.subject}</strong><span>{statusLabels[item.status]}</span>
        </li>)}</ul>}
    </section>}
  </div>;
}
