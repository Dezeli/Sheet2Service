import React, { useEffect, useRef, useState } from 'react';
import { previewRecords, safeWebUrl, templates, validateConfig } from './config';
import './preview.css';
import Charts from './Charts.jsx';

const text = (value) => value === null || value === undefined || String(value).trim() === '' ? '-' : String(value);
const templateNotes = {
  cards: '카드로 항목 살펴보기',
  table: '표에서 항목 비교하기',
  grouped: '분류별 항목 살펴보기',
};

function Picture({ value }) {
  const url = safeWebUrl(value);
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [url]);
  return url && !failed
    ? <img className="service-image" src={url} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
    : <div className="service-image service-image-empty">이미지 없음</div>;
}

function Fields({ ids = [], record, columns }) {
  return <dl className="service-fields">{ids.map((id) => {
    const value = text(record.values[id]);
    return <div key={id}><dt>{columns.find((column) => column.id === id)?.label || id}</dt>
      <dd>{value.length > 250 ? <details><summary>{value.slice(0, 100)}… 더 보기</summary><p>{value}</p></details> : value}</dd></div>;
  })}</dl>;
}

function Cards({ page, records, columns, openDetail }) {
  const b = page.bindings;
  return <div className="service-grid">{records.map((record) => <article className="service-card" key={record.id}>
    {b.image && <Picture value={record.values[b.image]} />}
    <div className="service-card-body">
      {b.badge && <span className="service-badge">{text(record.values[b.badge])}</span>}
      <h3>{page.detailPage ? <button className="service-title-button" onClick={() => openDetail(page.detailPage, record.id)}>{text(record.values[b.title])}</button> : text(record.values[b.title])}</h3>
      {b.subtitle && <p className="muted">{text(record.values[b.subtitle])}</p>}
      <Fields ids={b.fields} record={record} columns={columns} />
    </div>
  </article>)}</div>;
}

function Grouped({ page, records, columns, openDetail }) {
  const groups = new Map();
  for (const record of records) {
    const key = text(record.values[page.bindings.group]);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(record);
  }
  return <div className="service-groups">{Array.from(groups.entries()).map(([name, items], index) => <section className="service-group" key={name} aria-labelledby={`${page.id}_group_${index}`}>
    <div className="service-group-heading">
      <h3 id={`${page.id}_group_${index}`}>{name}</h3>
      <span>{items.length.toLocaleString()}개 항목</span>
    </div>
    <Cards page={page} records={items} columns={columns} openDetail={openDetail} />
  </section>)}</div>;
}

function TableCell({ value }) {
  const display = text(value);
  const link = safeWebUrl(value);
  const content = display.length > 120 ? <details><summary>{display.slice(0, 80)}… 더 보기</summary><p>{display}</p></details> : display;
  return link ? <a href={link} target="_blank" rel="noopener noreferrer">{display.length > 80 ? `${display.slice(0, 80)}…` : display}</a> : content;
}

function Table({ page, records, columns }) {
  const fields = page.bindings.fields || [];
  return <div className="service-table-scroll" role="region" aria-label={page.title} tabIndex={0}>
    <table className="service-table">
      <thead><tr>{fields.map((id) => <th scope="col" key={id}>{columns.find((column) => column.id === id)?.label || id}</th>)}</tr></thead>
      <tbody>{records.map((record) => <tr key={record.id}>
        {fields.map((id) => <td key={id}><TableCell value={record.values[id]} /></td>)}
      </tr>)}</tbody>
    </table>
  </div>;
}

function Detail({ page, record, columns }) {
  const b = page.bindings;
  const link = safeWebUrl(record.values[b.link]);
  const phone = text(record.values[b.phone]);
  const dial = /^[+\d() .-]+$/.test(phone) && /\d/.test(phone) ? phone.replace(/[^+\d]/g, '') : null;
  return <article className="service-detail">
    {b.image && <Picture value={record.values[b.image]} />}
    <div>{b.badge && <span className="service-badge">{text(record.values[b.badge])}</span>}
      <h3>{text(record.values[b.title])}</h3>
      <div className="service-actions">
        {link && <a href={link} target="_blank" rel="noopener noreferrer">외부 링크 열기</a>}
        {b.phone && (dial ? <a href={`tel:${dial}`}>{phone}</a> : <span>{phone}</span>)}
      </div>
      <Fields ids={b.fields} record={record} columns={columns} />
    </div>
  </article>;
}

