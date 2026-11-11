import React, { useEffect, useRef, useState } from 'react';
import ServiceDialog from '../components/ServiceDialog';
import { api, jsonOptions, query } from './api.js';
import { moment, rulesOf } from './rules.js';
import { ItemLink } from './nav';
import { Empty, Icon, IconButton, Pager, SearchField, Stepper, TimeField } from '../components/ui';

const emptyForm = { name: '', capacity: '', attributes: [], from: '', to: '', start: '', end: '' };
const PAGE_SIZE = 10;

/** "2024년 정보화교육 - ITQ 엑셀": the shared series small, the distinguishing part as the name. */
function splitName(name) {
  const at = name.indexOf(' - ');
  return at > 0 ? { series: name.slice(0, at), title: name.slice(at + 3) } : { series: '', title: name };
}

/** A child named "<its parent> - 2024년 8월 오후반" reads as "2024년 8월 오후반" under that parent. */
function childLabel(child, parent) {
  const { series, title } = splitName(child.name);
  return series && parent.name.includes(series) ? title : child.name;
}

/**
 * Register, rename, describe, pause and delete the things people reserve, laid out like the booking screen:
 * categories on the left, the entries of one in the middle, the chosen entry and what sits under it on the right.
 */
export default function ResourceAdmin({ uploadId, service, persona, csrf }) {
  const [tops, setTops] = useState(null);
  const [group, setGroup] = useState(null); // the category on the left; null when the sheet has none
  const [list, setList] = useState({ resources: [], page: 1, count: 0 });
  const [applied, setApplied] = useState('');
  const [chosen, setChosen] = useState(null);
  const [stack, setStack] = useState([]);
  const [inside, setInside] = useState({ resources: [], page: 1, count: 0 });
  const [editor, setEditor] = useState(null); // { id?, parent?, level, form }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const ticket = useRef(0);
  const levels = service.resources.levels;
  const rules = rulesOf(service);
  const capacityLabel = rules.capacityBy === 'people' ? '정원' : '같은 시간 최대';
  const unitOf = rules.capacityBy === 'people' ? '명' : '건';
  const grouped = Boolean(tops?.some((item) => item.children_count > 0));
  const shown = stack.at(-1) || chosen;
  const base = `/api/uploads/${uploadId}/resources/`;

  async function loadTops() {
    const data = await api(`${base}${query({ all: 1, size: 20 })}`);
    setTops(data.resources);
    return data.resources;
  }
  async function load(page = 1, at = group, q = applied, keep = false) {
    const mine = ++ticket.current;
    try {
      const data = await api(`${base}${query({ all: 1, size: PAGE_SIZE, page, q, parent: q ? '' : at?.id })}`);
      if (mine !== ticket.current) return;
      setList(data); setError('');
      if (!keep) choose(data.resources[0] || null);
      else if (chosen) choose(data.resources.find((item) => item.id === chosen.id) || chosen, true);
    } catch (caught) { setError(caught.message); }
  }
  useEffect(() => {
    loadTops().then((items) => {
      const first = items.find((item) => item.children_count > 0);
      if (first) { setGroup(first); load(1, first, ''); } else { setGroup(null); setList({ resources: items, page: 1, count: items.length }); choose(items[0] || null); }
    }).catch((caught) => setError(caught.message));
  }, [uploadId]);

  function choose(item, keepStack = false) { setChosen(item); if (!keepStack) setStack([]); }
  function loadInside(page = 1, parent = shown) {
    if (!parent || !parent.children_count) { setInside({ resources: [], page: 1, count: 0 }); return; }
    api(`${base}${query({ all: 1, size: PAGE_SIZE, page, parent: parent.id })}`).then(setInside).catch((caught) => setError(caught.message));
  }
  useEffect(() => { loadInside(1); }, [shown?.id, shown?.children_count]);

  async function refresh() {
    const items = await loadTops();
    if (grouped || items.some((item) => item.children_count > 0)) {
      const nextGroup = items.find((item) => item.id === group?.id) || items.find((item) => item.children_count > 0) || null;
      setGroup(nextGroup);
      await load(list.page, nextGroup, applied, true);
    } else { setList({ resources: items, page: 1, count: items.length }); }
    if (shown) {
      try {
        const fresh = await api(`${base}${shown.id}/`);
        if (stack.length) setStack([...stack.slice(0, -1), { ...shown, ...fresh }]); else setChosen({ ...chosen, ...fresh });
      } catch { choose(null); }
    }
    loadInside(inside.page);
  }

  function openEditor(resource = null, parent = null) {
    setError(''); setMessage('');
    setEditor(resource
      ? { id: resource.id, level: resource.level, form: { name: resource.name, capacity: resource.capacity ?? '', attributes: Object.entries(resource.attributes || {}).map(([key, value]) => ({ key, value })) } }
      : { parent, level: parent ? parent.level + 1 : 0, form: { ...emptyForm, attributes: [] } });
  }

  async function save(event) {
    event.preventDefault();
    if (busy || !csrf) return;
    setBusy(true); setError('');
    const attributes = Object.fromEntries(editor.form.attributes.filter((item) => item.key.trim()).map((item) => [item.key.trim(), item.value]));
    const body = { persona: persona.id, name: editor.form.name.trim(), capacity: editor.form.capacity === '' ? null : Number(editor.form.capacity), attributes };
    try {
      if (editor.id) await api(`${base}${editor.id}/`, jsonOptions('PATCH', csrf, body));
      else {
        const created = await api(base, jsonOptions('POST', csrf, { ...body, parent_id: editor.parent?.id }));
        const { from, to, start, end } = editor.form;
        if (from) {  // a new 차수 that runs on a fixed schedule: its period and daily hours become its session
          const last = to || from;
          await api(`/api/uploads/${uploadId}/slots/`, jsonOptions('POST', csrf, { persona: persona.id, resource_id: created.id,
            date: from, starts_at: moment(from, start || '00:00'), ends_at: moment(last, end || '24:00'),
            time_slot: start && end && last !== from ? `${start}~${end}` : '', capacity: editor.form.capacity === '' ? null : Number(editor.form.capacity) }));
        }
      }
      setMessage(editor.id ? '수정했습니다.' : `${levels[editor.level] || '항목'}을(를) 추가했습니다.`);
      setEditor(null); await refresh();
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  async function toggleActive(resource) {
    if (busy || !csrf) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await api(`${base}${resource.id}/`, jsonOptions('PATCH', csrf, { persona: persona.id, active: !resource.active }));
      setMessage(resource.active ? `"${resource.name}"을(를) 사용 중지했습니다. 예약자에게 보이지 않습니다.` : `"${resource.name}"을(를) 다시 사용합니다.`);
      await refresh();
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  async function remove(resource) {
    if (busy || !csrf || !window.confirm(`"${resource.name}"을(를) 삭제할까요? 예약 기록이 있으면 삭제 대신 사용 중지됩니다.`)) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await api(`${base}${resource.id}/`, jsonOptions('DELETE', csrf, { persona: persona.id }));
      setMessage(result.deleted ? `"${resource.name}"을(를) 삭제했습니다.` : result.detail);
      if (result.deleted && shown?.id === resource.id) { if (stack.length) setStack(stack.slice(0, -1)); else choose(null); }
      await refresh();
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  const tools = (item, size) => <div className="ui-actions">
    <IconButton icon="edit" tone="info" label={`${item.name} 수정`} size={size} disabled={busy} onClick={(event) => { event.stopPropagation(); openEditor(item); }} />
    <IconButton icon={item.active ? 'pause' : 'play'} tone={item.active ? 'warn' : 'approve'} label={item.active ? `${item.name} 사용 중지` : `${item.name} 다시 사용`} size={size} disabled={busy}
      onClick={(event) => { event.stopPropagation(); toggleActive(item); }} />
    <IconButton icon="trash" tone="danger" label={`${item.name} 삭제`} size={size} disabled={busy} onClick={(event) => { event.stopPropagation(); remove(item); }} />
  </div>;
  const meta = (item) => item.children_count > 0
    ? `${levels[item.level + 1] || '하위 항목'} ${item.children_count.toLocaleString()}개`
    : [`${capacityLabel} ${item.capacity ?? `${rules.limit} (기본)`}${item.capacity ? unitOf : ''}`, item.booking_count ? `진행 중 예약 ${item.booking_count.toLocaleString()}건` : ''].filter(Boolean).join(' · ');
  const entryLevel = levels[grouped ? 1 : 0] || '항목';
  const setForm = (changes) => setEditor({ ...editor, form: { ...editor.form, ...changes } });
  const setAttribute = (index, changes) => setForm({ attributes: editor.form.attributes.map((item, i) => (i === index ? { ...item, ...changes } : item)) });

  return <div className="browse-layout resource-admin is-flat">

    <div className="panel browse-pair">
      <section className="browse-catalog" aria-label="목록">
        <div className="browse-catalog__head">
          <h2>{applied ? '검색 결과' : group?.name || '항목'}</h2>
          <span className="resource-admin__head-tools">
            {group && !applied && <>{!group.active && <span className="service-badge tone-muted">사용 중지</span>}{tools(group, 16)}</>}
            <button type="button" data-intent="primary" className="with-icon" disabled={busy || !csrf} onClick={() => openEditor(null, applied ? null : group)}>
              <Icon name="plus" size={16} />{applied || !group ? levels[0] || '항목' : entryLevel} 추가</button>
          </span>
        </div>
        {grouped && <div className="resource-admin__groups" role="group" aria-label={levels[0] || '분류'}>
          {tops.map((item) => <button type="button" key={item.id} className={`chip${group?.id === item.id && !applied ? ' is-selected' : ''}${item.active ? '' : ' is-inactive'}`}
            aria-pressed={group?.id === item.id && !applied} onClick={() => { setGroup(item); setApplied(''); load(1, item, ''); }}>{item.name}<small>{item.children_count}</small></button>)}
          <button type="button" className="chip resource-admin__add-group" disabled={busy || !csrf} onClick={() => openEditor(null, null)}><Icon name="plus" size={14} />{levels[0] || '분류'}</button>
        </div>}
        <div className="ui-toolbar">
          <SearchField value={applied} placeholder="이름으로 찾기" onSearch={(text) => { setApplied(text); load(1, group, text); }} />
        </div>
        {error && !editor && <p className="error" role="alert">{error}</p>}
        {message && <p className="notice" role="status">{message}</p>}
        {!list.resources.length && <Empty>{applied ? '맞는 항목이 없습니다.' : '아직 항목이 없습니다. 오른쪽 위에서 추가하세요.'}</Empty>}
        <div className="browse-list">{list.resources.map((item) => {
          const name = splitName(item.name);
          const parentName = item.path.split(' / ').slice(-2, -1)[0];
          const series = name.series || (applied && parentName !== item.name ? parentName : '');
          return <button type="button" key={item.id} className={`browse-item${chosen?.id === item.id ? ' is-chosen' : ''}${item.active ? '' : ' is-inactive'}`}
            aria-pressed={chosen?.id === item.id} title={item.path.split(' / ').join(' › ')} onClick={() => choose(item)}>
            <span className="browse-item__name">{series && <small>{series}</small>}<strong>{name.title}</strong></span>
            <span className="browse-meta">{!item.active && <span className="service-badge tone-muted">사용 중지</span>}{meta(item)}</span>
            <Icon name="next" size={18} />
          </button>;
        })}</div>
        <Pager page={list.page} count={list.count} size={list.size || PAGE_SIZE} disabled={busy} onPage={(page) => load(page, group, applied, true)} />
      </section>

      <aside className="browse-detail" aria-label="선택한 항목">
        {!shown && <Empty>왼쪽에서 고르면 여기서 고치고, 그 아래 항목을 관리합니다.</Empty>}
        {shown && <>
          <div className="browse-detail__head">
            {stack.length > 0 && <IconButton icon="back" label="위로" onClick={() => setStack(stack.slice(0, -1))} />}
            <div className="resource-admin__title">
              <p className="browse-detail__path">{[...shown.path.split(' / ').slice(0, -1), splitName(shown.name).series].filter(Boolean).join(' › ')}</p>
              <h3 title={shown.name}>{splitName(shown.name).title}</h3>
            </div>
            {tools(shown)}
          </div>
          {!shown.active && <p className="notice">사용 중지된 항목입니다. 예약자에게 보이지 않습니다.</p>}
          <dl className="browse-detail__facts">
            {shown.children_count === 0 && <div><dt>{capacityLabel}</dt><dd>{shown.capacity ? `${shown.capacity}${unitOf}` : `${rules.limit}${unitOf} (기본값)`}</dd></div>}
            {shown.children_count === 0 && <div><dt>진행 중 예약</dt><dd>{(shown.booking_count || 0).toLocaleString()}건</dd></div>}
            {Object.entries(shown.attributes || {}).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
          </dl>
          {shown.children_count === 0 && <p className="resource-admin__links"><ItemLink item={shown.id} path={shown.path} menu="schedule">일정표에서 보기</ItemLink>
            <ItemLink item={shown.id} path={shown.path} menu="review">예약 목록 보기</ItemLink></p>}

          {(shown.children_count > 0 || shown.level < levels.length - 1) && <>
          <div className="resource-admin__children-head">
            <p className="browse-detail__label">{levels[shown.level + 1] || '하위 항목'} {inside.count.toLocaleString()}개</p>
            <button type="button" className="text-button with-icon" disabled={busy || !csrf} onClick={() => openEditor(null, shown)}>
              <Icon name="plus" size={14} />{levels[shown.level + 1] || '하위 항목'} 추가</button>
          </div>
          {inside.count === 0 && <p className="muted resource-admin__hint">{shown.children_count === 0 ? '하위 항목을 추가하면 이 항목은 묶음이 되고, 예약은 하위 항목에서 받습니다.' : ''}</p>}
          {inside.resources.length > 0 && <ul className="browse-rows">{inside.resources.map((item) => <li key={item.id} className={`${item.children_count ? 'is-drill' : ''}${item.active ? '' : ' is-full'}`}
            onClick={item.children_count ? () => setStack([...stack, item]) : undefined}>
            <div className="browse-rows__text"><strong title={item.name}>{childLabel(item, shown)}</strong><span className="browse-meta">{!item.active && <span className="service-badge tone-muted">사용 중지</span>}{meta(item)}</span></div>
            {item.children_count ? <Icon name="next" size={18} /> : tools(item, 16)}
          </li>)}</ul>}
          <Pager page={inside.page} count={inside.count} size={inside.size || PAGE_SIZE} onPage={(page) => loadInside(page)} />
          </>}
        </>}
      </aside>
    </div>

    {editor && <ServiceDialog title={editor.id ? '항목 수정' : `${levels[editor.level] || '항목'} 추가`} busy={busy} error={error} onClose={() => setEditor(null)}>
      <form onSubmit={save}><fieldset className="form-grid" disabled={busy}>
        {editor.parent && <p className="muted">{editor.parent.path.split(' / ').join(' › ')} 아래</p>}
        <label>이름<input type="text" required maxLength={300} autoFocus value={editor.form.name} onChange={(event) => setForm({ name: event.target.value })} /></label>
        <div><span className="field-label">{capacityLabel}</span>
          <div className="setting-control">
            <Stepper label={capacityLabel} min={0} zeroLabel={`기본값 (${rules.limit})`} unit={unitOf}
              value={editor.form.capacity === '' ? 0 : Number(editor.form.capacity)} onChange={(value) => setForm({ capacity: value || '' })} />
          </div></div>
        {!editor.id && <div><span className="field-label">정해진 일정 (선택)</span>
          <div className="schedule-fields">
            <input type="date" aria-label="시작일" value={editor.form.from} onChange={(event) => setForm({ from: event.target.value })} />
            <span aria-hidden="true">~</span>
            <input type="date" aria-label="종료일" min={editor.form.from || undefined} value={editor.form.to} onChange={(event) => setForm({ to: event.target.value })} />
            <TimeField label="시작 시각" value={editor.form.start} onChange={(start) => setForm({ start })} />
            <span aria-hidden="true">~</span>
            <TimeField label="끝 시각" allow24 value={editor.form.end} onChange={(end) => setForm({ end })} />
          </div>
          <small className="muted">강좌처럼 기간과 시간이 정해져 있으면 넣으세요. 예약자는 시간을 고르지 않고 이 일정에 신청합니다. 비우면 예약 규칙대로 날짜·시간을 고릅니다.</small>
        </div>}
        <div><span className="field-label">안내 정보</span>
          <ul className="attribute-list">{editor.form.attributes.map((item, index) => <li key={index}>
            <input type="text" aria-label="이름" placeholder="예: 요금" maxLength={60} value={item.key} onChange={(event) => setAttribute(index, { key: event.target.value })} />
            <input type="text" aria-label="값" placeholder="예: 10,000원" maxLength={500} value={item.value} onChange={(event) => setAttribute(index, { value: event.target.value })} />
            <IconButton icon="trash" tone="danger" label="삭제" onClick={() => setForm({ attributes: editor.form.attributes.filter((_, i) => i !== index) })} />
          </li>)}</ul>
          <button type="button" className="text-button with-icon" onClick={() => setForm({ attributes: [...editor.form.attributes, { key: '', value: '' }] })}><Icon name="plus" size={16} />정보 추가</button>
        </div>
        <div className="dialog-actions"><button type="submit" data-intent="primary" disabled={busy || !csrf || !editor.form.name.trim()}>저장</button></div>
      </fieldset></form>
    </ServiceDialog>}
  </div>;
}
