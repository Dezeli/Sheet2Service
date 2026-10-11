// Reuse validated service semantics; never infer a title from a CSV-specific name.
export function rowSummary(row, columns, titleColumns = []) {
  const fields = columns.map((column, index) => ({
    number: index + 1, label: column.label, value: String(row.values[index] ?? '').trim(),
    uniqueness: column.non_empty_count > 0 ? column.unique_count / column.non_empty_count : 0,
  })).filter((field) => field.value);
  const title = titleColumns.map((number) => fields.find((field) => field.number === number)).find(Boolean);
  const supporting = fields.filter((field) => field.number !== title?.number)
    .sort((a, b) => {
      const compact = (field) => field.value.length <= 100 && !/[\r\n]|https?:\/\//i.test(field.value);
      return Number(compact(b)) - Number(compact(a)) || b.uniqueness - a.uniqueness || a.number - b.number;
    }).slice(0, title ? 2 : 3);
  return { title, supporting };
}
