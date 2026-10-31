/** Rows from the API become records keyed by column id; the dashboard runtime reads those. */
export function recordsFromRows(rows, columns) {
  return rows.map((row) => ({
    id: String(row.row_number),
    values: Object.fromEntries(columns.map((column, index) => [column.id, row.values[index] ?? null])),
  }));
}

export function safeWebUrl(value) {
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}
