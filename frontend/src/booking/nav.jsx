import React, { createContext, useContext } from 'react';

/*
  Places inside a generated service are addresses: /<upload>/<persona>?menu=<screen>&item=<resource id>.
  BookingService owns the current place and offers go(); ItemLink turns any item name into a real link to it,
  so a click moves there in place, a middle click opens a tab, and Back returns.
*/
export const NavContext = createContext(null);
export const useNav = () => useContext(NavContext);

export function placeHref(uploadId, page, menu, item, view) {
  const params = new URLSearchParams();
  if (menu) params.set('menu', menu);
  if (item) params.set('item', item);
  if (view) params.set('view', view);
  const text = params.toString();
  return `/${uploadId}/${page}${text ? `?${text}` : ''}`;
}

/** The last part of a path is the item; the full path stays in the tooltip. */
export const itemName = (path) => String(path || '').split(' / ').at(-1);
export const parentName = (path) => String(path || '').split(' / ').slice(-2, -1)[0] || '';
export const pathTitle = (path) => String(path || '').split(' / ').join(' › ');

/** A link to a screen, optionally opened on a ready-made view such as `pending`; plain text when there is nowhere to go. */
export function PlaceLink({ menu, item, view, page, title, className = '', children }) {
  const nav = useNav();
  const target = page || nav?.page;
  if (!nav || !menu || !(page || nav.has(menu))) return <span className={className} title={title}>{children}</span>;
  return <a href={placeHref(nav.uploadId, target, menu, item, view)} className={`item-link ${className}`} title={title} onClick={(event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (target !== nav.page) return; // another persona's page: a normal navigation
    event.preventDefault();
    event.stopPropagation();
    nav.go(menu, item, view);
  }}>{children}</a>;
}

/**
 * An item's name as a link to where the item lives for this persona: `menu` on `page` (this page when omitted).
 * Without a screen to go to it stays plain text.
 */
export function ItemLink({ item, path, menu, page, children, className = '' }) {
  return <PlaceLink menu={item ? menu : ''} item={item} page={page} title={pathTitle(path)} className={className}>{children ?? itemName(path)}</PlaceLink>;
}
