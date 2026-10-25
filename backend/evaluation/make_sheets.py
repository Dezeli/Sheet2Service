"""Generate operational sample sheets with known flows; deterministic, no model calls.

Each sheet carries at least two implicit flows with different evidence so the understanding
step can be scored (docs/sheet-understanding.md, 평가). Run: python backend/evaluation/make_sheets.py
"""
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent / "sheets"
rng = random.Random(20261025)
NAMES = ["김민수", "이서연", "박지훈", "최수아", "정우진", "강하은", "조현우", "윤지민", "임도현", "한예은",
         "오준서", "서지우", "신유진", "권태양", "황소율"]
DEPTS = ["도로과", "환경과", "복지과", "주차관리과", "건축과"]


def phone():
    return f"010-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}"


def day(base, spread):
    return base + timedelta(days=rng.randint(0, spread))


def fmt(d):
    return d.strftime("%Y-%m-%d") if d else ""


def complaints():
    """민원 접수 대장: 처리 흐름(상태 컬럼) + 회신 흐름(여부 컬럼), 처리기한 = 접수일 + 7일."""
    header = ["민원번호", "접수일", "민원인", "연락처", "민원유형", "민원내용", "처리상태", "담당부서", "처리기한", "처리일",
              "처리결과", "회신여부", "회신일", "회신내용"]
    types = ["도로파손", "불법주차", "소음", "쓰레기", "가로등", "기타"]
    rows = []
    for index in range(1, 141):
        received = day(date(2026, 7, 1), 100)
        status = rng.choices(["접수", "배정", "처리중", "완료", "반려"], weights=[12, 14, 18, 46, 10])[0]
        kind = rng.choice(types)
        dept = rng.choice(DEPTS) if status != "접수" else ""
        closed = day(received, 9) if status in ("완료", "반려") else None
        result = ""
        if status == "완료":
            result = rng.choice(["현장 조치 완료", "보수 완료", "계도 조치", "민원인 안내 완료"])
        elif status == "반려":
            result = rng.choice(["관할 외 사안", "중복 접수", "내용 불명확"])
        replied = status in ("완료", "반려") and rng.random() < 0.65
        rows.append([f"M-2026-{index:04d}", fmt(received), rng.choice(NAMES), phone(), kind,
                     rng.choice(["인도 보도블록이 깨져 있어요", "골목에 차량이 계속 불법주차됩니다", "밤마다 공사 소음이 심합니다",
                                 "쓰레기가 방치되어 있습니다", "가로등이 꺼져 있습니다", "기타 문의드립니다"]),
                     status, dept, fmt(received + timedelta(days=7)), fmt(closed), result,
                     "Y" if replied else "N", fmt(closed + timedelta(days=rng.randint(0, 2))) if replied else "",
                     ("처리 결과를 안내드렸습니다" if replied else "")])
    truth = {
        "kind": "register",
        "columnRoles": ["identifier", "date_created", "actor_name", "contact", "category", "note|title", "status", "owner",
                        "date_due", "date_closed", "result", "flag", "date_event|date_closed", "result"],
        "processes": [
            {"title": "민원 처리", "basis": "status_column", "columns": [7, 8, 10, 11],
             "states": ["접수", "배정", "처리중", "완료", "반려"],
             "transitions": [["접수", "배정"], ["접수", "반려"], ["배정", "처리중"], ["처리중", "완료"]]},
            {"title": "민원인 회신", "basis": "flag_and_dates", "columns": [12, 13, 14],
             "states": ["N", "Y"], "transitions": [["N", "Y"]], "after": 0}],
        "rules": ["처리기한 = 접수일 + 7일"]}
    return "민원접수대장.csv", header, rows, truth


