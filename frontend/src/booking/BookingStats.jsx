import React, { useEffect, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import { api, query, statusLabels } from './api.js';
import { IconButton } from '../components/ui';
import { ItemLink, PlaceLink } from './nav';

// the order a booking moves through, so the bar reads left to right like the ledger
const FLOW = [['requested', 'pending'], ['waiting', 'pending'], ['approved', 'ok'], ['won', 'ok'], ['in_use', 'ok'],
  ['completed', 'muted'], ['cancelled', 'muted'], ['rejected', 'bad'], ['lost', 'muted'], ['other', 'muted']];

/** Today first: what the front desk handles now, then where every booking stands, then the busiest items. */
export default function BookingStats({ uploadId, persona, scope }) {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState('');
  async function load() {
    try { setStats(await api(`/api/uploads/${uploadId}/bookings/stats/${query({ persona: persona.id, scope })}`)); setError(''); }
    catch (caught) { setError(caught.message); }
  }
  useEffect(() => { load(); }, [uploadId, persona.id, scope]);
  const parts = stats ? FLOW.filter(([status]) => stats.counts[status]).map(([status, tone]) => ({ status, tone, count: stats.counts[status] })) : [];
  return <section className="panel ledger-stats" aria-labelledby="booking-stats-title">
    <div className="section-title"><h2 id="booking-stats-title" className="icon-heading"><SectionIcon name="dashboard" />예약 현황</h2>
      <IconButton icon="refresh" label="새로고침" onClick={load} /></div>
    {error && <p className="error" role="alert">{error}</p>}
    {stats && <div className="ledger-stats__body"><div className="ledger-stats__main">
      <div className="ledger-focus">
        <div><span className="ledger-focus__label"><PlaceLink menu="review" view="today">오늘</PlaceLink></span><strong>{stats.today.toLocaleString()}</strong><span className="ledger-focus__unit">건</span></div>
        <div><span className="ledger-focus__label">오늘 이후 예정</span><strong>{stats.upcoming.toLocaleString()}</strong><span className="ledger-focus__unit">건</span></div>
        <div className="is-quiet"><span className="ledger-focus__label"><PlaceLink menu="review" view="pending">승인 대기</PlaceLink></span><strong>{stats.counts.requested.toLocaleString()}</strong><span className="ledger-focus__unit">건</span></div>
      </div>
      <div className="ledger-flow">
        <div className="ledger-flow__head"><span>전체 {stats.total.toLocaleString()}건</span><span className="muted">시트 기록 {stats.imported.toLocaleString()} · 새 예약 {stats.new.toLocaleString()} · 항목 {stats.resources.toLocaleString()}</span></div>
        {stats.total > 0 && <div className="ledger-flow__bar" role="img" aria-label={parts.map((part) => `${statusLabels[part.status]} ${part.count}건`).join(', ')}>
          {parts.map((part) => <i key={part.status} className={`tone-${part.tone} is-${part.status}`} style={{ flexGrow: part.count }} />)}
        </div>}
        <ul className="ledger-flow__legend">{parts.map((part) => <li key={part.status}><i className={`tone-${part.tone} is-${part.status}`} aria-hidden="true" />
          {statusLabels[part.status]}<b>{part.count.toLocaleString()}</b></li>)}</ul>
      </div>
      </div>
      {stats.top_resources.length > 0 && <div className="top-resources"><h3>예약이 많은 항목</h3>
        <ol>{stats.top_resources.map((item) => <li key={item.id}><ItemLink item={item.id} path={item.path} menu="review">{item.name}</ItemLink>
          <strong>{item.count.toLocaleString()}</strong></li>)}</ol></div>}
    </div>}
  </section>;
}
