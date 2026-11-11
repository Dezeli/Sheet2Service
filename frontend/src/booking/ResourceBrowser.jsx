import React, { useEffect, useRef, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import { api, hasFeature, whenText } from './api.js';
import { Empty, Icon, IconButton, Pager, SearchField, Seats } from '../components/ui';
import ReserveDialog from './ReserveDialog';
import { SHEET_STATS, attributeText } from './rules.js';

const INFO_KEYS = ['정원', '기록 기준 금액', '평일금액', '주말금액', '성수기금액', '요금', '금액', '이용료', '자주 쓰인 시간대', '평균 인원', '시설수', '이용시작시간', '이용종료시간', '운영시간'];

/** Three or four facts a booker wants on the card, in a fixed order. */
function highlights(resource) {
  const items = [];
  if (resource.capacity !== null && resource.capacity !== undefined) items.push(['정원', String(resource.capacity)]);
  for (const key of INFO_KEYS) {
    if (key === '정원') continue;
    const value = resource.attributes?.[key];
    if (value && items.length < 4) items.push([key, attributeText(key, value)]);
  }
  return items;
}

function thresholds(range) {
  const span = range.max - range.min;
  if (span <= 0) return [];
  const step = span / 4;
  const round = (value) => value >= 1000 ? Math.round(value / 1000) * 1000 : value >= 10 ? Math.round(value) : Math.round(value * 10) / 10;
  return [...new Set([range.min + step, range.min + 2 * step, range.min + 3 * step].map(round))].filter((v) => v > range.min && v < range.max);
}

function buildQuery({ page, q, parent, group, selected, numeric }) {
  const params = new URLSearchParams();
  params.set('page', page);
  if (q) params.set('q', q);
  // inside a branch its own children come first; the group chip only picks where browsing starts
  if (parent && !q) params.set('parent', parent.id);
  else if (group) params.set('group', group);
  for (const [label, value] of Object.entries(selected)) if (value) params.append('f', `${label}:${value}`);
  for (const [label, item] of Object.entries(numeric)) if (item) params.append(item.kind, `${label}:${item.value}`);
  return params.toString();
}

/** Browse what can be reserved: filter chips from the sheet's own attributes, cards with the facts, reserve from the card. */
export default function ResourceBrowser({ uploadId, service, persona, csrf, focus = '', onReserved }) {
  const [facets, setFacets] = useState(null);
  const [trail, setTrail] = useState([]);
  const [list, setList] = useState({ resources: [], page: 1, count: 0, has_next: false, filtering: false });
  const [applied, setApplied] = useState('');
  const [group, setGroup] = useState('');
  const [selected, setSelected] = useState({});
  const [numeric, setNumeric] = useState({});
  const [open, setOpen] = useState(null);
  const [slots, setSlots] = useState(null);
  const [reserving, setReserving] = useState(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const sequence = useRef(0);
  const canReserve = service.booking.acceptsNew && hasFeature(persona, 'make_reservation');
  const usesSlots = service.sheetKind === 'schedule_slots';
  const levels = service.resources.levels;
  const unit = service.booking.unit;
  const useGroupChips = Boolean(facets?.groups?.length);

  async function load(page = 1, state = {}) {
    const ticket = ++sequence.current;
    const current = { page, q: applied, parent: trail[trail.length - 1], group, selected, numeric, ...state };
    setLoading(true); setError('');
    try {
      const data = await api(`/api/uploads/${uploadId}/resources/?${buildQuery(current)}`);
      if (ticket === sequence.current) setList(data);
    } catch (caught) { if (ticket === sequence.current) setError(caught.message); }
    finally { if (ticket === sequence.current) setLoading(false); }
  }
  useEffect(() => {
    api(`/api/uploads/${uploadId}/resources/facets/`).then((data) => {
      setFacets(data);
      if (data.groups?.length) { setGroup(data.groups[0].id); load(1, { group: data.groups[0].id }); }
      else load(1);
    }).catch(() => { setFacets({ facets: [], ranges: [], groups: [] }); load(1); });
  }, [uploadId]);

  // an item named in the address (a link from 내 예약) opens here: a branch shows its children, a leaf its detail
  useEffect(() => {
    if (!focus || !facets) return undefined;
    let active = true;
    api(`/api/uploads/${uploadId}/resources/${focus}/`).then((item) => {
      if (!active) return;
      const top = facets.groups?.find((entry) => item.path === entry.name || item.path.startsWith(`${entry.name} / `));
      if (top) setGroup(top.id);
      if (item.children_count > 0) { setTrail([item]); setOpen(null); load(1, { parent: item, q: '' }); }
      else setOpen(item);
    }).catch(() => {});
    return () => { active = false; };
  }, [uploadId, focus, facets]);

  useEffect(() => {
    if (!open || !usesSlots) { setSlots(null); return; }
    let active = true;
    api(`/api/uploads/${uploadId}/slots/?resource=${open.id}${canReserve ? '&available=1' : ''}`)
      .then((data) => { if (active) setSlots(data.slots); })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [open, uploadId, usesSlots, canReserve]);

  function pickGroup(id) { setGroup(id); setTrail([]); setOpen(null); load(1, { group: id, parent: undefined }); }
  function toggleFacet(label, value) {
    const next = { ...selected, [label]: selected[label] === value ? '' : value };
    setSelected(next); setOpen(null); load(1, { selected: next });
  }
  function toggleNumeric(label, kind, value) {
    const current = numeric[label];
    const next = { ...numeric, [label]: current && current.value === value ? null : { kind, value } };
    setNumeric(next); setOpen(null); load(1, { numeric: next });
  }
  function clearAll() {
    setSelected({}); setNumeric({}); setApplied(''); setOpen(null); setTrail([]);
    load(1, { selected: {}, numeric: {}, q: '', parent: undefined });
  }
  function enter(resource) {
    setMessage('');
    if (resource.children_count > 0) {  // a branch is never booked itself: go into it, also from search results
      const next = [...trail, resource];
      setTrail(next); setOpen(null); setApplied(''); load(1, { parent: resource, q: '' });
    } else setOpen(resource);
  }
  function jump(index) {
    const next = trail.slice(0, index);
    setTrail(next); setOpen(null); load(1, { parent: next[next.length - 1] });
  }
  const activeFilters = Object.values(selected).filter(Boolean).length + Object.values(numeric).filter(Boolean).length + (applied ? 1 : 0);
  const searching = activeFilters > 0;
  const levelLabel = levels[list.resources[0]?.level ?? trail.length] || levels[levels.length - 1] || '항목';

  const crumbs = trail.length > 0 || (open && !useGroupChips);
  const groupName = facets?.groups?.find((item) => item.id === group)?.name;
  const reserveLabel = service.booking.approvalRequired ? '예약 신청' : '예약';

  return <div className="resource-browser">
    <section className="panel">
      <div className="section-title"><h2 className="icon-heading"><SectionIcon name="table" />{service.subject}</h2>
        <span className="section-count">{searching ? `검색 결과 ${list.count.toLocaleString()}개` : `${levelLabel} ${list.count.toLocaleString()}개`}</span></div>
      <div className="ui-toolbar">
        <SearchField value={applied} placeholder="이름으로 찾기" onSearch={(text) => { setApplied(text); setOpen(null); load(1, { q: text }); }} />
        {activeFilters > 0 && <button type="button" className="text-button" onClick={clearAll}>조건 지우기</button>}
      </div>
      {useGroupChips && <div className="facet-row"><span className="facet-label">{levels[0]}</span>
        <div className="chip-group">{facets.groups.map((item) => <button type="button" key={item.id} className={`chip${group === item.id ? ' is-selected' : ''}`}
          aria-pressed={group === item.id} onClick={() => pickGroup(item.id)}>{item.name}<small>{item.count}</small></button>)}</div></div>}
      {facets?.facets?.map((facet) => <div className="facet-row" key={facet.label}><span className="facet-label">{facet.label}</span>
        <div className="chip-group">{facet.values.map((item) => <button type="button" key={item.value} className={`chip${selected[facet.label] === item.value ? ' is-selected' : ''}`}
          aria-pressed={selected[facet.label] === item.value} onClick={() => toggleFacet(facet.label, item.value)}>{item.value}<small>{item.count}</small></button>)}</div></div>)}
      {facets?.ranges?.map((range) => {
        const money = /금액|요금|료$|원/.test(range.label);
        const kind = range.label === '정원' || /인원|수$/.test(range.label) ? 'min' : money ? 'max' : 'min';
        const steps = thresholds(range);
        if (!steps.length) return null;
        return <div className="facet-row" key={range.label}><span className="facet-label">{range.label}</span>
          <div className="chip-group">{steps.map((value) => <button type="button" key={value} className={`chip${numeric[range.label]?.value === value ? ' is-selected' : ''}`}
            aria-pressed={numeric[range.label]?.value === value} onClick={() => toggleNumeric(range.label, kind, value)}>
            {kind === 'min' ? `${value.toLocaleString()} 이상` : `${value.toLocaleString()}${money ? '원' : ''} 이하`}</button>)}</div></div>;
      })}
      {crumbs && <nav className="resource-trail" aria-label="위치">
        <IconButton icon="back" label="위로" onClick={() => (open ? setOpen(null) : jump(trail.length - 1))} />
        <button type="button" className="crumb" onClick={() => jump(0)}>{useGroupChips ? groupName || '전체' : '전체'}</button>
        {trail.map((item, index) => <React.Fragment key={item.id}><Icon name="next" size={14} />
          <button type="button" className="crumb" onClick={() => jump(index + 1)}>{item.name}</button></React.Fragment>)}
        {open && <><Icon name="next" size={14} /><strong>{open.name}</strong></>}
      </nav>}
      {error && <p className="error" role="alert">{error}</p>}
      {message && <p className="notice" role="status">{message}</p>}
      {!open && <>
        {!list.resources.length && !loading && <Empty>{searching ? '조건에 맞는 항목이 없습니다.' : '등록된 항목이 없습니다.'}</Empty>}
        <div className="resource-cards">{list.resources.map((item) => {
          const leaf = item.children_count === 0;
          const facts = highlights(item);
          return <article className={`resource-card${leaf ? '' : ' is-branch'}`} key={item.id} onClick={() => enter(item)}>
            <div className="resource-card-head">
              <button type="button" className="service-title-button" onClick={(event) => { event.stopPropagation(); enter(item); }}>{item.name}</button>
              {!leaf && <span className="count-badge">{item.children_count}<Icon name="next" size={14} /></span>}
            </div>
            {searching && item.level > 0 && item.path.split(' / ').slice(-2, -1)[0] !== item.name && <p className="resource-card-path muted" title={item.path.split(' / ').join(' › ')}>{item.path.split(' / ').slice(-2, -1)[0]}</p>}
            {facts.length > 0 && <dl className="resource-card-facts">{facts.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>}
            {leaf && canReserve && <div className="resource-card-actions">
              {usesSlots ? <span className="muted">회차 보기</span>
                : <button type="button" data-intent="primary" disabled={!csrf} onClick={(event) => { event.stopPropagation(); setReserving({ resource: item }); }}>{reserveLabel}</button>}
            </div>}
          </article>;
        })}</div>
        <Pager page={list.page} count={list.count} disabled={loading} onPage={(page) => load(page)} />
      </>}
      {open && <article className="resource-detail">
        <div className="resource-detail-head"><h3>{open.name}</h3>
          {canReserve && !usesSlots && open.children_count === 0 && <button type="button" data-intent="primary" disabled={!csrf} onClick={() => setReserving({ resource: open })}>{reserveLabel}</button>}
        </div>
        {(open.capacity !== null || Object.keys(open.attributes || {}).some((label) => !SHEET_STATS.includes(label))) && <dl className="resource-attributes">
          {open.capacity !== null && <div><dt>정원</dt><dd>{open.capacity}</dd></div>}
          {Object.entries(open.attributes || {}).filter(([label]) => !SHEET_STATS.includes(label)).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{attributeText(label, value)}</dd></div>)}
        </dl>}
        {usesSlots && <div className="slot-list">
          <h4>회차</h4>
          {slots === null && <p className="muted" role="status">불러오는 중…</p>}
          {slots && !slots.length && <Empty>{canReserve ? '예약할 수 있는 회차가 없습니다.' : '등록된 회차가 없습니다.'}</Empty>}
          {slots && slots.length > 0 && <ul>{slots.map((slot) => {
            const full = slot.closed || slot.remaining === 0;
            return <li key={slot.id} className={full ? 'is-full' : undefined}>
              <span>{whenText(slot, unit)}</span>
              {slot.closed ? <span className="muted">마감</span> : slot.capacity !== null && <Seats remaining={slot.remaining} total={slot.capacity} unit="명" />}
              {canReserve && !full && <button type="button" data-intent="primary" disabled={!csrf} onClick={() => setReserving({ resource: open, slot })}>{reserveLabel}</button>}
            </li>;
          })}</ul>}
        </div>}
      </article>}
    </section>
    {reserving && <ReserveDialog uploadId={uploadId} service={service} persona={persona} csrf={csrf}
      resource={reserving.resource} slot={reserving.slot} onClose={() => setReserving(null)}
      onDone={(created) => { setReserving(null); setMessage(created.status === 'approved' ? '예약이 확정됐습니다.' : '예약을 신청했습니다. 승인되면 내 예약에서 확인할 수 있습니다.'); onReserved?.(created); load(list.page); }} />}
  </div>;
}
