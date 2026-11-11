import React, { useEffect, useState } from 'react';
import { Icon } from '../components/ui';
import { placeHref, useNav } from '../booking/nav';

const ROTATE_MS = 5000;
const MAX = 5;
const dateText = (value) => new Date(value).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' });

/**
 * The latest notices in one line above a booker's screens, so nobody has to open a tab to see them.
 * Several notices take turns every few seconds (held while pointed at or focused); a click opens that notice.
 */
export default function NoticeTicker({ uploadId }) {
  const nav = useNav();
  const [notices, setNotices] = useState([]);
  const [index, setIndex] = useState(0);
  const [held, setHeld] = useState(false);

  useEffect(() => {
    let active = true;
    fetch(`/api/uploads/${uploadId}/notices/?page=1`, { credentials: 'same-origin' })
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => { if (active && data) setNotices(data.notices.slice(0, MAX)); })
      .catch(() => {});
    return () => { active = false; };
  }, [uploadId]);

  const still = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  useEffect(() => {
    if (notices.length < 2 || held || still) return undefined;
    const timer = setInterval(() => setIndex((current) => (current + 1) % notices.length), ROTATE_MS);
    return () => clearInterval(timer);
  }, [notices.length, held, still]);

  if (!notices.length) return null;
  const item = notices[index % notices.length];
  const step = (by) => setIndex((current) => (current + by + notices.length) % notices.length);
  return <div className="notice-ticker" onMouseEnter={() => setHeld(true)} onMouseLeave={() => setHeld(false)}
    onFocus={() => setHeld(true)} onBlur={() => setHeld(false)}>
    <span className="notice-ticker__tag">공지</span>
    <a key={item.id} className="notice-ticker__item" href={placeHref(uploadId, nav?.page, 'notices', item.id)} aria-live={held ? 'off' : 'polite'}
      onClick={(event) => {
        if (!nav || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault(); nav.go('notices', item.id);
      }}>
      <strong>{item.title}</strong><time dateTime={item.published_at || item.updated_at}>{dateText(item.published_at || item.updated_at)}</time>
    </a>
    {notices.length > 1 && <span className="notice-ticker__steps">
      <button type="button" aria-label="이전 공지" onClick={() => step(-1)}><Icon name="prev" size={16} /></button>
      <span className="notice-ticker__count">{index % notices.length + 1}/{notices.length}</span>
      <button type="button" aria-label="다음 공지" onClick={() => step(1)}><Icon name="next" size={16} /></button>
    </span>}
  </div>;
}
