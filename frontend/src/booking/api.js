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

export const statusTone = {
  requested: 'pending', approved: 'ok', rejected: 'bad', cancelled: 'muted', in_use: 'ok',
  completed: 'muted', waiting: 'pending', won: 'ok', lost: 'muted', other: 'muted',
};

export const featureLabels = {
  browse_resources: '찾기', make_reservation: '예약하기', my_reservations: '내 예약', inquiry: '문의', notices: '공지',
  manage_resources: '관리', manage_schedule: '일정·정원', review_reservations: '예약 관리', reply_inquiries: '문의 답변',
  manage_notices: '공지 관리', manage_data: '데이터 관리', dashboard: '대시보드',
};

export const personaIcons = { booker: 'user', admin: 'admin', staff: 'request', org_manager: 'admin', finance: 'analysis', viewer: 'user' };

export const modeLabels = {
  approval: '신청 후 관리자 승인', instant: '신청 즉시 확정', lottery: '추첨', record_only: '기록 조회만', none: '예약 없음',
};

export function formatDate(value) {
  if (!value) return '';
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
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

/** One line describing when a booking or slot happens, from whichever fields the sheet had. */
export function whenText(item) {
  const parts = [];
  if (item.starts_at && item.ends_at) {
    const sameDay = item.starts_at.slice(0, 10) === item.ends_at.slice(0, 10);
    parts.push(sameDay ? `${formatDate(item.starts_at)} ${formatTime(item.starts_at)}~${formatTime(item.ends_at)}`
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
