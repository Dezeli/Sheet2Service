import React, { useEffect, useRef, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import { api, hasFeature, whenShort, whenText } from './api.js';
import { Empty, Icon, IconButton, Pager, SearchField, Seats } from '../components/ui';
import ReserveDialog from './ReserveDialog';
import { SHEET_STATS, attributeText } from './rules.js';

const INFO_KEYS = ['정원', '기록 기준 금액', '평일금액', '주말금액', '성수기금액', '요금', '금액', '이용료', '자주 쓰인 시간대', '평균 인원', '시설수', '이용시작시간', '이용종료시간', '운영시간'];

/** Up to three facts a booker wants on the card, in a fixed order. */
function highlights(resource) {
  const items = [];
  if (resource.capacity !== null && resource.capacity !== undefined) items.push(['정원', String(resource.capacity)]);
  for (const key of INFO_KEYS) {
    if (key === '정원') continue;
    const value = resource.attributes?.[key];
    if (value && items.length < 3) items.push([key, attributeText(key, value)]);
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

const CATALOG_SIZE = 10;

function buildQuery({ page, q, parent, group, selected, numeric, size }) {
  const params = new URLSearchParams();
  params.set('page', page);
  if (size) params.set('size', size);
  params.set('summary', '1');
  if (q) params.set('q', q);
  if (parent && !q) params.set('parent', parent.id);
  else if (group) params.set('group', group);
  for (const [label, value] of Object.entries(selected || {})) if (value) params.append('f', `${label}:${value}`);
  for (const [label, item] of Object.entries(numeric || {})) if (item) params.append(item.kind, `${label}:${item.value}`);
  return params.toString();
}

/**
 * "2024년 정보화교육 - ITQ 엑셀 자격증": the shared series goes small above, the part that tells entries apart stays the title.
 */
function splitName(name) {
  const at = name.indexOf(' - ');
  return at > 0 ? { series: name.slice(0, at), title: name.slice(at + 3) } : { series: '', title: name };
}

/** A child named "<its parent> - 2024년 8월 오후반" is shown as just "2024년 8월 오후반" under that parent. */
function childLabel(child, parent) {
  const { series, title } = splitName(child.name);
  return series && parent.name.includes(series) ? title : child.name;
}

/** Only what decides whether to open it: the next open session for dated sessions, otherwise how many choices are inside. */
function SummaryLine({ item, usesSlots, levels }) {
  const summary = item.summary;
  if (usesSlots && summary) {
    if (!summary.next_slot) return <span className="browse-meta is-quiet">열린 회차 없음</span>;
    const slot = summary.next_slot;
    return <span className="browse-meta">
      <span className="browse-meta__when"><Icon name="calendar" size={14} />{whenShort(slot, 'time_slot')}{summary.open_slots > 1 ? <em> 외 {summary.open_slots - 1}회</em> : null}</span>
      {slot.capacity !== null && <Seats remaining={slot.remaining} total={slot.capacity} unit="명" />}
    </span>;
  }
  if (item.children_count > 0) return <span className="browse-meta">{levels[item.level + 1] || '하위 항목'} {(summary?.leaves || item.children_count).toLocaleString()}개</span>;
  const facts = highlights(item).slice(0, 2);
  return facts.length ? <span className="browse-meta">{facts.map(([key, value]) => <span key={key}>{key} <b>{value}</b></span>)}</span> : null;
}

/**
 * Browse and reserve on a wide screen: categories on the left, the catalog in the middle,
 * and the chosen entry on the right with what can be booked under it. The list stays put while the right side changes.
 */
export default function ResourceBrowser({ uploadId, service, persona, csrf, focus = '', onReserved }) {
  const [facets, setFacets] = useState(null);
  const [group, setGroup] = useState('');
  const [list, setList] = useState({ resources: [], page: 1, count: 0, has_next: false });
  const [applied, setApplied] = useState('');
  const [selected, setSelected] = useState({});
  const [numeric, setNumeric] = useState({});
  const [loading, setLoading] = useState(false);
  const [chosen, setChosen] = useState(null); // the catalog entry shown on the right
  const [stack, setStack] = useState([]); // deeper entries opened inside the right panel
  const [inside, setInside] = useState({ resources: [], page: 1, count: 0 });
  const [slots, setSlots] = useState(null);
  const [reserving, setReserving] = useState(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const sequence = useRef(0);
  const panelTicket = useRef(0);
  const canReserve = service.booking.acceptsNew && hasFeature(persona, 'make_reservation');
  const usesSlots = service.sheetKind === 'schedule_slots';
  const levels = service.resources.levels;
  const unit = service.booking.unit;
  const groups = facets?.groups || [];
  const reserveLabel = service.booking.approvalRequired ? '예약 신청' : '예약';
  const shown = stack.at(-1) || chosen;

  async function load(page = 1, state = {}) {
    const ticket = ++sequence.current;
    const current = { page, q: applied, group, selected, numeric, size: CATALOG_SIZE, ...state };
    setLoading(true); setError('');
    try {
      const data = await api(`/api/uploads/${uploadId}/resources/?${buildQuery(current)}`);
      if (ticket !== sequence.current) return;
      setList(data);
      // the right side is never empty on a wide screen: the first entry opens unless one is already chosen
      if (state.keepChoice !== true) choose((usesSlots && data.resources.find((item) => item.summary?.next_slot)) || data.resources[0] || null);
    } catch (caught) { if (ticket === sequence.current) setError(caught.message); }
    finally { if (ticket === sequence.current) setLoading(false); }
  }

  useEffect(() => {
    api(`/api/uploads/${uploadId}/resources/facets/`).then((data) => {
      setFacets(data);
      const first = data.groups?.[0]?.id || '';
      setGroup(first);
      if (!focus) load(1, { group: first });
    }).catch(() => { setFacets({ facets: [], ranges: [], groups: [] }); if (!focus) load(1); });
  }, [uploadId]);

  // an item named in the address (a link from 내 예약) opens on the right, inside its catalog entry when it is deeper
  useEffect(() => {
    if (!focus || !facets) return undefined;
    let active = true;
    api(`/api/uploads/${uploadId}/resources/${focus}/`).then(async (item) => {
      if (!active) return;
      const top = facets.groups?.find((entry) => item.path === entry.name || item.path.startsWith(`${entry.name} / `));
      const nextGroup = top?.id || '';
      setGroup(nextGroup);
      await load(1, { group: nextGroup, keepChoice: true });
      const entryDepth = top ? 1 : 0;
      if (item.level > entryDepth && item.parent) {
        const parent = await api(`/api/uploads/${uploadId}/resources/${item.parent}/`);
        if (!active) return;
        if (parent.level === entryDepth) { choose(parent); setStack(item.children_count ? [] : [item]); return; }
      }
      choose(item);
    }).catch(() => load(1));
    return () => { active = false; };
  }, [uploadId, focus, facets]);

  function choose(item) { setChosen(item); setStack([]); setMessage(''); }

  // what sits under the entry on the right; a leaf instead shows its sessions
  useEffect(() => {
    const ticket = ++panelTicket.current;
    setInside({ resources: [], page: 1, count: 0 }); setSlots(null);
    if (!shown) return;
    if (shown.children_count > 0) loadInside(1, shown, ticket);
    else if (usesSlots) {
      api(`/api/uploads/${uploadId}/slots/?resource=${shown.id}${canReserve ? '&available=1' : ''}`)
        .then((data) => { if (ticket === panelTicket.current) setSlots(data.slots); })
        .catch((caught) => setError(caught.message));
    }
  }, [shown?.id]);

  function loadInside(page, parent = shown, ticket = panelTicket.current) {
    api(`/api/uploads/${uploadId}/resources/?${buildQuery({ page, parent })}`)
      .then((data) => { if (ticket === panelTicket.current) setInside(data); })
      .catch((caught) => setError(caught.message));
  }

  function pickGroup(id) { setGroup(id); load(1, { group: id }); }
  function toggleFacet(label, value) { const next = { ...selected, [label]: selected[label] === value ? '' : value }; setSelected(next); load(1, { selected: next }); }
  function toggleNumeric(label, kind, value) {
    const current = numeric[label];
    const next = { ...numeric, [label]: current && current.value === value ? null : { kind, value } };
    setNumeric(next); load(1, { numeric: next });
  }
  function clearAll() { setSelected({}); setNumeric({}); setApplied(''); load(1, { selected: {}, numeric: {}, q: '' }); }

  const activeFilters = Object.values(selected).filter(Boolean).length + Object.values(numeric).filter(Boolean).length + (applied ? 1 : 0);
  const searching = activeFilters > 0;
  const groupName = groups.find((item) => item.id === group)?.name;
  const entryLevel = levels[groups.length ? 1 : 0] || '항목';
  const hasFilters = Boolean(facets?.facets?.length || facets?.ranges?.some((range) => thresholds(range).length));

  // where the entry on the right sits: the entries opened above it (or its sheet path), then its own series
  const shownPath = shown ? [
    stack.length ? [chosen, ...stack].slice(0, -1).map((item) => splitName(item.name).title).join(' › ') : shown.path.split(' / ').slice(0, -1).join(' › '),
    splitName(shown.name).series,
  ].filter(Boolean).join(' › ') : '';

  const reserveButton = (resource, slot) => canReserve && <button type="button" data-intent="primary" disabled={!csrf}
    onClick={(event) => { event.stopPropagation(); setReserving({ resource, slot }); }}>{reserveLabel}</button>;

  return <div className={`browse-layout${groups.length ? '' : ' is-flat'}`}>
    {groups.length > 0 && <nav className="browse-groups" aria-label={levels[0] || '분류'}>
      <p className="browse-groups__title">{levels[0] || '분류'}</p>
      {groups.map((item) => <button type="button" key={item.id} aria-current={group === item.id && !searching ? 'true' : undefined} onClick={() => pickGroup(item.id)}>
        <span>{item.name}</span><small>{item.count}</small></button>)}
    </nav>}

    <div className="panel browse-pair">
    <section className="browse-catalog" aria-label="목록">
      <div className="browse-catalog__head">
        <h2>{searching ? '검색 결과' : groupName || service.subject}</h2>
        <span className="section-count">{searching ? `${list.count.toLocaleString()}개` : `${entryLevel} ${list.count.toLocaleString()}개`}</span>
      </div>
      <div className="ui-toolbar">
        <SearchField value={applied} placeholder="이름으로 찾기" onSearch={(text) => { setApplied(text); load(1, { q: text }); }} />
        {activeFilters > 0 && <button type="button" className="text-button" onClick={clearAll}>조건 지우기</button>}
      </div>
      {hasFilters && <div className="browse-filters">
        {facets.facets.map((facet) => <div className="facet-row" key={facet.label}><span className="facet-label">{facet.label}</span>
          <div className="chip-group">{facet.values.map((item) => <button type="button" key={item.value} className={`chip${selected[facet.label] === item.value ? ' is-selected' : ''}`}
            aria-pressed={selected[facet.label] === item.value} onClick={() => toggleFacet(facet.label, item.value)}>{item.value}<small>{item.count}</small></button>)}</div></div>)}
        {facets.ranges.map((range) => {
          const money = /금액|요금|료$|원/.test(range.label);
          const kind = range.label === '정원' || /인원|수$/.test(range.label) ? 'min' : money ? 'max' : 'min';
          const steps = thresholds(range);
          if (!steps.length) return null;
          return <div className="facet-row" key={range.label}><span className="facet-label">{range.label}</span>
            <div className="chip-group">{steps.map((value) => <button type="button" key={value} className={`chip${numeric[range.label]?.value === value ? ' is-selected' : ''}`}
              aria-pressed={numeric[range.label]?.value === value} onClick={() => toggleNumeric(range.label, kind, value)}>
              {kind === 'min' ? `${value.toLocaleString()} 이상` : `${value.toLocaleString()}${money ? '원' : ''} 이하`}</button>)}</div></div>;
        })}
      </div>}
      {error && <p className="error" role="alert">{error}</p>}
      {!list.resources.length && !loading && <Empty>{searching ? '조건에 맞는 항목이 없습니다.' : '등록된 항목이 없습니다.'}</Empty>}
      <div className="browse-list">{list.resources.map((item) => {
        const name = splitName(item.name);
        const parent = item.path.split(' / ').slice(-2, -1)[0];
        const series = name.series || (searching && parent !== item.name ? parent : '');
        return <button type="button" key={item.id} className={`browse-item${chosen?.id === item.id ? ' is-chosen' : ''}`} aria-pressed={chosen?.id === item.id}
          title={item.path.split(' / ').join(' › ')} onClick={() => choose(item)}>
          <span className="browse-item__name">{series && <small>{series}</small>}<strong>{name.title}</strong></span>
          <SummaryLine item={item} usesSlots={usesSlots} levels={levels} />
          <Icon name="next" size={18} />
        </button>;
      })}</div>
      <Pager page={list.page} count={list.count} size={list.size || CATALOG_SIZE} disabled={loading} onPage={(page) => load(page, { keepChoice: true })} />
    </section>

    <aside className="browse-detail" aria-label="선택한 항목">
      {!shown && <Empty>왼쪽 목록에서 고르면 여기서 보고 예약합니다.</Empty>}
      {shown && <>
        <div className="browse-detail__head">
          {stack.length > 0 && <IconButton icon="back" label="위로" onClick={() => setStack(stack.slice(0, -1))} />}
          <div>
            <p className="browse-detail__path">{shownPath}</p>
            <h3 title={shown.name}>{splitName(shown.name).title}</h3>
          </div>
        </div>
        {message && <p className="notice" role="status">{message}</p>}
        {(shown.capacity !== null || Object.keys(shown.attributes || {}).some((label) => !SHEET_STATS.includes(label))) && <dl className="browse-detail__facts">
          {shown.capacity !== null && <div><dt>정원</dt><dd>{shown.capacity}</dd></div>}
          {Object.entries(shown.attributes || {}).filter(([label]) => !SHEET_STATS.includes(label)).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{attributeText(label, value)}</dd></div>)}
        </dl>}

        {shown.children_count > 0 && <>
          <p className="browse-detail__label">{levels[shown.level + 1] || '하위 항목'} {inside.count.toLocaleString()}개</p>
          <ul className="browse-rows">{inside.resources.map((item) => {
            const branch = item.children_count > 0;
            const drill = branch || usesSlots;
            return <li key={item.id} className={drill ? 'is-drill' : undefined} onClick={drill ? () => setStack([...stack, item]) : undefined}>
              <div className="browse-rows__text"><strong title={item.name}>{childLabel(item, shown)}</strong><SummaryLine item={item} usesSlots={usesSlots} levels={levels} /></div>
              {drill ? <Icon name="next" size={18} /> : reserveButton(item)}
            </li>;
          })}</ul>
          <Pager page={inside.page} count={inside.count} onPage={(page) => loadInside(page)} />
        </>}

        {shown.children_count === 0 && !usesSlots && canReserve && <div className="browse-detail__cta">{reserveButton(shown)}</div>}
        {shown.children_count === 0 && usesSlots && <>
          <p className="browse-detail__label">회차</p>
          {slots === null && <p className="muted" role="status">불러오는 중…</p>}
          {slots && !slots.length && <Empty>{canReserve ? '예약할 수 있는 회차가 없습니다.' : '등록된 회차가 없습니다.'}</Empty>}
          {slots && slots.length > 0 && <ul className="browse-rows">{slots.map((slot) => {
            const full = slot.closed || slot.remaining === 0;
            return <li key={slot.id} className={full ? 'is-full' : undefined}>
              <div className="browse-rows__text"><strong>{whenText(slot, unit)}</strong>
                {slot.closed ? <span className="muted">마감</span> : slot.capacity !== null && <Seats remaining={slot.remaining} total={slot.capacity} unit="명" />}</div>
              {!full && reserveButton(shown, slot)}
            </li>;
          })}</ul>}
        </>}
      </>}
    </aside>
    </div>

    {reserving && <ReserveDialog uploadId={uploadId} service={service} persona={persona} csrf={csrf}
      resource={reserving.resource} slot={reserving.slot} onClose={() => setReserving(null)}
      onDone={(created) => {
        setReserving(null);
        setMessage(created.status === 'approved' ? '예약이 확정됐습니다.' : '예약을 신청했습니다. 승인되면 내 예약에서 확인할 수 있습니다.');
        onReserved?.(created); load(list.page, { keepChoice: true });
        if (shown?.children_count > 0) loadInside(inside.page);
      }} />}
  </div>;
}
