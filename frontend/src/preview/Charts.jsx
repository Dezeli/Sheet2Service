import React from 'react';
import { countGroups } from './charts.js';

const colors = ['#2457c5', '#147d73', '#9b4dab', '#b06416', '#547195', '#aa3d50', '#657526', '#6d5ac8'];

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
        <div><strong>{total.toLocaleString()}</strong><span>개 항목</span></div>
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
    <p className="muted">{aggregates ? `CSV 전체 ${Object.values(aggregates)[0]?.total.toLocaleString() ?? 0}개` : `현재 미리보기에 표시된 ${records.length.toLocaleString()}개`} 항목을 기준으로 집계했습니다. 빈 값은 별도 그룹으로 셉니다.</p>
    <div className="chart-grid">{configs.map((config, index) => <Chart key={index} config={config} records={records} aggregates={aggregates} />)}</div>
  </section>;
}
