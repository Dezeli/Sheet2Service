import React, { useEffect, useId, useRef, useState } from 'react';

/*
 * Shared controls for every service screen. How to pick a control:
 * - 2–5 short exclusive options: Segmented (all visible, one tap).
 * - a small number: Stepper (− n +, typing still works).
 * - a long or growing list: a search-as-you-type dropdown (ChoiceCombobox, or ResourceCombobox for resources).
 * - text with a fixed shape (time, phone): an input that formats itself while typing.
 * - an action whose meaning an icon carries on its own (close, refresh, edit, delete, page): IconButton with a label for screen readers.
 */

const PATHS = {
  close: <path d="M6 6l12 12M18 6 6 18" />,
  back: <path d="m14 6-6 6 6 6" />,
  prev: <path d="m15 6-6 6 6 6" />,
  next: <path d="m9 6 6 6-6 6" />,
  down: <path d="m7 10 5 5 5-5" />,
  refresh: <><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 4v7h-7" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  edit: <><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="m13.5 6.5 4 4" /></>,
  trash: <><path d="M4 7h16M10 11v6M14 11v6" /><path d="M6 7l1 13h10l1-13M9 7V4h6v3" /></>,
  check: <path d="m5 12 5 5L19 7" />,
  pause: <><circle cx="12" cy="12" r="9" /><path d="M10 9v6M14 9v6" /></>,
  play: <><circle cx="12" cy="12" r="9" /><path d="m10 8.5 5 3.5-5 3.5z" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M7 3v4M17 3v4M3 11h18" /></>,
  today: <><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M7 3v4M17 3v4M3 11h18" /><circle cx="12" cy="16" r="1.6" /></>,
  phone: <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2" />,
  download: <><path d="M12 4v11M7 10l5 5 5-5" /><path d="M5 20h14" /></>,
  filter: <path d="M3 5h18l-7 8v6l-4 2v-8z" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  eye: <><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="3" /></>,
  eyeOff: <><path d="M10.6 5.6A9.6 9.6 0 0 1 12 5.5C18 5.5 21.5 12 21.5 12a17 17 0 0 1-2.6 3.4M6.6 6.6A16 16 0 0 0 2.5 12S6 18.5 12 18.5a9.2 9.2 0 0 0 4.4-1.1" /><path d="M3 3l18 18M9.9 9.9a3 3 0 0 0 4.2 4.2" /></>,
  reply: <><path d="M10 8 4 13l6 5" /><path d="M4 13h10a6 6 0 0 1 6 6" /></>,
  detail: <><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></>,
};

export function Icon({ name, size = 18 }) {
  return <svg className="ui-icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{PATHS[name]}</svg>;
}

/** A button that is only an icon; `label` names it for screen readers and as its tooltip. */
export function IconButton({ icon, label, tone, className = '', size, ...props }) {
  return <button type="button" className={`ui-icon-button${tone ? ` tone-${tone}` : ''} ${className}`} aria-label={label} title={label} {...props}>
    <Icon name={icon} size={size} />
  </button>;
}

/** ‹ 3 / 12 ›, hidden when everything fits on one page. */
export function Pager({ page, count, size = 20, onPage, disabled, label = '페이지' }) {
  const pages = Math.max(1, Math.ceil(count / size));
  if (pages <= 1) return null;
  return <nav className="ui-pager" aria-label={label}>
    <IconButton icon="prev" label="이전 페이지" disabled={disabled || page <= 1} onClick={() => onPage(page - 1)} />
    <span aria-live="polite"><strong>{page.toLocaleString()}</strong> / {pages.toLocaleString()}</span>
    <IconButton icon="next" label="다음 페이지" disabled={disabled || page >= pages} onClick={() => onPage(page + 1)} />
  </nav>;
}

/** Up to five exclusive options, all visible. */
export function Segmented({ options, value, onChange, label, disabled, size }) {
  return <div className={`ui-segmented${size === 'small' ? ' is-small' : ''}`} role="radiogroup" aria-label={label}>
    {options.map((option) => <button type="button" key={String(option.value)} role="radio" aria-checked={value === option.value}
      disabled={disabled || option.disabled} title={option.hint} onClick={() => onChange(option.value)}>{option.label}</button>)}
  </div>;
}

