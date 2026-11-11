import React, { useEffect, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import { api, jsonOptions, query, statusLabels, statusTone, whenText } from './api.js';
import { formatPhoneInput, phoneDigits, rememberBooker, rememberedBooker } from './rules.js';
import { Empty, IconButton, Pager } from '../components/ui';
import { ItemLink } from './nav';

/** Bookings made in this browser, or found by the name and phone number entered when booking. */
export default function MyBookings({ uploadId, service, persona, csrf, refreshKey = 0 }) {
  const unit = service?.booking?.unit || 'day';
  const [list, setList] = useState({ bookings: [], page: 1, count: 0, has_next: false });
  const [draft, setDraft] = useState(rememberedBooker);
  const [lookup, setLookup] = useState(null); // { name, phone } once a lookup succeeds
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function load(page = 1, who = lookup) {
    try { setList(await api(`/api/uploads/${uploadId}/bookings/${query({ persona: persona.id, page, ...(who || {}) })}`)); setError(''); }
    catch (caught) { setError(caught.message); }
  }
  useEffect(() => { load(1); }, [uploadId, persona.id, refreshKey]);

  function find(event) {
    event.preventDefault();
    const who = { name: draft.name.trim(), phone: phoneDigits(draft.phone) };
    if (!who.name || !who.phone) { setError('예약할 때 입력한 이름과 전화번호를 입력해 주세요.'); return; }
    rememberBooker(who.name, formatPhoneInput(who.phone));
    setLookup(who); setMessage(''); load(1, who);
  }
  function clear() { setLookup(null); setDraft({ name: '', phone: '' }); setMessage(''); load(1, null); }

  async function cancel(item) {
    if (busy || !csrf || !window.confirm('이 예약을 취소할까요?')) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await api(`/api/uploads/${uploadId}/bookings/${item.id}/`, jsonOptions('PATCH', csrf, { persona: persona.id, action: 'cancel', ...(lookup || {}) }));
      setMessage('예약을 취소했습니다.'); await load(list.page);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  return <section className="panel">
    <div className="section-title"><h2 className="icon-heading"><SectionIcon name="reservation" />내 예약</h2>
      <IconButton icon="refresh" label="새로고침" disabled={busy} onClick={() => load(list.page)} /></div>
    <form className="my-lookup" onSubmit={find}>
      <input type="text" aria-label="예약자 이름" placeholder="이름" maxLength={200} autoComplete="name" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
      <input type="tel" inputMode="tel" aria-label="전화번호" placeholder="010-1234-5678" maxLength={13} autoComplete="tel" value={draft.phone}
        onChange={(event) => setDraft({ ...draft, phone: formatPhoneInput(event.target.value) })} />
      <button type="submit" disabled={busy || !draft.name.trim() || !phoneDigits(draft.phone)}>조회</button>
      {lookup && <IconButton icon="close" label="조회 지우기" onClick={clear} />}
    </form>
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p className="notice" role="status">{message}</p>}
    {!list.bookings.length && <Empty>{lookup ? '이 이름과 전화번호로 된 예약이 없습니다.' : '예약 내역이 없습니다.'}</Empty>}
    <ul className="booking-list">{list.bookings.map((item) => <li key={item.id} className="booking-card">
      <div className="booking-card-head">
        <strong>{item.resource ? <ItemLink item={item.resource.id} path={item.resource.path} menu="browse" /> : '항목 없음'}</strong>
        <span className={`service-badge tone-${statusTone[item.status]}`}>{statusLabels[item.status]}</span>
      </div>
      <p>{whenText(item, unit) || '일시 미정'}{item.party_size ? ` · ${item.party_size}명` : ''}</p>
      {item.purpose && <p className="muted">{item.purpose}</p>}
      {item.processing_note && <p className="booking-note">{item.processing_note}</p>}
      {['requested', 'approved', 'waiting', 'won'].includes(item.status) &&
        <button type="button" data-intent="danger" disabled={busy || !csrf} onClick={() => cancel(item)}>예약 취소</button>}
    </li>)}</ul>
    <Pager page={list.page} count={list.count} disabled={busy} onPage={(page) => load(page)} />
  </section>;
}
