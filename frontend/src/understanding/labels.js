// Korean labels for the SheetUnderstanding vocabularies (backend/uploads/sheet_understanding.py).
export const KINDS = {
  register: '대장 · 건마다 상태가 바뀜', catalog: '목록 · 항목 조회', ledger: '장부 · 기록이 쌓임', schedule: '일정',
  roster: '명부 · 사람·조직', reference: '참조표 · 코드', mixed: '혼합',
};
export const ACTOR_KINDS = { requester: '요청', handler: '처리', approver: '승인', viewer: '조회', system: '시스템' };
export const ROLES = {
  identifier: '식별자', title: '제목', category: '분류', status: '상태', owner: '담당자', actor_name: '요청자 이름',
  contact: '연락처', date_created: '등록일', date_updated: '수정일', date_due: '기한', date_event: '대상 날짜',
  date_closed: '종료일', time: '시각', duration: '기간·일수', amount: '금액', quantity: '수량', number: '측정값',
  location: '위치', coordinate: '좌표', url: '링크', image: '이미지', reference_code: '참조 코드', result: '결과',
  note: '메모', flag: '여부', derived: '계산값', unknown: '모름',
};
export const CONFIDENCE = { high: '높음', medium: '보통', low: '낮음' };
export const BASES = {
  status_column: '상태 컬럼', milestone_dates: '단계별 날짜', flag_and_dates: '여부 컬럼', amount_balance: '수량·금액 변동',
  inferred: '의미로 추정',
};
export const STATE_KINDS = { start: '시작', active: '진행', waiting: '대기', done: '완료', cancelled: '취소·중단' };
