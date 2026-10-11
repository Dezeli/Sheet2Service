import React, { useEffect, useRef, useState } from 'react';
import { featureLabels, recommendedSelection, restoreFeatures, rolesOf, selectedFirst, toggleFeature } from './features';
import './workflow.css';
import SectionIcon from '../components/SectionIcon';

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) throw new Error(data?.detail || '요청을 처리하지 못했습니다.');
  return data;
}

export default function WorkflowReview({ uploadId, csrfToken, onApplied, onBack }) {
  const [proposal, setProposal] = useState(null);
  const [selected, setSelected] = useState([]);
  const [dashboard, setDashboard] = useState([]);
  const [manageData, setManageData] = useState(false);
  const [custom, setCustom] = useState('user');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [applied, setApplied] = useState(false);
  const [customResult, setCustomResult] = useState(null);
  const calling = useRef(false);
  const base = `/api/uploads/${uploadId}/workflow/`;

  async function load(restore = false) {
    const result = await api(base);
    setProposal(result);
    if (restore && result.selected) {
      setSelected(restoreFeatures(result.selected, [...result.recommended, ...result.templates]));
      const roles = rolesOf(result.selected);
      setDashboard(roles.dashboard); setManageData(roles.admin.includes('manage_catalog'));
      setApplied(true);
    } else if (restore) {
      setSelected(recommendedSelection(result.recommended));
      setDashboard(result.dashboard.filter((option) => option.implemented).map((option) => option.template));
      setManageData(result.recommended.some((option) => option.template === 'browse_only' && option.implemented));
    }
    return result;
  }
  useEffect(() => { load(true).catch((caught) => setError(caught.message)); }, [uploadId]);

  function toggle(option) {
    setSelected((current) => toggleFeature(current, option));
    setApplied(false); setError('');
  }

  function toggleDashboard(option) {
    setDashboard((current) => current.includes(option.template)
      ? current.filter((id) => id !== option.template) : [...current, option.template]);
    setApplied(false); setError('');
  }

  async function runCustom(event) {
    event.preventDefault();
    if (description.trim().length < 10 || busy || calling.current) return;
    calling.current = true; setBusy(true); setError('');
    setCustomResult(null);
    try {
      const preflight = await api(`${base}custom-preview/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ scope: custom, description }),
      });
      const result = await api(`${base}custom-run/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ scope: custom, description, approved: true,
          approval_note: `전송 버튼으로 ${custom} 추가 기능 추천 Claude API 1회 호출 승인`,
          request_fingerprint: preflight.request_fingerprint }),
      });
      setCustomResult(result.result);
      if (result.result.status !== 'supported') return;
      await load();
      setDescription('');
    } catch (caught) { setError(caught.message); }
    finally { calling.current = false; setBusy(false); }
  }

  async function apply() {
    if ((!selected.length && !dashboard.length && !manageData) || busy || calling.current) return;
    calling.current = true; setBusy(true); setError('');
    try {
      await api(base, { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({ features: selected.map((item) => item.reference),
          roles: { dashboard, admin: manageData ? ['manage_catalog'] : [] } }),
      });
      setApplied(true); onApplied?.(selected.length ? 'User' : dashboard.length ? 'DashBoard' : 'Admin');
    } catch (caught) { setError(caught.message); }
    finally { calling.current = false; setBusy(false); }
  }

  function options(items, scope) {
    const isSelected = (option) => scope === 'dashboard' ? dashboard.includes(option.template)
      : option.template === 'manage_catalog' ? manageData : selected.some((item) => item.template === option.template);
    return <div className="workflow-role-options">{selectedFirst(items, isSelected).map((option) => {
      const active = isSelected(option);
      const saved = selected.find((item) => item.template === option.template);
      const exclusive = ['request_review', 'request_auto'].includes(option.template) &&
        proposal.recommended.filter((item) => ['request_review', 'request_auto'].includes(item.template)).length > 1;
      const title = scope === 'dashboard' || option.template === 'manage_catalog' ? option.name
        : (active && saved?.[`${scope}_title`]) || option[`${scope}_title`] || option.name || featureLabels[option.template];
      return <button type="button" key={option.template} className="workflow-role-option" aria-pressed={active}
        style={{ gridColumn: scope === 'dashboard' ? 1 : scope === 'user' ? 2 : 3,
          gridRow: 2 + (scope === 'dashboard' ? selectedFirst(items, isSelected).findIndex((item) => item.template === option.template)
            : pairedRows.some((item) => item.template === option.template)
              ? pairedRows.findIndex((item) => item.template === option.template)
              : pairedRows.length + selectedFirst(items.filter((item) => ['browse_only', 'manage_catalog'].includes(item.template)), isSelected)
                .findIndex((item) => item.template === option.template)) }}
        data-role={scope} data-feature={option.template}
        data-paired={scope !== 'dashboard' && !['browse_only', 'manage_catalog'].includes(option.template) ? 'true' : 'false'}
        disabled={busy || !option.implemented} onClick={() => {
          if (scope === 'dashboard') toggleDashboard(option);
          else if (option.template === 'manage_catalog') { setManageData((value) => !value); setApplied(false); setError(''); }
          else toggle(option);
        }}>
        <span className="workflow-check" aria-hidden="true">{active ? '✓' : ''}</span>
        <span className="workflow-option-content"><strong title={title}>{title}</strong>
          {exclusive && <span className="workflow-option-rules">
            {exclusive && <span className="workflow-rule-exclusive">접수 방식 · 택 1</span>}
          </span>}
        </span>
        {!option.implemented && <span className="workflow-unavailable">미구현</span>}
      </button>;
    })}</div>;
  }

  if (!proposal) return <section className="panel"><p>서비스 구성을 불러오는 중입니다.</p>{error && <p className="error" role="alert">{error}</p>}</section>;
  const adminOptions = [
    ...proposal.recommended.filter((option) => option.template !== 'browse_only'),
    ...(proposal.recommended.some((option) => option.template === 'browse_only')
      ? [{ template: 'manage_catalog', name: proposal.data_title || '데이터 관리', implemented: true }] : []),
  ];
  const pairedRows = selectedFirst(proposal.recommended.filter((option) => option.template !== 'browse_only'),
    (option) => selected.some((item) => item.template === option.template));
  const selectableUserCount = recommendedSelection(proposal.recommended).length;
  const selectableAdminCount = recommendedSelection(adminOptions).length;
  return <>
  <section className="panel data-panel workflow-review" aria-labelledby="workflow-title">
    <div className="section-title preview-heading">
      <div><h2 id="workflow-title" className="icon-heading"><SectionIcon name="features" />서비스 기능 선택</h2><p className="preview-note">필요한 기능을 선택하세요. 연결된 사용자·관리자 기능은 함께 선택됩니다.</p></div>
    </div>
    {proposal.generation_warning && <p className="notice" role="status">{proposal.generation_warning}</p>}
    {!proposal.recommended.length && !proposal.generation_warning && <p className="notice">아직 추천 기능이 없습니다. AI 제안을 생성해 주세요.</p>}
    {proposal.service_summary && <p className="workflow-service-summary">{proposal.service_summary}</p>}
    <div className="workflow-grid-scroll"><div className="workflow-columns">
      <section><h3><span className="icon-heading"><SectionIcon name="dashboard" />대시보드</span><span className="workflow-role-count">{dashboard.length}/{proposal.dashboard.filter((item) => item.implemented).length}개 선택</span></h3>{options(proposal.dashboard, 'dashboard')}</section>
      <section><h3><span className="icon-heading"><SectionIcon name="user" />사용자</span><span className="workflow-role-count">{selected.length}/{selectableUserCount}개 선택</span></h3>{options(proposal.recommended, 'user')}</section>
      <section><h3><span className="icon-heading"><SectionIcon name="admin" />관리자</span><span className="workflow-role-count">{selected.filter((item) => item.template !== 'browse_only').length + Number(manageData)}/{selectableAdminCount}개 선택</span></h3>{options(adminOptions, 'admin')}</section>
    </div></div>
    {proposal.recommended.some((option) => option.template === 'request_review') && proposal.recommended.some((option) => option.template === 'request_auto') &&
      <p className="workflow-choice-note">신청·승인과 즉시 접수 중 하나만 선택할 수 있습니다.</p>}
    <form className="workflow-custom" onSubmit={runCustom}>
      <h3 className="icon-heading"><SectionIcon name="help" />생각하시는 기능이 없나요?</h3>
      <fieldset className="inquiry-form" disabled={busy}>
        <label className="workflow-target-field"><span className="workflow-field-label">대상</span><select value={custom} onChange={(event) => { setCustom(event.target.value); setCustomResult(null); }}>
          <option value="user">사용자</option><option value="admin">관리자</option></select></label>
        <label className="workflow-content-field"><span className="workflow-field-label">내용</span><textarea rows={2} value={description} placeholder="추가로 필요한 기능을 적어주세요." minLength={10} maxLength={500} required
          onChange={(event) => { setDescription(event.target.value); setCustomResult(null); }} /></label>
        <button type="submit" disabled={description.trim().length < 10} aria-label="전송하여 기능 추천받기">{busy ? <><span className="loading-spinner" aria-hidden="true" /><span className="visually-hidden">추천을 준비하고 있습니다.</span></> : '전송'}</button>
      </fieldset>
      <p className="workflow-submit-note">입력하신 기능의 지원 여부를 확인합니다.</p>
    </form>
      {customResult && <p className="notice" role="status">
        {customResult.status === 'supported'
          ? customResult.message.replace('추가할 수 있습니다.', '지원합니다. 위 목록에서 선택해 주세요.')
          : customResult.message}
      </p>}
    {error && <p className="error" role="alert">{error}</p>}
    {applied && !onApplied && <div className="workflow-ready">
      <a href={`/${uploadId}/User`} target="_blank" rel="noopener noreferrer">유저</a>
      <a href={`/${uploadId}/DashBoard`} target="_blank" rel="noopener noreferrer">대시보드</a>
      <a href={`/${uploadId}/Admin`} target="_blank" rel="noopener noreferrer">관리자</a>
    </div>}
  </section>
  <div className="workflow-apply selection-navigation">
    {onBack && <button type="button" className="service-back-button" disabled={busy} onClick={onBack}>이전</button>}
    <button type="button" className="workflow-generate" disabled={busy || (!selected.length && !dashboard.length && !manageData)} onClick={apply}>서비스 프리뷰 생성하기</button>
  </div>
  </>;
}
