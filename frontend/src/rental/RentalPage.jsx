import React, { useEffect, useRef, useState } from 'react';
import '../inquiry/inquiry.css';
import ServiceDialog from '../components/ServiceDialog';

const labels = { pending: '승인 대기', approved: '승인', rejected: '거절', loaned: '대여 중', returned: '반납 완료', cancelled: '취소' };
const actions = { approved: '승인', rejected: '거절', loaned: '대여 시작', returned: '반납 완료' };
const empty = (key) => ({ [key]: [], page: 1, count: 0, has_next: false });
async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) throw new Error(data?.detail || '대여를 처리하지 못했습니다.');
  return data;
}
function Paging({ value, busy, onPage, label }) {
  return <nav className="service-pagination" aria-label={label}>
    <button type="button" disabled={busy || value.page === 1} onClick={() => onPage(value.page - 1)}>이전</button>
    <span>{value.page} / {Math.max(1, Math.ceil(value.count / 20))}</span>
    <button type="button" disabled={busy || !value.has_next} onClick={() => onPage(value.page + 1)}>다음</button>
  </nav>;
}

export default function RentalPage({ uploadId, config, admin = false }) {
  const [stocks, setStocks] = useState(empty('stocks'));
  const [rentals, setRentals] = useState(empty('rentals'));
  const [rows, setRows] = useState({ rows: [], page: 1, row_count: 0 });
  const [inventory, setInventory] = useState({ row_id: '', total: '1' });
  const [stockEditor, setStockEditor] = useState(null);
  const [creating, setCreating] = useState(false);
  const [requestForm, setRequestForm] = useState(null);
  const [rentalEditor, setRentalEditor] = useState(null);
  const [csrf, setCsrf] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const working = useRef(false);
  const base = `/api/uploads/${uploadId}/`;
  const stockUrl = (page) => `${base}rental-stocks/?page=${page}${admin ? '' : '&available=1'}`;
  const rentalUrl = (page) => `${base}rentals/?page=${page}${admin ? '' : '&mine=1'}`;

  useEffect(() => {
    let active = true;
    Promise.all([api('/api/session/'), api(stockUrl(1)), api(rentalUrl(1)),
      admin ? api(`${base}managed-rows/?page=1`) : Promise.resolve(null)])
      .then(([session, items, requests, candidates]) => {
        if (!active) return;
        setCsrf(session.csrf_token); setStocks(items); setRentals(requests); if (candidates) setRows(candidates);
      }).catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId, admin]);

  async function refresh() {
    const [items, requests] = await Promise.all([api(stockUrl(1)), api(rentalUrl(1))]);
    setStocks(items); setRentals(requests);
  }
  async function mutate(path, method, body, success) {
    if (working.current || !csrf) return;
    working.current = true; setBusy(true); setError(''); setMessage('');
    let saved = false;
    try {
      await api(`${base}${path}`, { method,
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify(body) });
      saved = true; setMessage(success); setStockEditor(null); setRentalEditor(null); setRequestForm(null);
      if (path === 'rental-stocks/') { setInventory({ row_id: '', total: '1' }); setCreating(false); }
      await refresh();
    } catch (caught) { setError(saved ? '저장됐지만 목록을 불러오지 못했습니다. 새로고침해 주세요.' : caught.message); }
    finally { working.current = false; setBusy(false); }
  }
  function loadStocks(page) { api(stockUrl(page)).then(setStocks).catch((caught) => setError(caught.message)); }
  function loadRentals(page) { api(rentalUrl(page)).then(setRentals).catch((caught) => setError(caught.message)); }
  function loadRows(page) { api(`${base}managed-rows/?page=${page}`).then(setRows).catch((caught) => setError(caught.message)); }

  return <div className="inquiry-page template-workspace">
    <div className="workspace-heading"><h2>{config[admin ? 'admin' : 'user'].title || (admin ? '대여·반납 관리' : '대여 신청')}</h2>
      {admin && <button type="button" data-intent="primary" disabled={busy} onClick={() => { setError(''); setCreating(true); }}>대여 항목 등록</button>}</div>
    {error && <p className="error" role="alert">{error}</p>}
    {admin && creating && <ServiceDialog title="대여 항목 등록" busy={busy} error={error} onClose={() => setCreating(false)}>
      <form onSubmit={(event) => { event.preventDefault(); mutate('rental-stocks/', 'POST',
        { row_id: inventory.row_id, total: Number(inventory.total) }, '재고를 등록했습니다.'); }}>
        <fieldset disabled={busy} className="inquiry-form">
          <label>항목<select required value={inventory.row_id} onChange={(event) => setInventory({ ...inventory, row_id: event.target.value })}>
            <option value="">선택해 주세요</option>
            {inventory.row_id && !rows.rows.some((row) => row.id === inventory.row_id) && <option value={inventory.row_id}>선택한 항목</option>}
            {rows.rows.map((row) => <option key={row.id} value={row.id}>{row.values[config.user.subjectColumn - 1] || `항목 ${row.row_number}`}</option>)}
          </select></label>
          <nav className="service-pagination" aria-label="대여 항목 페이지">
            <button type="button" disabled={rows.page === 1} onClick={() => loadRows(rows.page - 1)}>이전</button>
            <span>{rows.page} / {Math.max(1, Math.ceil(rows.row_count / 20))}</span>
            <button type="button" disabled={rows.page * 20 >= rows.row_count} onClick={() => loadRows(rows.page + 1)}>다음</button>
          </nav>
          <label>총 재고<input required type="number" min="0" max="10000" step="1" value={inventory.total} onChange={(event) => setInventory({ ...inventory, total: event.target.value })} /></label>
          <button type="submit" disabled={!csrf}>등록</button>
        </fieldset>
      </form>
    </ServiceDialog>}
    <section className="panel workspace-main"><div className="section-title"><h3>{admin ? '재고' : '대여 항목'}</h3>
      <button type="button" disabled={busy} className="service-back-button" onClick={() => refresh().catch((caught) => setError(caught.message))}>새로고침</button></div>
      {!admin && <p className="muted">신청 후 관리자 승인 시 수량이 확보됩니다.</p>}
      {!stocks.stocks.length && <p className="muted">{admin ? '대여 항목을 등록해 주세요.' : '대여 가능한 항목이 없습니다.'}</p>}
      <div className="inquiry-list compact-item-grid">{stocks.stocks.map((stock) => <article className="inquiry-item" key={stock.id}>
        <strong>{stock.subject}</strong><p>가능 {stock.available} / 총 {stock.total}{admin && ` · 확보·대여 중 ${stock.held}`}</p>
        {admin && (!stock.active || !stock.row_id) && <p className="muted">{!stock.row_id ? '원본 항목 삭제됨' : '접수 중지'}</p>}
        {admin ? <button type="button" disabled={busy} onClick={() => setStockEditor({ ...stock, total: String(stock.total) })}>재고·접수 변경</button>
          : <button type="button" data-intent="primary" disabled={busy || !stock.available || rentals.rentals.some((item) => item.stock_id === stock.id && ['pending', 'approved', 'loaned'].includes(item.status))}
              onClick={() => setRequestForm({ stock_id: stock.id, subject: stock.subject, available: stock.available, quantity: '1', content: '' })}>대여 신청</button>}
      </article>)}</div>
      <Paging value={stocks} busy={busy} label="재고 페이지" onPage={loadStocks} />
    </section>
    {stockEditor && <ServiceDialog title={stockEditor.subject} busy={busy} error={error} onClose={() => setStockEditor(null)}>
      <form onSubmit={(event) => { event.preventDefault(); mutate(`rental-stocks/${stockEditor.id}/`, 'PATCH',
        { total: Number(stockEditor.total), active: stockEditor.active }, '재고를 저장했습니다.'); }}>
        <fieldset disabled={busy} className="inquiry-form">
          <label>총 재고<input required type="number" min={stockEditor.held} max="10000" step="1" value={stockEditor.total} onChange={(event) => setStockEditor({ ...stockEditor, total: event.target.value })} /></label>
          <label>접수 상태<select value={stockEditor.active ? 'active' : 'closed'} onChange={(event) => setStockEditor({ ...stockEditor, active: event.target.value === 'active' })}>
            <option value="active">접수 중</option><option value="closed">접수 중지</option></select></label>
          <button type="submit" disabled={!csrf}>저장</button><button type="button" onClick={() => setStockEditor(null)}>닫기</button>
        </fieldset>
      </form>
    </ServiceDialog>}
    {!admin && requestForm && <ServiceDialog title={requestForm.subject} busy={busy} error={error} onClose={() => setRequestForm(null)}>
      <form onSubmit={(event) => { event.preventDefault(); mutate('rentals/', 'POST',
        { stock_id: requestForm.stock_id, quantity: Number(requestForm.quantity), content: requestForm.content }, '대여 신청을 접수했습니다.'); }}>
        <fieldset disabled={busy} className="inquiry-form">
          <label>수량<input required type="number" min="1" max={requestForm.available} step="1" value={requestForm.quantity} onChange={(event) => setRequestForm({ ...requestForm, quantity: event.target.value })} /></label>
          <label>신청 내용 (선택)<textarea maxLength={2000} value={requestForm.content} onChange={(event) => setRequestForm({ ...requestForm, content: event.target.value })} /></label>
          <button type="submit" disabled={!csrf}>신청</button><button type="button" onClick={() => setRequestForm(null)}>닫기</button>
        </fieldset>
      </form>
    </ServiceDialog>}
    <section className="panel workspace-side"><h3>{admin ? '대여 내역' : '내 대여 신청'}</h3>
      {!rentals.rentals.length && <p className="muted">대여 내역이 없습니다.</p>}
      <div className="inquiry-list">{rentals.rentals.map((item) => <details className="inquiry-item" key={item.id}>
        <summary><strong>{item.subject} · {item.quantity}개</strong><span className="service-badge">{labels[item.status]}</span></summary>
        {item.content && <p className="inquiry-text">{item.content}</p>}
        {item.processing_note && <p className="inquiry-text">{item.processing_note}</p>}
        {admin && item.admin_actions.length > 0 && <button type="button" disabled={busy} onClick={() => setRentalEditor({
          id: item.id, subject: item.subject, status: item.admin_actions[0], actions: item.admin_actions, processing_note: item.processing_note,
        })}>처리</button>}
        {!admin && item.can_cancel && <button type="button" disabled={busy || !csrf}
          onClick={() => mutate(`rentals/${item.id}/`, 'PATCH', { status: 'cancelled' }, '신청을 취소했습니다.')}>취소</button>}
      </details>)}</div>
      {message && <p className="notice" role="status">{message}</p>}
      <Paging value={rentals} busy={busy} label="대여 내역 페이지" onPage={loadRentals} />
    </section>
    {admin && rentalEditor && <ServiceDialog title={rentalEditor.subject} busy={busy} error={error} onClose={() => setRentalEditor(null)}>
      <form onSubmit={(event) => { event.preventDefault(); mutate(`rentals/${rentalEditor.id}/`, 'PATCH',
        { status: rentalEditor.status, processing_note: rentalEditor.processing_note }, '처리했습니다.'); }}>
        <fieldset disabled={busy} className="inquiry-form">
          <label>처리<select value={rentalEditor.status} onChange={(event) => setRentalEditor({ ...rentalEditor, status: event.target.value })}>
            {rentalEditor.actions.map((action) => <option key={action} value={action}>{actions[action]}</option>)}
          </select></label>
          <label>처리 메모 (선택)<textarea maxLength={2000} value={rentalEditor.processing_note} onChange={(event) => setRentalEditor({ ...rentalEditor, processing_note: event.target.value })} /></label>
          <button type="submit" disabled={!csrf}>처리</button><button type="button" onClick={() => setRentalEditor(null)}>닫기</button>
        </fieldset>
      </form>
    </ServiceDialog>}
  </div>;
}
