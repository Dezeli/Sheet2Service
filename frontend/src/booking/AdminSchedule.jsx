import React, { useEffect, useRef, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import ServiceDialog from '../components/ServiceDialog';
import { actionsFor, api, formatMoment, jsonOptions, query, statusLabels, statusTone, whenText } from './api.js';
import ResourceCalendar, { cellTime } from './ResourceCalendar';
import { ItemLink, pathTitle, useNav } from './nav';
import { Empty, Icon, IconButton, Pager, Segmented, SearchField } from '../components/ui';

const iso = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const monday = () => { const d = new Date(); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return iso(d); };
const shift = (text, days) => { const d = new Date(`${text}T00:00:00`); d.setDate(d.getDate() + days); return iso(d); };
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];
const rangeText = (first, last) => `${Number(first.slice(5, 7))}월 ${Number(first.slice(8))}일 – ${first.slice(5, 7) === last.slice(5, 7) ? '' : `${Number(last.slice(5, 7))}월 `}${Number(last.slice(8))}일`;

/** Resources down, days across for a week, or one resource's month as a calendar. */
/** The Monday of the week a date falls in, and a short label for a date ("2025. 5. 19."). */
const weekOf = (text) => { const d = new Date(`${text}T00:00:00`); d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
const dayLabel = (text) => { const d = new Date(`${text}T00:00:00`); return `${d.getFullYear()}. ${d.getMonth() + 1}. ${d.getDate()}.`; };

export default function AdminSchedule({ uploadId, service, persona, csrf, scope, focus = '' }) {
  const nav = useNav();
  const [view, setView] = useState(focus ? 'month' : 'week');
  const [calendarResource, setCalendarResource] = useState(null);
  // the item in the address is the calendar's item: picking one, a link, Back and Forward all land here
  useEffect(() => {
    if (!focus) { setCalendarResource(null); return undefined; }
    let active = true;
    setView('month');
    api(`/api/uploads/${uploadId}/resources/${focus}/`).then((item) => { if (active) setCalendarResource(item); }).catch(() => {});
    return () => { active = false; };
  }, [uploadId, focus]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [from, setFrom] = useState(monday());
  const [data, setData] = useState(null);
  const [applied, setApplied] = useState('');
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const ticket = useRef(0);
  const needsScope = false; // a part to narrow to is optional
  const unit = service.booking.unit;

  async function load(nextPage = page) {
    if (needsScope && !scope) { setData(null); return; }
    const mine = ++ticket.current;
    try {
      const result = await api(`/api/uploads/${uploadId}/bookings/schedule/${query({ persona: persona.id, scope, from, days: 7, q: applied, page: nextPage })}`);
      if (mine === ticket.current) { setData(result); setPage(result.page); setError(''); }
    } catch (caught) { if (mine === ticket.current) setError(caught.message); }
  }
  useEffect(() => { load(1); }, [uploadId, persona.id, scope, from, applied]);

  async function act(item, action, text) {
    if (busy || !csrf) return;
    setBusy(true); setError('');
    try {
      const updated = await api(`/api/uploads/${uploadId}/bookings/${item.id}/`, jsonOptions('PATCH', csrf, { persona: persona.id, action, note: text }));
      setMessage(`${statusLabels[updated.status]} 처리했습니다.`); setDetail(null); setNote(''); setRefreshKey((n) => n + 1); await load(page);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }
  async function openDetail(item) {
    try { setDetail(await api(`/api/uploads/${uploadId}/bookings/${item.id}/${query({ persona: persona.id })}`)); setNote(''); }
    catch (caught) { setError(caught.message); }
  }

  const days = data?.days || Array.from({ length: 7 }, (_, i) => shift(from, i));
  const today = iso(new Date());
  return <section className="panel schedule">
    <div className="section-title"><h2 className="icon-heading"><SectionIcon name="schedule" />일정표</h2>
      {view === 'week' && data && <span className="section-count">예약된 항목 {data.count.toLocaleString()}개</span>}</div>
    {needsScope && !scope && <p className="notice">위에서 담당 범위를 먼저 선택해 주세요.</p>}
    <div className="schedule-views"><Segmented label="일정표 보기" value={view} onChange={(next) => { if (next === 'week' && focus) nav.go('schedule'); setView(next); }}
      options={[{ value: 'week', label: '주간 전체' }, { value: 'month', label: '항목별 달력' }]} /></div>
    {view === 'month' && (!needsScope || scope) && <ResourceCalendar uploadId={uploadId} persona={persona} scope={scope} resource={calendarResource}
      onPickResource={(item) => nav.go('schedule', item?.id || '')} onOpen={openDetail} refreshKey={refreshKey} />}
    {view === 'week' && <>
    <div className="ui-toolbar">
      <div className="period-nav">
        <IconButton icon="prev" label="이전 주" onClick={() => setFrom(shift(from, -7))} />
        <strong>{rangeText(days[0], days[days.length - 1])}</strong>
        <IconButton icon="next" label="다음 주" onClick={() => setFrom(shift(from, 7))} />
        {from !== monday() && <button type="button" className="text-button" onClick={() => setFrom(monday())}>이번 주</button>}
        <label className="date-jump" title="날짜로 이동"><Icon name="calendar" /><span className="visually-hidden">날짜로 이동</span>
          <input type="date" value={from} onChange={(event) => { if (event.target.value) setFrom(shift(event.target.value, -((new Date(`${event.target.value}T00:00:00`).getDay() + 6) % 7))); }} /></label>
      </div>
      <SearchField value={applied} placeholder="항목 이름" onSearch={setApplied} />
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="table-scroll" role="region" aria-label="주간 일정표" tabIndex={0}>
      <table className="schedule-table">
        <thead><tr><th scope="col">{service.resources.levels.at(-1) || '항목'}</th>
          {days.map((day) => <th scope="col" key={day} className={day === today ? 'is-today' : undefined}>{Number(day.slice(8))}일 <small>{WEEKDAYS[new Date(`${day}T00:00:00`).getDay()]}</small></th>)}</tr></thead>
        <tbody>{(data?.resources || []).map((row) => <tr key={row.id}>
          <th scope="row"><div className="schedule-resource"><ItemLink item={row.id} path={row.path} menu="schedule">{row.name}</ItemLink>
            {row.count > 0 && <span className="count-badge schedule-count">이번 주 {row.count}건</span>}</div></th>
          {days.map((day) => {
            // bookings sharing a time are one class or session: one card with how many, not a card each
            const groups = [];
            for (const item of row.days[day] || []) {
              const time = cellTime(item);
              const found = groups.find((group) => group.time === time);
              if (found) found.items.push(item); else groups.push({ time, items: [item] });
            }
            return <td key={day} className={`schedule-cell${day === today ? ' is-today' : ''}`}>
              {groups.slice(0, 4).map((group) => {
                const first = group.items[0];
                const pending = group.items.some((item) => item.status === 'requested');
                return group.items.length === 1
                  ? <button type="button" key={first.id} className={`schedule-item tone-${statusTone[first.status]}`} onClick={() => openDetail(first)} title={`${first.booker || '기록'} · ${statusLabels[first.status]}`}>
                    <span>{first.booker || (first.imported ? '기록' : '-')}</span><small>{group.time}</small></button>
                  : <button type="button" key={`${group.time}-${first.id}`} className={`schedule-item is-group tone-${pending ? 'pending' : statusTone[first.status]}`}
                    onClick={() => nav.go('review', row.id)} title={`${group.items.length}건 · 예약 관리에서 보기`}>
                    <span>{group.items.length}건{pending ? ' · 승인 대기 있음' : ''}</span><small>{group.time}</small></button>;
              })}
              {groups.length > 4 && <small className="muted">+{groups.length - 4}</small>}
            </td>;
          })}
        </tr>)}</tbody>
      </table>
    </div>
    {data && !data.resources.length && <div className="schedule-empty">
      <p>{applied ? '이 주에 이 이름으로 예약된 항목이 없습니다.' : '이 주에는 예약이 없습니다.'}</p>
      {(data.nearby?.previous || data.nearby?.next) && <div className="schedule-empty__jumps">
        {data.nearby.previous && <button type="button" data-intent="secondary" className="with-icon" onClick={() => setFrom(weekOf(data.nearby.previous))}>
          <Icon name="prev" size={16} />지난 예약 · {dayLabel(data.nearby.previous)}</button>}
        {data.nearby.next && <button type="button" data-intent="secondary" className="with-icon" onClick={() => setFrom(weekOf(data.nearby.next))}>
          다음 예약 · {dayLabel(data.nearby.next)}<Icon name="next" size={16} /></button>}
      </div>}
    </div>}
    {message && <p className="notice" role="status">{message}</p>}
    {data && <Pager page={page} count={data.count} onPage={(next) => load(next)} />}
    </>}
    {detail && <ServiceDialog title="예약 상세" busy={busy} error={error} onClose={() => setDetail(null)}>
      <dl className="resource-attributes">
        <div><dt>항목</dt><dd>{detail.resource ? <>{pathTitle(detail.resource.path)}
          <span className="detail-links"><ItemLink item={detail.resource.id} path={detail.resource.path} menu="review">이 항목 예약만 보기</ItemLink></span></> : '-'}</dd></div>
        <div><dt>일시</dt><dd>{whenText(detail, unit) || '-'}</dd></div>
        <div><dt>상태</dt><dd>{statusLabels[detail.status]}{detail.status_label ? ` (시트 표기: ${detail.status_label})` : ''}</dd></div>
        {detail.booker && <div><dt>예약자</dt><dd>{detail.booker}</dd></div>}
        {detail.party_size !== null && <div><dt>인원</dt><dd>{detail.party_size}</dd></div>}
        {detail.purpose && <div><dt>내용</dt><dd>{detail.purpose}</dd></div>}
        {detail.requested_at && <div><dt>신청 일시</dt><dd>{formatMoment(detail.requested_at)}</dd></div>}
        {detail.processing_note && <div><dt>처리 메모</dt><dd>{detail.processing_note}</dd></div>}
      </dl>
      {detail.imported && <p className="muted">시트에서 가져온 기록입니다.</p>}
      {actionsFor(persona, detail.status).length > 0 && <fieldset className="form-grid detail-actions" disabled={busy}>
        <label>메모 (거절할 때는 사유)<textarea rows={2} maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)} /></label>
        <div className="dialog-actions">{actionsFor(persona, detail.status).map(([action, label, intent]) =>
          <button type="button" key={action} data-intent={intent} disabled={busy || !csrf || (action === 'reject' && !note.trim())}
            onClick={() => act(detail, action, note)}>{label}</button>)}</div>
      </fieldset>}
    </ServiceDialog>}
  </section>;
}