def equipment():
    """장비 대여 대장: 대여 흐름(날짜 사슬) + 점검 흐름(여부 컬럼), 보증금 - 공제 = 환급액."""
    header = ["대여번호", "장비명", "장비코드", "대여자", "소속", "신청일", "승인일", "대여일", "반납예정일", "반납일",
              "보증금", "공제액", "환급액", "점검완료", "점검일", "점검자", "비고"]
    items = [("빔프로젝터", "EQ-PJ"), ("노트북", "EQ-NB"), ("무선마이크", "EQ-MC"), ("카메라", "EQ-CM"), ("스피커", "EQ-SP")]
    rows = []
    for index in range(1, 121):
        name, code = rng.choice(items)
        applied = day(date(2026, 6, 1), 120)
        stage = rng.choices(["신청", "승인", "대여중", "반납"], weights=[10, 12, 23, 55])[0]
        approved = day(applied, 2) if stage != "신청" else None
        lent = day(approved, 2) if stage in ("대여중", "반납") else None
        due = lent + timedelta(days=rng.choice([3, 5, 7])) if lent else None
        returned = day(lent, 9) if stage == "반납" else None
        deposit = rng.choice([30000, 50000, 100000])
        deduction = rng.choice([0, 0, 0, 5000, 10000]) if returned else ""
        refund = deposit - deduction if returned else ""
        checked = bool(returned) and rng.random() < 0.7
        rows.append([f"R{index:04d}", name, f"{code}-{rng.randint(1, 9):02d}", rng.choice(NAMES), rng.choice(DEPTS),
                     fmt(applied), fmt(approved), fmt(lent), fmt(due), fmt(returned), deposit, deduction, refund,
                     "O" if checked else "", fmt(returned + timedelta(days=rng.randint(0, 3))) if checked else "",
                     rng.choice(NAMES) if checked else "", rng.choice(["", "", "", "연장 요청", "파손 확인", "케이블 누락"])])
    truth = {
        "kind": "register",
        "columnRoles": ["identifier", "title", "reference_code", "actor_name", "category", "date_created", "date_updated",
                        "date_event", "date_due", "date_closed", "amount", "amount", "derived", "flag", "date_event",
                        "owner", "note"],
        "processes": [
            {"title": "장비 대여", "basis": "milestone_dates", "columns": [6, 7, 8, 10],
             "states": ["신청", "승인", "대여중", "반납"],
             "transitions": [["신청", "승인"], ["승인", "대여중"], ["대여중", "반납"]]},
            {"title": "반납 점검", "basis": "flag_and_dates", "columns": [14, 15, 16],
             "states": ["", "O"], "transitions": [["", "O"]], "after": 0}],
        "rules": ["환급액 = 보증금 - 공제액"]}
    return "장비대여대장.csv", header, rows, truth


def classroom():
    """강의실 예약 대장: 승인 흐름(상태 컬럼) + 사용 확인(여부 컬럼); 예약일은 신청일 뒤."""
    header = ["예약번호", "신청일", "신청자", "소속", "연락처", "강의실", "예약일", "시작시간", "종료시간", "인원", "사용목적",
              "승인상태", "승인자", "승인일", "사용확인", "확인자"]
    rooms = ["101호", "102호", "201호", "세미나실A", "세미나실B", "대강당"]
    rows = []
    for index in range(1, 161):
        applied = day(date(2026, 8, 1), 90)
        status = rng.choices(["대기", "승인", "거절", "취소"], weights=[15, 60, 12, 13])[0]
        event = day(applied + timedelta(days=1), 20)
        start = rng.choice([9, 10, 13, 14, 15, 18])
        approver = rng.choice(NAMES[:4]) if status in ("승인", "거절") else ""
        approved = day(applied, 2) if status in ("승인", "거절") else None
        used = status == "승인" and event < date(2026, 10, 25) and rng.random() < 0.8
        rows.append([f"RS-{index:04d}", fmt(applied), rng.choice(NAMES), rng.choice(DEPTS), phone(), rng.choice(rooms),
                     fmt(event), f"{start:02d}:00", f"{start + rng.choice([1, 2, 3]):02d}:00", rng.randint(4, 40),
                     rng.choice(["팀 회의", "교육", "세미나", "면접", "워크숍"]), status, approver, fmt(approved),
                     "O" if used else "", rng.choice(NAMES[4:8]) if used else ""])
    truth = {
        "kind": "register",
        "columnRoles": ["identifier", "date_created", "actor_name", "category", "contact", "category|location", "date_event",
                        "time", "time", "quantity", "note|category", "status", "owner", "date_updated", "flag", "owner"],
        "processes": [
            {"title": "예약 승인", "basis": "status_column", "columns": [12, 13, 14],
             "states": ["대기", "승인", "거절", "취소"],
             "transitions": [["대기", "승인"], ["대기", "거절"], ["대기", "취소"], ["승인", "취소"]]},
            {"title": "사용 확인", "basis": "flag_and_dates", "columns": [15, 16],
             "states": ["", "O"], "transitions": [["", "O"]], "after": 0}],
        "rules": []}
    return "강의실예약대장.csv", header, rows, truth


