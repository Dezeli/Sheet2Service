import React, { useEffect, useRef, useState } from 'react';
import AdminPreview from '../admin/AdminPreview';
import BlueprintChat from './BlueprintChat';
import ServiceDialog from '../components/ServiceDialog';
import '../user/user.css';
import '../inquiry/inquiry.css';
import './blueprint.css';

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const value = await response.json().catch(() => null);
  if (!response.ok) throw new Error(value?.detail || '요청을 처리하지 못했습니다.');
  return value;
}

function label(columns, number) {
  const column = columns[number - 1];
  return column?.label || column?.name || `열 ${number}`;
}

function statusLabel(item) {
  return item.workflow.states.find((state) => state.id === item.status)?.label || item.status;
}

function SubmissionList({ items, role, onTransition, busy }) {
  const [expanded, setExpanded] = useState(null);
  if (!items.length) return <p className="muted">아직 접수된 내용이 없습니다.</p>;
  if (role === 'admin') return <div className="table-scroll" role="region" aria-label="신청 목록" tabIndex={0}>
    <table className="request-management-table"><thead><tr><th scope="col">번호</th><th scope="col">신청 항목</th>
      <th scope="col">상태</th><th scope="col">신청일</th></tr></thead>
      <tbody>{items.map((item, index) => <React.Fragment key={item.id}><tr>
        <td>{index + 1}</td><td><div className="request-subject-cell">
          <button type="button" className="request-subject" aria-expanded={expanded === item.id}
            onClick={() => setExpanded((current) => current === item.id ? null : item.id)}>{item.subject}</button>
          <div className="blueprint-table-actions">{item.workflow.transitions
            .filter((step) => step.from === item.status && step.actor === role)
            .map((step) => <button type="button" key={`${step.from}-${step.to}`} disabled={busy}
              onClick={() => onTransition(item, step)}>{step.label}</button>)}</div></div></td>
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
      {item.workflow.transitions.filter((step) => step.from === item.status && step.actor === role)
        .map((step) => <button type="button" className="service-back-button" key={`${step.from}-${step.to}`}
          disabled={busy} onClick={() => onTransition(item, step)}>{step.label}</button>)}</div>
  </li>)}</ul>;
}

