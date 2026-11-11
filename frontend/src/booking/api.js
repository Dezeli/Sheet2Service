export async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = response.status === 204 ? {} : await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof data?.detail === 'string' ? data.detail : '요청을 처리하지 못했습니다. 다시 시도해 주세요.');
  }
  if (!data) throw new Error('서버 응답을 읽지 못했습니다.');
  return data;
}

export function jsonOptions(method, csrf, body) {
  return { method, headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify(body) };
}

export function query(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

export const statusLabels = {
  requested: '승인 대기', approved: '예약 확정', rejected: '거절', cancelled: '취소', in_use: '이용 중',
  completed: '이용 완료', waiting: '대기', won: '당첨', lost: '미당첨', other: '기타',
};

// What a reviewer may do from each status, coloured by what the action does: approve green, start blue,
// put back amber, refuse or cancel red (ui.css, button intents).
export const statusActions = {
  requested: [['approve', '승인', 'approve'], ['reject', '거절', 'danger']],
  waiting: [['approve', '승인', 'approve'], ['reject', '거절', 'danger']],
  approved: [['check_in', '이용 시작', 'info'], ['complete', '완료', 'approve'], ['cancel', '취소', 'danger']],
  won: [['check_in', '이용 시작', 'info'], ['complete', '완료', 'approve'], ['cancel', '취소', 'danger']],
  in_use: [['complete', '완료', 'approve']],
  rejected: [['reopen', '다시 접수', 'warn']],
  cancelled: [['reopen', '다시 접수', 'warn']],
  completed: [], lost: [['reopen', '다시 접수', 'warn']], other: [['reopen', '다시 접수', 'warn']],
};

// which duty a step belongs to (the server checks the same: personas.py STEP_FEATURES)
const STEP_FEATURES = { approve: 'review_reservations', reject: 'review_reservations', cancel: 'review_reservations', reopen: 'review_reservations',
  check_in: 'run_sessions', complete: 'run_sessions' };
/** The steps this role may take on a booking in this status. */
export function actionsFor(persona, status) {
  return (statusActions[status] || []).filter(([action]) => persona?.features?.includes(STEP_FEATURES[action]));
}

export const statusTone = {
  requested: 'pending', approved: 'ok', rejected: 'bad', cancelled: 'muted', in_use: 'ok',
  completed: 'muted', waiting: 'pending', won: 'ok', lost: 'muted', other: 'muted',
};

export const featureLabels = {
  browse_resources: '찾기', make_reservation: '예약하기', my_reservations: '내 예약', inquiry: '문의', notices: '공지',
  manage_resources: '관리', manage_schedule: '일정·정원', review_reservations: '예약 관리', reply_inquiries: '문의 답변',
  manage_notices: '공지 관리', manage_data: '데이터 관리', dashboard: '대시보드', manage_payments: '결제 확인',
};

export const personaIcons = { booker: 'user', admin: 'admin', staff: 'request', org_manager: 'admin', finance: 'analysis', viewer: 'user' };

export const modeLabels = {
  approval: '신청 후 관리자 승인', instant: '신청 즉시 확정', lottery: '추첨', record_only: '기록 조회만', none: '예약 없음',
};

export function formatDate(value) {
  if (!value) return '';
  const date = value instanceof Date ? value : new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' });
}

export function formatMoment(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function formatTime(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}

const pad = (n) => String(n).padStart(2, '0');
const shortDay = (d, withYear) => `${withYear ? `${d.getFullYear()}. ` : ''}${d.getMonth() + 1}. ${d.getDate()}.`;
const shortClock = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;

/** whenText for a table cell: numeric dates and 24-hour clocks so a range fits one line; the year only when it is not this one. */
export function whenShort(item, unit = 'day') {
  const thisYear = new Date().getFullYear();
  const at = (value) => { if (!value) return null; const d = value instanceof Date ? value : new Date(String(value).length === 10 ? `${value}T00:00:00` : value); return Number.isNaN(d.getTime()) ? null : d; };
  const day = (d) => shortDay(d, d.getFullYear() !== thisYear);
  const start = at(item.starts_at); const end = at(item.ends_at);
  if (start && end) {
    const midnight = (d) => d.getHours() === 0 && d.getMinutes() === 0;
    if (start.toDateString() === end.toDateString()) return `${day(start)} ${shortClock(start)}–${shortClock(end)}`;
    // a course over weeks at the same hours: the weeks, then the hours
    if (item.time_slot && !(start.getHours() === 0 && start.getMinutes() === 0)) return `${day(start)} – ${shortDay(end, end.getFullYear() !== start.getFullYear())} · ${item.time_slot}`;
    if (midnight(start) && midnight(end)) {
      const days = Math.round((end - start) / 86400000);
      const last = new Date(end); if (unit !== 'stay') last.setDate(last.getDate() - 1);
      if (unit !== 'stay' && days === 1) return day(start);
      const until = unit === 'stay' ? end : last;
      return `${day(start)} – ${shortDay(until, until.getFullYear() !== start.getFullYear())} (${days}${unit === 'stay' ? '박' : '일'})`;
    }
    return `${day(start)} ${shortClock(start)} – ${shortDay(end, end.getFullYear() !== start.getFullYear())} ${shortClock(end)}`;
  }
  if (start) return `${day(start)} ${shortClock(start)}`;
  const date = item.date ? at(item.date) : null;
  return [date ? day(date) : '', item.time_slot || ''].filter(Boolean).join(' ');
}

/** One line describing when a booking or slot happens, from whichever fields the sheet had. */
export function whenText(item, unit = 'day') {
  const parts = [];
  if (item.starts_at && item.ends_at) {
    const startsAt = new Date(item.starts_at); const endsAt = new Date(item.ends_at);
    const sameDay = startsAt.toDateString() === endsAt.toDateString();
    if (!sameDay && item.time_slot && /^\d{2}:\d{2}~\d{2}:\d{2}$/.test(item.time_slot)) return `${formatDate(startsAt)} ~ ${formatDate(endsAt)} · ${item.time_slot}`;
    const midnight = (d) => d.getHours() === 0 && d.getMinutes() === 0;
    if (!sameDay && midnight(startsAt) && midnight(endsAt)) {
      const days = Math.round((endsAt - startsAt) / 86400000);
      const last = new Date(endsAt); if (unit !== 'stay') last.setDate(last.getDate() - 1);
      parts.push(unit === 'stay' ? `${formatDate(startsAt)} ~ ${formatDate(endsAt)} (${days}박)`
        : days === 1 ? formatDate(startsAt) : `${formatDate(startsAt)} ~ ${formatDate(last)} (${days}일)`);
    } else parts.push(sameDay ? `${formatDate(item.starts_at)} ${formatTime(item.starts_at)}~${formatTime(item.ends_at)}`
      : `${formatMoment(item.starts_at)} ~ ${formatMoment(item.ends_at)}`);
  } else if (item.starts_at) {
    parts.push(formatMoment(item.starts_at));
  } else if (item.date) {
    parts.push(formatDate(item.date));
    if (item.time_slot) parts.push(item.time_slot);
  } else if (item.time_slot) {
    parts.push(item.time_slot);
  }
  return parts.join(' ');
}

export function hasFeature(persona, ...features) {
  return features.some((feature) => persona?.features?.includes(feature));
}
