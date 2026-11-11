import React, { useEffect, useMemo, useState } from 'react';
import Charts from './Charts.jsx';
import { recordsFromRows, safeWebUrl } from './config.js';
import { chartConfigsV2, columnId, columnLabel, validateConfigV2 } from './configV2.js';
import './preview.css';
import SectionIcon from '../components/SectionIcon';
import { Empty, IconButton, Pager, Segmented } from '../components/ui';

const labels = { cards: '카드 목록', table: '표 목록', grouped: '그룹 목록' };
const display = (value) => value === null || value === undefined || String(value).trim() === '' ? '빈 값' : String(value);
const fieldValue = (record, columns, number) => display(record.values[columnId(columns, number)]);

function Fields({ record, columns, numbers }) {
  return <dl className="service-fields">{numbers.map((number) => <div key={number} className={fieldValue(record, columns, number).length > 80 || /[\r\n]/.test(fieldValue(record, columns, number)) ? 'field-wide' : undefined}>
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
          : <span className="service-table-value" title={fieldValue(record, columns, number)}>{fieldValue(record, columns, number)}</span>}
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
    {record ? <>
      <div className="resource-trail"><IconButton icon="back" label="목록으로" onClick={() => setSelectedRecord(null)} /><strong>상세</strong></div>
      <Fields record={record} columns={columns} numbers={columns.map((_, index) => index + 1)} />
    </> : <>
      {config.views.length > 1 && <Segmented label="보기" value={selectedIndex} onChange={setSelectedIndex}
        options={config.views.map((item, index) => ({ value: index, label: `${labels[item.template]}${config.views.filter((candidate) => candidate.template === item.template).length > 1 ? ` ${index + 1}` : ''}` }))} />}
      <Charts configs={chartConfigsV2(view.charts, columns)} records={records} aggregates={chartAggregates} />
      {!records.length ? <Empty>표시할 항목이 없습니다.</Empty>
        : view.template === 'cards' ? <Cards view={view} records={records} columns={columns} openDetail={openDetail} />
          : view.template === 'grouped' ? <Grouped view={view} records={records} columns={columns} openDetail={openDetail} />
            : <Table view={view} records={records} columns={columns} openDetail={openDetail} />}
    </>}
  </div>;
}

export default function ServicePreviewV2({ uploadId, report, config, usedFallback }) {
  const [opened, setOpened] = useState(true);
  const [browseAll, setBrowseAll] = useState(false);
  useEffect(() => { showAllRows(); }, [uploadId]);  // the dashboard always counts the whole sheet
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

  return <section className="panel" aria-labelledby="service-preview-title">
    <div className="section-title"><h2 id="service-preview-title" className="icon-heading"><SectionIcon name="analysis" />데이터 통계</h2>
      <span className="section-tools"><span className="section-count">{report.row_count.toLocaleString()}행</span>
        <IconButton icon="down" label={opened ? '접기' : '펼치기'} className={opened ? 'is-flipped' : ''} aria-expanded={opened} onClick={() => setOpened(!opened)} /></span></div>
    {loading && !browseAll && <p className="muted" role="status">집계하는 중…</p>}
    {opened && <>
      <PreviewRuntimeV2 key={String(browseAll)} config={config} columns={report.columns} records={records}
        chartAggregates={browseAll ? chartAggregates : null} />
      {browseAll && <Pager page={page} count={report.row_count} disabled={loading} onPage={openPage} />}
      {error && <p className="error" role="alert">{error}</p>}
    </>}
  </section>;
}
