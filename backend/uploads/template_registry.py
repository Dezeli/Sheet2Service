"""Authoritative feature names, paired roles and implementation status."""

TEMPLATES = (
    {"template": "browse_only", "name": "목록 조회", "implemented": True,
     "user_template": "browse_only", "admin_template": "manage_catalog",
     "user_description": "목록·항목 정보 보기", "admin_description": "데이터·필드·선택지 관리"},
    {"template": "inquiry", "name": "문의 접수", "implemented": True,
     "user_template": "inquiry", "admin_template": "reply_inquiries",
     "user_description": "문의 작성·상태·답변 확인", "admin_description": "문의 답변·상태 관리"},
    {"template": "request_review", "name": "신청·승인", "implemented": True,
     "user_template": "request_review", "admin_template": "review_requests",
     "user_description": "신청·취소·결과 확인. 단순 예약 신청에도 사용 가능",
     "admin_description": "승인·거절·사유 입력·처리 완료"},
    {"template": "request_auto", "name": "즉시 접수", "implemented": True,
     "user_template": "request_auto", "admin_template": "monitor_requests",
     "user_description": "요청 제출·취소·처리 상태 확인", "admin_description": "접수·처리 시작·완료"},
    {"template": "notice", "name": "공지", "implemented": True,
     "user_template": "notice", "admin_template": "manage_notices",
     "user_description": "게시된 공지 목록·내용 확인",
     "admin_description": "공지 작성·수정·게시·게시 해제. 예약 게시·첨부·알림 제외"},
    {"template": "reservation", "name": "일정·정원 관리 예약", "implemented": True,
     "user_template": "reservation", "admin_template": "manage_reservations",
     "user_description": "항목별 시간·잔여 정원 조회, 1인 1자리 예약·취소",
     "admin_description": "항목별 예약 시간 생성, 정원 변경·접수 마감, 예약 내역 조회. 반복 일정·승인·결제는 제외"},
    {"template": "rental", "name": "대여·반납", "implemented": True,
     "user_template": "rental", "admin_template": "manage_rentals",
     "user_description": "항목·수량 선택, 대여 신청·시작 전 취소·내 상태 확인. 수량은 승인 시 확보",
     "admin_description": "항목별 재고·접수 설정, 승인·거절·대여 시작·전량 반납 처리. 기간 예약·부분 반납·결제 제외"},
    {"template": "order", "name": "주문", "implemented": False,
     "user_description": "상품·수량 선택·주문", "admin_description": "주문 상태·재고 관리"},
    {"template": "waitlist", "name": "대기 신청", "implemented": False,
     "extension_of": "reservation", "user_description": "대기 등록·취소·순번 확인",
     "admin_description": "예약 확장: 대기 순서 관리·참여 확정"},
    {"template": "quote", "name": "견적 요청", "implemented": True,
     "user_template": "quote", "admin_template": "manage_quotes",
     "user_description": "항목·요청 조건 입력, 전달된 견적 확인·수락·거절, 시작 전 취소",
     "admin_description": "금액·통화·제안 초안 작성·전달, 요청 거절, 수락 후 진행·완료 처리. 전달 후 금액 수정·결제·자동 가격 계산 제외"},
    {"template": "survey", "name": "설문·피드백", "implemented": False,
     "user_description": "설문·피드백 응답 제출", "admin_description": "문항 구성·응답 집계"},
    {"template": "work_request", "name": "작업 요청", "implemented": False,
     "extension_of": "request_review", "user_description": "작업 요청 등록·진행 상황 확인",
     "admin_description": "신청·문의 확장: 담당자 배정·처리 상태 관리"},
    {"template": "favorites", "name": "즐겨찾기", "implemented": False,
     "user_description": "관심 항목 저장·조회", "admin_description": "별도 관리자 기능 없음"},
)
REGISTRY = {item["template"]: item for item in TEMPLATES}
IMPLEMENTED = tuple(item for item in TEMPLATES if item["implemented"])
PLANNED = tuple(item["template"] for item in TEMPLATES if not item["implemented"])
ROLE_TITLES = {
    "browse_only": ("목록 조회", "데이터 관리"),
    "inquiry": ("문의 접수", "문의 답변"),
    "request_review": ("이용 신청", "신청 승인·처리"),
    "request_auto": ("요청 접수", "접수 처리"),
    "notice": ("공지 조회", "공지 관리"),
    "reservation": ("일정 예약", "일정·정원 관리"),
    "rental": ("대여 신청", "대여·반납 관리"),
    "order": ("상품 주문", "주문 관리"),
    "waitlist": ("대기 신청", "대기 순서 관리"),
    "quote": ("견적 요청", "견적 작성·관리"),
    "survey": ("설문 응답", "설문·응답 관리"),
    "work_request": ("작업 요청", "담당자·작업 관리"),
    "favorites": ("관심 항목 저장", ""),
}
DASHBOARD = (
    {"template": "csv_statistics", "name": "데이터 통계", "implemented": True},
    {"template": "request_statistics", "name": "신청·접수 현황", "implemented": True},
    {"template": "inquiry_statistics", "name": "문의 현황", "implemented": True},
)


def describe(template):
    return {**{key: REGISTRY[template][key] for key in
            ("name", "implemented", "user_description", "admin_description")},
            "user_title": ROLE_TITLES[template][0], "admin_title": ROLE_TITLES[template][1]}