def stock():
    """비품 입출고 장부: 수량 변동 흐름(장부) + 발주 흐름(여부 컬럼 + 날짜); 금액 = 수량 × 단가."""
    header = ["일자", "품목코드", "품목명", "분류", "구분", "수량", "단가", "금액", "잔여수량", "담당자", "발주요청", "발주일",
              "입고예정일", "비고"]
    items = [("ST-001", "A4용지", "사무용품", 4500), ("ST-002", "토너", "소모품", 85000), ("ST-003", "볼펜", "사무용품", 800),
             ("ST-004", "마스크", "위생용품", 500), ("ST-005", "건전지", "소모품", 1200)]
    balance = {code: 200 for code, *_ in items}
    rows = []
    current = date(2026, 7, 1)
    for index in range(1, 181):
        current += timedelta(days=rng.randint(0, 2))
        code, name, kind, price = rng.choice(items)
        inbound = rng.random() < 0.35
        quantity = rng.randint(20, 100) if inbound else rng.randint(1, 30)
        balance[code] += quantity if inbound else -quantity
        if balance[code] < 0:
            quantity += balance[code]
            balance[code] = 0
        ordered = (not inbound) and balance[code] < 40 and rng.random() < 0.7
        order_day = current + timedelta(days=rng.randint(0, 2)) if ordered else None
        rows.append([fmt(current), code, name, kind, "입고" if inbound else "출고", quantity, price, quantity * price,
                     balance[code], rng.choice(NAMES[:5]), "Y" if ordered else "N", fmt(order_day),
                     fmt(order_day + timedelta(days=7)) if order_day else "",
                     rng.choice(["", "", "", "긴급", "반품 처리", "분기 정산"])])
    truth = {
        "kind": "ledger",
        "columnRoles": ["date_created|date_event", "reference_code", "title", "category", "category", "quantity", "amount",
                        "derived", "quantity|derived", "owner", "flag", "date_event", "date_due", "note"],
        "processes": [
            {"title": "입출고 기록", "basis": "amount_balance", "columns": [5, 6, 9],
             "states": ["입고", "출고"], "transitions": []},
            {"title": "재고 발주", "basis": "flag_and_dates", "columns": [11, 12, 13],
             "states": ["N", "Y"], "transitions": [["N", "Y"]]}],
        "rules": ["금액 = 수량 × 단가"]}
    return "비품입출고장부.csv", header, rows, truth


def members():
    """동호회 회원 명부: 회비 납부 흐름(여부 컬럼) + 탈퇴 흐름(여부 컬럼), 등급은 분류."""
    header = ["회원번호", "이름", "연락처", "이메일", "가입일", "등급", "회비납부", "납부일", "납부금액", "탈퇴여부", "탈퇴일",
              "최근참여일", "비고"]
    rows = []
    for index in range(1, 131):
        joined = day(date(2024, 1, 1), 900)
        grade = rng.choices(["일반", "우수", "휴면"], weights=[60, 25, 15])[0]
        left = rng.random() < 0.12
        paid = (not left) and grade != "휴면" and rng.random() < 0.75
        pay_day = day(date(2026, 1, 5), 60) if paid else None
        last = day(date(2026, 6, 1), 140) if not left and grade != "휴면" else day(joined, 200)
        name = rng.choice(NAMES)
        rows.append([f"MB{index:03d}", name, phone(), f"user{index}@example.com", fmt(joined), grade, "Y" if paid else "N",
                     fmt(pay_day), 50000 if paid else "", "Y" if left else "N", fmt(day(last, 30)) if left else "",
                     fmt(last), rng.choice(["", "", "", "임원", "신규", "연락 두절"])])
    truth = {
        "kind": "roster",
        "columnRoles": ["identifier", "actor_name", "contact", "contact", "date_created", "category|status", "flag", "date_event",
                        "amount", "flag", "date_closed", "date_updated", "note"],
        "processes": [
            {"title": "회비 납부", "basis": "flag_and_dates", "columns": [7, 8, 9],
             "states": ["N", "Y"], "transitions": [["N", "Y"]]},
            {"title": "탈퇴", "basis": "flag_and_dates", "columns": [10, 11],
             "states": ["N", "Y"], "transitions": [["N", "Y"]]}],
        "rules": []}
    return "동호회회원명부.csv", header, rows, truth