/** − n +, with typing allowed; `zeroLabel` names 0 (e.g. "제한 없음"). */
export function Stepper({ value, onChange, min = 0, max = 100000, step = 1, label, unit = '', zeroLabel, disabled }) {
  const number = Number.isFinite(Number(value)) ? Number(value) : min;
  const clamp = (next) => Math.min(max, Math.max(min, next));
  return <div className="ui-stepper" role="group" aria-label={label}>
    <IconButton icon="minus" label={`${label} 줄이기`} disabled={disabled || number <= min} onClick={() => onChange(clamp(number - step))} />
    <label className="ui-stepper-value">
      <span className="visually-hidden">{label}</span>
      {zeroLabel && number === 0
        ? <button type="button" className="ui-stepper-zero" disabled={disabled} onClick={() => onChange(clamp(step))}>{zeroLabel}</button>
        : <><input type="text" inputMode="numeric" value={String(number)} disabled={disabled}
          onChange={(event) => { const digits = event.target.value.replace(/\D/g, ''); onChange(clamp(digits === '' ? min : Number(digits))); }} />
          {unit && <span className="ui-stepper-unit">{unit}</span>}</>}
    </label>
    <IconButton icon="plus" label={`${label} 늘리기`} disabled={disabled || number >= max} onClick={() => onChange(clamp(number + step))} />
  </div>;
}

/** A search box that applies as you type (after a short pause), with a clear button. */
export function SearchField({ value, onChange, onSearch, placeholder = '검색', label = '검색어', delay = 250 }) {
  const [text, setText] = useState(value || '');
  const sent = useRef((value || '').trim()); // only a changed term searches, so mounting never fires a search
  const send = (term) => { if (term !== sent.current) { sent.current = term; onSearch?.(term); } };
  useEffect(() => { setText(value || ''); sent.current = (value || '').trim(); }, [value]);
  useEffect(() => {
    const timer = setTimeout(() => send(text.trim()), delay);
    return () => clearTimeout(timer);
  }, [text]);
  return <div className="ui-search">
    <Icon name="search" />
    <input type="search" aria-label={label} placeholder={placeholder} maxLength={100} value={text}
      onChange={(event) => { setText(event.target.value); onChange?.(event.target.value); }}
      onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); send(text.trim()); } }} />
    {text && <IconButton icon="close" label="검색어 지우기" className="ui-search-clear" onClick={() => { setText(''); onChange?.(''); send(''); }} />}
  </div>;
}

/** "930" → "09:30", "1400" → "14:00"; the colon is placed while typing. `allow24` accepts 24:00 for a closing time. */
export function formatClock(text, allow24 = false) {
  const digits = String(text || '').replace(/\D/g, '').slice(0, 4);
  if (digits.length <= 2) return digits;
  const hours = digits.length === 3 ? `0${digits[0]}` : digits.slice(0, 2);
  const minutes = digits.length === 3 ? digits.slice(1) : digits.slice(2);
  return `${hours}:${minutes}`;
}

export function validClock(text, allow24 = false) {
  if (allow24 && text === '24:00') return true;
  return /^([01]\d|2[0-3]):[0-5]\d$/.test(text || '');
}

export function TimeField({ value, onChange, label, allow24 = false, disabled, required }) {
  const [text, setText] = useState(value || '');
  useEffect(() => { setText(value || ''); }, [value]);
  const invalid = text.length === 5 && !validClock(text, allow24);
  return <input type="text" inputMode="numeric" className="ui-time" aria-label={label} placeholder={allow24 ? '24:00' : '09:00'} maxLength={5}
    value={text} disabled={disabled} required={required} aria-invalid={invalid}
    onChange={(event) => {
      const next = formatClock(event.target.value, allow24);
      setText(next);
      if (validClock(next, allow24) || next === '') onChange(next);
    }}
    onBlur={() => { if (text.length === 2 && Number(text) <= (allow24 ? 24 : 23)) { const whole = `${text}:00`; setText(whole); onChange(whole); } }} />;
}

