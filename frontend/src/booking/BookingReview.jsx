import React, { useEffect, useRef, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import ServiceDialog from '../components/ServiceDialog';
import { api, jsonOptions, query, statusActions, statusLabels, statusTone, whenShort, whenText } from './api.js';
import { Empty, IconButton, Pager, SearchField, Segmented } from '../components/ui';
import { ItemLink, pathTitle, useNav } from './nav';

// the server's rule for a settled payment, so the row offers only the step that applies
const VOID = ['cancelled', 'rejected', 'lost'];
const isPaid = (value) => /(완료|납부|결제됨|^y$|^yes$|^paid$|^true$)/i.test(value || '');

const todayText = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
// the ready-made views a dashboard figure opens; each is just a set of filters
const VIEWS = { pending: () => ({ status: 'requested', from: '', to: '' }), today: () => ({ status: '', from: todayText(), to: todayText() }) };
const viewOf = (filters) => (filters.status === 'requested' && !filters.from && !filters.to ? 'pending'
  : !filters.status && filters.from && filters.from === todayText() && filters.to === filters.from ? 'today'
  : !filters.status && !filters.from && !filters.to ? '' : null);
// steps that can run over many bookings at once, in the order a desk uses them
const BULK = [['approve', '승인'], ['check_in', '이용 시작'], ['complete', '완료'], ['reject', '거절'], ['cancel', '취소'], ['reopen', '다시 접수']];

// what happened, as a desk would say it: the step taken, not the two states around it
const STEP_NAMES = { approved: '승인', rejected: '거절', cancelled: '취소', in_use: '이용 시작', completed: '이용 완료', requested: '다시 접수', won: '당첨', lost: '미당첨', waiting: '대기 등록' };
const PAYMENT_STEPS = { 결제완료: '결제 확인', 미결제: '결제 취소' };
function eventStep(event) {
  const [head, ...rest] = String(event.note || '').split(' · ');
  if (event.from && event.from === event.to) {
    return PAYMENT_STEPS[head] ? { name: PAYMENT_STEPS[head], tone: head === '결제완료' ? 'ok' : 'bad', note: rest.join(' · ') } : { name: '메모', tone: 'muted', note: event.note };
  }
  if (!event.from) return { name: event.to === 'requested' ? '예약 신청' : event.to === 'approved' ? '예약 신청 · 즉시 확정' : `예약 신청 · ${statusLabels[event.to]}`, tone: event.to === 'requested' ? 'pending' : statusTone[event.to], note: event.note };
  return { name: STEP_NAMES[event.to] || statusLabels[event.to], tone: statusTone[event.to], note: event.note };
}
const eventTime = (value) => new Date(value).toLocaleString('ko-KR', { month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });

/** Every booking a reviewing persona may see, with filters and the status actions. */
export default function BookingReview({ uploadId, service, persona, csrf, scope, focus = '', view = '', mode = 'review' }) {
  const payments = mode === 'payments';
  const unit = service.booking.unit || 'day';
  const [list, setList] = useState({ bookings: [], page: 1, count: 0, has_next: false });
  const [filters, setFilters] = useState(() => ({ status: '', q: '', from: '', to: '', payment: '', ...(VIEWS[view]?.() || {}) }));
  const [picked, setPicked] = useState(() => new Set());
  const [detail, setDetail] = useState(null);
  const [acting, setActing] = useState(null); // { item, action, label }
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const ticket = useRef(0);
  const needsScope = ['staff', 'org_manager'].includes(persona.id);
  const [summary, setSummary] = useState(null);
  const loadSummary = () => (payments && !(needsScope && !scope)
    ? api(`/api/uploads/${uploadId}/bookings/stats/${query({ persona: persona.id, scope })}`).then((data) => setSummary(data.payments)).catch(() => setSummary(null))
    : Promise.resolve());

  async function load(page = 1, criteria = filters) {
    if (needsScope && !scope) { setList({ bookings: [], page: 1, count: 0, has_next: false }); return; }
    const mine = ++ticket.current;
    try {
      const data = await api(`/api/uploads/${uploadId}/bookings/${query({ persona: persona.id, scope, page, resource: focus, ...criteria })}`);
      if (mine === ticket.current) { setList(data); setError(''); setPicked(new Set()); }
    } catch (caught) { if (mine === ticket.current) setError(caught.message); }
  }
  const nav = useNav();
  const [focusItem, setFocusItem] = useState(null);
  // an item named in the address narrows the list to its bookings
  useEffect(() => {
    setDetail(null); setFocusItem(null);
    if (focus) api(`/api/uploads/${uploadId}/resources/${focus}/`).then(setFocusItem).catch(() => setFocusItem(null));
  }, [uploadId, focus]);
  useEffect(() => { load(1); loadSummary(); }, [uploadId, persona.id, scope, focus]);
  // a dashboard figure clicked while this screen is open swaps the view in place
  const shownView = useRef(view);
  useEffect(() => {
    if (shownView.current === view) return;
    shownView.current = view;
    const next = { ...filters, ...(VIEWS[view]?.() || { status: '', from: '', to: '' }) };
    setFilters(next); load(1, next);
  }, [view]);

  function applyFilters(changes) {
    const next = { ...filters, ...changes };
    setFilters(next); load(1, next);
  }

  async function run(item, action, text) {
    if (busy || !csrf) return;
    setBusy(true); setError(''); setMessage('');
    try {
      if (item === 'picked') {
        const result = await api(`/api/uploads/${uploadId}/bookings/bulk/`, jsonOptions('POST', csrf, { persona: persona.id, action, note: text, ids: [...picked] }));
        setMessage(`${result.done.toLocaleString()}건 처리했습니다.${result.skipped ? ` 지금 상태에서 할 수 없는 ${result.skipped.toLocaleString()}건은 건너뛰었습니다.` : ''}`);
        setActing(null); setNote('');
        await load(list.page);
        return;
      }
      const updated = await api(`/api/uploads/${uploadId}/bookings/${item.id}/`, jsonOptions('PATCH', csrf, { persona: persona.id, action, note: text }));
      setMessage(payments ? `${updated.payment || '결제 상태'}로 바꿨습니다.` : `${statusLabels[updated.status]} 처리했습니다.`);
      setActing(null); setNote(''); setDetail(null);
      await Promise.all([load(list.page), loadSummary()]);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  async function openDetail(item) {
    try { setDetail(await api(`/api/uploads/${uploadId}/bookings/${item.id}/${query({ persona: persona.id })}`)); }
    catch (caught) { setError(caught.message); }
  }

  const filtered = Boolean(filters.status || filters.q || filters.from || filters.to || filters.payment);
  const empty = { status: '', q: '', from: '', to: '', payment: '' };
  return <section className="panel booking-review">
    <div className="section-title"><h2 className="icon-heading"><SectionIcon name={payments ? 'payment' : 'request'} />{payments ? '결제 확인' : '예약 관리'}</h2>
      <span className="section-count">{list.count.toLocaleString()}건</span></div>
    {needsScope && !scope && <p className="notice">담당 범위를 먼저 고르세요.</p>}
    {payments && summary && <div className="ledger-focus payment-summary">
      <div><span className="ledger-focus__label"><button type="button" className="link-button" onClick={() => applyFilters({ payment: 'unpaid' })}>미결제 ›</button></span>
        <strong>{summary.unpaid.toLocaleString()}</strong><span className="ledger-focus__unit">건</span></div>
      <div><span className="ledger-focus__label">받을 금액</span><strong>{Math.round(summary.unpaid_amount).toLocaleString()}</strong><span className="ledger-focus__unit">원</span></div>
      <div className="is-quiet"><span className="ledger-focus__label"><button type="button" className="link-button" onClick={() => applyFilters({ payment: 'paid' })}>결제 완료 ›</button></span>
        <strong>{summary.paid.toLocaleString()}</strong><span className="ledger-focus__unit">건</span></div>
    </div>}
    <div className="ui-toolbar">
      {focus && <span className="focus-chip">{focusItem ? focusItem.name : '항목'}의 예약
        <IconButton icon="close" label="항목 조건 지우기" onClick={() => nav.go(payments ? 'payments' : 'review')} /></span>}
      {!payments && <Segmented label="빠른 보기" value={viewOf(filters)} onChange={(next) => applyFilters(VIEWS[next]?.() || { status: '', from: '', to: '' })}
        options={[{ value: '', label: '전체' }, { value: 'pending', label: '승인 대기' }, { value: 'today', label: '오늘' }]} />}
      <SearchField value={filters.q} placeholder="예약자·전화번호·항목" onSearch={(q) => applyFilters({ q })} />
      {payments && <Segmented label="결제 상태" value={filters.payment} onChange={(payment) => applyFilters({ payment })}
        options={[{ value: '', label: '전체' }, { value: 'unpaid', label: '미결제' }, { value: 'paid', label: '결제됨' }]} />}
      <select aria-label="상태" value={filters.status} onChange={(event) => applyFilters({ status: event.target.value })}>
        <option value="">모든 상태</option>
        {Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <span className="ui-date-range">
        <input type="date" aria-label="시작일" value={filters.from} max={filters.to || undefined} onChange={(event) => applyFilters({ from: event.target.value })} />
        <span aria-hidden="true">~</span>
        <input type="date" aria-label="종료일" value={filters.to} min={filters.from || undefined} onChange={(event) => applyFilters({ to: event.target.value })} />
      </span>
      {filtered && <button type="button" className="text-button" onClick={() => { setFilters(empty); load(1, empty); }}>조건 지우기</button>}
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p className="notice" role="status">{message}</p>}
    {picked.size > 0 && <div className="bulk-bar" role="region" aria-label="선택한 예약">
      <strong>{picked.size}건 선택</strong>
      <select aria-label="선택한 예약 처리" value="" disabled={busy || !csrf} onChange={(event) => {
        const [action, label] = BULK.find(([value]) => value === event.target.value);
        if (action === 'reject' || action === 'cancel') setActing({ item: 'picked', action, label: `${picked.size}건 ${label}` }); else run('picked', action, '');
      }}><option value="" disabled>선택한 예약 처리</option>
        {BULK.filter(([action]) => list.bookings.some((item) => picked.has(item.id) && (statusActions[item.status] || []).some(([step]) => step === action)))
          .map(([action, label]) => <option key={action} value={action}>{label}</option>)}</select>
      <button type="button" className="text-button" onClick={() => setPicked(new Set())}>선택 해제</button>
    </div>}
    {list.bookings.length > 0 && <div className="table-scroll" role="region" aria-label="예약 목록" tabIndex={0}>
      <table className="booking-table">
        <thead><tr>{!payments && <th scope="col" className="cell-pick"><input type="checkbox" aria-label="이 페이지 모두 선택"
          checked={list.bookings.every((item) => picked.has(item.id))} onChange={(event) => setPicked(event.target.checked ? new Set(list.bookings.map((item) => item.id)) : new Set())} /></th>}
          {!payments && <th scope="col" className="cell-status">상태</th>}<th scope="col">항목</th><th scope="col">일시</th><th scope="col">예약자</th>
          {payments && <><th scope="col" className="num">금액</th><th scope="col">결제</th></>}<th scope="col"><span className="visually-hidden">처리</span></th></tr></thead>
        <tbody>{list.bookings.map((item) => <tr key={item.id} className={payments && VOID.includes(item.status) ? 'is-inactive' : undefined}>
          {!payments && <td className="cell-pick"><input type="checkbox" aria-label={`${item.booker || item.resource?.name || '예약'} 선택`} checked={picked.has(item.id)}
            onChange={() => setPicked((current) => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next; })} /></td>}
          {!payments && <td className="cell-status"><span className={`service-badge tone-${statusTone[item.status]}`} title={item.status_label || undefined}>{statusLabels[item.status]}</span></td>}
          <td className="cell-resource">{item.resource ? <ItemLink item={item.resource.id} path={item.resource.path} menu="schedule" className="cell-name" /> : '항목 없음'}
            {payments && VOID.includes(item.status) && <small className="cell-sub">{statusLabels[item.status]}</small>}</td>
          <td className="cell-when" title={whenText(item, unit)}>{(whenShort(item, unit) || '-').split(' – ').map((part, index) => <React.Fragment key={index}>{index ? ' – ' : ''}<span className="when-part">{part}</span></React.Fragment>)}</td>
          <td>{item.booker || (item.imported ? <span className="muted">시트 기록</span> : '-')}{item.party_size ? <span className="muted"> · {item.party_size}명</span> : null}{item.phone && <small className="cell-sub">{item.phone}</small>}</td>
          {payments ? <>
            <td className="num">{item.amount !== null ? `${Number(item.amount).toLocaleString()}원` : '-'}</td>
            <td><span className={`service-badge tone-${isPaid(item.payment) ? 'ok' : 'pending'}`}>{item.payment || '확인 전'}</span></td>
          </> : null}
          <td className="cell-actions"><div className="row-tools"><IconButton icon="detail" label="예약 상세" onClick={() => openDetail(item)} />{payments ? <div className="ui-actions">
            {isPaid(item.payment)
              ? <IconButton icon="close" tone="danger" label="결제 취소" disabled={busy || !csrf} onClick={() => setActing({ item, action: 'mark_unpaid', label: '결제 취소' })} />
              : <IconButton icon="check" tone="approve" label="결제 확인" disabled={busy || !csrf} onClick={() => run(item, 'mark_paid', '')} />}
          </div> : statusActions[item.status]?.length
            ? <select className="status-action" aria-label={`${item.resource?.name || '예약'} 처리`} value="" disabled={busy || !csrf} onChange={(event) => {
              const [action, label] = statusActions[item.status].find(([value]) => value === event.target.value);
              if (action === 'reject' || action === 'cancel') setActing({ item, action, label }); else run(item, action, '');
            }}><option value="" disabled>처리</option>
              {statusActions[item.status].map(([action, label]) => <option key={action} value={action}>{label}</option>)}</select>
            : <span className="status-action is-empty" aria-hidden="true" />}</div></td>
        </tr>)}</tbody>
      </table>
    </div>}
    {!list.bookings.length && !error && (!needsScope || scope) && <Empty>{filtered ? '조건에 맞는 예약이 없습니다.' : '예약이 없습니다.'}</Empty>}
    <Pager page={list.page} count={list.count} disabled={busy} onPage={(page) => load(page)} />
    {acting && <ServiceDialog title={acting.label} busy={busy} error={error} onClose={() => { setActing(null); setNote(''); }}>
      <form onSubmit={(event) => { event.preventDefault(); run(acting.item, acting.action, note); }}><fieldset className="form-grid" disabled={busy}>
        <p className="muted">{acting.item === 'picked' ? '지금 상태에서 할 수 없는 예약은 건너뜁니다.' : `${acting.item.resource?.name || ''} · ${whenText(acting.item, unit)}`}</p>
        <label>{acting.action === 'reject' ? '거절 사유' : '메모 (선택)'}<textarea rows={3} required={acting.action === 'reject'} maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)} /></label>
        <div className="dialog-actions"><button type="submit" data-intent={acting.action === 'reject' ? 'danger' : 'primary'} disabled={busy || !csrf}>{acting.label}</button></div>
      </fieldset></form>
    </ServiceDialog>}
    {detail && <ServiceDialog title="예약 상세" busy={busy} error={error} onClose={() => setDetail(null)}>
      <dl className="resource-attributes">
        <div><dt>항목</dt><dd>{detail.resource ? <>{pathTitle(detail.resource.path)}
          <span className="detail-links"><ItemLink item={detail.resource.id} path={detail.resource.path} menu={payments ? 'payments' : 'review'}>이 항목 예약만 보기</ItemLink>
            <ItemLink item={detail.resource.id} path={detail.resource.path} menu="schedule">일정표에서 보기</ItemLink></span></> : '-'}</dd></div>
        <div><dt>일시</dt><dd>{whenText(detail, unit) || '-'}</dd></div>
        <div><dt>상태</dt><dd>{statusLabels[detail.status]}{detail.status_label ? ` (시트 표기: ${detail.status_label})` : ''}</dd></div>
        {detail.booker && <div><dt>예약자</dt><dd>{detail.booker}</dd></div>}
        {detail.phone && <div><dt>전화번호</dt><dd><a href={`tel:${detail.phone.replace(/-/g, '')}`}>{detail.phone}</a></dd></div>}
        {detail.party_size !== null && <div><dt>인원</dt><dd>{detail.party_size}</dd></div>}
        {detail.purpose && <div><dt>내용</dt><dd>{detail.purpose}</dd></div>}
        {detail.amount !== null && <div><dt>금액</dt><dd>{Number(detail.amount).toLocaleString()}원</dd></div>}
        {detail.payment && <div><dt>결제</dt><dd>{detail.payment}</dd></div>}
        {detail.staff && <div><dt>담당</dt><dd>{detail.staff}</dd></div>}
        {detail.organization && <div><dt>기관</dt><dd>{detail.organization}</dd></div>}
        {Object.entries(detail.attributes || {}).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
        {detail.requested_at && <div><dt>신청 일시</dt><dd>{eventTime(detail.requested_at)}</dd></div>}
        {detail.processing_note && <div><dt>처리 메모</dt><dd>{detail.processing_note}</dd></div>}
      </dl>
      {detail.events?.length > 0 && <><h3>처리 이력</h3><ol className="booking-timeline">{detail.events.map((event, index) => {
        const step = eventStep(event);
        const who = service.personas?.find((item) => item.id === event.persona)?.title || (event.persona === 'booker' ? '예약자' : event.persona);
        return <li key={index} className={`tone-${step.tone}`}>
          <div className="booking-timeline__head"><strong>{step.name}</strong><time dateTime={event.at}>{eventTime(event.at)}</time></div>
          {(who || step.note) && <p className="booking-timeline__meta">{who}{who && step.note ? ' · ' : ''}{step.note}</p>}
        </li>;
      })}</ol></>}
      {detail.imported && <p className="muted">시트에서 가져온 기록</p>}
    </ServiceDialog>}
  </section>;
}