export default function BlueprintService({ uploadId, page, service }) {
  const [blueprint, setBlueprint] = useState(service.blueprint);
  const [csrf, setCsrf] = useState('');
  const [rows, setRows] = useState([]);
  const [pageNumber, setPageNumber] = useState(1);
  const [rowCount, setRowCount] = useState(0);
  const [query, setQuery] = useState('');
  const [filterColumn, setFilterColumn] = useState('');
  const [filterValue, setFilterValue] = useState('');
  const [criteria, setCriteria] = useState({});
  const [detail, setDetail] = useState(null);
  const [editor, setEditor] = useState(null);
  const [formValues, setFormValues] = useState({});
  const [submissions, setSubmissions] = useState({});
  const [charts, setCharts] = useState({});
  const [busy, setBusy] = useState(false);
  const working = useRef(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [adminTab, setAdminTab] = useState('fields');
  const [fieldLabels, setFieldLabels] = useState(service.upload.field_labels || {});
  const report = { ...service.upload.analysis, columns: service.upload.analysis.columns.map((column, index) => ({
    ...column, original_label: column.label, label: fieldLabels[String(index + 1)] || column.label,
  })) };
  const columns = report.columns;
  const base = `/api/uploads/${uploadId}/blueprint/`;

  async function loadRows(nextPage = 1, nextCriteria = criteria) {
    const params = new URLSearchParams({ page: String(nextPage) });
    if (nextCriteria.q) params.set('q', nextCriteria.q);
    if (nextCriteria.column && nextCriteria.value) {
      params.set('filter_column', nextCriteria.column);
      params.set('filter_value', nextCriteria.value);
    }
    const result = await api(`${base}rows/?${params}`);
    setRows(result.rows); setRowCount(result.row_count); setPageNumber(result.page); setCriteria(nextCriteria);
  }

  async function loadSubmissions() {
    const role = page === 'Admin' ? 'admin' : 'owner';
    const results = await Promise.all(blueprint.workflows.map((flow) =>
      api(`${base}submissions/?workflow=${encodeURIComponent(flow.id)}&role=${role}`)));
    setSubmissions(Object.fromEntries(blueprint.workflows.map((flow, index) => [flow.id, results[index].items])));
  }

  useEffect(() => {
    api('/api/session/').then((result) => setCsrf(result.csrf_token)).catch((caught) => setError(caught.message));
  }, [uploadId]);
  useEffect(() => {
    if (page === 'User') loadRows(1, {}).catch((caught) => setError(caught.message));
    if (page !== 'DashBoard') loadSubmissions().catch((caught) => setError(caught.message));
    if (page === 'DashBoard' && blueprint.catalog.charts.length) {
      const numbers = [...new Set(blueprint.catalog.charts.map((chart) => chart.groupColumn))];
      api(`/api/uploads/${uploadId}/chart-counts/?columns=${numbers.join(',')}`)
        .then((result) => setCharts(result.columns)).catch((caught) => setError(caught.message));
    }
  }, [uploadId, page, blueprint]);

  async function submit(event) {
    event.preventDefault();
    if (!editor || !csrf || working.current) return;
    working.current = true;
    setBusy(true); setError(''); setMessage('');
    let saved = false;
    try {
      await api(`${base}submissions/`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ workflow_id: editor.workflow.id, row_id: editor.row.id, values: formValues }) });
      saved = true;
      setEditor(null); setFormValues({}); setMessage('신청이 접수되었습니다.');
      await loadSubmissions();
    } catch (caught) { setError(saved ? '접수됐지만 목록을 불러오지 못했습니다. 새로고침해 주세요.' : caught.message); }
    finally { working.current = false; setBusy(false); }
  }

  async function transition(item, step) {
    if (!csrf || working.current) return;
    working.current = true;
    setBusy(true); setError(''); setMessage('');
    let saved = false;
    try {
      await api(`${base}submissions/${item.id}/`, { method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ actor: page === 'Admin' ? 'admin' : 'owner', to: step.to }) });
      saved = true;
      setMessage(`${step.label} 처리했습니다.`);
      await loadSubmissions();
    } catch (caught) { setError(saved ? '처리됐지만 목록을 불러오지 못했습니다. 새로고침해 주세요.' : caught.message); }
    finally { working.current = false; setBusy(false); }
  }

  return <div className="blueprint-service">
    <div className="panel"><h2>{blueprint.title}</h2><p>{blueprint.summary}</p></div>
    <BlueprintChat uploadId={uploadId} page={page} csrf={csrf} onApplied={(value) => {
      setBlueprint(value); setDetail(null); setEditor(null); setCriteria({});
      setQuery(''); setFilterColumn(''); setFilterValue('');
      setAdminTab((current) => ['fields', 'choices', 'records'].includes(current)
        || value.workflows.some((flow) => flow.id === current) ? current : 'fields');
    }} />
    {error && !editor && <p className="error" role="alert">{error}</p>}
    {page === 'DashBoard' && <section className="panel"><h2>데이터 현황</h2>
      <p>전체 {service.upload.analysis.row_count.toLocaleString()}개 항목</p>
      <div className="blueprint-chart-grid">{blueprint.catalog.charts.map((chart) => {
        const groups = charts[`column_${chart.groupColumn}`]?.groups || [];
        return <section key={chart.groupColumn}><h3>{label(columns, chart.groupColumn)}별 항목</h3>
          <ul>{groups.map((group) => <li key={group.label}><span>{group.label}</span><strong>{group.count.toLocaleString()}</strong></li>)}</ul>
        </section>;
      })}</div>
    </section>}
    {page === 'User' && <div className="template-workspace blueprint-workspace">
      <section className="panel workspace-main"><div className="section-title"><h2>항목 목록</h2>
        <span className="muted">{rowCount.toLocaleString()}개</span></div>
      <form className="list-controls blueprint-search" onSubmit={(event) => { event.preventDefault(); loadRows(1, {
        q: query.trim(), column: filterColumn, value: filterValue,
      }).catch((caught) => setError(caught.message)); }}>
        {!!blueprint.catalog.searchColumns.length && <div className="list-search-row"><label className="list-search">
          <svg className="list-search-icon" aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg>
          <input aria-label="검색어" type="search" value={query} maxLength={200} placeholder="검색어를 입력하세요"
            onChange={(event) => setQuery(event.target.value)} /></label></div>}
        <div className="list-filter-row">
          {!!blueprint.catalog.filterColumns.length && <><svg className="list-filter-icon" aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 5h18l-7 8v6l-4 2v-8z" /></svg>
            <label><select aria-label="필터 컬럼" value={filterColumn} onChange={(event) => { setFilterColumn(event.target.value); setFilterValue(''); }}>
              <option value="">전체</option>{blueprint.catalog.filterColumns.map((number) =>
                <option key={number} value={number}>{label(columns, number)}</option>)}</select></label>
            <label><input aria-label="필터 값" value={filterValue} disabled={!filterColumn}
              placeholder={filterColumn ? '정확한 값을 입력하세요' : '필터를 선택하세요'}
              onChange={(event) => setFilterValue(event.target.value)} /></label></>}
          <div className="list-filter-actions"><button type="submit" data-intent="secondary">검색</button>
            <button type="button" className="service-back-button" onClick={() => {
              setQuery(''); setFilterColumn(''); setFilterValue(''); loadRows(1, {}).catch((caught) => setError(caught.message));
            }}>초기화</button></div>
        </div>
      </form>
      {!rows.length && <p className="muted">조건에 맞는 항목이 없습니다.</p>}
      <div className="catalog-list">{rows.map((row) => <article key={row.id} className="catalog-row">
        <div className="catalog-row-content"><h3><button type="button" className="service-title-button" onClick={() => setDetail(row)}>
          {row.values[blueprint.catalog.titleColumn - 1] || `항목 ${row.row_number}`}</button></h3>
        <dl className="catalog-summary">{blueprint.catalog.visibleColumns
          .filter((number) => number !== blueprint.catalog.titleColumn && row.values[number - 1])
          .slice(0, 3).map((number) => <div key={number}><dt>{label(columns, number)}</dt>
            <dd title={String(row.values[number - 1])}>{row.values[number - 1]}</dd></div>)}</dl></div>
        <div className="admin-row-actions"><button type="button" className="service-back-button"
          onClick={() => setDetail(row)}>상세 보기</button>
          {blueprint.workflows.map((flow) => <button key={flow.id} type="button" data-intent="primary" disabled={busy || !csrf}
            onClick={() => { setEditor({ row, workflow: flow }); setFormValues({}); setError(''); }}>{flow.title}</button>)}</div>
      </article>)}</div>
      <nav className="service-pagination" aria-label="항목 페이지 이동"><button type="button" disabled={pageNumber <= 1}
        onClick={() => loadRows(pageNumber - 1).catch((caught) => setError(caught.message))}>이전</button>
        <span>{pageNumber} / {Math.max(1, Math.ceil(rowCount / 20))}</span>
        <button type="button" disabled={pageNumber * 20 >= rowCount}
          onClick={() => loadRows(pageNumber + 1).catch((caught) => setError(caught.message))}>다음</button></nav>
      </section>
      {!!blueprint.workflows.length && <section className="panel workspace-side"><div className="section-title">
        <h2>내 신청 현황</h2><button type="button" className="service-back-button" disabled={busy}
          onClick={() => loadSubmissions().catch((caught) => setError(caught.message))}>새로고침</button></div>
        {message && <p className="notice" role="status">{message}</p>}
        {blueprint.workflows.map((flow) => <div className="blueprint-workflow-history" key={flow.id}>
          <h3>{flow.title}</h3><SubmissionList items={submissions[flow.id] || []}
            role="owner" onTransition={transition} busy={busy} />
        </div>)}
      </section>}
    </div>}
    {page === 'User' && detail && <ServiceDialog title={String(detail.values[blueprint.catalog.titleColumn - 1] || `항목 ${detail.row_number}`)}
      onClose={() => setDetail(null)}>
      <dl className="catalog-detail">{columns.map((column, index) => <div key={index}
        className={String(detail.values[index] || '').length > 80 ? 'field-wide' : undefined}>
        <dt>{label(columns, index + 1)}</dt><dd>{detail.values[index] || '—'}</dd>
      </div>)}</dl>
    </ServiceDialog>}
    {page === 'User' && editor && <ServiceDialog title={editor.workflow.title} busy={busy} error={error}
      onClose={() => { setEditor(null); setError(''); }}>
      <div className="editor-subject"><span className="muted">신청 항목</span>
        <p>{editor.row.values[editor.workflow.subjectColumn - 1] || `항목 ${editor.row.row_number}`}</p></div>
      <form onSubmit={submit}><fieldset className="inquiry-form" disabled={busy}>
        {editor.workflow.fields.map((field) => <label key={field.id}>{field.label}
          {field.type === 'text' && /내용|사유|설명|메시지|요청/.test(field.label)
            ? <textarea required={field.required} maxLength={5000} value={formValues[field.id] || ''}
              onChange={(event) => setFormValues((current) => ({ ...current, [field.id]: event.target.value }))} />
            : <input type={field.type} required={field.required} maxLength={field.type === 'text' ? 5000 : undefined}
              value={formValues[field.id] || ''} onChange={(event) => setFormValues((current) => ({ ...current, [field.id]: event.target.value }))} />}
        </label>)}
        <div className="dialog-form-actions"><button type="button" className="service-back-button" disabled={busy}
          onClick={() => { setEditor(null); setError(''); }}>취소</button>
          <button type="submit" disabled={busy || !csrf}>{busy ? '제출 중...' : '신청 제출'}</button></div>
      </fieldset></form>
    </ServiceDialog>}
    {page === 'Admin' && <div className="admin-shell">
      <aside className="admin-sidebar"><p className="admin-sidebar-title">관리 메뉴</p>
        <nav aria-label="관리 메뉴">
          {[{ id: 'fields', label: '필드 구성' }, { id: 'choices', label: '선택지 관리' },
            { id: 'records', label: '데이터 관리' },
            ...blueprint.workflows.map((flow) => ({ id: flow.id, label: `${flow.title} 내역` }))]
            .map((item) => <button type="button" key={item.id}
              aria-current={adminTab === item.id ? 'page' : undefined}
              onClick={() => setAdminTab(item.id)}>{item.label}</button>)}
        </nav>
      </aside>
      <div className="admin-content">
        {['fields', 'choices', 'records'].includes(adminTab)
          ? <AdminPreview key={adminTab} uploadId={uploadId} report={report}
            dashboardConfig={{ version: 2, views: [{ template: 'table', columns: blueprint.catalog.visibleColumns }] }}
            workflowConfig={null} titleColumns={[blueprint.catalog.titleColumn]} embedded
            onFieldLabelsChange={setFieldLabels} viewTemplate={adminTab} />
          : blueprint.workflows.filter((flow) => flow.id === adminTab).map((flow) => <section className="panel blueprint-management" key={flow.id}>
            <div className="section-title"><h2>{flow.title} 내역</h2>
              <button type="button" className="service-back-button" disabled={busy}
                onClick={() => loadSubmissions().catch((caught) => setError(caught.message))}>새로고침</button></div>
            {message && <p className="notice" role="status">{message}</p>}
            <SubmissionList items={submissions[flow.id] || []}
              role="admin" onTransition={transition} busy={busy} />
          </section>)}
      </div>
    </div>}
  </div>;
}
