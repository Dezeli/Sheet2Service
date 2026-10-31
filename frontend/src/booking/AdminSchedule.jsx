import React, { useEffect, useRef, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import ServiceDialog from '../components/ServiceDialog';
import { api, formatMoment, formatTime, jsonOptions, query, statusLabels, statusTone, whenText } from './api.js';

const iso = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const monday = () => { const d = new Date(); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return iso(d); };
const shift = (text, days) => { const d = new Date(`${text}T00:00:00`); d.setDate(d.getDate() + days); return iso(d); };
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];
const actionsFor = {
  requested: [['approve', '승인', 'primary'], ['reject', '거절', 'danger']], waiting: [['approve', '승인', 'primary'], ['reject', '거절', 'danger']],
  approved: [['check_in', '이용 시작', 'secondary'], ['complete', '완료', 'secondary'], ['cancel', '취소', 'danger']],
  won: [['complete', '완료', 'secondary'], ['cancel', '취소', 'danger']], in_use: [['complete', '완료', 'primary']],
};

function cellTime(item) {
  if (item.time_slot) return item.time_slot;
  if (item.starts_at && item.ends_at) {
    const s = new Date(item.starts_at); const e = new Date(item.ends_at);
    if (s.toDateString() !== e.toDateString() && s.getHours() === 0 && e.getHours() === 0) return '숙박·기간';
    return `${formatTime(item.starts_at)}~${formatTime(item.ends_at)}`;
  }
  return '';
}

