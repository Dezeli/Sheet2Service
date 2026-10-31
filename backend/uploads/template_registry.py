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
)
REGISTRY = {item["template"]: item for item in TEMPLATES}
IMPLEMENTED = tuple(item for item in TEMPLATES if item["implemented"])
ROLE_TITLES = {
    "browse_only": ("목록 조회", "데이터 관리"),
    "inquiry": ("문의 접수", "문의 답변"),
    "request_review": ("이용 신청", "신청 승인·처리"),
    "request_auto": ("요청 접수", "접수 처리"),
    "notice": ("공지 조회", "공지 관리"),
    "reservation": ("일정 예약", "일정·정원 관리"),
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
