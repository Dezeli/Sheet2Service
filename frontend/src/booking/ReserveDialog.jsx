import React, { useEffect, useMemo, useState } from 'react';
import ServiceDialog from '../components/ServiceDialog';
import { api, jsonOptions, query, whenText } from './api.js';

const iso = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const todayIso = () => iso(new Date());
const monthOf = (text) => text.slice(0, 7);
const addDays = (text, days) => { const d = new Date(`${text}T00:00:00`); d.setDate(d.getDate() + days); return iso(d); };
const daysBetween = (a, b) => Math.round((new Date(`${b}T00:00:00`) - new Date(`${a}T00:00:00`)) / 86400000);
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

/** An always-open month calendar. Single pick, or a range when `range` is set (two taps). */
function Calendar({ uploadId, persona, resource, start, end, range, onChange }) {
  const [month, setMonth] = useState(monthOf(start || todayIso()));
  const [availability, setAvailability] = useState({});
  const today = todayIso();
  useEffect(() => {
    if (!resource) return;
    let active = true;
    api(`/api/uploads/${uploadId}/bookings/availability/${query({ persona: persona.id, resource: resource.id, month })}`)
      .then((data) => { if (active) setAvailability(data.days || {}); })
      .catch(() => { if (active) setAvailability({}); });
    return () => { active = false; };
  }, [uploadId, persona.id, resource, month]);

  const cells = useMemo(() => {
    const [year, mon] = month.split('-').map(Number);
    const first = new Date(year, mon - 1, 1);
    const list = [];
    for (let i = 0; i < first.getDay(); i += 1) list.push(null);
    const count = new Date(year, mon, 0).getDate();
    for (let day = 1; day <= count; day += 1) list.push(iso(new Date(year, mon - 1, day)));
    return list;
  }, [month]);
  const shift = (delta) => {
    const [year, mon] = month.split('-').map(Number);
    const next = new Date(year, mon - 1 + delta, 1);
    setMonth(monthOf(iso(next)));
  };
  const inRange = (day) => range && start && end && day > start && day < end;
  const title = `${month.slice(0, 4)}년 ${Number(month.slice(5))}월`;
  return <div className="calendar" role="group" aria-label="날짜 선택">
    <div className="calendar-head">
      <button type="button" className="service-back-button" onClick={() => shift(-1)} disabled={month <= monthOf(today)} aria-label="이전 달">‹</button>
      <strong>{title}</strong>
      <button type="button" className="service-back-button" onClick={() => shift(1)} aria-label="다음 달">›</button>
    </div>
    <div className="calendar-grid">
      {WEEKDAYS.map((name) => <span key={name} className="calendar-weekday">{name}</span>)}
      {cells.map((day, index) => {
        if (!day) return <span key={`blank-${index}`} />;
        const info = availability[day];
        const past = day < today;
        const full = Boolean(info?.full);
        const selected = day === start || day === end;
        return <button type="button" key={day} disabled={past || (full && !range)}
          className={`calendar-day${selected ? ' is-selected' : ''}${inRange(day) ? ' in-range' : ''}${full ? ' is-full' : ''}${info && !full ? ' has-bookings' : ''}`}
          aria-pressed={selected} onClick={() => onChange(day)}>
          <span>{Number(day.slice(8))}</span>
          {full && <small>마감</small>}
          {info && !full && <small>{info.count}</small>}
        </button>;
      })}
    </div>
  </div>;
}

function Chips({ options, value, onChange, label, allowCustom = false, customLabel = '직접 입력', custom, onCustom }) {
  return <div className="chip-group" role="group" aria-label={label}>
    {options.map((option) => <button type="button" key={option} className={`chip${value === option ? ' is-selected' : ''}`}
      aria-pressed={value === option} onClick={() => onChange(option)}>{option}</button>)}
    {allowCustom && <button type="button" className={`chip${custom ? ' is-selected' : ''}`} aria-pressed={custom} onClick={onCustom}>{customLabel}</button>}
  </div>;
}

