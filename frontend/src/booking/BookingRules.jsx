import React, { useEffect, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import { Icon, IconButton, Segmented, Stepper, TimeField } from '../components/ui';
import { api, jsonOptions, query } from './api.js';
import ResourceCombobox from './ResourceCombobox';
import { STEPS, WEEKDAY_NAMES, availabilityNote, duration, sessionsFrom } from './rules.js';

const MODES = [
  { value: 'day', label: '하루', help: '날짜만 고릅니다.' },
  { value: 'time_slot', label: '정한 타임', help: '관리자가 만든 타임 중에서 고릅니다.' },
  { value: 'time_range', label: '시간 단위', help: '운영 시간 안에서 시작과 끝을 고릅니다.' },
  { value: 'stay', label: '숙박', help: '입실일과 퇴실일을 고릅니다.' },
  { value: 'period', label: '기간', help: '시작일과 종료일을 고릅니다.' },
];
const LENGTHS = [20, 30, 40, 50, 60, 90, 120, 180];
const GAPS = [0, 10, 15, 20, 30, 60];
const minutesOf = (clock) => (clock === '24:00' ? 1440 : /^\d{2}:\d{2}$/.test(clock || '') ? Number(clock.slice(0, 2)) * 60 + Number(clock.slice(3)) : null);
const withDefaults = (rules) => ({ ...rules, perPerson: rules.perPerson || { limit: 0, per: 'day' } });

function Setting({ name, hint, children }) {
  return <div className="setting"><div className="setting-name">{name}{hint && <small>{hint}</small>}</div><div className="setting-control">{children}</div></div>;
}

/** How a service, or one branch of it, offers time and how many bookings fit at once. The server validates and saves. */
export default function BookingRules({ uploadId, service, persona, csrf, onSaved }) {
  const [target, setTarget] = useState(null); // null is the whole service
  const [info, setInfo] = useState(null);
  const [form, setForm] = useState(null);
  const [table, setTable] = useState({ open: '10:00', close: '16:00', length: 60, gap: 0 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    let active = true;
    setForm(null); setError('');
    api(`/api/uploads/${uploadId}/booking-rules/${query({ resource: target?.id })}`)
      .then((data) => { if (active) { setInfo(data); setForm(withDefaults(data.rules)); } })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId, target?.id]);

  const header = <div className="section-title"><h2 className="icon-heading"><SectionIcon name="rules" />예약 규칙</h2></div>;
  if (!form) return <section className="panel">{header}{error ? <p className="error" role="alert">{error}</p> : <p className="muted" role="status">불러오는 중…</p>}</section>;

  const change = (changes) => { setForm({ ...form, ...changes }); setMessage(''); setError(''); };
  const changeHourly = (changes) => change({ hourly: { ...form.hourly, ...changes } });
  const changeSession = (index, changes) => change({ sessions: form.sessions.map((item, i) => (i === index ? { ...item, ...changes } : item)) });
  const span = (minutesOf(form.hourly.close) ?? 0) - (minutesOf(form.hourly.open) ?? 0);
  const blocks = Math.max(0, Math.floor(span / form.hourly.step));
  const byPeople = form.capacityBy === 'people';
  const ownsRules = Boolean(target && info?.source?.id === target.id);
  const mode = MODES.find((item) => item.value === form.timeMode);

  async function send(rules, text) {
    if (busy || !csrf) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const data = await api(`/api/uploads/${uploadId}/booking-rules/`, jsonOptions('PATCH', csrf, { persona: persona.id, rules, resource_id: target?.id }));
      setInfo(data); setForm(withDefaults(data.rules));
      if (!target) onSaved?.(data.rules);
      setMessage(text);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  return <section className="panel booking-rules">
    {header}
    <div className="rules-target">
      <div className="chip-group">
        <button type="button" className={`chip${!target ? ' is-selected' : ''}`} aria-pressed={!target} onClick={() => setTarget(null)}>서비스 전체</button>
        {(info?.overrides || []).map((item) => <button type="button" key={item.id} className={`chip${target?.id === item.id ? ' is-selected' : ''}`}
          aria-pressed={target?.id === item.id} onClick={() => setTarget(item)} title={item.path}>{item.name}</button>)}
      </div>
      <ResourceCombobox uploadId={uploadId} value={target} onChange={setTarget} label="규칙을 따로 둘 항목" placeholder="항목별로 따로 정하기" />
      {target && !ownsRules && <p className="muted">지금은 {info?.source ? `"${info.source.name}"` : '서비스 전체'} 규칙을 따릅니다. 저장하면 이 항목{target.children_count ? '과 하위 항목' : ''}에만 적용됩니다.</p>}
    </div>
    {service.sheetKind === 'schedule_slots' && <p className="notice">회차별 정원은 회차·정원 메뉴에서 정합니다.</p>}

    <form onSubmit={(event) => { event.preventDefault(); send(form, '저장했습니다.'); }}>
      <fieldset className="setting-list" disabled={busy}>
        <Setting name="시간 단위">
          <Segmented label="시간 단위" value={form.timeMode} onChange={(timeMode) => change({ timeMode })} options={MODES} />
          <p className="setting-help">{mode?.help}</p>
        </Setting>

        {form.timeMode === 'time_slot' && <Setting name="예약 타임" hint={`${form.sessions.length}개`}>
          <div className="session-maker">
            <TimeField label="첫 타임 시작" value={table.open} onChange={(open) => setTable({ ...table, open })} />
            <span aria-hidden="true">~</span>
            <TimeField label="마지막 타임 끝" value={table.close} onChange={(close) => setTable({ ...table, close })} />
            <select aria-label="한 타임 길이" value={table.length} onChange={(event) => setTable({ ...table, length: Number(event.target.value) })}>
              {LENGTHS.map((value) => <option key={value} value={value}>{duration(value)}씩</option>)}</select>
            <select aria-label="타임 사이 쉬는 시간" value={table.gap} onChange={(event) => setTable({ ...table, gap: Number(event.target.value) })}>
              {GAPS.map((value) => <option key={value} value={value}>{value ? `${duration(value)} 쉬고` : '쉬는 시간 없이'}</option>)}</select>
            <button type="button" data-intent="info" onClick={() => {
              const made = sessionsFrom(table.open, table.close, table.length, table.gap);
              if (made.length) change({ sessions: made }); else setError('끝 시각이 시작보다 한 타임 이상 늦어야 합니다.');
            }}>타임 만들기</button>
          </div>
          <ul className="session-list">{form.sessions.map((item, index) => <li key={index}>
            <input type="text" aria-label="타임 이름" maxLength={40} required value={item.label} onChange={(event) => changeSession(index, { label: event.target.value })} />
            <TimeField label="시작" value={item.start} onChange={(start) => changeSession(index, { start })} />
            <span aria-hidden="true">~</span>
            <TimeField label="끝" value={item.end} onChange={(end) => changeSession(index, { end })} />
            <IconButton icon="trash" tone="danger" label={`${item.label || '타임'} 삭제`} onClick={() => change({ sessions: form.sessions.filter((_, i) => i !== index) })} />
          </li>)}</ul>
          {form.sessions.length < 24 && <button type="button" className="text-button with-icon" onClick={() => change({ sessions: [...form.sessions, { label: '', start: '', end: '' }] })}>
            <Icon name="plus" size={16} />타임 추가</button>}
        </Setting>}

        {form.timeMode === 'time_range' && <>
          <Setting name="운영 시간">
            <TimeField label="운영 시작" value={form.hourly.open} onChange={(open) => changeHourly({ open })} />
            <span aria-hidden="true">~</span>
            <TimeField label="운영 종료" allow24 value={form.hourly.close} onChange={(close) => changeHourly({ close })} />
          </Setting>
          <Setting name="예약 간격">
            <select aria-label="예약 간격" value={form.hourly.step} onChange={(event) => changeHourly({ step: Number(event.target.value), minSteps: 1, maxSteps: 0 })}>
              {STEPS.map((step) => <option key={step} value={step}>{duration(step)}</option>)}</select>
          </Setting>
          <Setting name="한 번 이용 시간">
            <select aria-label="최소 이용" value={form.hourly.minSteps} onChange={(event) => changeHourly({ minSteps: Number(event.target.value) })}>
              {Array.from({ length: Math.max(1, blocks) }, (_, i) => i + 1).map((count) => <option key={count} value={count}>최소 {duration(count * form.hourly.step)}</option>)}</select>
            <span aria-hidden="true">~</span>
            <select aria-label="최대 이용" value={form.hourly.maxSteps} onChange={(event) => changeHourly({ maxSteps: Number(event.target.value) })}>
              <option value={0}>최대 제한 없음</option>
              {Array.from({ length: Math.max(0, blocks) }, (_, i) => i + 1).filter((count) => count >= form.hourly.minSteps)
                .map((count) => <option key={count} value={count}>최대 {duration(count * form.hourly.step)}</option>)}</select>
          </Setting>
        </>}

        <Setting name="같은 시간 최대" hint={byPeople ? '예약 인원을 더해 셉니다' : '예약 한 건이 한 자리입니다'}>
          <Segmented label="세는 기준" value={form.capacityBy} onChange={(capacityBy) => change({ capacityBy })}
            options={[{ value: 'bookings', label: '건수' }, { value: 'people', label: '인원' }]} />
          <Stepper label="같은 시간 최대" min={1} value={form.limit} unit={byPeople ? '명' : '건'} onChange={(limit) => change({ limit })} />
          <p className="setting-help">항목에 따로 넣은 {byPeople ? '정원' : '수'}가 있으면 그 값을 씁니다.</p>
        </Setting>

        <Setting name="1인 예약">
          <Stepper label="1인 예약 수" min={0} max={100} zeroLabel="제한 없음" unit="건" value={form.perPerson.limit}
            onChange={(limit) => change({ perPerson: { ...form.perPerson, limit } })} />
          {form.perPerson.limit > 0 && <Segmented label="세는 기간" value={form.perPerson.per} onChange={(per) => change({ perPerson: { ...form.perPerson, per } })}
            options={[{ value: 'day', label: '하루에' }, { value: 'upcoming', label: '예약해 둔 것 합쳐서' }]} />}
          {form.perPerson.limit > 0 && <p className="setting-help">전화번호가 같으면 같은 사람으로 셉니다.</p>}
        </Setting>

        <Setting name="휴무 요일">
          <div className="chip-group weekday-chips">{WEEKDAY_NAMES.map((name, day) => {
            const closed = form.closedWeekdays.includes(day);
            return <button type="button" key={name} className={`chip${closed ? ' is-selected' : ''}`} aria-pressed={closed}
              onClick={() => change({ closedWeekdays: closed ? form.closedWeekdays.filter((item) => item !== day) : [...form.closedWeekdays, day].sort() })}>{name}</button>;
          })}</div>
        </Setting>
      </fieldset>

      <div className="rules-footer">
        <p className="muted">{availabilityNote(form)}</p>
        {error && <p className="error" role="alert">{error}</p>}
        {message && <p className="notice" role="status">{message}</p>}
        <div className="dialog-actions">
          {!target && info?.defaults && <button type="button" className="text-button tone-warn" onClick={() => { setForm(withDefaults(info.defaults)); setMessage(''); }}>시트 기준으로 되돌리기</button>}
          {ownsRules && <button type="button" className="text-button tone-danger" onClick={() => window.confirm(`"${target.name}"의 규칙을 지우고 상위 규칙을 따르게 할까요?`)
            && send(null, '항목 규칙을 지웠습니다.')}>항목 규칙 지우기</button>}
          <button type="submit" disabled={busy || !csrf}>{busy ? '저장 중…' : '저장'}</button>
        </div>
      </div>
    </form>
  </section>;
}
