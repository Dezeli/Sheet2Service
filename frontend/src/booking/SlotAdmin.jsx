import React, { useEffect, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import ServiceDialog from '../components/ServiceDialog';
import { api, jsonOptions, query, whenText } from './api.js';

const today = () => new Date().toISOString().slice(0, 10);

/** Time slots and their capacity: the sheet's own 회차 plus whatever the admin opens. */
export default function SlotAdmin({ uploadId, service, persona, csrf }) {
  const [resources, setResources] = useState([]);
  const [resource, setResource] = useState('');
  const [resourceQuery, setResourceQuery] = useState('');
  const [list, setList] = useState({ slots: [], page: 1, count: 0, has_next: false });
  const [upcoming, setUpcoming] = useState(true);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ date: today(), time_slot: '', starts_at: '', ends_at: '', capacity: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    api(`/api/uploads/${uploadId}/resources/${query({ q: resourceQuery, all: 1 })}`)
      .then((data) => setResources(data.resources.filter((item) => item.children_count === 0 || resourceQuery)))
      .catch((caught) => setError(caught.message));
  }, [uploadId, resourceQuery]);

  async function load(page = 1) {
    try {
      setList(await api(`/api/uploads/${uploadId}/slots/${query({ page, resource, from: upcoming ? today() : '' })}`));
      setError('');
    } catch (caught) { setError(caught.message); }
  }
  useEffect(() => { load(1); }, [uploadId, resource, upcoming]);

  async function create(event) {
    event.preventDefault();
    if (busy || !csrf) return;
    setBusy(true); setError('');
    const body = { persona: persona.id, resource_id: resource || undefined, date: form.date || undefined, time_slot: form.time_slot,
      starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : undefined,
      ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : undefined,
      capacity: form.capacity === '' ? null : Number(form.capacity) };
    try {
      await api(`/api/uploads/${uploadId}/slots/`, jsonOptions('POST', csrf, body));
      setMessage('일정을 추가했습니다.'); setCreating(false); await load(1);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  async function patch(slot, changes, text) {
    if (busy || !csrf) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await api(`/api/uploads/${uploadId}/slots/${slot.id}/`, jsonOptions('PATCH', csrf, { persona: persona.id, ...changes }));
      setMessage(text); await load(list.page);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  async function remove(slot) {
    if (busy || !csrf || !window.confirm('이 일정을 삭제할까요?')) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await api(`/api/uploads/${uploadId}/slots/${slot.id}/`, jsonOptions('DELETE', csrf, { persona: persona.id }));
      setMessage('일정을 삭제했습니다.'); await load(list.page);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  function changeCapacity(slot) {
    const value = window.prompt('정원을 입력하세요. 비우면 제한 없음.', slot.capacity ?? '');
    if (value === null) return;
    patch(slot, { capacity: value.trim() === '' ? null : Number(value) }, '정원을 변경했습니다.');
  }

  return <section className="panel">
    <div className="section-title"><h2 className="icon-heading"><SectionIcon name="reservation" />일정·정원</h2>
      <button type="button" data-intent="primary" disabled={busy || !csrf} onClick={() => { setError(''); setCreating(true); }}>일정 추가</button></div>
    <p className="muted">시트에 있던 회차는 참가 기록과 함께 들어왔습니다. 정원을 두면 잔여 자리를 넘는 예약은 막힙니다.</p>
    <div className="booking-filters">
      <input type="search" aria-label="항목 검색" placeholder="항목 검색" maxLength={100} value={resourceQuery} onChange={(event) => setResourceQuery(event.target.value)} />
      <select aria-label="항목" value={resource} onChange={(event) => setResource(event.target.value)}>
        <option value="">모든 항목</option>
        {resources.map((item) => <option key={item.id} value={item.id}>{item.path}</option>)}
      </select>
      <label className="check-label"><input type="checkbox" checked={upcoming} onChange={(event) => setUpcoming(event.target.checked)} /> 오늘 이후만</label>
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="table-scroll" role="region" aria-label="일정 목록" tabIndex={0}>
      <table className="booking-table">
        <thead><tr><th scope="col">항목</th><th scope="col">일시</th><th scope="col">정원</th><th scope="col">기록·예약</th><th scope="col">상태</th><th scope="col">관리</th></tr></thead>
        <tbody>{list.slots.map((slot) => <tr key={slot.id}>
          <td>{slot.resource_name || '-'}</td>
          <td>{whenText(slot) || '-'}</td>
          <td>{slot.capacity ?? '제한 없음'}</td>
          <td>{slot.imported_count ? `기록 ${slot.imported_count}` : ''}{slot.imported_count && slot.booked ? ' · ' : ''}{slot.booked ? `예약 ${slot.booked}` : ''}{!slot.imported_count && !slot.booked ? '-' : ''}{slot.remaining !== null ? <small className="muted"> (잔여 {slot.remaining})</small> : null}</td>
          <td>{slot.closed ? '마감' : '접수 중'}</td>
          <td><div className="booking-actions">
            <button type="button" data-intent="secondary" disabled={busy} onClick={() => changeCapacity(slot)}>정원</button>
            <button type="button" data-intent="secondary" disabled={busy} onClick={() => patch(slot, { closed: !slot.closed }, slot.closed ? '접수를 다시 받습니다.' : '마감했습니다.')}>{slot.closed ? '접수 재개' : '마감'}</button>
            <button type="button" className="admin-danger" disabled={busy} onClick={() => remove(slot)}>삭제</button>
          </div></td>
        </tr>)}</tbody>
      </table>
    </div>
    {!list.slots.length && <p className="muted">일정이 없습니다.</p>}
    {message && <p className="notice" role="status">{message}</p>}
    <nav className="service-pagination" aria-label="일정 페이지">
      <button type="button" disabled={busy || list.page === 1} onClick={() => load(list.page - 1)}>이전</button>
      <span>{list.page} / {Math.max(1, Math.ceil(list.count / 20))}</span>
      <button type="button" disabled={busy || !list.has_next} onClick={() => load(list.page + 1)}>다음</button>
    </nav>
    {creating && <ServiceDialog title="일정 추가" busy={busy} error={error} onClose={() => setCreating(false)}>
      <form onSubmit={create}><fieldset className="inquiry-form" disabled={busy}>
        <label>항목<select required={resources.length > 0} value={resource} onChange={(event) => setResource(event.target.value)}>
          <option value="">선택해 주세요</option>
          {resources.map((item) => <option key={item.id} value={item.id}>{item.path}</option>)}
        </select></label>
        <label>날짜<input type="date" value={form.date} onChange={(event) => setForm({ ...form, date: event.target.value })} /></label>
        <label>시간대 표기 (선택)<input type="text" maxLength={120} placeholder="예: 오전10시~12시" value={form.time_slot} onChange={(event) => setForm({ ...form, time_slot: event.target.value })} /></label>
        <label>시작 (선택)<input type="datetime-local" value={form.starts_at} onChange={(event) => setForm({ ...form, starts_at: event.target.value })} /></label>
        <label>종료 (선택)<input type="datetime-local" value={form.ends_at} onChange={(event) => setForm({ ...form, ends_at: event.target.value })} /></label>
        <label>정원 (선택)<input type="number" min={1} max={100000} value={form.capacity} onChange={(event) => setForm({ ...form, capacity: event.target.value })} /></label>
        <div className="admin-row-actions"><button type="submit" data-intent="primary" disabled={busy || !csrf}>추가</button>
          <button type="button" className="service-back-button" onClick={() => setCreating(false)}>취소</button></div>
      </fieldset></form>
    </ServiceDialog>}
  </section>;
}