CRYPTIC = {
    "민원번호": "cmpl_no", "접수일": "rcpt_dt", "민원인": "rqst_nm", "연락처": "tel", "민원유형": "type_cd", "민원내용": "cont",
    "처리상태": "stat", "담당부서": "dept", "처리기한": "due_dt", "처리일": "prcs_dt", "처리결과": "rslt", "회신여부": "reply_yn",
    "회신일": "reply_dt", "회신내용": "reply_cont",
    "대여번호": "rent_no", "장비명": "eqp_nm", "장비코드": "eqp_cd", "대여자": "user_nm", "소속": "dept_nm", "신청일": "req_dt",
    "승인일": "aprv_dt", "대여일": "rent_dt", "반납예정일": "due_dt", "반납일": "rtn_dt", "보증금": "dpst", "공제액": "ddct",
    "환급액": "rfnd", "점검완료": "chk_yn", "점검일": "chk_dt", "점검자": "chk_nm", "비고": "rmk",
    "예약번호": "rsv_no", "신청자": "rqst_nm", "강의실": "room", "예약일": "rsv_dt", "시작시간": "st_tm", "종료시간": "ed_tm",
    "인원": "cnt", "사용목적": "purp", "승인상태": "aprv_stat", "승인자": "aprv_nm", "사용확인": "use_yn", "확인자": "cfm_nm",
    "일자": "dt", "품목코드": "item_cd", "품목명": "item_nm", "분류": "cls", "구분": "io_gb", "수량": "qty", "단가": "uprc",
    "금액": "amt", "잔여수량": "bal_qty", "담당자": "chrg_nm", "발주요청": "ord_yn", "발주일": "ord_dt", "입고예정일": "exp_dt",
    "회원번호": "mbr_no", "이름": "nm", "이메일": "email", "가입일": "join_dt", "등급": "grd", "회비납부": "pay_yn",
    "납부일": "pay_dt", "납부금액": "pay_amt", "탈퇴여부": "wdrw_yn", "탈퇴일": "wdrw_dt", "최근참여일": "last_dt",
}


def messy(name, header, rows, truth):
    """The same business as a real office sheet often is: cryptic headers, mixed date formats,
    thousands separators, stray spaces, an empty trailing column."""
    def mess_date(text):
        if not text or len(text) != 10:
            return text
        year, month, dayn = text.split("-")
        return rng.choice([f"{year}.{month}.{dayn}", f"{year}/{month}/{dayn}", f"{year}{month}{dayn}", text])

    def mess_value(value, role):
        if isinstance(value, int) and role in ("amount", "derived") and value >= 1000:
            return f"{value:,}"
        if isinstance(value, str) and role.startswith("date_") and value:
            return mess_date(value)
        if isinstance(value, str) and role in ("status", "category", "flag") and value and rng.random() < 0.15:
            return value + " "
        return value
    roles = truth["columnRoles"]
    new_header = [CRYPTIC.get(column, column) for column in header] + ["etc"]
    new_rows = [[mess_value(value, roles[index]) for index, value in enumerate(row)] + [""] for row in rows]
    new_truth = json.loads(json.dumps(truth))
    new_truth["columnRoles"] = roles + ["unknown"]
    new_truth["messy"] = ["약어 헤더", "날짜 형식 혼합", "천 단위 구분 기호", "값 끝 공백", "빈 컬럼"]
    return name.replace(".csv", "_지저분.csv"), new_header, new_rows, new_truth


def write(name, header, rows, truth):
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    (OUT / name.replace(".csv", ".truth.json")).write_text(
        json.dumps(truth, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(name, len(rows), "rows")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for build in (complaints, equipment, classroom, stock, members):
        name, header, rows, truth = build()
        write(name, header, rows, truth)
        write(*messy(name, header, rows, truth))


if __name__ == "__main__":
    main()