/** A dropdown over a known list of strings that narrows as you type. For short lists use Segmented or a select. */
export function ChoiceCombobox({ options, value, onChange, label, placeholder = '선택하거나 입력해서 찾기', emptyLabel, disabled }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [active, setActive] = useState(0);
  const listId = useId();
  const list = useRef(null);
  const term = open ? text.trim().toLocaleLowerCase() : '';
  const items = [...(emptyLabel ? [{ value: '', label: emptyLabel }] : []),
    ...options.map((item) => (typeof item === 'string' ? { value: item, label: item } : item))]
    .filter((item) => !term || item.label.toLocaleLowerCase().includes(term)).slice(0, 200);
  const current = [...(emptyLabel ? [{ value: '', label: emptyLabel }] : []), ...options.map((item) => (typeof item === 'string' ? { value: item, label: item } : item))]
    .find((item) => item.value === value);
  useEffect(() => { list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' }); }, [active]);
  function pick(item) { onChange(item.value); setOpen(false); setText(''); }
  return <div className={`combobox${open ? ' is-open' : ''}`}>
    <div className="combobox-field">
      <input type="text" role="combobox" aria-label={label} aria-expanded={open} aria-controls={listId} disabled={disabled}
        aria-activedescendant={open && items[active] ? `${listId}-${active}` : undefined}
        placeholder={current && open ? current.label : placeholder} value={open ? text : current?.label || ''}
        onFocus={() => { setOpen(true); setText(''); setActive(0); }} onBlur={() => setTimeout(() => setOpen(false), 120)}
        onChange={(event) => { setText(event.target.value); setActive(0); }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') { event.preventDefault(); setOpen(true); setActive((i) => Math.min(items.length - 1, i + 1)); }
          else if (event.key === 'ArrowUp') { event.preventDefault(); setActive((i) => Math.max(0, i - 1)); }
          else if (event.key === 'Enter' && open && items[active]) { event.preventDefault(); pick(items[active]); event.currentTarget.blur(); }
          else if (event.key === 'Escape') { setOpen(false); event.currentTarget.blur(); }
        }} />
      <span className="combobox-mark"><Icon name="down" size={16} /></span>
    </div>
    {open && <div className="combobox-popup">
      <ul id={listId} ref={list} role="listbox" aria-label={`${label} 목록`} onMouseDown={(event) => event.preventDefault()}>
        {items.map((item, index) => <li key={`${item.value}-${index}`} id={`${listId}-${index}`} data-index={index} role="option"
          aria-selected={index === active} className={`${index === active ? 'is-active' : ''}${item.value === value ? ' is-current' : ''}`}
          onMouseEnter={() => setActive(index)} onClick={() => pick(item)}><span className="combobox-name">{item.label}</span></li>)}
        {!items.length && <li role="presentation" className="combobox-empty">맞는 값이 없습니다.</li>}
      </ul>
    </div>}
  </div>;
}

/**
 * The ledger's one signature: how much room is left, said the same way everywhere a place can run out (a session,
 * a time block, a slot, a day). The bar is the share already taken; "마감" when nothing is left.
 */
export function Seats({ remaining, total, unit = '자리', compact = false }) {
  if (remaining === null || remaining === undefined) return null;
  const full = remaining <= 0;
  const share = total ? Math.min(1, Math.max(0, (total - remaining) / total)) : full ? 1 : 0;
  return <span className={`seats${full ? ' is-full' : share >= .75 ? ' is-low' : ''}${compact ? ' is-compact' : ''}`}>
    {!compact && <span className="seats__text">{full ? '마감' : `${remaining.toLocaleString()}${unit} 남음`}</span>}
    {total ? <span className="seats__bar" aria-hidden="true"><i style={{ '--taken': share }} /></span> : null}
  </span>;
}

/** Quiet text for an empty list. */
export function Empty({ children }) {
  return <p className="ui-empty">{children}</p>;
}
