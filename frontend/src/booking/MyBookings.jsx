import React, { useEffect, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import ServiceDialog from '../components/ServiceDialog';
import { api, formatMoment, jsonOptions, query, statusLabels, statusTone, whenText } from './api.js';
import { formatPhoneInput, phoneDigits } from './rules.js';
import { Empty, Icon, IconButton, Pager, Stepper } from '../components/ui';
import { ItemLink } from './nav';

const OPEN = ['requested', 'approved', 'waiting', 'won'];
const PAGE_SIZE = 10;
const digitsOnly = (text) => text.replace(/\D/g, '').slice(0, 4);
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];
/** The day a booking starts, for the date tile at the start of its row. */
function startDay(item) {
  const raw = item.date || item.starts_at;
  if (!raw) return null;
  const d = new Date(raw.length === 10 ? `${raw}T00:00:00` : raw);
  return Number.isNaN(d.getTime()) ? null : { month: d.getMonth() + 1, day: d.getDate(), weekday: WEEKDAYS[d.getDay()], year: d.getFullYear() };
}
const todayIso = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };

/**
 * 비회원 예약 조회. The list shows bookings half hidden (홍*동 · 010-5***-1231): the ones made in this browser,
 * or the ones found by name and phone. The PIN chosen when booking opens one: its details, changes and cancelling.
 */
