import React, { useEffect, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import ServiceDialog from '../components/ServiceDialog';
import { api, jsonOptions, query, whenText } from './api.js';
import ResourceCombobox from './ResourceCombobox';
import { Empty, Icon, IconButton, Pager, Seats, Stepper, TimeField } from '../components/ui';

const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };

/** Time slots and their capacity: the sheet's own 회차 plus whatever the admin opens. */
export default function SlotAdmin({ uploadId, service, persona, csrf }) {
  const [resource, setResource] = useState(null);
  const [list, setList] = useState({ slots: [], page: 1, count: 0, has_next: false });
  const [upcoming, setUpcoming] = useState(true);
  const [creating, setCreating] = useState(false);
  const [capacityOf, setCapacityOf] = useState(null);
  const [form, setForm] = useState({ date: today(), start: '', end: '', capacity: 0 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function load(page = 1) {
    try {
      setList(await api(`/api/uploads/${uploadId}/slots/${query({ page, resource: resource?.id, from: upcoming ? today() : '' })}`));
      setError('');
    } catch (caught) { setError(caught.message); }
  }
  useEffect(() => { load(1); }, [uploadId, resource?.id, upcoming]);

  async function create(event) {
    event.preventDefault();
    if (busy || !csrf) return;
    setBusy(true); setError('');
    const at = (clock) => (clock ? new Date(`${form.date}T${clock}:00`).toISOString() : undefined);
    const body = { persona: persona.id, resource_id: resource?.id, date: form.date || undefined,
      time_slot: form.start && form.end ? `${form.start}~${form.end}` : '', starts_at: form.start && form.end ? at(form.start) : undefined,
      ends_at: form.start && form.end ? at(form.end) : undefined, capacity: form.capacity || null };
    try {
      await api(`/api/uploads/${uploadId}/slots/`, jsonOptions('POST', csrf, body));
      setMessage('회차를 추가했습니다.'); setCreating(false); await load(1);
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
    if (busy || !csrf || !window.confirm('이 회차를 삭제할까요?')) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await api(`/api/uploads/${uploadId}/slots/${slot.id}/`, jsonOptions('DELETE', csrf, { persona: persona.id }));
      setMessage('회차를 삭제했습니다.'); await load(list.page);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  async function saveCapacity(event) {
    event.preventDefault();
    await patch(capacityOf.slot, { capacity: capacityOf.value || null }, '정원을 바꿨습니다.');
    setCapacityOf(null);
  }

  return <section className="panel">
    <div className="section-title"><h2 className="icon-heading"><SectionIcon name="schedule" />회차·정원</h2>
      <span className="section-tools"><span className="section-count">{list.count.toLocaleString()}개</span>
        <button type="button" data-intent="primary" className="with-icon" disabled={busy || !csrf} onClick={() => { setError(''); setCreating(true); }}><Icon name="plus" size={16} />회차 추가</button></span></div>
    <div className="ui-toolbar">
      <ResourceCombobox uploadId={uploadId} value={resource} onChange={setResource} leafOnly label="항목" placeholder="모든 항목" />
      <label className="ui-check"><input type="checkbox" checked={upcoming} onChange={(event) => setUpcoming(event.target.checked)} />지난 회차 숨기기</label>
    </div>
    {error && !creating && <p className="error" role="alert">{error}</p>}
    {message && <p className="notice" role="status">{message}</p>}
    {list.slots.length > 0 && <div className="table-scroll" role="region" aria-label="회차 목록" tabIndex={0}>
      <table className="booking-table">
        <thead><tr><th scope="col">항목</th><th scope="col">일시</th><th scope="col" className="num">정원</th><th scope="col" className="num">참가</th><th scope="col">상태</th>
          <th scope="col"><span className="visually-hidden">관리</span></th></tr></thead>
        <tbody>{list.slots.map((slot) => <tr key={slot.id}>
          <td>{slot.resource_name || '-'}</td>
          <td className="cell-when">{whenText(slot) || '-'}</td>
          <td className="num">{slot.capacity ?? <span className="muted">제한 없음</span>}</td>
          <td className="num">{(slot.imported_count + slot.booked).toLocaleString()}{slot.remaining !== null && <div><Seats remaining={slot.remaining} total={slot.capacity} unit="명" /></div>}</td>
          <td><span className={`service-badge tone-${slot.closed ? 'muted' : 'ok'}`}>{slot.closed ? '마감' : '접수 중'}</span></td>
          <td className="cell-actions"><div className="ui-actions">
            <IconButton icon="edit" tone="info" label="정원 바꾸기" disabled={busy} onClick={() => setCapacityOf({ slot, value: slot.capacity || 0 })} />
            <IconButton icon={slot.closed ? 'play' : 'pause'} tone={slot.closed ? 'approve' : 'warn'} label={slot.closed ? '접수 재개' : '마감'} disabled={busy}
              onClick={() => patch(slot, { closed: !slot.closed }, slot.closed ? '접수를 다시 받습니다.' : '마감했습니다.')} />
            <IconButton icon="trash" tone="danger" label="삭제" disabled={busy} onClick={() => remove(slot)} />
          </div></td>
        </tr>)}</tbody>
      </table>
    </div>}
    {!list.slots.length && <Empty>회차가 없습니다.</Empty>}
    <Pager page={list.page} count={list.count} disabled={busy} onPage={(page) => load(page)} />
    {capacityOf && <ServiceDialog title="정원" busy={busy} onClose={() => setCapacityOf(null)}>
      <form onSubmit={saveCapacity}><fieldset className="form-grid" disabled={busy}>
        <p className="muted">{capacityOf.slot.resource_name} · {whenText(capacityOf.slot)}</p>
        <Stepper label="정원" min={0} zeroLabel="제한 없음" unit="명" value={capacityOf.value} onChange={(value) => setCapacityOf({ ...capacityOf, value })} />
        <div className="dialog-actions"><button type="submit" disabled={busy || !csrf}>저장</button></div>
      </fieldset></form>
    </ServiceDialog>}
    {creating && <ServiceDialog title="회차 추가" busy={busy} error={error} onClose={() => setCreating(false)}>
      <form onSubmit={create}><fieldset className="form-grid" disabled={busy}>
        <div><span className="field-label">항목</span><ResourceCombobox uploadId={uploadId} value={resource} onChange={setResource} leafOnly label="회차를 만들 항목" /></div>
        <div className="form-row">
          <label>날짜<input type="date" required value={form.date} onChange={(event) => setForm({ ...form, date: event.target.value })} /></label>
          <div><span className="field-label">시간</span><div className="setting-control">
            <TimeField label="시작" value={form.start} onChange={(start) => setForm({ ...form, start })} />
            <span aria-hidden="true">~</span>
            <TimeField label="끝" value={form.end} onChange={(end) => setForm({ ...form, end })} /></div></div>
        </div>
        <div><span className="field-label">정원</span><Stepper label="정원" min={0} zeroLabel="제한 없음" unit="명" value={form.capacity} onChange={(capacity) => setForm({ ...form, capacity })} /></div>
        <div className="dialog-actions"><button type="submit" disabled={busy || !csrf || !resource || !form.date}>추가</button></div>
      </fieldset></form>
    </ServiceDialog>}
  </section>;
}
