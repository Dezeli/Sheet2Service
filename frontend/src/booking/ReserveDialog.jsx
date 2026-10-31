import React, { useEffect, useState } from 'react';
import ServiceDialog from '../components/ServiceDialog';
import { api, jsonOptions, query, whenText } from './api.js';

const today = () => new Date().toISOString().slice(0, 10);

/** Reserve one resource. The fields follow the time model the sheet revealed. */
export default function ReserveDialog({ uploadId, service, persona, csrf, resource, slot: presetSlot, onClose, onDone }) {
  const booking = service.booking;
  const [slots, setSlots] = useState(null);
  const [slot, setSlot] = useState(presetSlot || null);
  const [form, setForm] = useState({ date: today(), starts_at: '', ends_at: '', time_slot: '', party_size: '', booker: '', purpose: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const usesSlots = service.sheetKind === 'schedule_slots';

  useEffect(() => {
    if (!usesSlots || presetSlot || !resource) return;
    let active = true;
    api(`/api/uploads/${uploadId}/slots/${query({ resource: resource.id, available: 1 })}`)
      .then((data) => { if (active) setSlots(data.slots); })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId, resource, usesSlots, presetSlot]);

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError('');
    const body = { persona: persona.id, booker: form.booker, purpose: form.purpose };
    if (form.party_size) body.party_size = Number(form.party_size);
    if (slot) body.slot_id = slot.id;
    else {
      body.resource_id = resource.id;
      const model = booking.timeModel;
      if (model === 'date' || model === 'date_slot') body.date = form.date;
      if (model === 'date_slot' && form.time_slot) body.time_slot = form.time_slot;
      if (model === 'range' || model === 'start') body.starts_at = form.starts_at ? new Date(form.starts_at).toISOString() : '';
      if (model === 'range') body.ends_at = form.ends_at ? new Date(form.ends_at).toISOString() : '';
    }
    try {
      const created = await api(`/api/uploads/${uploadId}/bookings/`, jsonOptions('POST', csrf, body));
      onDone(created);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  const title = slot ? `${slot.resource_name || resource?.name || ''} 예약` : `${resource?.name || ''} 예약`;
  const needsName = Boolean(booking.bookerColumn);
  const model = booking.timeModel;
  return <ServiceDialog title={title} busy={busy} error={error} onClose={onClose} className="reserve-dialog">
    <form onSubmit={submit}><fieldset className="inquiry-form" disabled={busy}>
      {resource && <p className="muted">{resource.path}</p>}
      {usesSlots && !presetSlot && <div>
        <span className="field-label">회차 선택</span>
        {slots === null && <p className="muted">회차를 불러오는 중입니다.</p>}
        {slots && !slots.length && <p className="muted">예약할 수 있는 회차가 없습니다.</p>}
        {slots && slots.length > 0 && <ul className="slot-picker">{slots.map((item) => <li key={item.id}>
          <label><input type="radio" name="slot" checked={slot?.id === item.id} onChange={() => setSlot(item)} />
            <span>{whenText(item)}</span>
            <span className="muted">{item.remaining === null ? '정원 제한 없음' : `잔여 ${item.remaining}`}</span></label>
        </li>)}</ul>}
      </div>}
      {slot && <p className="reserve-when">{whenText(slot)}{slot.remaining !== null && slot.remaining !== undefined && <span className="muted"> · 잔여 {slot.remaining}</span>}</p>}
      {!slot && !usesSlots && (model === 'date' || model === 'date_slot') &&
        <label>이용 날짜<input type="date" required min={today()} value={form.date} onChange={(event) => setForm({ ...form, date: event.target.value })} /></label>}
      {!slot && !usesSlots && model === 'date_slot' &&
        <label>시간대<input type="text" maxLength={120} placeholder="예: 10:00~12:00" value={form.time_slot} onChange={(event) => setForm({ ...form, time_slot: event.target.value })} /></label>}
      {!slot && !usesSlots && (model === 'range' || model === 'start') &&
        <label>시작<input type="datetime-local" required value={form.starts_at} onChange={(event) => setForm({ ...form, starts_at: event.target.value })} /></label>}
      {!slot && !usesSlots && model === 'range' &&
        <label>종료<input type="datetime-local" required value={form.ends_at} onChange={(event) => setForm({ ...form, ends_at: event.target.value })} /></label>}
      <label>예약자 이름{needsName ? '' : ' (선택)'}<input type="text" required={needsName} maxLength={200} value={form.booker}
        onChange={(event) => setForm({ ...form, booker: event.target.value })} /></label>
      <label>인원 (선택)<input type="number" min={1} max={100000} value={form.party_size} onChange={(event) => setForm({ ...form, party_size: event.target.value })} /></label>
      <label>요청 사항·목적 (선택)<textarea maxLength={2000} value={form.purpose} onChange={(event) => setForm({ ...form, purpose: event.target.value })} /></label>
      <p className="muted">{booking.approvalRequired ? '신청 후 관리자가 승인하면 예약이 확정됩니다.' : '신청하면 바로 예약이 확정됩니다.'}</p>
      <div className="admin-row-actions">
        <button type="submit" data-intent="primary" disabled={busy || !csrf || (usesSlots && !slot)}>{busy ? '접수 중…' : booking.approvalRequired ? '예약 신청' : '예약하기'}</button>
        <button type="button" className="service-back-button" disabled={busy} onClick={onClose}>취소</button>
      </div>
    </fieldset></form>
  </ServiceDialog>;
}
