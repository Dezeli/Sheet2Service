export function publicColumns(columns) {
  return columns.map((column, index) => ({ ...column, number: index + 1 }))
    .filter((column) => !/(?:^|[_\s-])(?:id|uuid|identifier)(?:$|[_\s-])|(?:아이디|식별자|식별번호|고유번호|관리번호|서비스\s*id)/i.test(column.label));
}

export function summaryColumns(columns, subjectColumn) {
  const visible = publicColumns(columns).filter((column) => column.number !== subjectColumn);
  return visible.filter((column) => column.candidate !== 'text' || column.unique_count < Math.max(3, column.non_empty_count * .8))
    .concat(visible).filter((column, index, items) => items.findIndex((item) => item.number === column.number) === index).slice(0, 3);
}
