/** Booking rules as the server sends them in service.booking.rules, with the wording shown to people. */

// Python's weekday(): Monday is 0
export const WEEKDAY_NAMES = ['월', '화', '수', '목', '금', '토', '일'];
export const STEPS = [10, 15, 20, 30, 60, 90, 120, 180, 240];

export const timeModeLabels = {
  day: '하루 단위',
  time_slot: '정한 타임',
  time_range: '시간 단위',
  stay: '숙박',
  period: '기간',
};


const FALLBACK = {
  timeMode: 'day', sessions: [], hourly: { open: '09:00', close: '18:00', step: 60, minSteps: 1, maxSteps: 0 },
  capacityBy: 'bookings', limit: 1, closedWeekdays: [], perPerson: { limit: 0, per: 'day' },
};

export function rulesOf(service) {
  const rules = service?.booking?.rules;
  return rules ? rules : { ...FALLBACK, timeMode: service?.booking?.unit || 'day' };
}

export function duration(minutes) {
  if (minutes % 60) return minutes > 60 ? `${Math.floor(minutes / 60)}시간 ${minutes % 60}분` : `${minutes}분`;
  return `${minutes / 60}시간`;
}

/** An ISO timestamp for a local date and an "HH:MM" clock; "24:00" is the next midnight. */
export function moment(date, clock) {
  const [hours, minutes] = clock.split(':').map(Number);
  const value = new Date(`${date}T00:00:00`);
  value.setMinutes(hours * 60 + minutes);
  return value.toISOString();
}

const toMinutes = (clock) => Number(clock.slice(0, 2)) * 60 + Number(clock.slice(3, 5));
const toClock = (minutes) => `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;

/** Back-to-back sessions of one length between two clocks, with an optional break after each: the admin's time table. */
export function sessionsFrom(open, close, length, gap = 0) {
  if (!/^\d{2}:\d{2}$/.test(open) || !/^\d{2}:\d{2}$/.test(close) || length <= 0) return [];
  const list = [];
  for (let start = toMinutes(open); start + length <= toMinutes(close) && list.length < 24; start += length + gap) {
    list.push({ label: `${toClock(start)}~${toClock(start + length)}`, start: toClock(start), end: toClock(start + length) });
  }
  return list;
}

// Statistics the service derived from the sheet's records; they help admins, not someone booking.
export const SHEET_STATS = ['기록 건수', '평균 이용 기간', '원본 코드'];

/** A resource attribute as a booker reads it: money gets commas and 원. */
export function attributeText(key, value) {
  const text = String(value ?? '');
  if (/금액|요금|료$|비용|가격/.test(key) && /^\d{3,}$/.test(text.replace(/,/g, ''))) return `${Number(text.replace(/,/g, '')).toLocaleString()}원`;
  return text;
}

/** "010-1234-5678" or "+82 10 1234 5678" -> "01012345678"; '' when it is not a phone number. Mirrors the server. */
export function phoneDigits(text) {
  let digits = String(text || '').replace(/\D/g, '');
  if (digits.startsWith('82') && (digits.length === 11 || digits.length === 12)) digits = `0${digits.slice(2)}`;
  return /^0\d{8,10}$/.test(digits) ? digits : '';
}

/** Hyphens placed while typing: 010-1234-5678, 011-123-4567, 02-123-4567, 02-1234-5678. */
export function formatPhoneInput(text) {
  const digits = String(text || '').replace(/\D/g, '').slice(0, 11);
  const head = digits.startsWith('02') ? 2 : 3;
  const first = digits.slice(0, head);
  const rest = digits.slice(head);
  if (!rest) return first;
  const complete = digits.startsWith('02') ? [9, 10] : digits.startsWith('010') ? [11] : [10, 11];
  if (complete.includes(digits.length)) return `${first}-${rest.slice(0, -4)}-${rest.slice(-4)}`;
  if (rest.length <= 4) return `${first}-${rest}`;
  return `${first}-${rest.slice(0, 4)}-${rest.slice(4)}`;
}

// The last name and number a booker used in this tab, so the next booking and the lookup are filled in.
const BOOKER_KEY = 'sheet2service.booker';
export function rememberedBooker() {
  try { return JSON.parse(sessionStorage.getItem(BOOKER_KEY)) || { name: '', phone: '' }; } catch { return { name: '', phone: '' }; }
}
export function rememberBooker(name, phone) {
  try { sessionStorage.setItem(BOOKER_KEY, JSON.stringify({ name, phone })); } catch { /* storage may be unavailable */ }
}

export function perPersonText(rules) {
  const { limit, per } = rules.perPerson || {};
  if (!limit) return '';
  return per === 'day' ? `1인 하루 ${limit}건` : `1인 ${limit}건까지 예약 가능`;
}

/** One line telling a booker how time is offered and how many fit at once. */
export function availabilityNote(rules, limit = rules.limit) {
  const parts = [];
  if (rules.timeMode === 'time_range') {
    const { open, close, step, minSteps, maxSteps } = rules.hourly;
    parts.push(`${open}~${close} 운영`, `${duration(step)} 단위`);
    if (minSteps > 1) parts.push(`최소 ${duration(step * minSteps)}`);
    if (maxSteps) parts.push(`최대 ${duration(step * maxSteps)}`);
  } else parts.push(timeModeLabels[rules.timeMode] || '');
  parts.push(rules.capacityBy === 'people' ? `같은 시간 ${limit}명까지` : `같은 시간 ${limit}건까지`);
  parts.push(perPersonText(rules));
  if (rules.closedWeekdays?.length) parts.push(`${rules.closedWeekdays.map((day) => WEEKDAY_NAMES[day]).join('·')} 휴무`);
  return parts.filter(Boolean).join(' · ');
}
