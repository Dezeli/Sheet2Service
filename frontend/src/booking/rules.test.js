import test from 'node:test';
import assert from 'node:assert/strict';
import { availabilityNote, duration, formatPhoneInput, moment, phoneDigits, rulesOf, sessionsFrom } from './rules.js';

const hourly = { timeMode: 'time_range', sessions: [], hourly: { open: '09:00', close: '22:00', step: 30, minSteps: 2, maxSteps: 6 },
  capacityBy: 'bookings', limit: 2, closedWeekdays: [0, 6], perPerson: { limit: 1, per: 'day' } };

test('describes hours, length, capacity and closed days in one line', () => {
  assert.equal(availabilityNote(hourly), '09:00~22:00 운영 · 30분 단위 · 최소 1시간 · 최대 3시간 · 같은 시간 2건까지 · 1인 하루 1건 · 월·일 휴무');
  assert.equal(availabilityNote({ ...hourly, timeMode: 'time_slot', capacityBy: 'people', closedWeekdays: [], perPerson: { limit: 0, per: 'day' } }, 20), '정한 타임 · 같은 시간 20명까지');
});

test('durations and moments', () => {
  assert.equal(duration(90), '1시간 30분');
  assert.equal(duration(45), '45분');
  assert.equal(duration(120), '2시간');
  assert.equal(new Date(moment('2026-11-16', '24:00')).getTime(), new Date('2026-11-17T00:00:00').getTime());
  assert.equal(new Date(moment('2026-11-16', '09:30')).getTime(), new Date('2026-11-16T09:30:00').getTime());
});

test('services without stored rules fall back to their unit', () => {
  assert.equal(rulesOf({ booking: { unit: 'stay' } }).timeMode, 'stay');
  assert.equal(rulesOf({ booking: { unit: 'day', rules: hourly } }).limit, 2);
});

test('builds an hourly time table and stops before closing', () => {
  const table = sessionsFrom('10:00', '16:00', 60);
  assert.equal(table.length, 6);
  assert.deepEqual(table[0], { label: '10:00~11:00', start: '10:00', end: '11:00' });
  assert.equal(table.at(-1).label, '15:00~16:00');
  assert.deepEqual(sessionsFrom('10:00', '12:00', 50, 10).map((item) => item.label), ['10:00~10:50', '11:00~11:50']);
  assert.deepEqual(sessionsFrom('10:00', '9:00', 60), []);
});

test('phone numbers read like the server reads them', () => {
  assert.equal(phoneDigits('010-1234-5678'), '01012345678');
  assert.equal(phoneDigits('+82 10 1234 5678'), '01012345678');
  assert.equal(phoneDigits('02-123-4567'), '021234567');
  assert.equal(phoneDigits('12-34'), '');
});

test('phone numbers take their hyphens while typing', () => {
  const typed = (digits) => [...digits].reduce((shown, digit) => formatPhoneInput(shown + digit), '');
  assert.equal(typed('010'), '010');
  assert.equal(typed('0101'), '010-1');
  assert.equal(typed('0101234'), '010-1234');
  assert.equal(typed('01012345'), '010-1234-5');
  assert.equal(typed('01012345678'), '010-1234-5678');
  assert.equal(typed('010123456789'), '010-1234-5678');
  assert.equal(typed('0111234567'), '011-123-4567');
  assert.equal(typed('021234567'), '02-123-4567');
  assert.equal(typed('0212345678'), '02-1234-5678');
  assert.equal(formatPhoneInput('010 1234 5678'), '010-1234-5678');
  assert.equal(formatPhoneInput('010-1234-567'), '010-1234-567');  // deleting the last digit keeps the shape
});
