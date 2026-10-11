import React from 'react';

export default function SiteFooter({ email = 'firoms@ajou.ac.kr' }) {
  return <footer className="site-footer">
    <div className="site-footer-inner">
      <span className="site-footer-brand">Sheet2Service</span>
      <span className="site-footer-contact">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="3" y="5" width="18" height="14" rx="3" />
          <path d="m4 7 8 6 8-6" />
        </svg>
        <span className="site-footer-contact-label">Contact</span>
        <span>{email}</span>
      </span>
      <span className="site-footer-copyright">© {new Date().getFullYear()} Sheet2Service</span>
    </div>
  </footer>;
}
