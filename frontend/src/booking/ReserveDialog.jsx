import React, { useEffect, useMemo, useRef, useState } from 'react';
import ServiceDialog from '../components/ServiceDialog';
import { api, jsonOptions, query, whenText } from './api.js';
import { WEEKDAY_NAMES, attributeText, formatPhoneInput, moment, perPersonText, phoneDigits, rulesOf } from './rules.js';
import { IconButton, Seats, Stepper } from '../components/ui';

const iso = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const todayIso = () => iso(new Date());
const monthOf = (text) => text.slice(0, 7);
const addDays = (text, days) => { const d = new Date(`${text}T00:00:00`); d.setDate(d.getDate() + days); return iso(d); };
const daysBetween = (a, b) => Math.round((new Date(`${b}T00:00:00`) - new Date(`${a}T00:00:00`)) / 86400000);
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];
const dayText = (text) => { const d = new Date(`${text}T00:00:00`); return `${d.getMonth() + 1}월 ${d.getDate()}일 (${WEEKDAYS[d.getDay()]})`; };

/** An always-open month calendar. Single pick, or a range when `range` is set (two taps). Full and closed days are off. */
function Calendar({ uploadId, persona, resource, start, end, range, stay, onChange }) {
  const [month, setMonth] = useState(monthOf(start || todayIso()));
  const [availability, setAvailability] = useState({});
  const [limit, setLimit] = useState(0);
  const today = todayIso();
  useEffect(() => {
    if (!resource) return;
    let active = true;
    api(`/api/uploads/${uploadId}/bookings/availability/${query({ persona: persona.id, resource: resource.id, month })}`)
      .then((data) => { if (active) { setAvailability((known) => ({ ...known, ...(data.days || {}) })); setLimit(data.limit || 0); } })
      .catch(() => {});
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
    setMonth(monthOf(iso(new Date(year, mon - 1 + delta, 1))));
  };
  const blocked = (day) => Boolean(availability[day]?.full || availability[day]?.closed);
  // While picking the end of a range, it may not cross a full night: a stay may check out on one, a period may not include it.
  const choosingEnd = range && start && !end;
  const firstBlockedAfter = useMemo(() => {
    if (!choosingEnd) return null;
    const known = Object.keys(availability).filter((day) => day > start && blocked(day)).sort();
    return known[0] || null;
  }, [choosingEnd, start, availability]);
  function disabled(day) {
    if (day < today) return true;
    if (choosingEnd && day > start) return Boolean(firstBlockedAfter && (stay ? day > firstBlockedAfter : day >= firstBlockedAfter));
    if (choosingEnd && day === start) return stay;
    return blocked(day);
  }
  const inRange = (day) => range && start && end && day > start && day < end;
  const title = `${month.slice(0, 4)}년 ${Number(month.slice(5))}월`;
  return <div className="calendar" role="group" aria-label="날짜 선택">
    <div className="calendar-head">
      <IconButton icon="prev" label="이전 달" onClick={() => shift(-1)} disabled={month <= monthOf(today)} />
      <strong>{title}</strong>
      <IconButton icon="next" label="다음 달" onClick={() => shift(1)} />
    </div>
    <div className="calendar-grid">
      {WEEKDAYS.map((name) => <span key={name} className="calendar-weekday">{name}</span>)}
      {cells.map((day, index) => {
        if (!day) return <span key={`blank-${index}`} />;
        const info = availability[day];
        const selected = day === start || day === end;
        const past = day < today;
        const mark = past ? '' : info?.closed ? '휴무' : info?.full ? '마감' : info?.count ? String(info.count) : '';
        return <button type="button" key={day} disabled={disabled(day)}
          className={`calendar-day${selected ? ' is-selected' : ''}${inRange(day) ? ' in-range' : ''}${!past && info?.closed ? ' is-closed' : !past && info?.full ? ' is-full' : ''}${!past && info?.count && !info.full ? ' has-bookings' : ''}`}
          aria-pressed={selected} aria-label={`${day}${mark && Number.isNaN(Number(mark)) ? ` ${mark}` : ''}`} onClick={() => onChange(day)}>
          <span>{Number(day.slice(8))}</span>
          {mark && Number.isNaN(Number(mark)) ? <small>{mark}</small>
            : !past && info && info.remaining !== undefined && info.count > 0 ? <Seats compact remaining={info.remaining} total={limit} /> : null}
        </button>;
      })}
    </div>
  </div>;
}

/** What a booker needs to know before picking: a per-person limit and closed days, nothing about capacity. */
function bookerNote(rules) {
  const closed = rules.closedWeekdays?.length ? `${rules.closedWeekdays.map((day) => WEEKDAY_NAMES[day]).join('·')} 휴무` : '';
  return [perPersonText(rules), closed].filter(Boolean).join(' · ');
}

/** Sessions or time blocks of one day, with what is already taken switched off. */
function useDayState(uploadId, persona, resource, day, enabled) {
  const [state, setState] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    setState(null); setError('');
    if (!enabled || !day || !resource) return;
    let active = true;
    api(`/api/uploads/${uploadId}/bookings/availability/${query({ persona: persona.id, resource: resource.id, date: day })}`)
      .then((data) => { if (active) setState(data); })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId, persona.id, resource, day, enabled]);
  return [state, error];
}

