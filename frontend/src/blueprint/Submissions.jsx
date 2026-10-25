import React, { useEffect, useRef, useState } from 'react';
import ServiceDialog from '../components/ServiceDialog';

// Applications about catalog rows (예약·이용 신청): records of their own, opened per row by its state.

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const value = await response.json().catch(() => null);
  if (!response.ok) throw new Error(value?.detail || '요청을 처리하지 못했습니다.');
  return value;
}

export function statusLabel(item) {
  return item.workflow.states.find((state) => state.id === item.status)?.label || item.status;
}

export function applicationGate(workflow, blueprint, row) {
  // Mirrors submission_open on the server: the row's own flow decides whether it takes applications.
  const gate = workflow.openWhen;
  if (!gate) return { open: true, reason: '' };
  const flow = (blueprint.rowWorkflows || []).find((item) => item.id === gate.flow);
  const state = row.flows?.[gate.flow];
  if (!flow || !state) return { open: true, reason: '' };
  return gate.kinds.includes(state.kind) ? { open: true, reason: '' }
    : { open: false, reason: `${flow.title} 상태가 "${state.state}"인 항목은 지금 신청할 수 없습니다.` };
}

export function useSubmissions(uploadId, csrf, blueprint, role) {
  const [items, setItems] = useState({});
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const working = useRef(false);
  async function load() {
    try {
      const results = await Promise.all(blueprint.workflows.map((flow) =>
        api(`/api/uploads/${uploadId}/blueprint/submissions/?workflow=${encodeURIComponent(flow.id)}&role=${role}`)));
      setItems(Object.fromEntries(blueprint.workflows.map((flow, index) => [flow.id, results[index].items])));
      setError('');
    } catch (caught) { setError(caught.message); }
  }
  useEffect(() => { if (blueprint.workflows.length) load(); }, [uploadId, role]);
  async function transition(item, step) {
    if (!csrf || working.current) return;
    working.current = true; setBusy(true); setError(''); setMessage('');
    try {
      await api(`/api/uploads/${uploadId}/blueprint/submissions/${item.id}/`, { method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify({ actor: role, to: step.to }) });
      setMessage(`${step.label} 처리했습니다.`);
      await load();
    } catch (caught) { setError(caught.message); }
    finally { working.current = false; setBusy(false); }
  }
  async function create(workflow, row, values) {
    if (!csrf || working.current) return false;
    working.current = true; setBusy(true); setError(''); setMessage('');
    try {
      await api(`/api/uploads/${uploadId}/blueprint/submissions/`, { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ workflow_id: workflow.id, row_id: row.id, values }) });
      setMessage('신청이 접수되었습니다.');
      await load();
      return true;
    } catch (caught) { setError(caught.message); return false; }
    finally { working.current = false; setBusy(false); }
  }
  return { items, message, error, setError, busy, load, transition, create };
}

export function SubmissionList({ items, role, onTransition, busy }) {
  const [expanded, setExpanded] = useState(null);
  if (!items.length) return <p className="muted">아직 접수된 내용이 없습니다.</p>;
  const actions = (item) => item.workflow.transitions.filter((step) => step.from === item.status && step.actor === role);
  if (role === 'admin') return <div className="table-scroll" role="region" aria-label="신청 목록" tabIndex={0}>
    <table className="request-management-table"><thead><tr><th scope="col">번호</th><th scope="col">신청 항목</th>
      <th scope="col">상태</th><th scope="col">신청일</th></tr></thead>
      <tbody>{items.map((item, index) => <React.Fragment key={item.id}><tr>
        <td>{index + 1}</td><td><div className="request-subject-cell">
          <button type="button" className="request-subject" aria-expanded={expanded === item.id}
            onClick={() => setExpanded((current) => current === item.id ? null : item.id)}>{item.subject}</button>
          <div className="blueprint-table-actions">{actions(item).map((step) => <button type="button" key={`${step.from}-${step.to}`}
            disabled={busy} onClick={() => onTransition(item, step)}>{step.label}</button>)}</div></div></td>
        <td><span className="service-badge">{statusLabel(item)}</span></td>
        <td className="request-date"><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleDateString('ko-KR')}</time></td>
      </tr>{expanded === item.id && <tr className="request-detail-row"><td colSpan={4}><dl>{Object.entries(item.values)
        .filter(([, value]) => value !== null).map(([key, value]) => <div key={key}>
          <dt>{item.workflow.fields.find((field) => field.id === key)?.label || key}</dt><dd>{String(value)}</dd>
        </div>)}</dl></td></tr>}</React.Fragment>)}</tbody>
    </table></div>;
  return <ul className="user-request-list blueprint-request-list">{items.map((item) => <li key={item.id}>
    <div><strong>{item.subject}</strong><span className="muted">{new Date(item.created_at).toLocaleDateString('ko-KR')}</span>
      <dl>{Object.entries(item.values).filter(([, value]) => value !== null).map(([key, value]) => <div key={key}>
        <dt>{item.workflow.fields.find((field) => field.id === key)?.label || key}</dt><dd>{String(value)}</dd>
      </div>)}</dl></div>
    <div className="blueprint-request-status"><span className="service-badge">{statusLabel(item)}</span>
      {actions(item).map((step) => <button type="button" className="service-back-button" key={`${step.from}-${step.to}`}
        disabled={busy} onClick={() => onTransition(item, step)}>{step.label}</button>)}</div>
  </li>)}</ul>;
}

export function ApplicationDialog({ editor, busy, error, onClose, onSubmit }) {
  const [values, setValues] = useState({});
  return <ServiceDialog title={editor.workflow.title} busy={busy} error={error} onClose={onClose}>
    <div className="editor-subject"><span className="muted">신청 항목</span>
      <p>{editor.row.values[editor.workflow.subjectColumn - 1] || `항목 ${editor.row.row_number}`}</p></div>
    <form onSubmit={(event) => { event.preventDefault(); onSubmit(values); }}><fieldset className="inquiry-form" disabled={busy}>
      {editor.workflow.fields.map((field) => <label key={field.id}>{field.label}{!field.required && <span className="muted"> (선택)</span>}
        {field.type === 'text' && /내용|사유|설명|메시지|요청/.test(field.label)
          ? <textarea required={field.required} maxLength={5000} value={values[field.id] || ''}
            onChange={(event) => setValues((current) => ({ ...current, [field.id]: event.target.value }))} />
          : <input type={field.type} required={field.required} maxLength={field.type === 'text' ? 5000 : undefined}
            value={values[field.id] || ''} onChange={(event) => setValues((current) => ({ ...current, [field.id]: event.target.value }))} />}
      </label>)}
      <div className="dialog-form-actions"><button type="button" className="service-back-button" disabled={busy} onClick={onClose}>취소</button>
        <button type="submit" disabled={busy}>{busy ? '제출 중...' : '신청 제출'}</button></div>
    </fieldset></form>
  </ServiceDialog>;
}
