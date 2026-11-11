import React, { useEffect, useMemo, useState } from 'react';
import { api, formatDate, formatTime, query, statusLabels, statusTone } from './api.js';
import { availabilityNote } from './rules.js';
import ResourceCombobox from './ResourceCombobox';
import { Empty, IconButton, Seats } from '../components/ui';
import { ItemLink } from './nav';

const iso = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const thisMonth = () => iso(new Date()).slice(0, 7);
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

function monthDays(month) {
  const [year, mon] = month.split('-').map(Number);
  return new Date(year, mon, 0).getDate();
}

function shiftMonth(month, delta) {
  const [year, mon] = month.split('-').map(Number);
  return iso(new Date(year, mon - 1 + delta, 1)).slice(0, 7);
}

/** When a booking sits in its day: its slot name, its clock times, or a stay/period. */
export function cellTime(item) {
  if (item.time_slot) return item.time_slot;
  if (item.starts_at && item.ends_at) {
    const s = new Date(item.starts_at); const e = new Date(item.ends_at);
    if (s.toDateString() !== e.toDateString() && s.getHours() === 0 && e.getHours() === 0) return '숙박·기간';
    return `${formatTime(item.starts_at)}~${formatTime(item.ends_at)}`;
  }
  return '종일';
}

const byTime = (a, b) => (a.starts_at || a.time_slot || '').localeCompare(b.starts_at || b.time_slot || '');

