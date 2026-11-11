import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { createRoot } from 'react-dom/client';
import Landing from './Landing';
import UploadFlow from './UploadFlow';
import './landing.css';

const KIT = '/kit/';
const STYLES = ['system.css', 'ui/cards.css', 'motion/motion.css', 'backgrounds/backgrounds.css', 'layout/layout.css', 'icons/icon.css',
  'ui/base.css', 'ui/window/fragment.css', 'ui/calendar/fragment.css', 'moments/line-carries-colour/moment.css'];
const FONTS = 'https://fonts.googleapis.com/css2?family=Instrument+Sans:wdth,wght@75..100,400..700&display=swap';
// Hangul: Pretendard split by unicode range, so a page downloads only the syllables it shows
const HANGUL = 'https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css';

/** The kit's page shell: the head it needs before the first paint, its stylesheets ahead of the page's own CSS. */
function prepareDocument() {
  const html = document.documentElement;
  Object.entries({ lang: 'ko', 'data-type': 'software', 'data-radius': 'soft', 'data-ground': 'sage', 'data-buttons': 'arrow', 'data-motion': '' })
    .forEach(([name, value]) => html.setAttribute(name, value));
  document.title = 'Sheet2Service: 예약 시트로 만드는 예약 서비스';
  const head = document.head;
  const first = head.firstChild;
  const add = (tag, attributes) => {
    const element = document.createElement(tag);
    Object.entries(attributes).forEach(([name, value]) => element.setAttribute(name, value));
    head.insertBefore(element, first);
    return element;
  };
  add('meta', { name: 'description', content: '예약 대장, 시설 목록, 회차표 CSV를 올리면 예약자 화면과 관리자 화면을 만들어 주는 웹 앱입니다.' });
  add('meta', { name: 'page-type', content: 'software' });
  add('meta', { name: 'site-kind', content: 'software' });
  add('meta', { property: 'og:type', content: 'website' });
  add('meta', { property: 'og:title', content: 'Sheet2Service: 예약 시트로 만드는 예약 서비스' });
  add('meta', { property: 'og:description', content: 'CSV 한 장으로 예약자 화면과 관리자 화면을 만듭니다.' });
  add('meta', { property: 'og:image', content: '/share.jpg' });
  add('meta', { name: 'twitter:card', content: 'summary_large_image' });
  add('meta', { name: 'theme-color', content: '#f7f9fa' });
  add('link', { rel: 'icon', href: '/favicon.svg', type: 'image/svg+xml' });
  add('link', { rel: 'preconnect', href: 'https://fonts.googleapis.com' });
  add('link', { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' });
  add('link', { rel: 'stylesheet', href: FONTS });
  add('link', { rel: 'stylesheet', href: HANGUL });
  STYLES.forEach((path) => add('link', { rel: 'stylesheet', href: KIT + path }));
  // the hero's words wait for motion.js instead of flashing; the moment's guard (motion.md, moments.md)
  html.classList.add('m-enter', 'mo-js');
  setTimeout(() => html.classList.add('m-enter-done'), 700);
  setTimeout(() => html.classList.add('mo-safe'), 2500);
}

/** The kit's scripts after the markup is in the document: they find it on load, as on a static page. */
function Page() {
  useEffect(() => {
    const load = (path) => import(/* @vite-ignore */ `${KIT}${path}`).catch(() => {});
    load('backgrounds/backgrounds.js').then(() => Promise.all(['system.js', 'motion/motion.js', 'layout/layout.js'].map(load)));
  }, []);
  return <>{createPortal(<Landing />, document.body)}<UploadFlow /></>;
}

// The page's header, main and footer go straight into <body>, as the kit's checks and scripts expect; the React
// root itself stays a detached node.
export function mount() {
  prepareDocument();
  document.getElementById('root')?.remove();
  createRoot(document.createElement('div')).render(<Page />);
}
