import React, { useEffect, useState } from 'react';
import './workflow.css';

const labels = {
  request_review: '신청 후 승인', request_auto: '신청 즉시 접수', browse_only: '목록 둘러보기',
  review_requests: '신청 승인·거절', monitor_requests: '신청 현황 관리', manage_catalog: '목록·접수 관리',
};
const compatible = {
  request_review: 'review_requests', request_auto: 'monitor_requests', browse_only: 'manage_catalog',
};

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.detail || '요청을 처리하지 못했습니다.');
  return data;
}

export default function WorkflowReview({ uploadId, csrfToken, onApplied }) {
  const [proposal, setProposal] = useState(null);
  const [selected, setSelected] = useState({ user: null, admin: null });
  const [custom, setCustom] = useState(null);
  const [description, setDescription] = useState('');
  const [preflight, setPreflight] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [applied, setApplied] = useState(false);

  async function load() {
    const result = await api(`/api/uploads/${uploadId}/workflow/`);
    setProposal(result);
    if (result.selected) setApplied(true);
    return result;
  }

  useEffect(() => { load().catch((caught) => setError(caught.message)); }, [uploadId]);

  function select(scope, option) {
    setSelected((current) => ({ ...current, [scope]: option }));
    setApplied(false);
    setError('');
  }

  function startCustom(scope) {
    setCustom(scope); setDescription(''); setPreflight(null); setError('');
  }

  async function previewCustom(event) {
    event.preventDefault();
    setBusy(true); setError('');
    try {
      const result = await api(`/api/uploads/${uploadId}/workflow/custom-preview/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ scope: custom, description }),
      });
      setPreflight(result);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  async function runCustom() {
    if (!preflight || busy) return;
    setBusy(true); setError('');
    try {
      const result = await api(`/api/uploads/${uploadId}/workflow/custom-run/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ scope: custom, description, approved: true,
          approval_note: `${custom} 맞춤 플로우 제안 Claude API 1회 호출 승인`,
          request_fingerprint: preflight.request_fingerprint }),
      });
      const updated = await load();
      const option = updated.options[custom].find((item) => item.model_call_id === result.model_call_id);
      if (option) select(custom, option);
      setCustom(null); setPreflight(null);
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  async function apply() {
    if (!selected.user || !selected.admin || busy) return;
    setBusy(true); setError('');
    try {
      await api(`/api/uploads/${uploadId}/workflow/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ user: { model_call_id: selected.user.model_call_id, index: selected.user.index },
          admin: { model_call_id: selected.admin.model_call_id, index: selected.admin.index } }),
      });
      setApplied(true);
      onApplied?.();
    } catch (caught) { setError(caught.message); }
    finally { setBusy(false); }
  }

  if (!proposal) return <section className="panel"><p>서비스 구성을 불러오는 중입니다.</p>{error && <p className="error">{error}</p>}</section>;
  const mismatch = selected.user && selected.admin
    && compatible[selected.user.template] !== selected.admin.template;

  return <section className="panel workflow-review" aria-labelledby="workflow-title">
    <p className="eyebrow">SERVICE SETUP</p><h2 id="workflow-title">서비스 흐름 선택</h2>
    <div className="workflow-summary"><small>이 CSV의 한 줄 요약</small>
      <p>{proposal.service_summary || '기존 Preview 결과에는 서비스 요약이 없습니다. 원하는 흐름을 직접 설명해 주세요.'}</p></div>
    {['user', 'admin'].map((scope) => <div key={scope} className="workflow-section">
      <div className="section-title"><h3>{scope === 'user' ? '유저 플로우' : '관리자 플로우'}</h3>
        <span className="muted">한 가지를 선택해 주세요.</span></div>
      <div className="workflow-options">{proposal.options[scope].map((option, index) => {
        const active = selected[scope]?.model_call_id === option.model_call_id
          && selected[scope]?.index === option.index;
        return <button type="button" key={`${option.model_call_id}-${option.index}`}
          className="workflow-option" aria-pressed={active} onClick={() => select(scope, option)}>
          <span className="workflow-option-number">{index + 1}</span><strong>{labels[option.template]}</strong>
          <ol>{option.steps.map((step, at) => <li key={at}>{step}</li>)}</ol>
          <small>대상 항목: {option.subjectColumn}번 필드</small>
        </button>;
      })}
        <button type="button" className="workflow-option workflow-other" onClick={() => startCustom(scope)}>
          <span className="workflow-option-number">그외</span><strong>원하는 흐름 직접 설명</strong>
          <p>원하는 동작을 짧게 적고, 전송 내용을 확인한 뒤 새 후보를 받아보세요.</p>
        </button>
      </div>
    </div>)}
    {custom && <form className="workflow-custom" onSubmit={previewCustom}>
      <div className="section-title"><h3>{custom === 'user' ? '유저' : '관리자'} 플로우 직접 설명</h3>
        <button type="button" className="service-back-button" onClick={() => { setCustom(null); setPreflight(null); }}>닫기</button></div>
      <label>원하는 흐름
        <textarea value={description} minLength={10} maxLength={500} required
          onChange={(event) => { setDescription(event.target.value); setPreflight(null); }}
          placeholder="예: 유저가 항목을 선택해 신청하면 관리자가 승인하거나 거절합니다." />
      </label>
      <button type="submit" disabled={busy || description.trim().length < 10}>전송 범위 확인</button>
      {preflight && <div className="workflow-preflight">
        <h4>Claude API 호출 전 확인</h4>
        <p>목적: {preflight.purpose}</p>
        <p>전송: 입력한 설명, CSV의 열 이름·분석 유형·행 수. 원본 CSV와 데이터 예시 행은 보내지 않습니다.</p>
        <blockquote>{preflight.transmitted_data.user_description}</blockquote>
        <p>열 이름: {preflight.transmitted_data.column_names_and_types.join(', ')}</p>
        <p>모델: {preflight.model} · 계획된 호출: {preflight.planned_call_count}회 · 자동 재시도: {preflight.automatic_retries}회</p>
        <p>{preflight.cost_note}</p>
        <button type="button" onClick={runCustom} disabled={busy || !preflight.pricing_estimate_available}>
          {busy ? '후보를 만드는 중...' : 'Claude API 1회 호출 승인'}
        </button>
      </div>}
    </form>}
    {mismatch && <p className="notice">선택한 두 흐름이 연결되지 않습니다. 유저 플로우에 맞는 관리자 플로우를 선택해 주세요.</p>}
    {error && <p className="error" role="alert">{error}</p>}
    <div className="workflow-apply"><button type="button" disabled={busy || !selected.user || !selected.admin || mismatch} onClick={apply}>
      선택한 흐름으로 Preview 생성
    </button></div>
    {applied && <div className="workflow-ready"><p>선택한 흐름을 적용했습니다.</p>
      <a href={`/${uploadId}/User`} target="_blank" rel="noopener noreferrer">User 열기</a>
      <a href={`/${uploadId}/DashBoard`} target="_blank" rel="noopener noreferrer">Dashboard 열기</a>
      <a href={`/${uploadId}/Admin`} target="_blank" rel="noopener noreferrer">Admin 열기</a>
    </div>}
  </section>;
}
