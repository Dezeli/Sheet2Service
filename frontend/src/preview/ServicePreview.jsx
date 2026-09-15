import React, { useEffect, useRef, useState } from 'react';
import { previewRecords, reservationConfig, safeWebUrl, templates, validateConfig } from './config';
import './preview.css';
import Charts from './Charts.jsx';

const text = (value) => value === null || value === undefined || String(value).trim() === '' ? '—' : String(value);

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
      <dd>{value.length > 250 ? <details><summary>{value.slice(0, 100)}…</summary><p>{value}</p></details> : value}</dd></div>;
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
        {link && <a href={link} target="_blank" rel="noopener noreferrer">제공처 페이지 열기 ↗</a>}
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
    if (config.pages.some((item) => !templates[item.template].ready)) throw new Error('이 설정에는 아직 준비되지 않은 템플릿이 포함되어 있습니다.');
  } catch (err) { return <p className="error" role="alert">{err.message}</p>; }
  return <RuntimePages key={JSON.stringify(config)} config={config} columns={columns} records={records} />;
}

function RuntimePages({ config, columns, records }) {
  const [location, setLocation] = useState({ page: config.pages[0]?.id, record: records[0]?.id });
  const heading = useRef(null);
  const page = config.pages.find((item) => item.id === location.page);
  const record = records.find((item) => item.id === location.record);
  useEffect(() => { heading.current?.focus(); }, [location]);
  return <div className="service-runtime">
    <nav aria-label="서비스 페이지">{config.pages.filter((item) => item.template !== 'detail').map((item) => <button key={item.id} aria-current={page?.id === item.id ? 'page' : undefined} onClick={() => setLocation({ page: item.id, record: null })}>{item.title}</button>)}</nav>
    <h2 ref={heading} tabIndex={-1}>{page?.title || config.title}</h2>
    <Charts configs={page?.charts} records={records} />
    {!records.length ? <p>표시할 서비스가 없습니다.</p>
      : page?.template === 'cards' ? <Cards page={page} records={records} columns={columns} openDetail={(id, recordId) => setLocation({ page: id, record: recordId })} />
        : page?.template === 'detail' && record ? <Detail page={page} record={record} columns={columns} />
          : <p>표시할 항목을 선택해 주세요.</p>}
  </div>;
}

export default function ServicePreview({ report }) {
  const [opened, setOpened] = useState(false);
  let config;
  try { config = reservationConfig(report.columns); } catch { return null; }
  return <section className="panel" aria-labelledby="service-preview-title">
    <div className="section-title"><h2 id="service-preview-title">서비스 Preview</h2>
      <button onClick={() => setOpened(!opened)} aria-expanded={opened}>{opened ? 'Preview 닫기' : 'Preview 열기'}</button></div>
    <p className="muted">시설 예약 예시 설정으로 앞 {Math.min(report.preview.length, 5)}개 항목을 표시합니다. 접수 상태와 기간은 CSV에 저장된 값입니다.</p>
    {opened && <PreviewRuntime config={config} columns={report.columns} records={previewRecords(report)} />}
  </section>;
}
