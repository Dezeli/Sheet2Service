import React from 'react';
import { countGroups } from './charts.js';

// categories need telling apart at a glance: the service's own function colours first, then quieter tones (no violet)
const colors = ['#0d7480', '#2a64a8', '#c98a12', '#1f7a52', '#b4545f', '#5d6b72', '#8cc1c7', '#9fb0b7'];

function Chart({ config, records, aggregates }) {
  const summary = aggregates?.[config.groupBy];
  const groups = summary ? summary.groups : countGroups(records, config.groupBy);
  const total = summary ? summary.total : records.length;
  const max = Math.max(1, ...groups.map((item) => item.count));
  let offset = 0;
  const stops = groups.map((item, index) => {
    const start = offset;
    offset += item.ratio * 100;
    return `${colors[index]} ${start}% ${offset}%`;
  });
  return <figure className="service-chart">
    <figcaption>{config.title}</figcaption>
    {!total ? <p className="muted">집계할 데이터가 없습니다.</p> : <>
      {config.type === 'donut' && <div className="chart-donut" aria-hidden="true" style={{ background: `conic-gradient(${stops.join(',')})` }}>
        <div><strong>{total.toLocaleString()}</strong><span>건</span></div>
      </div>}
      <ul className="chart-values" aria-label={`${config.title} 집계 결과`}>
        {groups.map((item, index) => <li key={index}>
          <div className="chart-value-label"><span><i aria-hidden="true" style={{ background: colors[index] }} />{item.label}</span>
            <strong>{item.count} <small>({(item.ratio * 100).toFixed(1)}%)</small></strong></div>
          {config.type === 'bar' && <div className="chart-track" aria-hidden="true"><div style={{ width: `${item.count / max * 100}%`, background: colors[index] }} /></div>}
        </li>)}
      </ul>
    </>}
  </figure>;
}

export default function Charts({ configs, records, aggregates }) {
  if (!configs?.length) return null;
  return <section className="service-charts" aria-label="서비스 분포">
    <div className="chart-grid">{configs.map((config, index) => <Chart key={index} config={config} records={records} aggregates={aggregates} />)}</div>
  </section>;
}
