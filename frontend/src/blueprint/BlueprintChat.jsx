import React, { useEffect, useRef, useState } from 'react';

const pageLabels = { DashBoard: '대시보드', User: '사용자', Admin: '관리자' };

async function api(url, body, csrf) {
  const response = await fetch(url, { method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify(body) });
  const value = await response.json().catch(() => null);
  if (!response.ok) throw new Error(value?.detail || '요청을 처리하지 못했습니다.');
  return value;
}

function savedMessages(key) {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) || '[]');
    return Array.isArray(value) ? value.filter((item) =>
      ['user', 'assistant'].includes(item?.role) && typeof item.text === 'string').slice(-20) : [];
  } catch { return []; }
}

export default function BlueprintChat({ uploadId, page, csrf, onApplied }) {
  const storageKey = `blueprint-chat:${uploadId}`;
  const [open, setOpen] = useState(false);
  const [request, setRequest] = useState('');
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState(() => savedMessages(storageKey));
  const endRef = useRef(null);

  useEffect(() => {
    try { sessionStorage.setItem(storageKey, JSON.stringify(messages.slice(-20))); } catch { /* Storage may be unavailable. */ }
    if (open) endRef.current?.scrollIntoView({ block: 'end' });
  }, [messages, open, storageKey]);

  async function submit(event) {
    event.preventDefault();
    const prompt = request.trim();
    if (busy || !csrf || prompt.length < 10 || prompt.length > 500) return;
    setBusy(true);
    setRequest('');
    setMessages((current) => [...current, { role: 'user', text: prompt }].slice(-20));
    const base = `/api/uploads/${uploadId}/blueprint/`;
    const payload = { request: prompt, current_page: page };
    try {
      const approval = await api(`${base}approval/`, payload, csrf);
      const result = await api(`${base}revise/`, { ...payload, approved: true,
        request_fingerprint: approval.request_fingerprint,
        approval_note: '서비스 수정 요청 버튼으로 Claude API 1회 호출 승인' }, csrf);
      if (result.status === 'applied') onApplied(result.blueprint);
      setMessages((current) => [...current, { role: 'assistant', text: result.message }].slice(-20));
    } catch (caught) {
      setMessages((current) => [...current, { role: 'assistant', text: caught.message, error: true }].slice(-20));
    } finally { setBusy(false); }
  }

  return <>
    <button type="button" className="blueprint-chat-toggle" aria-expanded={open}
      aria-controls="blueprint-chat-panel" onClick={() => setOpen((value) => !value)}>
      {open ? '수정 요청 닫기' : '서비스 수정 요청'}
    </button>
    {open && <aside id="blueprint-chat-panel" className="blueprint-chat" aria-label="서비스 수정 요청">
      <div className="blueprint-chat-header"><div><strong>서비스 수정 요청</strong>
        <span>현재 화면: {pageLabels[page]}</span></div>
        <button type="button" aria-label="수정 요청 닫기" onClick={() => setOpen(false)}>×</button>
      </div>
      <div className="blueprint-chat-messages" role="log" aria-live="polite">
        <p className="blueprint-chat-intro">대시보드, 사용자, 관리자 화면의 목록·필터·차트·신청 흐름을 요청해 주세요. 현재 화면을 기준으로 “이 화면”이라고 말씀하셔도 됩니다.</p>
        {messages.map((item, index) => <p key={index}
          className={`blueprint-chat-message ${item.role}${item.error ? ' error' : ''}`}>
          <span>{item.role === 'user' ? '나' : 'Claude'}</span>{item.text}
        </p>)}
        {busy && <p className="blueprint-chat-message assistant" role="status">수정 요청을 처리하고 있습니다...</p>}
        <div ref={endRef} />
      </div>
      <form className="blueprint-chat-form" onSubmit={submit}>
        <label htmlFor="blueprint-chat-request">수정할 내용</label>
        <textarea id="blueprint-chat-request" value={request} minLength={10} maxLength={500} rows={3}
          onChange={(event) => setRequest(event.target.value)}
          onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault(); event.currentTarget.form?.requestSubmit();
          } }} placeholder="예: 사용자 목록에 장소 필터를 추가해 줘" />
        <p>CSV 컬럼 분석과 최대 10개 예시 행, 현재 서비스 설정, 현재 화면, 입력한 요청을 Claude에 보냅니다. 버튼을 누르면 Claude API를 1회 호출하며 자동 재시도하지 않습니다.</p>
        <button type="submit" disabled={busy || !csrf || request.trim().length < 10}>
          {busy ? '수정 중...' : 'Claude 1회 호출하여 수정'}</button>
      </form>
    </aside>}
  </>;
}
