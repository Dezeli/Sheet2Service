import React from 'react';

export default function ReadableText({ children, className = '' }) {
  const text = String(children ?? '');
  if (text.length <= 160 && text.split('\n').length <= 3) return <p className={`inquiry-text ${className}`}>{text}</p>;
  return <details className={`readable-text ${className}`}>
    <summary><span className="readable-preview">{text}</span><span className="readable-toggle">전체 내용</span></summary>
    <p className="inquiry-text">{text}</p>
  </details>;
}
