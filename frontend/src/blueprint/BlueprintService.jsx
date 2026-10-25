import React, { useEffect, useState } from 'react';
import AdminPreview from '../admin/AdminPreview';
import ServiceDialog from '../components/ServiceDialog';
import { FlowBadges, RowCreatePanel, RowFlowAdmin } from './RowFlows';
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

const URL_VALUE = /^https?:\/\/\S+$/;

function valueLabel(catalog, number, value) {
  const mapping = catalog.valueLabels?.find((item) => item.column === number);
  const shown = mapping?.values?.[String(value)];
  return shown === undefined ? value : shown;
}

function renderValue(value, catalog, number) {
  // Plain CSV values that are URLs open in a new tab; everything else stays text.
  const text = String(catalog && number ? valueLabel(catalog, number, value) : value);
  return URL_VALUE.test(text) ? <a href={text} target="_blank" rel="noopener noreferrer">{text}</a> : text;
}

export default function BlueprintService({ uploadId, page, service }) {
  const blueprint = service.blueprint;
  const [csrf, setCsrf] = useState('');
  const [rows, setRows] = useState([]);
  const [pageNumber, setPageNumber] = useState(1);
  const [rowCount, setRowCount] = useState(0);
  const [query, setQuery] = useState('');
  const [filterColumn, setFilterColumn] = useState('');
  const [filterValue, setFilterValue] = useState('');
  const [criteria, setCriteria] = useState({});
  const [detail, setDetail] = useState(null);
  const [charts, setCharts] = useState({});
  const [error, setError] = useState('');
  const [adminTab, setAdminTab] = useState('fields');
  const [fieldLabels, setFieldLabels] = useState(service.upload.field_labels || {});
  const report = { ...service.upload.analysis, columns: service.upload.analysis.columns.map((column, index) => ({
    ...column, original_label: column.label, label: fieldLabels[String(index + 1)] || column.label,
  })) };
  const columns = report.columns;
  const base = `/api/uploads/${uploadId}/blueprint/`;
  const rowFlows = blueprint.rowWorkflows || [];

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

  useEffect(() => {
    api('/api/session/').then((result) => setCsrf(result.csrf_token)).catch((caught) => setError(caught.message));
  }, [uploadId]);
  useEffect(() => {
    if (page === 'User') loadRows(1, {}).catch((caught) => setError(caught.message));
    if (page === 'DashBoard' && blueprint.catalog.charts.length) {
      const numbers = [...new Set(blueprint.catalog.charts.map((chart) => chart.groupColumn))];
      api(`/api/uploads/${uploadId}/chart-counts/?columns=${numbers.join(',')}`)
        .then((result) => setCharts(result.columns)).catch((caught) => setError(caught.message));
    }
  }, [uploadId, page]);

  return <div className="blueprint-service">
    <div className="panel"><h2>{blueprint.title}</h2><p>{blueprint.summary}</p></div>
    {error && <p className="error" role="alert">{error}</p>}
    {page === 'DashBoard' && <section className="panel"><h2>데이터 현황</h2>
      <p>전체 {service.upload.analysis.row_count.toLocaleString()}개 항목</p>
      <div className="blueprint-chart-grid">{blueprint.catalog.charts.map((chart) => {
        const groups = charts[`column_${chart.groupColumn}`]?.groups || [];
        return <section key={chart.groupColumn}><h3>{label(columns, chart.groupColumn)}별 항목</h3>
          <ul>{groups.map((group) => <li key={group.label}><span>{String(valueLabel(blueprint.catalog, chart.groupColumn, group.label))}</span><strong>{group.count.toLocaleString()}</strong></li>)}</ul>
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
          {row.values[blueprint.catalog.titleColumn - 1] || `항목 ${row.row_number}`}</button><FlowBadges row={row} flows={rowFlows} /></h3>
        <dl className="catalog-summary">{blueprint.catalog.visibleColumns
          .filter((number) => number !== blueprint.catalog.titleColumn && row.values[number - 1])
          .slice(0, 3).map((number) => <div key={number}><dt>{label(columns, number)}</dt>
            <dd title={String(row.values[number - 1])}>{renderValue(row.values[number - 1], blueprint.catalog, number)}</dd></div>)}</dl></div>
        <div className="admin-row-actions"><button type="button" className="service-back-button"
          onClick={() => setDetail(row)}>상세 보기</button></div>
      </article>)}</div>
      <nav className="service-pagination" aria-label="항목 페이지 이동"><button type="button" disabled={pageNumber <= 1}
        onClick={() => loadRows(pageNumber - 1).catch((caught) => setError(caught.message))}>이전</button>
        <span>{pageNumber} / {Math.max(1, Math.ceil(rowCount / 20))}</span>
        <button type="button" disabled={pageNumber * 20 >= rowCount}
          onClick={() => loadRows(pageNumber + 1).catch((caught) => setError(caught.message))}>다음</button></nav>
      </section>
      {(!!rowFlows.length || blueprint.createForm) && <RowCreatePanel uploadId={uploadId} csrf={csrf} blueprint={blueprint} columns={columns} />}
    </div>}
    {page === 'User' && detail && <ServiceDialog title={String(detail.values[blueprint.catalog.titleColumn - 1] || `항목 ${detail.row_number}`)}
      onClose={() => setDetail(null)}>
      <dl className="catalog-detail">{columns.map((column, index) => <div key={index}
        className={String(detail.values[index] || '').length > 80 ? 'field-wide' : undefined}>
        <dt>{label(columns, index + 1)}</dt><dd>{detail.values[index] ? renderValue(detail.values[index], blueprint.catalog, index + 1) : '—'}</dd>
      </div>)}</dl>
    </ServiceDialog>}
    {page === 'Admin' && <div className="admin-shell">
      <aside className="admin-sidebar"><p className="admin-sidebar-title">관리 메뉴</p>
        <nav aria-label="관리 메뉴">
          {[{ id: 'fields', label: '필드 구성' }, { id: 'choices', label: '선택지 관리' },
            { id: 'records', label: '데이터 관리' },
            ...rowFlows.map((flow) => ({ id: flow.id, label: flow.title }))]
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
          : <RowFlowAdmin key={adminTab} uploadId={uploadId} csrf={csrf} blueprint={blueprint} columns={columns}
            flow={rowFlows.find((flow) => flow.id === adminTab)} />}
      </div>
    </div>}
  </div>;
}
