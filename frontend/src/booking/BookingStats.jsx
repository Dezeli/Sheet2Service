import React, { useEffect, useState } from 'react';
import SectionIcon from '../components/SectionIcon';
import { api, query, statusLabels } from './api.js';

export default function BookingStats({ uploadId, persona, scope }) {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState('');
  async function load() {
    try { setStats(await api(`/api/uploads/${uploadId}/bookings/stats/${query({ persona: persona.id, scope })}`)); setError(''); }
    catch (caught) { setError(caught.message); }
  }
  useEffect(() => { load(); }, [uploadId, persona.id, scope]);
  return <section className="panel" aria-labelledby="booking-stats-title">
    <div className="section-title"><h2 id="booking-stats-title" className="icon-heading"><SectionIcon name="analysis" />예약 현황</h2>
      <button type="button" className="service-back-button" onClick={load}>새로고침</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    {stats && <>
      <dl className="metrics">
        <div><dt>전체 예약</dt><dd>{stats.total.toLocaleString()}</dd></div>
        <div><dt>오늘</dt><dd>{stats.today.toLocaleString()}</dd></div>
        <div><dt>예정</dt><dd>{stats.upcoming.toLocaleString()}</dd></div>
        <div><dt>승인 대기</dt><dd>{stats.counts.requested.toLocaleString()}</dd></div>
        <div><dt>확정</dt><dd>{stats.counts.approved.toLocaleString()}</dd></div>
        <div><dt>이용 완료</dt><dd>{stats.counts.completed.toLocaleString()}</dd></div>
        <div><dt>취소·거절</dt><dd>{(stats.counts.cancelled + stats.counts.rejected).toLocaleString()}</dd></div>
        <div><dt>항목 수</dt><dd>{stats.resources.toLocaleString()}</dd></div>
      </dl>
      <p className="muted">시트에서 가져온 기록 {stats.imported.toLocaleString()}건, 서비스에서 새로 받은 예약 {stats.new.toLocaleString()}건.
        {Object.entries(stats.counts).filter(([status, count]) => count && !['requested', 'approved', 'completed', 'cancelled', 'rejected'].includes(status))
          .map(([status, count]) => ` ${statusLabels[status]} ${count.toLocaleString()}건.`).join('')}</p>
      {stats.top_resources.length > 0 && <div className="top-resources"><h3>예약이 많은 항목</h3>
        <ol>{stats.top_resources.map((item) => <li key={item.path}><span>{item.path}</span><strong>{item.count.toLocaleString()}</strong></li>)}</ol></div>}
    </>}
  </section>;
}
