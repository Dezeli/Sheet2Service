import React from 'react';
import { countGroups } from './charts.js';

const colors = ['#2457c5', '#147d73', '#9b4dab', '#b06416', '#547195', '#aa3d50', '#657526', '#6d5ac8'];

function Chart({ config, records }) {
  const groups = countGroups(records, config.groupBy);
  const max = Math.max(1, ...groups.map((item) => item.count));
  let offset = 0;
  const stops = groups.map((item, index) => {
    const start = offset;
    offset += item.ratio * 100;
    return `${colors[index]} ${start}% ${offset}%`;
  });
  return <figure className="service-chart">
    <figcaption>{config.title}</figcaption>
    {!records.length ? <p className="muted">집계할 데이터가 없습니다.</p> : <>
      {config.type === 'donut' && <div className="chart-donut" aria-hidden="true" style={{ background: `conic-gradient(${stops.join(',')})` }}>
        <div><strong>{records.length}</strong><span>항목</span></div>
      </div>}
      <ul className="chart-values" aria-label={`${config.title} 집계 결과`}>
        {groups.map((item, index) => <li key={index}>
          <div className="chart-value-label"><span><i aria-hidden="true" style={{ background: colors[index] }} />{item.label}</span>
            <strong>{item.count}개 <small>({(item.ratio * 100).toFixed(1)}%)</small></strong></div>
          {config.type === 'bar' && <div className="chart-track" aria-hidden="true"><div style={{ width: `${item.count / max * 100}%`, background: colors[index] }} /></div>}
        </li>)}
      </ul>
    </>}
  </figure>;
}

export default function Charts({ configs, records }) {
  if (!configs?.length) return null;
  return <section className="service-charts" aria-label="서비스 분포">
    <p className="muted">현재 Preview의 {records.length}개 항목 기준입니다. 빈 값도 별도 분류로 포함합니다.</p>
    <div className="chart-grid">{configs.map((config, index) => <Chart key={index} config={config} records={records} />)}</div>
  </section>;
}
