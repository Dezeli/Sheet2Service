import React, { useEffect, useState } from 'react';
import './inquiry.css';
import ServiceDialog from '../components/ServiceDialog';
import SectionIcon from '../components/SectionIcon';
import { Empty, Icon, Pager, Segmented } from '../components/ui';
import ResourceCombobox from '../booking/ResourceCombobox';
import { formatPhoneInput, phoneDigits } from '../booking/rules.js';

const labels = { received: '접수', in_progress: '처리 중', resolved: '답변 완료' };
const tones = { received: 'pending', in_progress: 'pending', resolved: 'ok' };
const PAGE_SIZE = 10;
const pinOf = (text) => text.replace(/\D/g, '').slice(0, 4);
const dateText = (value) => new Date(value).toLocaleDateString('ko-KR', { year: 'numeric', month: 'numeric', day: 'numeric' });
const blank = { author: '', phone: '', title: '', body: '', resource: null, isPrivate: true, pin: '', pinAgain: '' };

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) throw new Error(data?.detail || '문의를 처리하지 못했습니다.');
  return data;
}

/**
 * The inquiry board a booker sees: every question, the asker half hidden. A public one opens for anyone;
 * a private one shows only its title until the PIN chosen when asking opens it.
 */
export default function InquiryBoard({ uploadId, withResource = false }) {
  const [list, setList] = useState({ inquiries: [], page: 1, count: 0 });
  const [csrf, setCsrf] = useState('');
  const [writing, setWriting] = useState(null); // the draft while the write dialog is open
  const [asking, setAsking] = useState(null); // the private inquiry whose PIN is being asked
  const [pin, setPin] = useState('');
  const [reading, setReading] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [dialogError, setDialogError] = useState('');
  const [message, setMessage] = useState('');
  const base = `/api/uploads/${uploadId}/inquiries/`;
  const load = (page = 1) => api(`${base}?board=1&size=${PAGE_SIZE}&page=${page}`).then(setList).catch((caught) => setError(caught.message));

  useEffect(() => {
    let active = true;
    Promise.all([api('/api/session/'), api(`${base}?board=1&size=${PAGE_SIZE}&page=1`)])
      .then(([session, result]) => { if (active) { setCsrf(session.csrf_token); setList(result); } })
      .catch((caught) => { if (active) setError(caught.message); });
    return () => { active = false; };
  }, [uploadId]);

  const pinOk = !writing?.isPrivate || (writing.pin.length === 4 && writing.pin === writing.pinAgain);
  const canSend = writing && writing.author.trim() && writing.title.trim() && writing.body.trim() && pinOk
    && (!writing.phone || phoneDigits(writing.phone));

  async function send(event) {
    event.preventDefault();
    if (busy || !csrf || !canSend) return;
    setBusy(true); setDialogError('');
    try {
      const created = await api(base, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ author: writing.author.trim(), title: writing.title, body: writing.body, is_private: writing.isPrivate,
          ...(writing.phone ? { phone: phoneDigits(writing.phone) } : {}), ...(writing.isPrivate ? { password: writing.pin } : {}),
          ...(writing.resource ? { resource_id: writing.resource.id } : {}) }) });
      setWriting(null); setMessage('문의를 남겼습니다. 답변이 달리면 이 목록에서 확인할 수 있습니다.');
      await load(1); setReading(created);
    } catch (caught) { setDialogError(caught.message); }
    finally { setBusy(false); }
  }

  function open(item) {
    setDialogError(''); setMessage('');
    if (item.locked) { setPin(''); setAsking(item); } else setReading(item);
  }
  async function unlock(event) {
    event.preventDefault();
    if (busy || !csrf || pin.length !== 4) return;
    setBusy(true); setDialogError('');
    try {
      const opened = await api(`${base}${asking.id}/unlock/`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ password: pin }) });
      setAsking(null); setReading(opened); load(list.page);
    } catch (caught) { setDialogError(caught.message); setPin(''); }
    finally { setBusy(false); }
  }

  return <section className="panel inquiry-board">
    <div className="board-head">
      <div><h2 className="icon-heading"><SectionIcon name="inquiry" />문의</h2>
        <p className="board-head__sub">궁금한 점을 남기면 담당자가 답변합니다. 비공개 문의는 비밀번호로만 열립니다.</p></div>
      <button type="button" data-intent="primary" className="with-icon" onClick={() => { setDialogError(''); setWriting({ ...blank }); }}>
        <Icon name="edit" size={16} />문의하기</button>
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p className="notice" role="status">{message}</p>}
    {!list.inquiries.length && <Empty>아직 문의가 없습니다. 첫 문의를 남겨 보세요.</Empty>}
    {list.inquiries.length > 0 && <ol className="board-list">{list.inquiries.map((item, index) => <li key={item.id}>
      <button type="button" onClick={() => open(item)}>
        <span className="board-list__no">{list.count - ((list.page - 1) * (list.size || PAGE_SIZE) + index)}</span>
        <span className={`service-badge tone-${tones[item.status]}`}>{labels[item.status]}</span>
        <span className="board-list__title">{item.is_private && <Icon name="lock" size={14} />}<strong>{item.title}</strong></span>
        <span className="board-list__author">{item.author || '-'}</span>
        <time className="board-list__date" dateTime={item.created_at}>{dateText(item.created_at)}</time>
      </button>
    </li>)}</ol>}
    <Pager page={list.page} count={list.count} size={list.size || PAGE_SIZE} disabled={busy} onPage={load} />

    {writing && <ServiceDialog title="문의하기" busy={busy} error={dialogError} onClose={() => setWriting(null)} className="inquiry-write">
      <form onSubmit={send}><fieldset className="inquiry-write__grid" disabled={busy}>
        <label>이름<input required maxLength={200} autoComplete="off" value={writing.author} onChange={(event) => setWriting({ ...writing, author: event.target.value })} /></label>
        <label>전화번호 (선택)<input type="tel" inputMode="tel" maxLength={13} autoComplete="off" value={writing.phone}
          aria-invalid={writing.phone.length >= 12 && !phoneDigits(writing.phone)} onChange={(event) => setWriting({ ...writing, phone: formatPhoneInput(event.target.value) })} />
          <small className="muted">담당자가 연락할 때만 쓰고 목록에는 나오지 않습니다.</small></label>
        {withResource && <div className="inquiry-write__wide"><span className="field-label">관련 항목 (선택)</span>
          <ResourceCombobox uploadId={uploadId} value={writing.resource} onChange={(resource) => setWriting({ ...writing, resource })} leafOnly label="관련 항목" placeholder="일반 문의" /></div>}
        <label className="inquiry-write__wide">제목<input required maxLength={120} value={writing.title} onChange={(event) => setWriting({ ...writing, title: event.target.value })} /></label>
        <label className="inquiry-write__wide">내용<textarea required rows={6} maxLength={5000} value={writing.body} onChange={(event) => setWriting({ ...writing, body: event.target.value })} /></label>
        <div className="inquiry-write__wide inquiry-write__privacy">
          <Segmented label="공개 여부" value={writing.isPrivate} onChange={(isPrivate) => setWriting({ ...writing, isPrivate })}
            options={[{ value: true, label: '비공개' }, { value: false, label: '공개' }]} />
          <small className="muted">{writing.isPrivate ? '비밀번호를 아는 사람만 내용과 답변을 볼 수 있습니다.' : '누구나 내용과 답변을 볼 수 있습니다. 같은 궁금증이 있는 분께 도움이 됩니다.'}</small>
        </div>
        {writing.isPrivate && <>
          <label>비밀번호<input type="password" inputMode="numeric" required maxLength={4} autoComplete="new-password" placeholder="숫자 4자리"
            value={writing.pin} onChange={(event) => setWriting({ ...writing, pin: pinOf(event.target.value) })} /></label>
          <label>비밀번호 확인<input type="password" inputMode="numeric" required maxLength={4} autoComplete="new-password" placeholder="한 번 더"
            aria-invalid={writing.pinAgain.length === 4 && writing.pin !== writing.pinAgain} value={writing.pinAgain} onChange={(event) => setWriting({ ...writing, pinAgain: pinOf(event.target.value) })} />
            {writing.pinAgain.length === 4 && writing.pin !== writing.pinAgain && <small className="reserve-pin__note is-bad">두 비밀번호가 다릅니다.</small>}</label>
        </>}
        <div className="inquiry-write__wide dialog-actions"><button type="submit" data-intent="primary" disabled={!csrf || !canSend}>{busy ? '보내는 중…' : '문의 남기기'}</button></div>
      </fieldset></form>
    </ServiceDialog>}

    {asking && <ServiceDialog title="비공개 문의" busy={busy} error={dialogError} onClose={() => setAsking(null)} className="pin-dialog">
      <form onSubmit={unlock} className="pin-form">
        <p className="muted">{asking.title}</p>
        <label>문의할 때 정한 숫자 4자리<input type="password" inputMode="numeric" autoFocus maxLength={4} autoComplete="off" value={pin}
          onChange={(event) => setPin(pinOf(event.target.value))} /></label>
        <button type="submit" data-intent="primary" disabled={busy || !csrf || pin.length !== 4}>{busy ? '확인 중…' : '열기'}</button>
      </form>
    </ServiceDialog>}

    {reading && <ServiceDialog title={reading.title} onClose={() => setReading(null)} className="inquiry-read">
      <p className="inquiry-read__meta"><span className={`service-badge tone-${tones[reading.status]}`}>{labels[reading.status]}</span>
        {reading.is_private && <span className="inquiry-read__private"><Icon name="lock" size={13} />비공개</span>}
        <span>{reading.author}</span><span>{dateText(reading.created_at)}</span></p>
      {reading.subject && <p className="inquiry-read__subject" title={reading.subject.split(' / ').join(' › ')}>관련 항목 · {reading.subject.split(' / ').at(-1)}</p>}
      <p className="inquiry-text">{reading.body}</p>
      <div className={`inquiry-read__answer${reading.answer ? '' : ' is-waiting'}`}>
        <h3>답변</h3>
        <p className="inquiry-text">{reading.answer || '아직 답변이 없습니다. 담당자가 확인하면 여기에 답변이 달립니다.'}</p>
      </div>
    </ServiceDialog>}
  </section>;
}