export default function MyBookings({ uploadId, service, persona, csrf, refreshKey = 0 }) {
  const unit = service?.booking?.unit || 'day';
  const [list, setList] = useState({ bookings: [], page: 1, count: 0, has_next: false });
  const [draft, setDraft] = useState('');
  const [searched, setSearched] = useState(null); // { name, phone } while showing bookings found by them
  const [asking, setAsking] = useState(null); // the booking whose PIN is being asked
  const [pin, setPin] = useState('');
  const [detail, setDetail] = useState(null);
  const [editing, setEditing] = useState(null); // { party, purpose }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [dialogError, setDialogError] = useState('');
  const [message, setMessage] = useState('');

  async function load(page = 1, who = searched) {
    try { setList(await api(`/api/uploads/${uploadId}/bookings/${query({ persona: persona.id, page, size: PAGE_SIZE, ...(who || {}) })}`)); setError(''); }
    catch (caught) { setError(caught.message); }
  }
  useEffect(() => { load(1); }, [uploadId, persona.id, refreshKey]);

  function find(event) {
    event.preventDefault();
    // digits are a phone number, anything else a name
    const text = draft.trim();
    if (!text) return;
    const who = /^[\d\s-]+$/.test(text) ? { phone: phoneDigits(text) || text } : { name: text };
    setSearched(who); setMessage(''); load(1, who);
  }
  function clearSearch() { setSearched(null); setMessage(''); load(1, null); }

  async function open(item) {
    setDialogError(''); setMessage('');
    if (item.locked) { setPin(''); setAsking(item); return; }
    try { setDetail(await api(`/api/uploads/${uploadId}/bookings/${item.id}/${query({ persona: persona.id })}`)); }
    catch (caught) { setPin(''); setAsking(item); }
  }
  async function unlock(event) {
    event.preventDefault();
    if (busy || !csrf || pin.length !== 4) return;
    setBusy(true); setDialogError('');
    try {
      const opened = await api(`/api/uploads/${uploadId}/bookings/${asking.id}/unlock/`, jsonOptions('POST', csrf, { password: pin }));
      setAsking(null); setDetail(opened); load(list.page);
    } catch (caught) { setDialogError(caught.message); setPin(''); }
    finally { setBusy(false); }
  }
  async function change(body, text) {
    if (busy || !csrf) return;
    setBusy(true); setDialogError('');
    try {
      const updated = await api(`/api/uploads/${uploadId}/bookings/${detail.id}/`, jsonOptions('PATCH', csrf, { persona: persona.id, ...body }));
      setDetail(updated); setEditing(null); setMessage(text); load(list.page);
    } catch (caught) { setDialogError(caught.message); }
    finally { setBusy(false); }
  }
  const cancel = () => window.confirm('이 예약을 취소할까요?') && change({ action: 'cancel' }, '예약을 취소했습니다.');
  const save = (event) => {
    event.preventDefault();
    const body = { action: 'edit' };
    if (editing.party !== (detail.party_size || 1)) body.party_size = editing.party;
    if (editing.purpose !== (detail.purpose || '')) body.purpose = editing.purpose;
    change(body, '예약을 수정했습니다.');
  };
  const changeable = detail && OPEN.includes(detail.status) && !(detail.date && detail.date < todayIso());

  const thisYear = new Date().getFullYear();
  return <section className="panel my-page">
    <div className="my-head">
      <div><h2 className="icon-heading"><SectionIcon name="reservation" />내 예약</h2>
        <p className="my-head__sub">{searched ? `"${searched.name || formatPhoneInput(searched.phone)}"(으)로 찾은 예약 ${list.count.toLocaleString()}건` : `이 브라우저에서 한 예약 ${list.count.toLocaleString()}건`}</p></div>
      <form className="my-find" onSubmit={find} title="다른 기기에서 한 예약은 예약할 때 입력한 이름 또는 전화번호로 찾습니다.">
        <span className="my-find__field"><Icon name="search" size={18} />
          <input type="search" aria-label="이름 또는 전화번호" placeholder="다른 기기에서 한 예약 찾기 · 이름 또는 전화번호" maxLength={200} autoComplete="off" value={draft}
            onChange={(event) => { const value = event.target.value; setDraft(/^[\d\s-]+$/.test(value) ? formatPhoneInput(value) : value); }} /></span>
        <button type="submit" data-intent="primary" disabled={busy || !draft.trim()}>찾기</button>
        {searched ? <IconButton icon="close" label="찾기 지우기" onClick={() => { setDraft(''); clearSearch(); }} />
          : <IconButton icon="refresh" label="새로고침" disabled={busy} onClick={() => load(list.page)} />}
      </form>
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p className="notice" role="status">{message}</p>}
    {!list.bookings.length && <Empty>{searched ? (searched.phone ? '이 전화번호로 된 예약이 없습니다.' : '이 이름으로 된 예약이 없습니다.') : '이 브라우저에서 한 예약이 없습니다. 다른 기기에서 했다면 위에서 찾아보세요.'}</Empty>}
    <ul className="my-bookings">{list.bookings.map((item) => {
      const day = startDay(item);
      const done = !OPEN.includes(item.status) || (item.date && item.date < todayIso());
      return <li key={item.id} className={`tone-${statusTone[item.status]}${done ? ' is-done' : ''}`}>
        <span className="my-date" aria-hidden="true">{day ? <>
          <small>{day.year !== thisYear ? `${day.year}. ` : ''}{day.month}월</small><b>{day.day}</b><small>{day.weekday}</small></> : <small>미정</small>}</span>
        <div className="my-bookings__main">
          <strong>{item.resource ? <ItemLink item={item.resource.id} path={item.resource.path} menu="browse" /> : '항목 없음'}</strong>
          <span className="my-bookings__when">{whenText(item, unit) || '일시 미정'}{item.party_size ? ` · ${item.party_size}명` : ''}</span>
          <span className="my-bookings__who">{item.locked && <Icon name="lock" size={13} />}{item.booker}{item.phone ? ` · ${item.phone}` : ''}</span>
        </div>
        <span className={`service-badge tone-${statusTone[item.status]}`}>{statusLabels[item.status]}</span>
        <button type="button" className="my-open" onClick={() => open(item)}>상세보기<Icon name="next" size={16} /></button>
      </li>;
    })}</ul>
    <Pager page={list.page} count={list.count} size={PAGE_SIZE} disabled={busy} onPage={(page) => load(page)} />

    {asking && <ServiceDialog title="예약 비밀번호" busy={busy} error={dialogError} onClose={() => setAsking(null)} className="pin-dialog">
      <form onSubmit={unlock} className="pin-form">
        <p className="muted">{asking.resource?.name} · {whenText(asking, unit)}</p>
        <label>예약할 때 정한 숫자 4자리<input type="password" inputMode="numeric" autoFocus maxLength={4} autoComplete="off" value={pin}
          onChange={(event) => setPin(digitsOnly(event.target.value))} /></label>
        <button type="submit" data-intent="primary" disabled={busy || !csrf || pin.length !== 4}>{busy ? '확인 중…' : '확인'}</button>
      </form>
    </ServiceDialog>}

    {detail && <ServiceDialog title="예약 상세" busy={busy} error={dialogError} onClose={() => { setDetail(null); setEditing(null); }}>
      <dl className="resource-attributes">
        <div><dt>항목</dt><dd>{detail.resource ? detail.resource.path.split(' / ').join(' › ') : '-'}</dd></div>
        <div><dt>일시</dt><dd>{whenText(detail, unit) || '-'}</dd></div>
        <div><dt>상태</dt><dd><span className={`service-badge tone-${statusTone[detail.status]}`}>{statusLabels[detail.status]}</span></dd></div>
        <div><dt>예약자</dt><dd>{detail.booker || '-'}{detail.phone ? ` · ${detail.phone}` : ''}</dd></div>
        {!editing && <div><dt>인원</dt><dd>{detail.party_size || 1}명</dd></div>}
        {!editing && <div><dt>요청 사항</dt><dd>{detail.purpose || '-'}</dd></div>}
        {detail.processing_note && <div><dt>처리 메모</dt><dd>{detail.processing_note}</dd></div>}
        {detail.requested_at && <div><dt>신청 일시</dt><dd>{formatMoment(detail.requested_at)}</dd></div>}
      </dl>
      {editing && <form className="my-edit" onSubmit={save}>
        <div className="reserve-inline"><span className="field-label">인원</span>
          <Stepper label="인원" value={editing.party} min={1} max={100} unit="명" onChange={(party) => setEditing({ ...editing, party })} /></div>
        <label>요청 사항<textarea rows={3} maxLength={2000} value={editing.purpose} onChange={(event) => setEditing({ ...editing, purpose: event.target.value })} /></label>
        <p className="muted">날짜를 바꾸려면 이 예약을 취소하고 다시 예약해 주세요.</p>
        <div className="dialog-actions">
          <button type="button" className="text-button" disabled={busy} onClick={() => setEditing(null)}>그만두기</button>
          <button type="submit" data-intent="primary" disabled={busy || !csrf}>{busy ? '저장 중…' : '저장'}</button>
        </div>
      </form>}
      {!editing && changeable && <div className="dialog-actions dialog-actions-split">
        <button type="button" data-intent="danger" disabled={busy || !csrf} onClick={cancel}>예약 취소</button>
        <button type="button" data-intent="info" disabled={busy} onClick={() => setEditing({ party: detail.party_size || 1, purpose: detail.purpose || '' })}>수정</button>
      </div>}
    </ServiceDialog>}
  </section>;
}
