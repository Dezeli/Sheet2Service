import React, { useEffect, useRef, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import { api, hasFeature, query, whenText } from './api.js';
import ReserveDialog from './ReserveDialog';

/** Walk the resource hierarchy the sheet revealed (기관 → 객실), search it, and reserve a leaf. */
export default function ResourceBrowser({ uploadId, service, persona, csrf, onReserved }) {
  const [trail, setTrail] = useState([]);           // ancestors of the current list
  const [list, setList] = useState({ resources: [], page: 1, count: 0, has_next: false, levels: [] });
  const [search, setSearch] = useState('');
  const [applied, setApplied] = useState('');
  const [selected, setSelected] = useState(null);   // a leaf opened for details
  const [slots, setSlots] = useState(null);
  const [reserving, setReserving] = useState(null); // { resource, slot }
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const sequence = useRef(0);
  const canReserve = service.booking.acceptsNew && hasFeature(persona, 'make_reservation');
  const usesSlots = service.sheetKind === 'schedule_slots';
  const levels = service.resources.levels;

  async function load(page = 1, parent = trail[trail.length - 1], q = applied) {
    const ticket = ++sequence.current;
    setLoading(true); setError('');
    try {
      const data = await api(`/api/uploads/${uploadId}/resources/${query({ page, q, parent: q ? '' : parent?.id })}`);
      if (ticket === sequence.current) setList(data);
    } catch (caught) { if (ticket === sequence.current) setError(caught.message); }
    finally { if (ticket === sequence.current) setLoading(false); }
  }
  useEffect(() => { load(1, undefined, ''); }, [uploadId]);

  useEffect(() => {
    if (!selected || !usesSlots) { setSlots(null); return; }
    let active = true;
    api(`/api/uploads/${uploadId}/slots/${query({ resource: selected.id, available: canReserve ? 1 : '' })}`)
      .then((data) => { if (active) setSlots(data.slots); })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [selected, uploadId, usesSlots, canReserve]);

  function open(resource) {
    setMessage('');
    if (resource.children_count > 0) {
      const next = [...trail, resource];
      setTrail(next); setSelected(null); setApplied(''); setSearch('');
      load(1, resource, '');
    } else {
      setSelected(resource);
    }
  }
  function jump(index) {
    const next = trail.slice(0, index);
    setTrail(next); setSelected(null); setApplied(''); setSearch('');
    load(1, next[next.length - 1], '');
  }
  function submitSearch(event) {
    event.preventDefault();
    setApplied(search.trim()); setSelected(null);
    load(1, trail[trail.length - 1], search.trim());
  }

  const levelLabel = levels[trail.length] || '항목';
  return <div className="resource-browser">
    <section className="panel">
      <div className="section-title"><h2 className="icon-heading"><SectionIcon name="table" />{service.subject} 찾기</h2>
        <span className="muted">{list.count.toLocaleString()}개 {applied ? '검색 결과' : levelLabel}</span></div>
      <form className="resource-search" onSubmit={submitSearch}>
        <input type="search" aria-label="검색어" placeholder={`${levels.join(' · ') || '항목'} 이름으로 검색`} maxLength={100}
          value={search} onChange={(event) => setSearch(event.target.value)} />
        <button type="submit" disabled={loading}>검색</button>
        {applied && <button type="button" className="service-back-button" onClick={() => { setSearch(''); setApplied(''); load(1, trail[trail.length - 1], ''); }}>검색 해제</button>}
      </form>
      <nav className="resource-trail" aria-label="위치">
        <button type="button" className="service-back-button" onClick={() => jump(0)} disabled={!trail.length && !selected}>전체</button>
        {trail.map((item, index) => <React.Fragment key={item.id}><span aria-hidden="true">›</span>
          <button type="button" className="service-back-button" onClick={() => jump(index + 1)}>{item.name}</button></React.Fragment>)}
        {selected && <><span aria-hidden="true">›</span><strong>{selected.name}</strong></>}
      </nav>
      {error && <p className="error" role="alert">{error}</p>}
      {message && <p className="notice" role="status">{message}</p>}
      {!selected && <>
        {!list.resources.length && !loading && <p className="muted">{applied ? '검색 결과가 없습니다.' : '등록된 항목이 없습니다.'}</p>}
        <ul className="resource-list">{list.resources.map((item) => <li key={item.id}>
          <button type="button" className="resource-row" onClick={() => open(item)}>
            <span className="resource-row-main"><strong>{applied ? item.path : item.name}</strong>
              <span className="muted">{item.children_count > 0 ? `${levels[item.level + 1] || '하위 항목'} ${item.children_count}개`
                : [item.capacity !== null ? `정원 ${item.capacity}` : null, item.booking_count ? `진행 중 예약 ${item.booking_count}` : null].filter(Boolean).join(' · ')}</span></span>
            <span className="resource-row-arrow" aria-hidden="true">{item.children_count > 0 ? '›' : '보기'}</span>
          </button>
        </li>)}</ul>
        {(list.count > 20) && <nav className="service-pagination" aria-label="항목 페이지">
          <button type="button" disabled={loading || list.page === 1} onClick={() => load(list.page - 1)}>이전</button>
          <span>{list.page} / {Math.max(1, Math.ceil(list.count / 20))}</span>
          <button type="button" disabled={loading || !list.has_next} onClick={() => load(list.page + 1)}>다음</button>
        </nav>}
      </>}
      {selected && <article className="resource-detail">
        <div className="section-title"><h3>{selected.name}</h3>
          {canReserve && !usesSlots && <button type="button" data-intent="primary" disabled={!csrf} onClick={() => setReserving({ resource: selected })}>
            {service.booking.approvalRequired ? '예약 신청' : '예약하기'}</button>}</div>
        <p className="muted">{selected.path}</p>
        <dl className="resource-attributes">
          {selected.capacity !== null && <div><dt>정원</dt><dd>{selected.capacity}</dd></div>}
          {Object.entries(selected.attributes || {}).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
        </dl>
        {usesSlots && <div className="slot-list">
          <h4>회차</h4>
          {slots === null && <p className="muted">회차를 불러오는 중입니다.</p>}
          {slots && !slots.length && <p className="muted">{canReserve ? '예약할 수 있는 회차가 없습니다.' : '등록된 회차가 없습니다.'}</p>}
          {slots && slots.length > 0 && <ul>{slots.map((slot) => <li key={slot.id}>
            <span>{whenText(slot)}</span>
            <span className="muted">{slot.capacity === null ? `참가 ${slot.imported_count + slot.booked}` : `잔여 ${slot.remaining} / 정원 ${slot.capacity}`}{slot.closed ? ' · 마감' : ''}</span>
            {canReserve && !slot.closed && (slot.remaining === null || slot.remaining > 0) &&
              <button type="button" data-intent="primary" disabled={!csrf} onClick={() => setReserving({ resource: selected, slot })}>예약</button>}
          </li>)}</ul>}
        </div>}
      </article>}
    </section>
    {reserving && <ReserveDialog uploadId={uploadId} service={service} persona={persona} csrf={csrf}
      resource={reserving.resource} slot={reserving.slot} onClose={() => setReserving(null)}
      onDone={(created) => { setReserving(null); setMessage(created.status === 'approved' ? '예약이 확정됐습니다. 내 예약에서 확인할 수 있습니다.' : '예약을 신청했습니다. 승인되면 내 예약에서 상태가 바뀝니다.'); onReserved?.(created); }} />}
  </div>;
}
