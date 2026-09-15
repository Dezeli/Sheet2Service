// Deterministic counts of the supplied records only, independent of rendering.
export function countGroups(records, columnId) {
  const groups = new Map();
  for (const record of records) {
    const value = record.values[columnId];
    const missing = value === null || value === undefined || String(value).trim() === '';
    const key = missing ? null : String(value);
    if (!groups.has(key)) groups.set(key, { key, label: missing ? '값 없음' : key, count: 0 });
    groups.get(key).count += 1;
  }
  const sorted = [...groups.values()].sort((a, b) => b.count - a.count);
  // Keep charts legible without dropping records. Preserve stable first-seen ties.
  const visible = sorted.length > 8
    ? [...sorted.slice(0, 7), { key: '__remainder__', label: `나머지 ${sorted.length - 7}개 분류`, count: sorted.slice(7).reduce((sum, item) => sum + item.count, 0) }]
    : sorted;
  return visible.map((item) => ({ ...item, ratio: item.count / records.length }));
}
