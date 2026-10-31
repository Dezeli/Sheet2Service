import React, { useEffect, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import { api, jsonOptions, query, statusLabels, statusTone, whenText } from './api.js';

export default function MyBookings({ uploadId, persona, csrf, refreshKey = 0 }) {
  const [list, setList] = useState({ bookings: [], page: 1, count: 0, has_next: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function load(page = 1) {
    try { setList(await api(`/api/uploads/${uploadId}/bookings/${query({ persona: persona.id, page })}`)); setError(''); }
    catch (caught) { setError(caught.message); }
  }
  useEffect(() => { load(1); }, [uploadId, persona.id, refreshKey]);

  async function cancel(item) {
    if (busy || !csrf) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await api(`/api/uploads/${uploadId}/bookings/${item.id}/`, jsonOptions('PATCH', csrf, { persona: persona.id, action: 'cancel' }));
      setMessage('예약을 취소했습니다.'); await load(list.page);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  return <section className="panel">
    <div className="section-title"><h2 className="icon-heading"><SectionIcon name="reservation" />내 예약</h2>
      <button type="button" className="service-back-button" disabled={busy} onClick={() => load(list.page)}>새로고침</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    {!list.bookings.length && <p className="muted">아직 예약이 없습니다. 항목을 찾아 예약해 보세요.</p>}
    <ul className="booking-list">{list.bookings.map((item) => <li key={item.id} className="booking-card">
      <div className="booking-card-head">
        <strong>{item.resource?.path || '항목 없음'}</strong>
        <span className={`service-badge tone-${statusTone[item.status]}`}>{statusLabels[item.status]}</span>
      </div>
      <p>{whenText(item) || '일시 미정'}{item.party_size ? ` · ${item.party_size}명` : ''}{item.booker ? ` · ${item.booker}` : ''}</p>
      {item.purpose && <p className="muted">{item.purpose}</p>}
      {item.processing_note && <p className="booking-note">처리 메모: {item.processing_note}</p>}
      {['requested', 'approved', 'waiting', 'won'].includes(item.status) &&
        <button type="button" className="admin-danger" disabled={busy || !csrf} onClick={() => cancel(item)}>예약 취소</button>}
    </li>)}</ul>
    {message && <p className="notice" role="status">{message}</p>}
    {list.count > 20 && <nav className="service-pagination" aria-label="내 예약 페이지">
      <button type="button" disabled={busy || list.page === 1} onClick={() => load(list.page - 1)}>이전</button>
      <span>{list.page} / {Math.max(1, Math.ceil(list.count / 20))}</span>
      <button type="button" disabled={busy || !list.has_next} onClick={() => load(list.page + 1)}>다음</button>
    </nav>}
  </section>;
}