/** Reserve one resource. Everything but the name and the note is chosen by pressing, not typing. */
export default function ReserveDialog({ uploadId, service, persona, csrf, resource, slot: presetSlot, onClose, onDone }) {
  const booking = service.booking;
  const unit = booking.unit || 'day';
  const usesSlots = service.sheetKind === 'schedule_slots';
  const [slots, setSlots] = useState(null);
  const [slot, setSlot] = useState(presetSlot || null);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [timeSlot, setTimeSlot] = useState('');
  const [customSlot, setCustomSlot] = useState(false);
  const [startHour, setStartHour] = useState(null);
  const [endHour, setEndHour] = useState(null);
  const [party, setParty] = useState(null);
  const [customParty, setCustomParty] = useState(false);
  const [booker, setBooker] = useState('');
  const [purpose, setPurpose] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!usesSlots || presetSlot || !resource) return;
    let active = true;
    api(`/api/uploads/${uploadId}/slots/${query({ resource: resource.id, available: 1 })}`)
      .then((data) => { if (active) setSlots(data.slots); })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId, resource, usesSlots, presetSlot]);

  const slotOptions = booking.slotOptions || [];
  const partyMax = Math.max(1, Math.min(50, resource?.capacity && unit !== 'stay' ? Math.min(resource.capacity, booking.partySizeMax || 10) : booking.partySizeMax || 10));
  const partyOptions = Array.from({ length: Math.min(partyMax, 12) }, (_, i) => String(i + 1));
  const [hourFrom, hourTo] = booking.hourRange || [8, 22];
  const hours = Array.from({ length: hourTo - hourFrom + 1 }, (_, i) => hourFrom + i);

  function pickDay(day) {
    if (unit === 'stay' || unit === 'period') {
      if (!start || (start && end) || day < start) { setStart(day); setEnd(''); }
      else if (day === start) { if (unit === 'period') setEnd(day); }
      else setEnd(day);
    } else {
      setStart(day); setEnd('');
    }
  }

  const ready = slot ? true
    : unit === 'time_range' ? Boolean(start && startHour !== null && endHour !== null && endHour > startHour)
    : unit === 'stay' ? Boolean(start && end && end > start)
    : unit === 'period' ? Boolean(start && end)
    : unit === 'time_slot' ? Boolean(start && (timeSlot || !slotOptions.length))
    : Boolean(start);
  const needsName = Boolean(booking.bookerColumn);
  const summary = slot ? whenText(slot, unit)
    : unit === 'stay' && start && end ? `${start} 입실 · ${end} 퇴실 (${daysBetween(start, end)}박)`
    : unit === 'period' && start && end ? (start === end ? `${start} (1일)` : `${start} ~ ${end} (${daysBetween(start, end) + 1}일)`)
    : unit === 'time_range' && start ? `${start} ${startHour !== null ? `${startHour}:00` : '--'}~${endHour !== null ? `${endHour}:00` : '--'}`
    : start ? `${start}${timeSlot ? ' ' + timeSlot : ''}` : '';

  async function submit(event) {
    event.preventDefault();
    if (busy || !ready) return;
    setBusy(true); setError('');
    const body = { persona: persona.id, booker, purpose };
    if (party) body.party_size = Number(party);
    if (slot) body.slot_id = slot.id;
    else {
      body.resource_id = resource.id;
      body.date = start;
      if (unit === 'stay' || unit === 'period') body.end_date = end;
      if (timeSlot && unit !== 'time_range') body.time_slot = timeSlot;
      if (unit === 'time_range') {
        body.starts_at = new Date(`${start}T${String(startHour).padStart(2, '0')}:00:00`).toISOString();
        body.ends_at = new Date(`${start}T${String(Math.min(endHour, 23)).padStart(2, '0')}:${endHour === 24 ? '59' : '00'}:00`).toISOString();
      }
    }
    try { onDone(await api(`/api/uploads/${uploadId}/bookings/`, jsonOptions('POST', csrf, body))); }
    catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  const info = resource ? Object.entries(resource.attributes || {}).filter(([key]) => ['기록 기준 금액', '평일금액', '주말금액', '성수기금액', '요금', '금액', '자주 쓰인 시간대', '평균 인원', '평균 이용 기간', '정원', '이용시작시간', '이용종료시간'].includes(key)) : [];
  const title = `${slot?.resource_name || resource?.name || ''} 예약`;
  return <ServiceDialog title={title} busy={busy} error={error} onClose={onClose} className="reserve-dialog">
    <form onSubmit={submit}><fieldset className="reserve-form" disabled={busy}>
      {resource && resource.path !== resource.name && <p className="muted">{resource.path}</p>}
      {(info.length > 0 || resource?.capacity) && <dl className="reserve-info">
        {resource?.capacity && <div><dt>정원</dt><dd>{resource.capacity}</dd></div>}
        {info.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}
      </dl>}
      {usesSlots && !presetSlot && <div className="reserve-step">
        <span className="field-label">회차</span>
        {slots === null && <p className="muted">회차를 불러오는 중입니다.</p>}
        {slots && !slots.length && <p className="muted">예약할 수 있는 회차가 없습니다.</p>}
        {slots && slots.length > 0 && <div className="chip-group">{slots.map((item) => <button type="button" key={item.id}
          className={`chip chip-wide${slot?.id === item.id ? ' is-selected' : ''}`} aria-pressed={slot?.id === item.id} onClick={() => setSlot(item)}>
          <span>{whenText(item, unit)}</span><small className="muted">{item.remaining === null ? '정원 제한 없음' : `잔여 ${item.remaining}`}</small></button>)}</div>}
      </div>}
      {!usesSlots && <div className="reserve-step">
        <span className="field-label">{unit === 'stay' ? '입실일과 퇴실일' : unit === 'period' ? '시작일과 종료일 (하루면 같은 날을 두 번)' : '날짜'}</span>
        <Calendar uploadId={uploadId} persona={persona} resource={resource} start={start} end={end} range={unit === 'stay' || unit === 'period'} onChange={pickDay} />
      </div>}
      {!usesSlots && (unit === 'time_slot' || (slotOptions.length > 0 && unit !== 'time_range')) && <div className="reserve-step">
        <span className="field-label">시간대</span>
        {slotOptions.length > 0 && !customSlot && <Chips label="시간대" options={slotOptions} value={timeSlot} onChange={setTimeSlot}
          allowCustom customLabel="다른 시간" custom={customSlot} onCustom={() => { setCustomSlot(true); setTimeSlot(''); }} />}
        {(customSlot || !slotOptions.length) && <input type="text" aria-label="시간대" maxLength={120} placeholder="예: 10:00~12:00" value={timeSlot} onChange={(event) => setTimeSlot(event.target.value)} />}
      </div>}
      {!usesSlots && unit === 'time_range' && <div className="reserve-step">
        <span className="field-label">시작 시각</span>
        <div className="chip-group">{hours.slice(0, -1).map((hour) => <button type="button" key={hour} className={`chip${startHour === hour ? ' is-selected' : ''}`}
          aria-pressed={startHour === hour} onClick={() => { setStartHour(hour); if (endHour !== null && endHour <= hour) setEndHour(null); }}>{hour}:00</button>)}</div>
        <span className="field-label">종료 시각</span>
        <div className="chip-group">{hours.map((hour) => <button type="button" key={hour} className={`chip${endHour === hour ? ' is-selected' : ''}`}
          disabled={startHour === null || hour <= startHour} aria-pressed={endHour === hour} onClick={() => setEndHour(hour)}>{hour}:00</button>)}</div>
      </div>}
      <div className="reserve-step">
        <span className="field-label">인원{booking.partySizeColumns?.length ? '' : ' (선택)'}</span>
        {!customParty && <Chips label="인원" options={partyOptions} value={party} onChange={setParty}
          allowCustom={partyMax > partyOptions.length || true} customLabel="더 많이" custom={customParty} onCustom={() => { setCustomParty(true); setParty(null); }} />}
        {customParty && <input type="number" aria-label="인원" min={1} max={100000} value={party || ''} onChange={(event) => setParty(event.target.value)} />}
      </div>
      <label>예약자 이름{needsName ? '' : ' (선택)'}<input type="text" required={needsName} maxLength={200} value={booker} onChange={(event) => setBooker(event.target.value)} /></label>
      <label>요청 사항·목적 (선택)<textarea maxLength={2000} value={purpose} onChange={(event) => setPurpose(event.target.value)} /></label>
      <p className="reserve-summary">{summary ? <strong>{summary}</strong> : <span className="muted">날짜를 선택하세요.</span>}
        <span className="muted"> · {booking.approvalRequired ? '신청 후 관리자가 승인하면 확정됩니다.' : '신청하면 바로 확정됩니다.'}</span></p>
      <div className="admin-row-actions">
        <button type="submit" data-intent="primary" disabled={busy || !csrf || !ready}>{busy ? '접수 중…' : booking.approvalRequired ? '예약 신청' : '예약하기'}</button>
        <button type="button" className="service-back-button" disabled={busy} onClick={onClose}>취소</button>
      </div>
    </fieldset></form>
  </ServiceDialog>;
}