// Runtime accepts configuration and records; it does not parse CSV or call a model.
export function PreviewRuntime({ config, columns, records }) {
  try {
    validateConfig(config, columns);
    if (config.pages.some((item) => !templates[item.template].ready)) throw new Error('아직 사용할 수 없는 미리보기 형식이 포함되어 있습니다.');
  } catch (err) { return <p className="error" role="alert">{err.message}</p>; }
  return <RuntimePages key={JSON.stringify(config)} config={config} columns={columns} records={records} />;
}

function RuntimePages({ config, columns, records }) {
  const [location, setLocation] = useState({ page: config.pages[0]?.id, record: records[0]?.id });
  const [lastListPage, setLastListPage] = useState(config.pages.find((item) => item.template !== 'detail')?.id);
  const heading = useRef(null);
  const page = config.pages.find((item) => item.id === location.page);
  const record = records.find((item) => item.id === location.record);
  const listPages = config.pages.filter((item) => item.template !== 'detail');
  const openList = (id) => {
    setLastListPage(id);
    setLocation({ page: id, record: null });
  };
  const openDetail = (id, recordId) => {
    if (page?.template !== 'detail') setLastListPage(page?.id);
    setLocation({ page: id, record: recordId });
  };
  useEffect(() => { heading.current?.focus(); }, [location]);
  return <div className="service-runtime">
    <div className="service-preview-meta">
      <span>{records.length.toLocaleString()}개 항목</span>
      <span>{listPages.length.toLocaleString()}개 목록 화면</span>
    </div>
    <nav className="service-view-tabs" aria-label="서비스 미리보기 화면 선택">{listPages.map((item) => <button key={item.id} type="button" aria-current={page?.id === item.id ? 'page' : undefined} onClick={() => openList(item.id)}>
      <strong>{item.title}</strong>
      <span>{templateNotes[item.template] || templates[item.template].label}</span>
    </button>)}</nav>
    {page?.template === 'detail' && <button type="button" className="service-back-button" onClick={() => openList(lastListPage || listPages[0]?.id)}>목록으로 돌아가기</button>}
    <h2 ref={heading} tabIndex={-1}>{page?.title || config.title}</h2>
    <Charts configs={page?.charts} records={records} />
    {!records.length ? <p>표시할 항목이 없습니다.</p>
      : page?.template === 'cards' ? <Cards page={page} records={records} columns={columns} openDetail={openDetail} />
        : page?.template === 'grouped' ? <Grouped page={page} records={records} columns={columns} openDetail={openDetail} />
        : page?.template === 'table' ? <Table page={page} records={records} columns={columns} />
        : page?.template === 'detail' && record ? <Detail page={page} record={record} columns={columns} />
          : <p>선택한 항목을 찾을 수 없습니다.</p>}
  </div>;
}

export default function ServicePreview({ report, config }) {
  const [opened, setOpened] = useState(true);
  if (!config) return null;
  const records = previewRecords(report);
  return <section className="panel" aria-labelledby="service-preview-title">
    <div className="section-title"><h2 id="service-preview-title">서비스 미리보기</h2>
      <button onClick={() => setOpened(!opened)} aria-expanded={opened}>{opened ? '미리보기 접기' : '미리보기 펼치기'}</button></div>
    <p className="muted">Claude API가 생성한 설정으로 CSV의 앞 {records.length.toLocaleString()}개 항목을 보여줍니다. 전체 데이터 연결과 저장 기능은 아직 제공하지 않습니다.</p>
    {opened && <PreviewRuntime config={config} columns={report.columns} records={records} />}
  </section>;
}