/** One resource's month: bookings per day, closed and full days, and the chosen day's sessions or time blocks. */
export default function ResourceCalendar({ uploadId, persona, scope, resource, onPickResource, onOpen, refreshKey = 0 }) {
  const [month, setMonth] = useState(thisMonth());
  const [schedule, setSchedule] = useState(null);
  const [availability, setAvailability] = useState({});
  const [rules, setRules] = useState(null);
  const [day, setDay] = useState('');
  const [dayState, setDayState] = useState(null);
  const [error, setError] = useState('');
  const today = iso(new Date());

  useEffect(() => {
    if (!resource) return;
    let active = true;
    setError('');
    const from = `${month}-01`;
    Promise.all([
      api(`/api/uploads/${uploadId}/bookings/schedule/${query({ persona: persona.id, scope, from, days: monthDays(month), resource: resource.id })}`),
      api(`/api/uploads/${uploadId}/bookings/availability/${query({ persona: persona.id, resource: resource.id, month })}`),
    ]).then(([rows, free]) => { if (active) { setSchedule(rows.resources[0] || { days: {}, conflicts: {} }); setAvailability(free.days || {}); } })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId, persona.id, scope, resource?.id, month, refreshKey]);

  // a picked item opens on a month that has its bookings: this month when it has any, else its latest one
  useEffect(() => {
    if (!resource) return undefined;
    let active = true;
    api(`/api/uploads/${uploadId}/bookings/${query({ persona: persona.id, scope, resource: resource.id })}`).then((data) => {
      const latest = data.bookings?.find((item) => item.date)?.date;
      if (!active || !latest) return;
      const current = thisMonth();
      const thisMonthHas = data.bookings.some((item) => item.date?.startsWith(current));
      if (!thisMonthHas && latest.slice(0, 7) < current) { setMonth(latest.slice(0, 7)); setDay(''); }
    }).catch(() => {});
    return () => { active = false; };
  }, [uploadId, persona.id, scope, resource?.id]);

  useEffect(() => {
    if (!resource) return;
    api(`/api/uploads/${uploadId}/booking-rules/${query({ resource: resource.id })}`).then((data) => setRules(data)).catch(() => setRules(null));
  }, [uploadId, resource?.id]);

  useEffect(() => {
    setDayState(null);
    if (!resource || !day) return;
    let active = true;
    api(`/api/uploads/${uploadId}/bookings/availability/${query({ persona: persona.id, resource: resource.id, date: day })}`)
      .then((data) => { if (active) setDayState(data); }).catch(() => {});
    return () => { active = false; };
  }, [uploadId, persona.id, resource?.id, day, refreshKey]);

  const cells = useMemo(() => {
    const [year, mon] = month.split('-').map(Number);
    const list = Array.from({ length: new Date(year, mon - 1, 1).getDay() }, () => null);
    for (let d = 1; d <= monthDays(month); d += 1) list.push(iso(new Date(year, mon - 1, d)));
    return list;
  }, [month]);

  const picker = <ResourceCombobox uploadId={uploadId} value={resource} leafOnly label="달력으로 볼 항목"
    onChange={(item) => { onPickResource(item); setDay(''); }} placeholder="항목 이름을 입력하거나 목록에서 고르세요" />;
  if (!resource) return <div className="resource-calendar">{picker}<Empty>항목을 고르면 한 달 일정이 나옵니다.</Empty></div>;
  const dayItems = day ? [...(schedule?.days?.[day] || [])].sort(byTime) : [];
  const unitWord = rules?.rules?.capacityBy === 'people' ? '명' : '건';

  return <div className="resource-calendar">
    {picker}
    <p className="detail-links"><ItemLink item={resource.id} path={resource.path} menu="review">이 항목 예약 목록</ItemLink></p>
    {rules && <p className="muted calendar-rule">{availabilityNote(rules.rules, resource.capacity || rules.rules.limit)}{rules.source ? ` (규칙: ${rules.source.name})` : ''}</p>}
    <div className="period-nav">
      <IconButton icon="prev" label="이전 달" onClick={() => { setMonth(shiftMonth(month, -1)); setDay(''); }} />
      <strong>{month.slice(0, 4)}년 {Number(month.slice(5))}월</strong>
      <IconButton icon="next" label="다음 달" onClick={() => { setMonth(shiftMonth(month, 1)); setDay(''); }} />
      {month !== thisMonth() && <button type="button" className="text-button" onClick={() => { setMonth(thisMonth()); setDay(''); }}>이번 달</button>}
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="month-grid" role="grid" aria-label={`${resource.name} 월간 일정`}>
      {WEEKDAYS.map((name) => <span key={name} className="calendar-weekday" role="columnheader">{name}</span>)}
      {cells.map((value, index) => {
        if (!value) return <span key={`blank-${index}`} className="month-cell is-blank" />;
        const items = [...(schedule?.days?.[value] || [])].sort(byTime);
        const info = availability[value];
        const extra = schedule?.conflicts?.[value];
        const mark = info?.closed ? '휴무' : extra ? `초과 ${extra}` : info?.full && value >= today ? '마감' : '';
        return <div key={value} role="gridcell" className={`month-cell${value === today ? ' is-today' : ''}${value === day ? ' is-selected' : ''}${info?.closed ? ' is-closed' : ''}${extra ? ' is-conflict' : ''}`}>
          <button type="button" className="month-day" onClick={() => setDay(value === day ? '' : value)} aria-pressed={value === day}
            aria-label={`${value} 예약 ${items.length}건${mark ? ` ${mark}` : ''}`}>
            <span>{Number(value.slice(8))}</span>{mark && <small>{mark}</small>}{!mark && items.length > 0 && <small>{items.length}건</small>}
          </button>
          {items.slice(0, 3).map((item) => <button type="button" key={item.id} className={`schedule-item tone-${statusTone[item.status]}`} onClick={() => onOpen(item)}
            title={`${item.booker || '기록'} · ${statusLabels[item.status]}`}><small>{cellTime(item)}</small><span>{item.booker || (item.imported ? '기록' : '-')}</span></button>)}
          {items.length > 3 && <button type="button" className="month-more" onClick={() => setDay(value)}>+{items.length - 3}건 더</button>}
        </div>;
      })}
    </div>
    {day && <div className="day-panel">
      <div className="day-panel-head"><h3>{formatDate(day)}</h3><IconButton icon="close" label="닫기" onClick={() => setDay('')} /></div>
      {dayState?.closed && <p className="notice">휴무일</p>}
      {dayState?.sessions && <div className="chip-group" aria-label="시간대별 남은 자리">{dayState.sessions.map((item) =>
        <span key={item.label} className={`chip chip-wide${item.remaining === 0 ? ' is-taken' : ''}`}><span>{item.label}</span>
          <Seats remaining={item.remaining} total={dayState.limit} unit={unitWord === '명' ? '명' : '자리'} /></span>)}</div>}
      {dayState?.blocks && <div className="chip-group" aria-label="시간별 남은 자리">{dayState.blocks.map((item) =>
        <span key={item.start} className={`chip chip-wide${item.remaining === 0 ? ' is-taken' : ''}`}><span>{item.start}</span><Seats compact remaining={item.remaining} total={dayState.limit} /></span>)}</div>}
      {dayState && dayState.remaining !== undefined && <Seats remaining={dayState.remaining} total={dayState.limit} unit={unitWord === '명' ? '명' : '자리'} />}
      {dayItems.length ? <ul className="day-bookings">{dayItems.map((item) => <li key={item.id}>
        <button type="button" className={`schedule-item tone-${statusTone[item.status]}`} onClick={() => onOpen(item)}>
          <small>{cellTime(item)}</small><span>{item.booker || (item.imported ? '시트 기록' : '-')}{item.party_size ? ` · ${item.party_size}명` : ''}</span>
          <small>{statusLabels[item.status]}{item.purpose ? ` · ${item.purpose}` : ''}</small>
        </button></li>)}</ul> : <Empty>예약이 없습니다.</Empty>}
    </div>}
  </div>;
}
