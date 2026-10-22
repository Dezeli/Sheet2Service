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
  const [draftBusy, setDraftBusy] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [pendingCandidates, setPendingCandidates] = useState([]);
  const [messages, setMessages] = useState(() => savedMessages(storageKey));
  const endRef = useRef(null);

  useEffect(() => {
    try { sessionStorage.setItem(storageKey, JSON.stringify(messages.slice(-20))); } catch { /* Storage may be unavailable. */ }
    if (open) endRef.current?.scrollIntoView({ block: 'end' });
  }, [messages, open, storageKey]);

  useEffect(() => {
    if (!open) return undefined;
    let active = true;
    fetch(`/api/uploads/${uploadId}/component-candidates/`, { credentials: 'same-origin' })
      .then((response) => response.ok ? response.json() : { items: [] })
      .then((value) => { if (active) setPendingCandidates(value.items || []); })
      .catch(() => { if (active) setPendingCandidates([]); });
    return () => { active = false; };
  }, [open, uploadId]);

  async function submit(event) {
    event.preventDefault();
    const prompt = request.trim();
    if (busy || draftBusy !== null || !csrf || prompt.length < 10 || prompt.length > 500) return;
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
      setMessages((current) => [...current, { role: 'assistant', text: result.message,
        candidateIds: result.candidates?.map((item) => item.id) || [] }].slice(-20));
    } catch (caught) {
      setMessages((current) => [...current, { role: 'assistant', text: caught.message, error: true }].slice(-20));
    } finally { setBusy(false); }
  }

  async function generateDraft(candidateId) {
    if (busy || draftBusy !== null || !csrf) return;
    setDraftBusy(candidateId);
    const base = `/api/uploads/${uploadId}/component-drafts/`;
    try {
      const approval = await api(`${base}approval/`, { candidate_id: candidateId }, csrf);
      const draft = approval.already_generated ? approval.draft : await api(`${base}generate/`, {
        candidate_id: candidateId, approved: true,
        request_fingerprint: approval.request_fingerprint,
        approval_note: '부품 초안 생성 버튼으로 Claude API 1회 호출 승인',
      }, csrf);
      setDrafts((current) => ({ ...current, [candidateId]: draft.content }));
    } catch (caught) {
      setMessages((current) => [...current, { role: 'assistant', text: caught.message, error: true }].slice(-20));
    } finally { setDraftBusy(null); }
  }

  function draftAction(candidateId) {
    return <div key={candidateId} className="blueprint-draft-action">
      <small>미구현 부품 후보 #{candidateId}. 초안 소스는 검증 전이며 서비스에 적용되지 않습니다.</small>
      {!drafts[candidateId] && <>
        <small>이 후보의 기능·요구·판단 근거와 관련 후보 메타데이터를 Claude에 보냅니다. 버튼을 누르면 1회 호출하며 자동 재시도하지 않습니다.</small>
        <button type="button" disabled={busy || draftBusy !== null}
          onClick={() => generateDraft(candidateId)}>
          {draftBusy === candidateId ? '초안 생성 중...' : 'Claude 1회 호출하여 부품 초안 생성'}
        </button>
      </>}
      {drafts[candidateId] && <div className="blueprint-draft-result">
        <strong>{drafts[candidateId].status === 'draft' ? '생성된 소스 초안' : '추가 정보 필요'}</strong>
        <p>{drafts[candidateId].status === 'draft' ? drafts[candidateId].summary : drafts[candidateId].question}</p>
        {drafts[candidateId].files?.map((file) => <details key={file.role}>
          <summary>{file.role}</summary><pre>{file.source}</pre>
        </details>)}
      </div>}
    </div>;
  }

  const messageCandidateIds = new Set(messages.flatMap((item) => item.candidateIds || []));

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
        {pendingCandidates.filter((item) => !messageCandidateIds.has(item.id)).map((item) =>
          <div key={item.id} className="blueprint-chat-message assistant">
            <span>저장된 미구현 후보</span>{draftAction(item.id)}
          </div>)}
        {messages.map((item, index) => <div key={index}
          className={`blueprint-chat-message ${item.role}${item.error ? ' error' : ''}`}>
          <span>{item.role === 'user' ? '나' : 'Claude'}</span>{item.text}
          {item.candidateIds?.map(draftAction)}
        </div>)}
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
        <p>CSV 컬럼 분석과 최대 10개 예시 행, 현재 서비스 설정, 현재 화면, 입력한 요청, 부품 등록부 메타데이터를 Claude에 보냅니다. 버튼을 누르면 Claude API를 1회 호출하며 자동 재시도하지 않습니다.</p>
        <button type="submit" disabled={busy || draftBusy !== null || !csrf || request.trim().length < 10}>
          {busy ? '수정 중...' : 'Claude 1회 호출하여 수정'}</button>
      </form>
    </aside>}
  </>;
}