/** Reserve one resource. Everything but the name and the note is chosen by pressing, not typing. */
export default function ReserveDialog({ uploadId, service, persona, csrf, resource, slot: presetSlot, onClose, onDone }) {
  const booking = service.booking;
  const target = presetSlot?.resource ? { id: presetSlot.resource } : resource;
  const [ruled, setRuled] = useState(null); // the rules this resource books under: its own, its branch's or the service's
  const rules = ruled?.rules || rulesOf(service);
  const mode = rules.timeMode;
  const usesSlots = service.sheetKind === 'schedule_slots' || Boolean(presetSlot); // a fixed schedule arrives as its session
  const [slots, setSlots] = useState(null);
  const [slot, setSlot] = useState(presetSlot || null);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [session, setSession] = useState('');
  const [fromBlock, setFromBlock] = useState(null);
  const [toBlock, setToBlock] = useState(null);
  const [party, setParty] = useState(1);
  const [booker, setBooker] = useState('');
  const [phone, setPhone] = useState('');
  const [purpose, setPurpose] = useState('');
  const [pin, setPin] = useState('');
  const [pinAgain, setPinAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const timed = Boolean(ruled) && !usesSlots && (mode === 'time_slot' || mode === 'time_range');
  // the dialog never grows, so the next choice is brought into view inside it instead
  const timeStep = useRef(null);
  const endStep = useRef(null);
  const [day, dayError] = useDayState(uploadId, persona, resource, start, timed);
  const reveal = (ref) => ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  useEffect(() => { if (day) reveal(timeStep); }, [day]);
  useEffect(() => { if (fromBlock !== null) reveal(endStep); }, [fromBlock]);

  useEffect(() => {
    if (!target) return;
    let active = true;
    api(`/api/uploads/${uploadId}/booking-rules/${query({ resource: target.id })}`)
      .then((data) => { if (active) setRuled(data); })
      .catch(() => { if (active) setRuled({ rules: rulesOf(service), source: null }); });
    return () => { active = false; };
  }, [uploadId, target?.id]);

  useEffect(() => {
    if (!usesSlots || presetSlot || !resource) return;
    let active = true;
    api(`/api/uploads/${uploadId}/slots/${query({ resource: resource.id, available: 1 })}`)
      .then((data) => { if (active) setSlots(data.slots); })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId, resource, usesSlots, presetSlot]);

  const limit = resource?.capacity || rules.limit;
  const byPeople = rules.capacityBy === 'people';
  const partyMax = Math.max(1, byPeople ? limit : 100);
  const blocks = day?.blocks || [];
  const step = rules.hourly.step;
  const minSteps = rules.hourly.minSteps;
  const maxSteps = rules.hourly.maxSteps || blocks.length;
  // a start block needs minSteps free blocks in a row from it
  const startable = (index) => blocks.slice(index, index + minSteps).length === minSteps && blocks.slice(index, index + minSteps).every((block) => block.available);
  const endChoices = fromBlock === null ? [] : (() => {
    const list = [];
    for (let index = fromBlock; index < blocks.length && index - fromBlock < maxSteps && blocks[index].available; index += 1) {
      if (index - fromBlock + 1 >= minSteps) list.push(index);
    }
    return list;
  })();

  function pickDay(value) {
    setSession(''); setFromBlock(null); setToBlock(null);
    if (mode === 'stay' || mode === 'period') {
      if (!start || end || value < start) { setStart(value); setEnd(''); }
      else if (value === start) { if (mode === 'period') setEnd(value); }
      else setEnd(value);
    } else { setStart(value); setEnd(''); }
  }

  const ready = slot ? true
    : mode === 'time_range' ? Boolean(start && fromBlock !== null && toBlock !== null)
    : mode === 'time_slot' ? Boolean(start && session)
    : mode === 'stay' ? Boolean(start && end && end > start)
    : mode === 'period' ? Boolean(start && end)
    : Boolean(start);
  // a booker is their name and phone number: it is how they find their bookings and how one-per-person is counted
  const isBooker = persona.id === 'booker';
  const needsName = isBooker || Boolean(booking.bookerColumn);
  const phoneOk = phone ? Boolean(phoneDigits(phone)) : !isBooker;
  // a booker picks a 4-digit PIN: with the name and phone it opens this booking from any device
  const pinOk = !isBooker || (pin.length === 4 && pin === pinAgain);
  const sessionInfo = rules.sessions.find((item) => item.label === session);
  // the choice so far in words, and what is still missing
  const summary = slot ? whenText(slot, mode)
    : !start ? ''
    : mode === 'stay' ? (end ? `${dayText(start)} 입실 → ${dayText(end)} 퇴실 · ${daysBetween(start, end)}박` : `${dayText(start)} 입실`)
    : mode === 'period' ? (end ? (start === end ? `${dayText(start)} · 1일` : `${dayText(start)} → ${dayText(end)} · ${daysBetween(start, end) + 1}일`) : `${dayText(start)}부터`)
    : mode === 'time_range' ? `${dayText(start)}${fromBlock !== null ? ` ${blocks[fromBlock].start}~${toBlock !== null ? blocks[toBlock].end : ''}` : ''}`
    : mode === 'time_slot' ? `${dayText(start)}${session ? ` ${session}${sessionInfo?.start && sessionInfo.label !== `${sessionInfo.start}~${sessionInfo.end}` ? ` (${sessionInfo.start}~${sessionInfo.end})` : ''}` : ''}`
    : dayText(start);
  const missing = slot || !start ? '' : (mode === 'stay' || mode === 'period') && !end ? (mode === 'stay' ? '퇴실일을 고르세요' : '종료일을 고르세요')
    : mode === 'time_range' && fromBlock === null ? '시작 시각을 고르세요'
    : mode === 'time_slot' && !session ? '시간대를 고르세요' : '';
  const hint = missing || (ready && !pinOk ? '예약 비밀번호 4자리를 정하세요' : '');

  async function submit(event) {
    event.preventDefault();
    if (busy || !ready) return;
    setBusy(true); setError('');
    const body = { persona: persona.id, booker, purpose };
    if (phone) body.phone = phone;
    if (isBooker) body.password = pin;
    if (party) body.party_size = Number(party);
    if (slot) body.slot_id = slot.id;
    else {
      body.resource_id = resource.id;
      body.date = start;
      if (mode === 'stay' || mode === 'period') body.end_date = end;
      if (mode === 'time_slot') body.time_slot = session;
      if (mode === 'time_range') {
        body.starts_at = moment(start, blocks[fromBlock].start);
        body.ends_at = moment(start, blocks[toBlock].end);
      }
    }
    try {
      const created = await api(`/api/uploads/${uploadId}/bookings/`, jsonOptions('POST', csrf, body));
      onDone(created);
    }
    catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  const info = resource ? Object.entries(resource.attributes || {}).filter(([key]) => ['기록 기준 금액', '평일금액', '주말금액', '성수기금액', '요금', '금액', '이용료', '정원', '이용시작시간', '이용종료시간'].includes(key)) : [];
  const title = `${slot?.resource_name || resource?.name || ''} 예약`;
  return <ServiceDialog title={title} busy={busy} error={error} onClose={onClose} className="reserve-dialog">
    <form onSubmit={submit}><fieldset className="reserve-form reserve-columns" disabled={busy}>
      <div className="reserve-when">
      {resource && resource.path.split(' / ').slice(-2, -1)[0] && resource.path.split(' / ').slice(-2, -1)[0] !== resource.name && <p className="muted reserve-path" title={resource.path.split(' / ').join(' › ')}>{resource.path.split(' / ').slice(-2, -1)[0]}</p>}
      {!ruled && <p className="muted" role="status">예약 규칙을 불러오는 중입니다.</p>}
      {presetSlot && <div className="reserve-step"><span className="field-label">회차</span><p className="reserve-preset">{whenText(presetSlot, mode)}
        {presetSlot.capacity !== null && <Seats remaining={presetSlot.remaining} total={presetSlot.capacity} unit="명" />}</p></div>}
      {usesSlots && !presetSlot && <div className="reserve-step">
        <span className="field-label">회차</span>
        {slots === null && <p className="muted">회차를 불러오는 중입니다.</p>}
        {slots && !slots.length && <p className="muted">예약할 수 있는 회차가 없습니다.</p>}
        {slots && slots.length > 0 && <div className="chip-group">{slots.map((item) => {
          const full = item.remaining === 0;
          return <button type="button" key={item.id} disabled={full}
            className={`chip chip-wide${slot?.id === item.id ? ' is-selected' : ''}${full ? ' is-taken' : ''}`} aria-pressed={slot?.id === item.id} onClick={() => setSlot(item)}>
            <span>{whenText(item, mode)}</span>{item.remaining === null ? <small className="muted">정원 제한 없음</small> : <Seats remaining={item.remaining} total={item.capacity} unit="명" />}</button>;
        })}</div>}
      </div>}
      {ruled && !usesSlots && <div className="reserve-step">
        <span className="field-label">{mode === 'stay' ? '입실일과 퇴실일' : mode === 'period' ? '시작일과 종료일 (하루면 같은 날을 두 번)' : '날짜'}</span>
        <Calendar uploadId={uploadId} persona={persona} resource={resource} start={start} end={end}
          range={mode === 'stay' || mode === 'period'} stay={mode === 'stay'} onChange={pickDay} />
      </div>}
      {timed && !start && <div className="reserve-step"><span className="field-label">{mode === 'time_slot' ? '시간대' : `시간 (${step}분 단위)`}</span>
        <p className="reserve-wait">날짜를 고르면 고를 수 있는 시간이 여기에 나옵니다.</p></div>}
      {timed && start && <div className="reserve-step" ref={timeStep}>
        <span className="field-label">{mode === 'time_slot' ? '시간대' : `시간 (${step}분 단위)`}</span>
        {dayError && <p className="error">{dayError}</p>}
        {!day && !dayError && <p className="muted">남은 시간을 확인하는 중입니다.</p>}
        {day && mode === 'time_slot' && <div className="chip-group" role="group" aria-label="시간대">
          {day.sessions.map((item) => <button type="button" key={item.label} disabled={!item.available}
            className={`chip chip-wide${session === item.label ? ' is-selected' : ''}${item.available ? '' : ' is-taken'}`}
            aria-pressed={session === item.label} onClick={() => setSession(item.label)}>
            <span>{item.label}</span>
            {item.start && item.label !== `${item.start}~${item.end}` && <small className="muted">{item.start}~{item.end}</small>}
            {item.available || !item.remaining ? <Seats remaining={item.remaining} total={day.limit} unit={byPeople ? '명' : '자리'} /> : <small className="muted">지난 시간</small>}
          </button>)}
        </div>}
        {day && mode === 'time_range' && <>
          {!blocks.some((_, index) => startable(index)) && <p className="muted">이 날은 남은 시간이 없습니다. 다른 날을 선택하세요.</p>}
          <span className="field-label">시작</span>
          <div className="chip-group" role="group" aria-label="시작 시각">{blocks.map((block, index) => <button type="button" key={block.start}
            disabled={!startable(index)} className={`chip${fromBlock === index ? ' is-selected' : ''}${block.available ? '' : ' is-taken'}`}
            aria-pressed={fromBlock === index} onClick={() => { setFromBlock(index); setToBlock(minSteps === 1 ? index : index + minSteps - 1); }}>
            <span>{block.start}</span>{day.limit > 1 && <Seats compact remaining={block.remaining} total={day.limit} />}</button>)}</div>
          {fromBlock !== null && <><span className="field-label">종료</span>
            <div className="chip-group" role="group" aria-label="종료 시각" ref={endStep}>{endChoices.map((index) => <button type="button" key={blocks[index].end}
              className={`chip${toBlock === index ? ' is-selected' : ''}`} aria-pressed={toBlock === index} onClick={() => setToBlock(index)}>
              {blocks[index].end}<small>{((index - fromBlock + 1) * step) % 60 ? `${(index - fromBlock + 1) * step}분` : `${((index - fromBlock + 1) * step) / 60}시간`}</small></button>)}</div></>}
        </>}
      </div>}
      </div>
      <div className="reserve-side">
      {(info.length > 0 || resource?.capacity) && <dl className="reserve-info">
        {resource?.capacity && <div><dt>{byPeople ? '정원' : '동시 예약'}</dt><dd>{resource.capacity}{byPeople ? '명' : '건'}</dd></div>}
        {info.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{attributeText(key, value)}</dd></div>)}
      </dl>}
      {ruled && bookerNote(rules) && <p className="muted reserve-rule">{bookerNote(rules)}</p>}
      <div className="reserve-step reserve-inline">
        <span className="field-label">인원</span>
        <Stepper label="인원" value={party} min={1} max={partyMax} unit="명" onChange={setParty} />
      </div>
      <div className="reserve-person">
        <label>예약자 이름{needsName ? '' : ' (선택)'}<input type="text" required={needsName} maxLength={200} autoComplete="name" value={booker} onChange={(event) => setBooker(event.target.value)} /></label>
        <label>전화번호{isBooker ? '' : ' (선택)'}<input type="tel" inputMode="tel" required={isBooker} maxLength={20} autoComplete="tel"
          aria-invalid={phone.length >= 12 && !phoneDigits(phone)} value={phone} onChange={(event) => setPhone(formatPhoneInput(event.target.value))} /></label>
      </div>
      {phone.length >= 12 && !phoneDigits(phone) && <p className="error">전화번호를 다시 확인해 주세요.</p>}
      {isBooker && <div className="reserve-pin">
        <label>예약 비밀번호<input type="password" inputMode="numeric" required maxLength={4} autoComplete="new-password" placeholder="숫자 4자리"
          value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, '').slice(0, 4))} /></label>
        <label>비밀번호 확인<input type="password" inputMode="numeric" required maxLength={4} autoComplete="new-password" placeholder="한 번 더"
          aria-invalid={pinAgain.length === 4 && pin !== pinAgain} value={pinAgain} onChange={(event) => setPinAgain(event.target.value.replace(/\D/g, '').slice(0, 4))} /></label>
        <small className={`reserve-pin__note${pinAgain.length === 4 && pin !== pinAgain ? ' is-bad' : ''}`}>{pinAgain.length === 4 && pin !== pinAgain ? '두 비밀번호가 다릅니다.' : '내 예약에서 이름, 전화번호와 함께 입력해 예약을 확인합니다.'}</small>
      </div>}
      <label>요청 사항 (선택)<textarea rows={3} maxLength={2000} value={purpose} onChange={(event) => setPurpose(event.target.value)} /></label>
      <div className="reserve-footer">
        <div className="reserve-summary"><span className="field-label">선택한 일정</span>
          {summary ? <strong>{summary}</strong> : <span className="muted">{usesSlots ? '왼쪽에서 회차를 고르세요' : '왼쪽 달력에서 날짜를 고르세요'}</span>}
          {hint && <span className="reserve-missing">{hint}</span>}
          <small className="muted">{party}명{booking.approvalRequired ? ' · 관리자 승인 후 확정' : ''}</small></div>
        <button type="submit" data-intent="primary" disabled={busy || !csrf || !ready || !ruled || !phoneOk || !pinOk}>{busy ? '접수 중…' : booking.approvalRequired ? '예약 신청' : '예약하기'}</button>
      </div>
      </div>
    </fieldset></form>
  </ServiceDialog>;
}
