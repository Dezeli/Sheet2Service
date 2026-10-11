import React, { useEffect, useRef, useState } from 'react';
import '../inquiry/inquiry.css';
import ServiceDialog from '../components/ServiceDialog';

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) throw new Error(data?.detail || '예약을 처리하지 못했습니다.');
  return data;
}
const date = (value) => new Date(value).toLocaleString('ko-KR');
const empty = (key) => ({ [key]: [], page: 1, count: 0, has_next: false });

function Paging({ value, busy, onPage, label }) {
  return <nav className="service-pagination" aria-label={label}>
    <button type="button" disabled={busy || value.page === 1} onClick={() => onPage(value.page - 1)}>이전</button>
    <span>{value.page} / {Math.max(1, Math.ceil(value.count / 20))}</span>
    <button type="button" disabled={busy || !value.has_next} onClick={() => onPage(value.page + 1)}>다음</button>
  </nav>;
}

export default function ReservationPage({ uploadId, config, admin = false }) {
  const [slots, setSlots] = useState(empty('slots'));
  const [bookings, setBookings] = useState(empty('reservations'));
  const [rows, setRows] = useState({ rows: [], page: 1, row_count: 0 });
  const [form, setForm] = useState({ row_id: '', starts_at: '', ends_at: '', capacity: '1' });
  const [editor, setEditor] = useState(null);
  const [creating, setCreating] = useState(false);
  const [csrf, setCsrf] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const working = useRef(false);
  const base = `/api/uploads/${uploadId}/`;
  const slotUrl = (page) => `${base}reservation-slots/?page=${page}${admin ? '' : '&available=1'}`;
  const bookingUrl = (page) => `${base}reservations/?page=${page}${admin ? '' : '&mine=1'}`;

  useEffect(() => {
    let active = true;
    Promise.all([api('/api/session/'), api(slotUrl(1)), api(bookingUrl(1)),
      admin ? api(`${base}managed-rows/?page=1`) : Promise.resolve(null)])
      .then(([session, times, list, items]) => {
        if (!active) return;
        setCsrf(session.csrf_token); setSlots(times); setBookings(list); if (items) setRows(items);
      }).catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId, admin]);

  async function refresh() {
    const [times, list] = await Promise.all([api(slotUrl(1)), api(bookingUrl(1))]);
    setSlots(times); setBookings(list);
  }
  async function mutate(path, method, body, success) {
    if (working.current || !csrf) return;
    working.current = true; setBusy(true); setError(''); setMessage('');
    let saved = false;
    try {
      await api(`${base}${path}`, { method,
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify(body) });
      saved = true; setMessage(success); setEditor(null);
      if (path === 'reservation-slots/') { setForm({ row_id: '', starts_at: '', ends_at: '', capacity: '1' }); setCreating(false); }
      await refresh();
    } catch (caught) {
      setError(saved ? '저장됐지만 목록을 불러오지 못했습니다. 새로고침해 주세요.' : caught.message);
    } finally { working.current = false; setBusy(false); }
  }
  function create(event) {
    event.preventDefault();
    mutate('reservation-slots/', 'POST', { ...form, capacity: Number(form.capacity),
      starts_at: new Date(form.starts_at).toISOString(), ends_at: new Date(form.ends_at).toISOString() }, '예약 시간을 만들었습니다.');
  }
  function loadSlots(page) { api(slotUrl(page)).then(setSlots).catch((caught) => setError(caught.message)); }
  function loadBookings(page) { api(bookingUrl(page)).then(setBookings).catch((caught) => setError(caught.message)); }

  return <div className="inquiry-page template-workspace">
    <div className="workspace-heading"><h2>{config[admin ? 'admin' : 'user'].title || (admin ? '예약 일정·정원 관리' : '시간 예약')}</h2>
      {admin && <button type="button" data-intent="primary" disabled={busy} onClick={() => { setError(''); setCreating(true); }}>예약 시간 추가</button>}</div>
    {error && <p className="error" role="alert">{error}</p>}
    {admin && creating && <ServiceDialog title="예약 시간 추가" busy={busy} error={error} onClose={() => setCreating(false)}>
      <form onSubmit={create}><fieldset className="inquiry-form" disabled={busy}>
        <label>항목<select required value={form.row_id} onChange={(event) => setForm({ ...form, row_id: event.target.value })}>
          <option value="">선택해 주세요</option>
          {form.row_id && !rows.rows.some((row) => row.id === form.row_id) && <option value={form.row_id}>선택한 항목</option>}
          {rows.rows.map((row) => <option key={row.id} value={row.id}>{row.values[config.user.subjectColumn - 1] || `항목 ${row.row_number}`}</option>)}
        </select></label>
        <nav className="service-pagination" aria-label="항목 페이지">
          <button type="button" disabled={rows.page === 1} onClick={() => api(`${base}managed-rows/?page=${rows.page - 1}`).then(setRows).catch((caught) => setError(caught.message))}>이전</button>
          <span>{rows.page} / {Math.max(1, Math.ceil(rows.row_count / 20))}</span>
          <button type="button" disabled={rows.page * 20 >= rows.row_count} onClick={() => api(`${base}managed-rows/?page=${rows.page + 1}`).then(setRows).catch((caught) => setError(caught.message))}>다음</button>
        </nav>
        <label>시작 (현재 시간대)<input required type="datetime-local" value={form.starts_at} onChange={(event) => setForm({ ...form, starts_at: event.target.value })} /></label>
        <label>종료 (현재 시간대)<input required type="datetime-local" value={form.ends_at} onChange={(event) => setForm({ ...form, ends_at: event.target.value })} /></label>
        <label>정원<input required type="number" min="1" max="10000" step="1" value={form.capacity} onChange={(event) => setForm({ ...form, capacity: event.target.value })} /></label>
        <button type="submit" disabled={!csrf}>추가</button>
      </fieldset></form>
    </ServiceDialog>}
    <section className="panel workspace-main"><div className="section-title"><h3>{admin ? '예약 일정' : '예약 가능한 시간'}</h3>
      <button type="button" disabled={busy} className="service-back-button" onClick={() => refresh().catch((caught) => setError(caught.message))}>새로고침</button></div>
      {!slots.slots.length && <p className="muted">{admin ? '예약 시간을 추가해 주세요.' : '예약 가능한 시간이 없습니다.'}</p>}
      <div className="inquiry-list compact-item-grid">{slots.slots.map((slot) => <article className="inquiry-item" key={slot.id}>
        <strong>{slot.subject}</strong><p>{date(slot.starts_at)} ~ {date(slot.ends_at)}</p>
        <p>{slot.closed ? '접수 마감' : `잔여 ${slot.remaining} / 정원 ${slot.capacity}`}</p>
        {admin ? <button type="button" disabled={busy} onClick={() => setEditor({ ...slot, capacity: String(slot.capacity) })}>정원·마감 변경</button>
          : <button type="button" data-intent="primary" disabled={busy || !csrf || !slot.remaining || new Date(slot.starts_at) <= new Date()
              || bookings.reservations.some((item) => item.slot.id === slot.id && !item.cancelled)}
              onClick={() => mutate('reservations/', 'POST', { slot_id: slot.id }, '예약했습니다.')}>예약</button>}
      </article>)}</div>
      <Paging value={slots} busy={busy} label="예약 시간 페이지" onPage={loadSlots} />
    </section>
    {editor && <ServiceDialog title={editor.subject} busy={busy} error={error} onClose={() => setEditor(null)}>
      <form onSubmit={(event) => { event.preventDefault(); mutate(`reservation-slots/${editor.id}/`, 'PATCH',
        { capacity: Number(editor.capacity), closed: editor.closed }, '저장했습니다.'); }}>
        <fieldset disabled={busy} className="inquiry-form">
          <label>정원<input required type="number" min={Math.max(1, editor.booked)} max="10000" step="1" value={editor.capacity} onChange={(event) => setEditor({ ...editor, capacity: event.target.value })} /></label>
          <label>접수 상태<select value={editor.closed ? 'closed' : 'open'} onChange={(event) => setEditor({ ...editor, closed: event.target.value === 'closed' })}>
            <option value="open">접수 중</option><option value="closed">접수 마감</option></select></label>
          <button type="submit" disabled={!csrf}>저장</button><button type="button" onClick={() => setEditor(null)}>닫기</button>
        </fieldset>
      </form>
    </ServiceDialog>}
    <section className="panel workspace-side"><h3>{admin ? '예약 내역' : '내 예약'}</h3>
      {!bookings.reservations.length && <p className="muted">예약 내역이 없습니다.</p>}
      <div className="inquiry-list">{bookings.reservations.map((item) => <article className="inquiry-item" key={item.id}>
        <strong>{item.slot.subject}</strong><p>{date(item.slot.starts_at)} ~ {date(item.slot.ends_at)}</p>
        <p>{item.cancelled ? '취소됨' : '예약 확정'}</p>
        {!admin && !item.cancelled && new Date(item.slot.starts_at) > new Date() && <button type="button" disabled={busy || !csrf}
          onClick={() => mutate(`reservations/${item.id}/`, 'PATCH', { cancelled: true }, '예약을 취소했습니다.')}>예약 취소</button>}
      </article>)}</div>
      {message && <p className="notice" role="status">{message}</p>}
      <Paging value={bookings} busy={busy} label="예약 내역 페이지" onPage={loadBookings} />
    </section>
  </div>;
}