/** Resources down, days across: who holds what when, and where a day holds more than it should. */
export default function AdminSchedule({ uploadId, service, persona, csrf, scope }) {
  const [from, setFrom] = useState(monday());
  const [data, setData] = useState(null);
  const [search, setSearch] = useState('');
  const [applied, setApplied] = useState('');
  const [conflictsOnly, setConflictsOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const ticket = useRef(0);
  const needsScope = ['staff', 'org_manager'].includes(persona.id);
  const unit = service.booking.unit;

  async function load(nextPage = page) {
    if (needsScope && !scope) { setData(null); return; }
    const mine = ++ticket.current;
    try {
      const result = await api(`/api/uploads/${uploadId}/bookings/schedule/${query({ persona: persona.id, scope, from, days: 7, q: applied, conflicts_only: conflictsOnly ? 1 : '', page: nextPage })}`);
      if (mine === ticket.current) { setData(result); setPage(result.page); setError(''); }
    } catch (caught) { if (mine === ticket.current) setError(caught.message); }
  }
  useEffect(() => { load(1); }, [uploadId, persona.id, scope, from, applied, conflictsOnly]);

  async function act(item, action, text) {
    if (busy || !csrf) return;
    setBusy(true); setError('');
    try {
      const updated = await api(`/api/uploads/${uploadId}/bookings/${item.id}/`, jsonOptions('PATCH', csrf, { persona: persona.id, action, note: text }));
      setMessage(`${statusLabels[updated.status]} 처리했습니다.`); setDetail(null); setNote(''); await load(page);
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
    <div className="section-title"><h2 className="icon-heading"><SectionIcon name="reservation" />일정표</h2>
      <span className="muted">{data ? `${data.count.toLocaleString()}개 항목` : ''}{data?.conflict_total ? ` · 중복·초과 ${data.conflict_total}건` : ''}</span></div>
    {needsScope && !scope && <p className="notice">위에서 담당 범위를 먼저 선택해 주세요.</p>}
    <div className="schedule-controls">
      <div className="booking-actions">
        <button type="button" className="service-back-button" onClick={() => setFrom(shift(from, -7))}>‹ 이전 주</button>
        <button type="button" className="service-back-button" onClick={() => setFrom(monday())}>이번 주</button>
        <button type="button" className="service-back-button" onClick={() => setFrom(shift(from, 7))}>다음 주 ›</button>
        <strong className="schedule-range">{days[0]} ~ {days[days.length - 1]}</strong>
      </div>
      <form className="resource-search" onSubmit={(event) => { event.preventDefault(); setApplied(search.trim()); }}>
        <input type="search" aria-label="항목 검색" placeholder="항목 검색" maxLength={100} value={search} onChange={(event) => setSearch(event.target.value)} />
        <button type="submit">검색</button>
        <label className="check-label"><input type="checkbox" checked={conflictsOnly} onChange={(event) => setConflictsOnly(event.target.checked)} /> 중복·초과만</label>
      </form>
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {data?.conflicts?.length > 0 && <div className="schedule-conflicts">
      <strong>중복·초과 {data.conflict_total}건</strong>
      <ul>{data.conflicts.slice(0, 12).map((item) => <li key={`${item.resource}-${item.date}`}>{item.date} · {item.path || item.name} · 정원 {item.capacity}보다 {item.extra}건 많음</li>)}</ul>
      <p className="muted">시트에서 가져온 기록끼리 겹친 것도 포함됩니다. 칸을 눌러 취소·거절로 정리할 수 있습니다.</p>
    </div>}
    <div className="table-scroll" role="region" aria-label="주간 일정표" tabIndex={0}>
      <table className="schedule-table">
        <thead><tr><th scope="col">{service.resources.levels.at(-1) || '항목'}</th>
          {days.map((day) => <th scope="col" key={day} className={day === today ? 'is-today' : undefined}>{Number(day.slice(8))}일 <small>{WEEKDAYS[new Date(`${day}T00:00:00`).getDay()]}</small></th>)}</tr></thead>
        <tbody>{(data?.resources || []).map((row) => <tr key={row.id}>
          <th scope="row"><div className="schedule-resource"><span>{row.name}</span>{row.path !== row.name && <small className="muted">{row.path.split(' / ').slice(0, -1).join(' › ')}</small>}
            <small className="muted">정원 {row.capacity ?? 1}</small></div></th>
          {days.map((day) => {
            const items = row.days[day] || [];
            const extra = row.conflicts[day];
            return <td key={day} className={`schedule-cell${extra ? ' is-conflict' : ''}${day === today ? ' is-today' : ''}`}>
              {extra ? <span className="schedule-flag">중복 {extra}건</span> : null}
              {items.slice(0, 4).map((item) => <button type="button" key={item.id} className={`schedule-item tone-${statusTone[item.status]}`} onClick={() => openDetail(item)} title={`${item.booker || '기록'} · ${statusLabels[item.status]}`}>
                <span>{item.booker || (item.imported ? '기록' : '-')}</span><small>{cellTime(item)}</small>
              </button>)}
              {items.length > 4 && <small className="muted">+{items.length - 4}</small>}
            </td>;
          })}
        </tr>)}</tbody>
      </table>
    </div>
    {data && !data.resources.length && <p className="muted">{conflictsOnly ? '이번 주에는 중복·초과가 없습니다.' : '표시할 항목이 없습니다.'}</p>}
    {message && <p className="notice" role="status">{message}</p>}
    {data && data.count > 20 && <nav className="service-pagination" aria-label="일정표 페이지">
      <button type="button" disabled={page === 1} onClick={() => load(page - 1)}>이전</button>
      <span>{page} / {Math.max(1, Math.ceil(data.count / 20))}</span>
      <button type="button" disabled={!data.has_next} onClick={() => load(page + 1)}>다음</button>
    </nav>}
    {detail && <ServiceDialog title="예약 상세" busy={busy} error={error} onClose={() => setDetail(null)}>
      <dl className="resource-attributes">
        <div><dt>항목</dt><dd>{detail.resource?.path || '-'}</dd></div>
        <div><dt>일시</dt><dd>{whenText(detail, unit) || '-'}</dd></div>
        <div><dt>상태</dt><dd>{statusLabels[detail.status]}{detail.status_label ? ` (시트 표기: ${detail.status_label})` : ''}</dd></div>
        {detail.booker && <div><dt>예약자</dt><dd>{detail.booker}</dd></div>}
        {detail.party_size !== null && <div><dt>인원</dt><dd>{detail.party_size}</dd></div>}
        {detail.purpose && <div><dt>내용</dt><dd>{detail.purpose}</dd></div>}
        {detail.requested_at && <div><dt>신청 일시</dt><dd>{formatMoment(detail.requested_at)}</dd></div>}
        {detail.processing_note && <div><dt>처리 메모</dt><dd>{detail.processing_note}</dd></div>}
      </dl>
      {detail.imported && <p className="muted">시트에서 가져온 기록입니다.</p>}
      {(actionsFor[detail.status] || []).length > 0 && <fieldset className="inquiry-form" disabled={busy}>
        <label>사유·메모 (거절은 필수)<textarea maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)} /></label>
        <div className="booking-actions">{(actionsFor[detail.status] || []).map(([action, label, intent]) =>
          <button type="button" key={action} data-intent={intent} className={intent === 'danger' ? 'admin-danger' : undefined} disabled={busy || !csrf || (action === 'reject' && !note.trim())}
            onClick={() => act(detail, action, note)}>{label}</button>)}</div>
      </fieldset>}
    </ServiceDialog>}
  </section>;
}
