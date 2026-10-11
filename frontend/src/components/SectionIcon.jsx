import React from 'react';

const paths = {
  table: <><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M3 10h18M9 10v10M15 10v10" /></>,
  analysis: <><path d="M4 4v16h16M9 16v-5M14 16V7M19 16v-8" /></>,
  features: <><rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="7" rx="2" /><rect x="3" y="14" width="7" height="7" rx="2" /><path d="M17.5 14v7M14 17.5h7" /></>,
  dashboard: <><rect x="3" y="3" width="7" height="18" rx="2" /><rect x="14" y="3" width="7" height="7" rx="2" /><rect x="14" y="14" width="7" height="7" rx="2" /></>,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21v-2a8 8 0 0 1 16 0v2" /></>,
  admin: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8.5 12l2.5 2.5 4.5-5" /></>,
  help: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 2-2.5 2-2.5 4M12 16.5h.01" /></>,
  inquiry: <><path d="M21 11a8 8 0 0 1-8 8H7l-4 3V11a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8Z" /><path d="M8 9h8M8 13h5" /></>,
  reservation: <><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M7 3v4M17 3v4M3 11h18M8 15h2M14 15h2" /></>,
  notice: <><path d="m4 10 15-5v14L4 14zM4 10v4M7 15l2 6h3l-2-5M22 9v6" /></>,
  rental: <><path d="m12 3 9 5-9 5-9-5zM3 8v9l9 5 9-5V8M12 13v9" /></>,
  quote: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 7h6M9 11h6M9 15h2M14 15h1M9 18h2M14 18h1" /></>,
  request: <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4V2h6v2M8 13l3 3 5-6" /></>,
};

export default function SectionIcon({ name }) {
  return <span className="section-icon" aria-hidden="true"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg></span>;
}
