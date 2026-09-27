import React, { useEffect, useMemo, useState } from 'react';
import Charts from './Charts.jsx';
import { recordsFromRows, safeWebUrl } from './config.js';
import { chartConfigsV2, columnId, columnLabel, validateConfigV2 } from './configV2.js';
import './preview.css';

const labels = { cards: '카드 목록', table: '표 목록', grouped: '그룹 목록' };
const display = (value) => value === null || value === undefined || String(value).trim() === '' ? '빈 값' : String(value);
const fieldValue = (record, columns, number) => display(record.values[columnId(columns, number)]);

function Fields({ record, columns, numbers }) {
  return <dl className="service-fields">{numbers.map((number) => <div key={number}>
    <dt>{columnLabel(columns, number)}</dt>
    <dd>{fieldValue(record, columns, number)}</dd>
  </div>)}</dl>;
}

function Cards({ view, records, columns, openDetail }) {
  return <div className="service-grid">{records.map((record) => {
    const imageUrl = view.imageColumn && safeWebUrl(record.values[columnId(columns, view.imageColumn)]);
    return <article className="service-card" key={record.id}>
      {imageUrl && <img className="service-image" src={imageUrl} alt="" loading="lazy" referrerPolicy="no-referrer" />}
      <div className="service-card-body">
        {view.badgeColumn && <span className="service-badge">{fieldValue(record, columns, view.badgeColumn)}</span>}
        <h3><button type="button" className="service-title-button" onClick={() => openDetail(record.id)}>
          {fieldValue(record, columns, view.titleColumn)}
        </button></h3>
        {view.subtitleColumn && <p className="muted">{fieldValue(record, columns, view.subtitleColumn)}</p>}
        <Fields record={record} columns={columns} numbers={view.fields} />
      </div>
    </article>;
  })}</div>;
}

function Grouped({ view, records, columns, openDetail }) {
  const groups = new Map();
  for (const record of records) {
    const name = fieldValue(record, columns, view.groupColumn);
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(record);
  }
  return <div className="service-groups">{[...groups.entries()].map(([name, items], index) => <section className="service-group" key={name}>
    <div className="service-group-heading"><h3>{name}</h3><span>{items.length.toLocaleString()}개 항목</span></div>
    <Cards view={view} records={items} columns={columns} openDetail={openDetail} key={index} />
  </section>)}</div>;
}

function Table({ view, records, columns, openDetail }) {
  return <div className="service-table-scroll" role="region" aria-label="서비스 표 목록" tabIndex={0}>
    <table className="service-table">
      <thead><tr>{view.columns.map((number) => <th scope="col" key={number}>{columnLabel(columns, number)}</th>)}</tr></thead>
      <tbody>{records.map((record) => <tr key={record.id}>{view.columns.map((number, index) => <td key={number}>
        {index === 0 ? <button type="button" className="service-title-button" onClick={() => openDetail(record.id)}
          aria-label={`${fieldValue(record, columns, number)} 상세 보기`}>{fieldValue(record, columns, number)}</button>
          : fieldValue(record, columns, number)}
      </td>)}</tr>)}</tbody>
    </table>
  </div>;
}

export function PreviewRuntimeV2({ config, columns, records, chartAggregates }) {
  try { validateConfigV2(config, columns); }
  catch (error) { return <p className="error" role="alert">{error.message}</p>; }
  return <ValidatedRuntime config={config} columns={columns} records={records} chartAggregates={chartAggregates} />;
}

function ValidatedRuntime({ config, columns, records, chartAggregates }) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [selectedRecord, setSelectedRecord] = useState(null);
  useEffect(() => setSelectedRecord(null), [records]);
  const view = config.views[selectedIndex];
  const record = records.find((item) => item.id === selectedRecord);
  const openDetail = (id) => setSelectedRecord(id);
  return <div className="service-runtime">
    <div className="service-preview-meta"><span>{records.length.toLocaleString()}개 항목</span>
      <span>{config.views.length.toLocaleString()}개 목록 화면</span></div>
    {record ? <>
      <button type="button" className="service-back-button" onClick={() => setSelectedRecord(null)}>목록으로 돌아가기</button>
      <h2>항목 상세</h2>
      <p className="muted">선택한 CSV 행의 모든 컬럼입니다.</p>
      <Fields record={record} columns={columns} numbers={columns.map((_, index) => index + 1)} />
    </> : <>
      <nav className="service-view-tabs" aria-label="서비스 미리보기 화면 선택">
        {config.views.map((item, index) => <button type="button" key={index}
          aria-current={index === selectedIndex ? 'page' : undefined} onClick={() => setSelectedIndex(index)}>
          <strong>{labels[item.template]} {index + 1}</strong>
        </button>)}
      </nav>
      <h2>{labels[view.template]}</h2>
      <Charts configs={chartConfigsV2(view.charts, columns)} records={records} aggregates={chartAggregates} />
      {!records.length ? <p>표시할 항목이 없습니다.</p>
        : view.template === 'cards' ? <Cards view={view} records={records} columns={columns} openDetail={openDetail} />
          : view.template === 'grouped' ? <Grouped view={view} records={records} columns={columns} openDetail={openDetail} />
            : <Table view={view} records={records} columns={columns} openDetail={openDetail} />}
    </>}
  </div>;
}

