import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import './fonts.css';
import './theme.css';
import BookingService from './booking/BookingService';
import SiteFooter from './components/SiteFooter';
import './service.css';
import './hierarchy.css';
import './ui.css';

export function mount(uploadId, page) {
  createRoot(document.getElementById('root')).render(<React.StrictMode>
    <BookingService uploadId={uploadId} page={page === 'DashBoard' ? 'DashBoard' : page} />
    <SiteFooter />
  </React.StrictMode>);
}
