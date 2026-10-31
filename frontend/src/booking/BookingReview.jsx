import React, { useEffect, useRef, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import ServiceDialog from '../components/ServiceDialog';
import { api, formatMoment, jsonOptions, query, statusLabels, statusTone, whenText } from './api.js';

const actionsFor = {
  requested: [['approve', '승인', 'primary'], ['reject', '거절', 'danger']],
  waiting: [['approve', '승인', 'primary'], ['reject', '거절', 'danger']],
  approved: [['check_in', '이용 시작', 'secondary'], ['complete', '완료', 'secondary'], ['cancel', '취소', 'danger']],
  won: [['check_in', '이용 시작', 'secondary'], ['complete', '완료', 'secondary'], ['cancel', '취소', 'danger']],
  in_use: [['complete', '완료', 'primary']],
  rejected: [['reopen', '다시 접수', 'secondary']],
  cancelled: [['reopen', '다시 접수', 'secondary']],
  completed: [], lost: [['reopen', '다시 접수', 'secondary']], other: [['reopen', '다시 접수', 'secondary']],
};

/** Every booking a reviewing persona may see, with filters and the status actions. */
export default function BookingReview({ uploadId, service, persona, csrf, scope, mode = 'review' }) {
  const payments = mode === 'payments';
  const [list, setList] = useState({ bookings: [], page: 1, count: 0, has_next: false });
  const [filters, setFilters] = useState({ status: '', q: '', from: '', to: '', payment: '' });
  const [draft, setDraft] = useState(filters);
  const [detail, setDetail] = useState(null);
  const [acting, setActing] = useState(null); // { item, action, label }
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const ticket = useRef(0);
  const needsScope = ['staff', 'org_manager'].includes(persona.id);

  async function load(page = 1, criteria = filters) {
    if (needsScope && !scope) { setList({ bookings: [], page: 1, count: 0, has_next: false }); return; }
    const mine = ++ticket.current;
    try {
      const data = await api(`/api/uploads/${uploadId}/bookings/${query({ persona: persona.id, scope, page, ...criteria })}`);
      if (mine === ticket.current) { setList(data); setError(''); }
    } catch (caught) { if (mine === ticket.current) setError(caught.message); }
  }
  useEffect(() => { load(1); }, [uploadId, persona.id, scope]);

  function applyFilters(event) {
    event.preventDefault();
    setFilters(draft); load(1, draft);
  }

  async function run(item, action, text) {
    if (busy || !csrf) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const updated = await api(`/api/uploads/${uploadId}/bookings/${item.id}/`, jsonOptions('PATCH', csrf, { persona: persona.id, action, note: text }));
      setMessage(payments ? `${updated.payment || '결제 상태'}로 바꿨습니다.` : `${statusLabels[updated.status]} 처리했습니다.`);
      setActing(null); setNote(''); setDetail(null);
      await load(list.page);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  async function openDetail(item) {
    try { setDetail(await api(`/api/uploads/${uploadId}/bookings/${item.id}/${query({ persona: persona.id })}`)); }
    catch (caught) { setError(caught.message); }
  }

  const counts = `${list.count.toLocaleString()}건`;
  return <section className="panel booking-review">
    <div className="section-title"><h2 className="icon-heading"><SectionIcon name={payments ? 'analysis' : 'request'} />{payments ? '결제 확인' : '예약 관리'}</h2><span className="muted">{counts}</span></div>
    {needsScope && !scope && <p className="notice">위에서 담당 범위를 먼저 선택해 주세요.</p>}
    <form className="booking-filters" onSubmit={applyFilters}>
      <input type="search" aria-label="검색어" placeholder="예약자·항목·목적 검색" maxLength={100} value={draft.q} onChange={(event) => setDraft({ ...draft, q: event.target.value })} />
      {payments && <select aria-label="결제 상태" value={draft.payment} onChange={(event) => setDraft({ ...draft, payment: event.target.value })}>
        <option value="">모든 결제 상태</option><option value="paid">결제됨</option><option value="unpaid">미결제·확인 전</option>
      </select>}
      <select aria-label="상태" value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}>
        <option value="">모든 상태</option>
        {Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <label>부터<input type="date" value={draft.from} onChange={(event) => setDraft({ ...draft, from: event.target.value })} /></label>
      <label>까지<input type="date" value={draft.to} onChange={(event) => setDraft({ ...draft, to: event.target.value })} /></label>
      <button type="submit" disabled={busy}>조회</button>
      <button type="button" className="service-back-button" disabled={busy} onClick={() => { const empty = { status: '', q: '', from: '', to: '', payment: '' }; setDraft(empty); setFilters(empty); load(1, empty); }}>초기화</button>
    </form>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="table-scroll" role="region" aria-label="예약 목록" tabIndex={0}>
      <table className="booking-table">
        <thead><tr><th scope="col">상태</th><th scope="col">{service.resources.levels.join(' / ') || '항목'}</th><th scope="col">일시</th>
          <th scope="col">예약자</th>{payments ? <><th scope="col">금액</th><th scope="col">결제</th></> : <><th scope="col">인원</th><th scope="col">내용</th></>}<th scope="col">처리</th></tr></thead>
        <tbody>{list.bookings.map((item) => <tr key={item.id}>
          <td><span className={`service-badge tone-${statusTone[item.status]}`}>{statusLabels[item.status]}</span>
            {item.status_label && item.status_label !== statusLabels[item.status] && <small className="muted"> {item.status_label}</small>}</td>
          <td><button type="button" className="service-title-button" onClick={() => openDetail(item)}>{item.resource?.path || '항목 없음'}</button></td>
          <td>{whenText(item) || '-'}</td>
          <td>{item.booker || (item.imported ? '시트 기록' : '-')}{item.organization ? <small className="muted"> {item.organization}</small> : null}</td>
          {payments ? <>
            <td>{item.amount !== null ? Number(item.amount).toLocaleString() : '-'}</td>
            <td>{item.payment || <span className="muted">확인 전</span>}</td>
          </> : <>
            <td>{item.party_size ?? '-'}</td>
            <td className="booking-purpose"><span title={item.purpose}>{item.purpose || (item.staff ? `담당 ${item.staff}` : '-')}</span></td>
          </>}
          <td><div className="booking-actions">{(payments ? [['mark_paid', '결제 확인', 'primary'], ['mark_unpaid', '결제 취소', 'danger']] : (actionsFor[item.status] || [])).map(([action, label, intent]) =>
            <button type="button" key={action} data-intent={intent} className={intent === 'danger' ? 'admin-danger' : undefined} disabled={busy || !csrf}
              onClick={() => action === 'reject' || action === 'cancel' || action === 'mark_unpaid' ? setActing({ item, action, label }) : run(item, action, '')}>{label}</button>)}</div></td>
        </tr>)}</tbody>
      </table>
    </div>
    {!list.bookings.length && !error && (!needsScope || scope) && <p className="muted">조건에 맞는 예약이 없습니다.</p>}
    {message && <p className="notice" role="status">{message}</p>}
    <nav className="service-pagination" aria-label="예약 페이지">
      <button type="button" disabled={busy || list.page === 1} onClick={() => load(list.page - 1)}>이전</button>
      <span>{list.page} / {Math.max(1, Math.ceil(list.count / 20))}</span>
      <button type="button" disabled={busy || !list.has_next} onClick={() => load(list.page + 1)}>다음</button>
    </nav>
    {acting && <ServiceDialog title={`${acting.label} 사유`} busy={busy} error={error} onClose={() => { setActing(null); setNote(''); }}>
      <form onSubmit={(event) => { event.preventDefault(); run(acting.item, acting.action, note); }}><fieldset className="inquiry-form" disabled={busy}>
        <p className="muted">{acting.item.resource?.path} · {whenText(acting.item)}</p>
        <label>{acting.action === 'reject' ? '거절 사유 (필수)' : '메모 (선택)'}<textarea required={acting.action === 'reject'} maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)} /></label>
        <div className="admin-row-actions"><button type="submit" data-intent={acting.action === 'reject' ? 'danger' : 'primary'} disabled={busy || !csrf}>{acting.label}</button>
          <button type="button" className="service-back-button" onClick={() => { setActing(null); setNote(''); }}>닫기</button></div>
      </fieldset></form>
    </ServiceDialog>}
    {detail && <ServiceDialog title="예약 상세" busy={busy} error={error} onClose={() => setDetail(null)}>
      <dl className="resource-attributes">
        <div><dt>항목</dt><dd>{detail.resource?.path || '-'}</dd></div>
        <div><dt>일시</dt><dd>{whenText(detail) || '-'}</dd></div>
        <div><dt>상태</dt><dd>{statusLabels[detail.status]}{detail.status_label ? ` (시트 표기: ${detail.status_label})` : ''}</dd></div>
        {detail.booker && <div><dt>예약자</dt><dd>{detail.booker}</dd></div>}
        {detail.party_size !== null && <div><dt>인원</dt><dd>{detail.party_size}</dd></div>}
        {detail.purpose && <div><dt>내용</dt><dd>{detail.purpose}</dd></div>}
        {detail.amount !== null && <div><dt>금액</dt><dd>{Number(detail.amount).toLocaleString()}</dd></div>}
        {detail.payment && <div><dt>결제</dt><dd>{detail.payment}</dd></div>}
        {detail.staff && <div><dt>담당</dt><dd>{detail.staff}</dd></div>}
        {detail.organization && <div><dt>기관</dt><dd>{detail.organization}</dd></div>}
        {Object.entries(detail.attributes || {}).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
        {detail.requested_at && <div><dt>신청 일시</dt><dd>{formatMoment(detail.requested_at)}</dd></div>}
        {detail.processing_note && <div><dt>처리 메모</dt><dd>{detail.processing_note}</dd></div>}
      </dl>
      {detail.events?.length > 0 && <><h3>처리 이력</h3><ul className="booking-events">{detail.events.map((event, index) => <li key={index}>
        <span>{formatMoment(event.at)}</span> <span>{event.from ? `${statusLabels[event.from]} → ` : ''}{statusLabels[event.to]}</span>
        {event.persona && <span className="muted"> · {event.persona}</span>}{event.note && <span className="muted"> · {event.note}</span>}</li>)}</ul></>}
      {detail.imported && <p className="muted">시트에서 가져온 기록입니다.</p>}
    </ServiceDialog>}
  </section>;
}