export default function ServicePreviewV2({ uploadId, report, config, usedFallback }) {
  const [opened, setOpened] = useState(true);
  const [browseAll, setBrowseAll] = useState(false);
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState(report.preview);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [chartAggregates, setChartAggregates] = useState(null);
  const records = useMemo(() => recordsFromRows(rows, report.columns), [rows, report.columns]);
  if (!config) return null;
  const totalPages = Math.max(1, Math.ceil(report.row_count / 20));

  async function openPage(nextPage) {
    if (loading || nextPage < 1 || nextPage > totalPages) return;
    setError('');
    if (nextPage === 1) {
      setRows(report.preview);
      setPage(1);
      return;
    }
    setLoading(true);
    try {
      const response = await fetch(`/api/uploads/${uploadId}/rows/?page=${nextPage}`, { credentials: 'same-origin' });
      const payload = await response.json();
      if (!response.ok || !Array.isArray(payload.rows) || payload.page !== nextPage) {
        throw new Error(typeof payload.detail === 'string' ? payload.detail : '데이터 페이지를 읽지 못했습니다.');
      }
      setRows(payload.rows);
      setPage(nextPage);
    } catch (caught) {
      setError(caught.message);
    } finally { setLoading(false); }
  }

  async function showAllRows() {
    if (loading) return;
    const columns = [...new Set(config.views.flatMap((view) => (view.charts || []).map((chart) => chart.groupColumn)))];
    if (!columns.length) {
      setBrowseAll(true);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`/api/uploads/${uploadId}/chart-counts/?columns=${columns.join(',')}`, { credentials: 'same-origin' });
      const payload = await response.json();
      if (!response.ok || payload.row_count !== report.row_count ||
          columns.some((number) => !payload.columns?.[`column_${number}`])) {
        throw new Error(typeof payload.detail === 'string' ? payload.detail : '전체 행 그래프를 집계하지 못했습니다.');
      }
      setChartAggregates(payload.columns);
      setBrowseAll(true);
    } catch (caught) {
      setError(caught.message);
    } finally { setLoading(false); }
  }

  function showFirstRows() {
    setBrowseAll(false);
    setRows(report.preview);
    setPage(1);
    setError('');
  }

  return <section className="panel" aria-labelledby="service-preview-title">
    <div className="section-title"><h2 id="service-preview-title">서비스 미리보기</h2>
      <button type="button" onClick={() => setOpened(!opened)} aria-expanded={opened}>
        {opened ? '미리보기 접기' : '미리보기 펼치기'}
      </button></div>
    <p className="muted">{browseAll
      ? `CSV 전체 ${report.row_count.toLocaleString()}개 항목을 20개씩 탐색합니다. 그래프는 전체 행 기준입니다.`
      : `CSV의 앞 ${records.length.toLocaleString()}개 항목을 보여줍니다.`} 저장 기능은 아직 제공하지 않습니다.</p>
    {usedFallback && <p className="notice">Claude 설정을 적용할 수 없어 전체 컬럼 표를 표시합니다.</p>}
    {opened && <>
      {report.row_count > 20 && <button type="button" className="service-back-button"
        disabled={loading}
        onClick={() => browseAll ? showFirstRows() : showAllRows()}>
        {loading ? '불러오는 중…' : browseAll ? '앞 20행만 보기' : '전체 행 보기'}
      </button>}
      <PreviewRuntimeV2 key={String(browseAll)} config={config} columns={report.columns} records={records}
        chartAggregates={browseAll ? chartAggregates : null} />
      {browseAll && report.row_count > 20 && <nav className="service-pagination" aria-label="데이터 페이지">
        <button type="button" disabled={loading || page === 1} onClick={() => openPage(page - 1)}>이전 20행</button>
        <span>{page.toLocaleString()} / {totalPages.toLocaleString()}페이지</span>
        <button type="button" disabled={loading || page === totalPages} onClick={() => openPage(page + 1)}>다음 20행</button>
      </nav>}
      {error && <p className="error" role="alert">{error}</p>}
    </>}
  </section>;
}
