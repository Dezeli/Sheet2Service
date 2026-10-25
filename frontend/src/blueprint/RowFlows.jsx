import React, { useEffect, useRef, useState } from 'react';
import ServiceDialog from '../components/ServiceDialog';

// Row workflows: the sheet's own rows are the cases; a transition edits the row in place.

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const value = await response.json().catch(() => null);
  if (!response.ok) throw new Error(value?.detail || '요청을 처리하지 못했습니다.');
  return value;
}

export function columnLabel(columns, number) {
  const column = columns[number - 1];
  return column?.label || column?.name || `열 ${number}`;
}

export function FlowBadges({ row, flows }) {
  if (!flows.length || !row.flows) return null;
  return <span className="row-flow-badges">{flows.map((flow) => {
    const state = row.flows[flow.id];
    if (!state) return null;
    // A bare flag value (Y, O, N) says nothing on its own; prefix the flow's name.
    const text = state.state.length <= 2 ? `${flow.title} ${state.state || '—'}` : state.state;
    return <span key={flow.id} className={`service-badge row-flow-${state.kind}`} title={flow.title}>{text}</span>;
  })}</span>;
}

function inputColumns(flow, step, columns) {
  // Columns the person may fill on this step: owner, result, and text companions of a flag flow.
  const done = flow.states.find((state) => state.value === step.to)?.kind === 'done';
  const numbers = [];
  if (flow.ownerColumn) numbers.push(flow.ownerColumn);
  if (done && flow.resultColumn) numbers.push(flow.resultColumn);
  if (done && flow.basis === 'flag_and_dates') {
    flow.companionColumns.filter((number) => !(flow.companionDates || []).includes(number) && number !== flow.resultColumn)
      .forEach((number) => numbers.push(number));
  }
  return [...new Set(numbers)].map((number) => ({ number, label: columnLabel(columns, number) }));
}

export function TransitionDialog({ pending, columns, busy, error, onClose, onSubmit }) {
  const [inputs, setInputs] = useState({});
  const fields = inputColumns(pending.flow, pending.step, columns);
  return <ServiceDialog title={`${pending.flow.title}: ${pending.step.to}`} busy={busy} error={error} onClose={onClose}>
    <div className="editor-subject"><span className="muted">대상</span><p>{pending.title}</p></div>
    <form onSubmit={(event) => { event.preventDefault(); onSubmit(inputs); }}>
      <fieldset className="inquiry-form" disabled={busy}>
        {fields.map((field) => <label key={field.number}>{field.label} <span className="muted">(선택)</span>
          {/내용|사유|결과|비고|메모/.test(field.label)
            ? <textarea maxLength={1000} value={inputs[field.number] || ''} onChange={(event) => setInputs((current) => ({ ...current, [field.number]: event.target.value }))} />
            : <input type="text" maxLength={1000} value={inputs[field.number] || ''} onChange={(event) => setInputs((current) => ({ ...current, [field.number]: event.target.value }))} />}
        </label>)}
        {!fields.length && <p className="muted">{pending.flow.title} 상태를 "{pending.step.to}"(으)로 바꿉니다.</p>}
        <div className="dialog-form-actions"><button type="button" className="service-back-button" disabled={busy} onClick={onClose}>취소</button>
          <button type="submit" disabled={busy}>{busy ? '처리 중...' : pending.step.to}</button></div>
      </fieldset></form>
  </ServiceDialog>;
}

