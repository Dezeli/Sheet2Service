import React, { useEffect, useId, useRef, useState } from 'react';
import { api, query as toQuery } from './api.js';

/** The part of `text` matching `term`, emphasized. */
function Marked({ text, term }) {
  const at = term ? text.toLocaleLowerCase().indexOf(term.toLocaleLowerCase()) : -1;
  if (at < 0) return text;
  return <>{text.slice(0, at)}<mark>{text.slice(at, at + term.length)}</mark>{text.slice(at + term.length)}</>;
}

/**
 * Pick one resource from hundreds: opens on focus with everything in path order, narrows as you type,
 * loads more on scroll, and works from the keyboard (↑ ↓ Enter Esc). `leafOnly` lists only what can be booked.
 */
export default function ResourceCombobox({ uploadId, value, onChange, leafOnly = false, label = '항목', placeholder = '이름을 입력하거나 목록에서 고르세요' }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [items, setItems] = useState([]);
  const [count, setCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);
  const ticket = useRef(0);
  const input = useRef(null);
  const list = useRef(null);
  const listId = useId();
  const term = open ? text.trim() : '';

  async function fetchPage(offset = 0) {
    const mine = ++ticket.current;
    setLoading(true);
    try {
      const data = await api(`/api/uploads/${uploadId}/resources/${toQuery({ flat: leafOnly ? 'leaf' : 'any', q: term, offset })}`);
      if (mine !== ticket.current) return;
      setItems((current) => (offset ? [...current, ...data.resources] : data.resources));
      setCount(data.count); setHasNext(data.has_next);
      if (!offset) setActive(0);
    } catch { if (mine === ticket.current && !offset) setItems([]); }
    finally { if (mine === ticket.current) setLoading(false); }
  }
  useEffect(() => {
    if (!open) return undefined;
    const timer = setTimeout(() => fetchPage(0), term ? 180 : 0);
    return () => clearTimeout(timer);
  }, [open, term, uploadId, leafOnly]);

  useEffect(() => {
    list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [active]);

  function show() { if (!open) { setText(''); setOpen(true); } }
  function close() { setOpen(false); setText(''); }
  function pick(item) { onChange(item); close(); input.current?.blur(); }

  function onKeyDown(event) {
    if (event.key === 'ArrowDown') { event.preventDefault(); if (!open) show(); else setActive((i) => Math.min(items.length - 1, i + 1)); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); setActive((i) => Math.max(0, i - 1)); }
    else if (event.key === 'Enter') { if (open && items[active]) { event.preventDefault(); pick(items[active]); } }
    else if (event.key === 'Escape') { if (open) { event.preventDefault(); close(); } }
    else if (event.key === 'Tab') close();
  }

  function onScroll(event) {
    const box = event.currentTarget;
    if (hasNext && !loading && box.scrollTop + box.clientHeight > box.scrollHeight - 40) fetchPage(items.length);
  }

  const shown = open ? text : value?.name || '';
  return <div className={`combobox${open ? ' is-open' : ''}`}>
    <div className="combobox-field">
      <input ref={input} type="text" role="combobox" aria-label={label} aria-expanded={open} aria-controls={listId} aria-autocomplete="list"
        aria-activedescendant={open && items[active] ? `${listId}-${active}` : undefined}
        placeholder={open && value ? value.name : placeholder} value={shown}
        onFocus={show} onClick={show} onChange={(event) => { setText(event.target.value); setOpen(true); }} onKeyDown={onKeyDown}
        onBlur={() => setTimeout(close, 120)} />
      {value && <button type="button" className="combobox-clear" aria-label={`${label} 선택 해제`} onMouseDown={(event) => event.preventDefault()}
        onClick={() => { onChange(null); input.current?.focus(); }}>×</button>}
      <svg className="combobox-mark" aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="m7 10 5 5 5-5" /></svg>
    </div>
    {value && !open && value.path && value.path.split(' / ').slice(-2, -1)[0] && value.path.split(' / ').slice(-2, -1)[0] !== value.name && <small className="combobox-path muted" title={value.path.split(' / ').join(' › ')}>{value.path.split(' / ').slice(-2, -1)[0]}</small>}
    {open && <div className="combobox-popup">
      <ul id={listId} ref={list} role="listbox" aria-label={`${label} 목록`} onScroll={onScroll} onMouseDown={(event) => event.preventDefault()}>
        {items.map((item, index) => {
          const group = item.path.split(' / ')[0];
          const header = !term && item.level > 0 && (index === 0 || items[index - 1].path.split(' / ')[0] !== group);
          return <React.Fragment key={item.id}>
            {header && <li role="presentation" className="combobox-group">{group}</li>}
            <li id={`${listId}-${index}`} data-index={index} role="option" aria-selected={index === active}
              className={`${index === active ? 'is-active' : ''}${value?.id === item.id ? ' is-current' : ''}`}
              onMouseEnter={() => setActive(index)} onClick={() => pick(item)}>
              <span className="combobox-name"><Marked text={item.name} term={term} /></span>
              {item.level > 0 && item.path.split(' / ').slice(-2, -1)[0] !== item.name && <small className="muted" title={item.path.split(' / ').join(' › ')}><Marked text={item.path.split(' / ').slice(-2, -1)[0] || ''} term={term} /></small>}
              {!leafOnly && item.children_count > 0 && <small className="combobox-badge">하위 {item.children_count}</small>}
            </li>
          </React.Fragment>;
        })}
        {!items.length && !loading && <li role="presentation" className="combobox-empty">"{term}"에 맞는 항목이 없습니다.</li>}
      </ul>
      <div className="combobox-foot muted">{loading ? '불러오는 중…' : `${count.toLocaleString()}개${hasNext ? ' · 아래로 내리면 더 보입니다' : ''}`}</div>
    </div>}
  </div>;
}
