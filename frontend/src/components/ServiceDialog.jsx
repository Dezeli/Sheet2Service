import React, { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { IconButton } from './ui';

export default function ServiceDialog({ title, busy, error, onClose, children, className = '' }) {
  const dialog = useRef(null);
  const titleId = useId();
  useEffect(() => {
    const element = dialog.current;
    element.dataset.role = document.querySelector('main.service-page')?.dataset.role || 'user';
    element.showModal();
    return () => element.close();
  }, []);
  return createPortal(<dialog ref={dialog} className={`service-page service-dialog ${className}`} aria-labelledby={titleId} tabIndex={-1} autoFocus
    onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
    <div className="section-title"><h2 id={titleId}>{title}</h2>
      <IconButton icon="close" label="닫기" disabled={busy} onClick={onClose} />
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {children}
  </dialog>, document.body);
}