export function useRowTransition(uploadId, csrf, actor, onDone) {
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const working = useRef(false);
  async function run(row, flow, step, inputs) {
    if (!csrf || working.current) return;
    working.current = true; setBusy(true); setError('');
    try {
      const updated = await api(`/api/uploads/${uploadId}/blueprint/rows/${row.id}/transition/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ flow_id: flow.id, to: step.to, actor, inputs: inputs || {} }),
      });
      setPending(null);
      onDone(updated, `${flow.title}: ${step.to} 처리했습니다.`);
    } catch (caught) { setError(caught.message); }
    finally { working.current = false; setBusy(false); }
  }
  function start(row, flow, step, title, columns) {
    if (inputColumns(flow, step, columns).length) { setPending({ row, flow, step, title }); setError(''); return; }
    run(row, flow, step, {});
  }
  return { pending, setPending, busy, error, setError, run, start };
}

export function availableSteps(flow, row, actor) {
  const state = row.flows?.[flow.id];
  if (!state || state.blocked) return [];
  return flow.transitions.filter((step) => step.from === state.state && step.actor === actor);
}

export function RowFlowAdmin({ uploadId, csrf, blueprint, flow, columns }) {
  const [rows, setRows] = useState([]);
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [stateFilter, setStateFilter] = useState('');
  const [message, setMessage] = useState('');
  const [history, setHistory] = useState(null);
  const [loadError, setLoadError] = useState('');
  const title = (row) => row.values[blueprint.catalog.titleColumn - 1] || `항목 ${row.row_number}`;
  const transition = useRowTransition(uploadId, csrf, 'admin', (updated, text) => {
    setRows((current) => current.map((row) => row.id === updated.id ? updated : row));
    setMessage(text);
  });

  async function load(next = 1, filter = stateFilter) {
    const params = new URLSearchParams({ page: String(next) });
    if (filter && flow.basis === 'status_column' && blueprint.catalog.filterColumns.includes(flow.statusColumn)) {
      params.set('filter_column', String(flow.statusColumn)); params.set('filter_value', filter);
    }
    try {
      const result = await api(`/api/uploads/${uploadId}/blueprint/rows/?${params}`);
      setRows(result.rows); setCount(result.row_count); setPage(result.page); setLoadError('');
    } catch (caught) { setLoadError(caught.message); }
  }
  useEffect(() => { load(1, ''); }, [uploadId, flow.id]);

  const serverFiltered = flow.basis === 'status_column' && blueprint.catalog.filterColumns.includes(flow.statusColumn);
  const shown = rows.filter((row) => !stateFilter || serverFiltered || row.flows?.[flow.id]?.state === stateFilter);
  return <section className="panel blueprint-management row-flow-admin">
    <div className="section-title"><h2>{flow.title}</h2>
      <div className="row-flow-controls">
        <label><span className="visually-hidden">상태</span>
          <select value={stateFilter} onChange={(event) => { setStateFilter(event.target.value); load(1, event.target.value); }}>
            <option value="">전체 상태</option>{flow.states.map((state) => <option key={state.value} value={state.value}>{state.value}</option>)}
          </select></label>
        <button type="button" className="service-back-button" disabled={transition.busy} onClick={() => load(page)}>새로고침</button>
      </div></div>
    <p className="muted row-flow-explain">{flow.basis === 'status_column' ? `${columnLabel(columns, flow.statusColumn)} 컬럼을 직접 바꿉니다.`
      : flow.basis === 'milestone_dates' ? `단계마다 ${flow.dateColumns.map((number) => columnLabel(columns, number)).join(' → ')}에 오늘 날짜를 기록합니다.`
      : `${columnLabel(columns, flow.flagColumn)}을(를) "${flow.doneValue}"로 표시하고 ${flow.companionColumns.map((number) => columnLabel(columns, number)).join(', ')}을(를) 채웁니다.`}
      {flow.after && ` ${blueprint.rowWorkflows.find((item) => item.id === flow.after)?.title}이(가) 끝난 건만 진행할 수 있습니다.`}</p>
    {message && <p className="notice" role="status">{message}</p>}
    {loadError && <p className="error" role="alert">{loadError}</p>}
    {!shown.length && <p className="muted">해당하는 건이 없습니다.</p>}
    {shown.length > 0 && <div className="table-scroll" role="region" aria-label={`${flow.title} 목록`} tabIndex={0}>
      <table className="request-management-table row-flow-table"><thead><tr><th scope="col">번호</th><th scope="col">항목</th>
        {flow.ownerColumn && <th scope="col">{columnLabel(columns, flow.ownerColumn)}</th>}
        {flow.dueColumn && <th scope="col">{columnLabel(columns, flow.dueColumn)}</th>}
        <th scope="col">상태</th><th scope="col">처리</th></tr></thead>
        <tbody>{shown.map((row) => {
          const state = row.flows?.[flow.id];
          const steps = availableSteps(flow, row, 'admin');
          return <tr key={row.id}>
            <td>{row.row_number - 1}</td>
            <td><div className="request-subject-cell"><span className="request-subject">{title(row)}</span>
              <button type="button" className="row-flow-history" onClick={async () => {
                try { setHistory({ title: title(row), items: (await api(`/api/uploads/${uploadId}/blueprint/rows/${row.id}/history/`)).items }); }
                catch (caught) { setLoadError(caught.message); }
              }}>이력</button></div></td>
            {flow.ownerColumn && <td>{row.values[flow.ownerColumn - 1] || <span className="muted">—</span>}</td>}
            {flow.dueColumn && <td className="request-date">{row.values[flow.dueColumn - 1] || <span className="muted">—</span>}</td>}
            <td><span className={`service-badge row-flow-${state?.kind}`}>{state?.state}</span>{state?.blocked && <small className="muted"> 선행 대기</small>}</td>
            <td><div className="blueprint-table-actions">{steps.map((step) => <button type="button" key={step.to} disabled={transition.busy}
              onClick={() => transition.start(row, flow, step, title(row), columns)}>{step.to}</button>)}</div></td>
          </tr>;
        })}</tbody></table></div>}
    <nav className="service-pagination" aria-label="페이지 이동"><button type="button" disabled={page <= 1} onClick={() => load(page - 1)}>이전</button>
      <span>{page} / {Math.max(1, Math.ceil(count / 20))}</span>
      <button type="button" disabled={page * 20 >= count} onClick={() => load(page + 1)}>다음</button></nav>
    {transition.pending && <TransitionDialog pending={transition.pending} columns={columns} busy={transition.busy} error={transition.error}
      onClose={() => { transition.setPending(null); transition.setError(''); }}
      onSubmit={(inputs) => transition.run(transition.pending.row, transition.pending.flow, transition.pending.step, inputs)} />}
    {history && <ServiceDialog title={`${history.title} 이력`} onClose={() => setHistory(null)}>
      {!history.items.length && <p className="muted">아직 기록이 없습니다.</p>}
      <ul className="row-flow-history-list">{history.items.map((item, index) => <li key={index}>
        <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString('ko-KR')}</time>
        <span>{item.flow ? `${item.flow}: ${item.from || '—'} → ${item.to}` : '접수됨'}</span>
        <small className="muted">{item.actor === 'admin' ? '관리자' : '사용자'}{Object.keys(item.changes).length ? ` · ${Object.entries(item.changes).map(([number, value]) => `${columnLabel(columns, Number(number))}=${value}`).join(', ')}` : ''}</small>
      </li>)}</ul>
    </ServiceDialog>}
  </section>;
}

export function RowCreatePanel({ uploadId, csrf, blueprint, columns }) {
  const form = blueprint.createForm;
  const flows = blueprint.rowWorkflows || [];
  const [mine, setMine] = useState([]);
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState({});
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const working = useRef(false);
  const title = (row) => row.values[blueprint.catalog.titleColumn - 1] || `접수 ${row.row_number - 1}`;
  const transition = useRowTransition(uploadId, csrf, 'user', (updated, text) => {
    setMine((current) => current.map((row) => row.id === updated.id ? updated : row));
    setMessage(text);
  });
  async function load() {
    try { setMine((await api(`/api/uploads/${uploadId}/blueprint/rows/mine/`)).items); }
    catch (caught) { setError(caught.message); }
  }
  useEffect(() => { load(); }, [uploadId]);
  async function submit(event) {
    event.preventDefault();
    if (!csrf || working.current) return;
    working.current = true; setBusy(true); setError('');
    try {
      await api(`/api/uploads/${uploadId}/blueprint/rows/mine/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ values }),
      });
      setOpen(false); setValues({}); setMessage('접수되었습니다.');
      await load();
    } catch (caught) { setError(caught.message); }
    finally { working.current = false; setBusy(false); }
  }
  return <section className="panel workspace-side row-create-panel"><div className="section-title">
    <h2>내 접수 현황</h2>
    <div className="row-flow-controls">
      <button type="button" className="service-back-button" disabled={busy} onClick={load}>새로고침</button>
      {form && <button type="button" data-intent="primary" disabled={busy || !csrf} onClick={() => { setOpen(true); setError(''); }}>새 건 접수</button>}
    </div></div>
    {message && <p className="notice" role="status">{message}</p>}
    {error && !open && <p className="error" role="alert">{error}</p>}
    {!mine.length && <p className="muted">아직 접수한 건이 없습니다.</p>}
    <ul className="user-request-list blueprint-request-list">{mine.map((row) => <li key={row.id}>
      <div><strong>{title(row)}</strong>
        <dl>{form.columns.filter((number) => row.values[number - 1]).map((number) => <div key={number}>
          <dt>{columnLabel(columns, number)}</dt><dd>{String(row.values[number - 1])}</dd></div>)}</dl></div>
      <div className="blueprint-request-status"><FlowBadges row={row} flows={flows} />
        {flows.flatMap((flow) => availableSteps(flow, row, 'user').map((step) => <button type="button" className="service-back-button"
          key={`${flow.id}-${step.to}`} disabled={transition.busy} onClick={() => transition.start(row, flow, step, title(row), columns)}>{step.to}</button>))}</div>
    </li>)}</ul>
    {open && <ServiceDialog title="새 건 접수" busy={busy} error={error} onClose={() => { setOpen(false); setError(''); }}>
      <form onSubmit={submit}><fieldset className="inquiry-form" disabled={busy}>
        {form.columns.map((number) => <label key={number}>{columnLabel(columns, number)}
          {/내용|사유|설명|요청|비고|메모/.test(columnLabel(columns, number))
            ? <textarea required maxLength={5000} value={values[number] || ''} onChange={(event) => setValues((current) => ({ ...current, [number]: event.target.value }))} />
            : <input type="text" required maxLength={5000} value={values[number] || ''} onChange={(event) => setValues((current) => ({ ...current, [number]: event.target.value }))} />}
        </label>)}
        <div className="dialog-form-actions"><button type="button" className="service-back-button" disabled={busy} onClick={() => { setOpen(false); setError(''); }}>취소</button>
          <button type="submit" disabled={busy || !csrf}>{busy ? '접수 중...' : '접수'}</button></div>
      </fieldset></form>
    </ServiceDialog>}
    {transition.pending && <TransitionDialog pending={transition.pending} columns={columns} busy={transition.busy} error={transition.error}
      onClose={() => { transition.setPending(null); transition.setError(''); }}
      onSubmit={(inputs) => transition.run(transition.pending.row, transition.pending.flow, transition.pending.step, inputs)} />}
  </section>;
}
