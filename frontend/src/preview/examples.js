// Fictional data used only on the template examples page.
export const exampleColumns = [
  { id: 'column_1', label: '시설명' },
  { id: 'column_2', label: '분류' },
  { id: 'column_3', label: '지역' },
  { id: 'column_4', label: '상태' },
  { id: 'column_5', label: '이용 안내' },
  { id: 'column_6', label: '전화번호' },
];

export const exampleRecords = [
  { id: 'example_1', values: {
    column_1: '가온 체육관', column_2: '체육', column_3: '가상시 중앙구',
    column_4: '운영 중', column_5: '평일 오전 9시부터 오후 6시까지 이용할 수 있습니다.', column_6: '02-0000-0001',
  } },
  { id: 'example_2', values: {
    column_1: '누리 수영장', column_2: '체육', column_3: '가상시 북구',
    column_4: '예약 필요', column_5: '방문 전에 이용 시간을 예약해 주세요.', column_6: '02-0000-0002',
  } },
  { id: 'example_3', values: {
    column_1: '햇살 문화센터', column_2: '문화', column_3: '가상시 남구',
    column_4: '운영 중', column_5: '문화 강좌와 전시를 운영합니다.', column_6: '02-0000-0003',
  } },
];

export const exampleConfig = {
  version: 1,
  title: '템플릿 예시',
  pages: [
    { id: 'cards_example', template: 'cards', title: '카드 목록 예시', detailPage: 'detail_example', bindings: {
      title: 'column_1', subtitle: 'column_3', badge: 'column_4', fields: ['column_2', 'column_5'],
    }, charts: [{ type: 'bar', title: '분류별 시설 수', groupBy: 'column_2', aggregate: 'count' }] },
    { id: 'table_example', template: 'table', title: '표 목록 예시', bindings: {
      fields: exampleColumns.map((column) => column.id),
    } },
    { id: 'grouped_example', template: 'grouped', title: '그룹 목록 예시', detailPage: 'detail_example', bindings: {
      title: 'column_1', group: 'column_2', subtitle: 'column_3', badge: 'column_4', fields: ['column_5'],
    } },
    { id: 'detail_example', template: 'detail', title: '상세 화면 예시', bindings: {
      title: 'column_1', badge: 'column_4', phone: 'column_6', fields: ['column_2', 'column_3', 'column_5'],
    } },
  ],
};
