# 예약 서비스 도출과 실행

`ReservationUnderstanding`(`docs/reservation-understanding.md`)에서 서비스까지는 전부 결정론이다. 모델 호출은 생성 때 1회뿐이고, 이후의 모든 화면·API는 저장된 설정과 데이터로만 동작한다.

## 설정 도출 (`reservation_service.derive_service`)

`Upload.service_config`에 저장된다.

- `resources`: 예약 대상 컬럼(상위→하위)과 그 라벨, 가로형 시트의 `widePairs`(대상 컬럼, 짝이 되는 시간 컬럼).
- `booking`: `mode`, 새 예약을 받는지(`acceptsNew`), 승인 단계가 있는지(`approvalRequired`), 상태 컬럼과 상태 값 매핑, 시간 모델(`date`·`date_slot`·`range`·`start`·`slot`·`none`), 역할별 컬럼 번호(예약자·인원·목적·금액·결제·승인·취소·추첨·담당자·기관·신청 일시·정원·예약자 속성). 자원 목록·정책 시트는 날짜 단위 예약(`date`), 가로형은 날짜+시간대(`date_slot`)로 고정한다.
- `personas`: 이해의 페르소나 그대로. 예약 대상이 없거나 기록만 있는 시트에서는 예약 기능을 뺀다.
- `dashboard.preview`: 기존 대시보드 런타임(v2 설정)용 표 1개와 집계 차트 최대 4개(상태·승인·결제·추첨·취소 → 도넛, 대상 묶음·대상·예약자 속성·담당자·시간대·기관 → 막대).

## 데이터 적재 (`apply_service`)

시트 행(`ManagedRow`)을 서비스 엔티티로 바꾼다. 다시 실행하면 이전 적재를 지우고 새로 만든다.

| 시트 모양 | 만드는 것 |
| --- | --- |
| `booking_records` | 대상 컬럼 조합의 고유 접두사마다 `Resource`(계층), 행마다 `Booking`(상태는 상태 값 매핑 → 접두사 일치 → 취소·승인·추첨 여부 → 키워드 순으로 결정) |
| `resource_catalog`, `policy` | 행마다 말단 `Resource`, 상위 컬럼은 부모 노드. 정원·요금·주소·연락처 등은 `attributes` |
| `schedule_slots` | 대상 `Resource`와 행마다 `Slot`(날짜·시간대·정원·시트에 적힌 참가 인원 `imported_count`) |
| `wide_schedule` | 대상 컬럼마다 `Resource`, 채워진 셀마다 `Booking`(값은 목적, 짝 시간 컬럼은 시간대) |
| `aggregate`, `unrelated` | 없음 |

시간은 `parse_date`·`parse_time`(`14:00`, `오후2시`, `12시`)·`parse_range`(`A~B`, 날짜의 하이픈은 범위로 보지 않음)·`parse_moment`로 읽어 `date`, `starts_at`, `ends_at`, `time_slot`에 넣는다. 모든 일시는 Asia/Seoul로 저장한다.

## 예약 규칙 (`booking_rules.py`)

`service_config.booking.rules`에 저장한다. 저장된 규칙이 없으면(규칙 도입 전 서비스 포함) `rules_of`가 시트에서 도출한 기본값을 쓴다. 한 시트에 대관·강좌·체험이 섞이는 경우가 많아 `Resource.rules`로 묶음·항목마다 별도 규칙을 둘 수 있고, 항목은 가장 가까운 상위의 규칙을 따른다(`rules_for`).

- `timeMode`: `day`(하루), `time_slot`(정해진 시간대), `time_range`(시간 단위), `stay`(숙박, 퇴실일 아침에 비움), `period`(기간, 마지막 날 포함). 저장하면 `booking.unit`도 같은 값으로 맞춘다.
- `sessions`: 시간대 이름과 시각. 기본값은 시트에서 자주 쓰인 시간대(`오후2시~4시` 같은 표기도 읽음), 없으면 오전·오후. 시각이 없는 시간대는 이름으로만 구분한다.
- `hourly`: 운영 시작·종료(`24:00` 허용), 간격(10~240분), 최소·최대 이용 칸 수(최대 0은 제한 없음). 기본 운영 시간은 기록의 시각 범위.
- `capacityBy`·`limit`: 같은 시간에 받는 수를 예약 건수(`bookings`)로 셀지 인원 합계(`people`)로 셀지와 기본 한도. 항목(`Resource.capacity`)에 숫자가 있으면 그 값이 우선한다. 기본은 정원 컬럼 이름에 정원·인원·수용·명이 있으면 인원, 아니면 건수 1.
- `closedWeekdays`: 휴무 요일(월=0).
- `perPerson`: 한 사람이 규칙 범위(규칙을 가진 묶음, 서비스 규칙이면 서비스 전체) 안에서 `day`(같은 날) 또는 `upcoming`(오늘 이후 진행 중) 기준으로 가질 수 있는 예약 수. 0은 제한 없음. 로그인이 없어 전화번호가 같으면 같은 사람으로 본다.

모든 예약을 한 항목 위의 시간 구간으로 바꿔(`occupancy`) 요청 구간 안의 최대 동시 부하(`peak`)를 구한다. 시각을 모르는 이름 전용 시간대는 같은 이름끼리와 시각 있는 예약하고만 겹친다. 예약 생성, 취소·거절된 예약 다시 열기, 달력·시간대 가용성, 일정표의 초과 표시가 모두 이 계산을 쓴다. 회차(`Slot`)의 정원은 기록된 참가 인원처럼 인원 합계로 센다.

## 예약자 식별

로그인 대신 이름과 전화번호로 예약자를 구분한다. 예약자 역할의 예약에는 둘 다 필수이고, 전화번호는 `phone_digits`로 숫자만 남겨(`+82` → `0`) `Booking.phone`에 저장한다. 기록형 시트의 연락처(`contact`) 컬럼은 예약자 전화번호로 가져온다(`phoneColumn`). 내 예약은 이 브라우저 세션의 예약이거나, `name`·`phone`을 주면 그 둘이 맞는 예약이며 취소도 같은 값으로 한다. 관리 화면 목록은 번호를 가리고(`010-****-5678`) 상세에서만 전부 보여 준다. 문자 인증은 없어 다른 번호를 넣으면 우회할 수 있다.

## API (`booking_views.py`)

모든 요청은 업로드 세션 안에서만 통하며 `persona` 파라미터로 역할을 밝힌다. 역할은 설정의 페르소나 중 하나여야 하고 그 기능이 있어야 한다(`service_access.requested_persona`).

- `resources/`: 상위 목록·`parent`로 하위·`q`로 경로 검색(`all=1`이면 사용 중지 포함). POST·PATCH·DELETE는 `manage_resources`. 이름을 바꾸면 하위 경로도 따라 바뀌고, 예약 기록이 있는 항목의 삭제는 사용 중지로 대신한다.
- `slots/`: `resource`·`from`·`available=1`. POST·PATCH(정원·마감)·DELETE는 `manage_schedule`.
- `booking-rules/`: GET은 현재 규칙(`resource`를 주면 그 항목이 따르는 규칙과 출처 `source`), 시트 기준 기본값, 별도 규칙이 있는 묶음 목록(`overrides`). PATCH(`rules`, `resource_id`)는 `manage_schedule` 또는 `manage_resources`이며 `resource_id`와 `rules: null`이면 그 묶음의 별도 규칙을 지운다. 검증은 `validate_rules`.
- `bookings/availability/`: `resource`와 `month`면 날짜별 마감·휴무·건수, `date`면 그날의 시간대(`sessions`) 또는 시간 칸(`blocks`)별 잔여와 선택 가능 여부.
- `bookings/`: `booker`는 자기 예약만, `staff`·`org_manager`는 `scope`(담당자명·기관명·대상 상위 이름)로 제한, `admin`·`finance`는 전체. 필터 `status`·`resource`·`from`·`to`·`q`. POST는 `make_reservation`(예약 규칙에 맞는 시간만, 말단 항목만, 한도·겹침·휴무 검사, 승인형이면 `requested`), PATCH `action`은 `approve`·`reject`(사유 필수)·`cancel`·`check_in`·`complete`·`reopen`(자리가 남아 있을 때만)이며 예약자는 자기 예약의 취소만 가능. 모든 전이는 `BookingEvent`에 남는다.
- `bookings/schedule/`: `from`부터 `days`(최대 31)일 동안 항목별 예약과 초과. `resource`를 주면 그 항목 하나(달력 보기).
- `bookings/stats/`, `bookings/scopes/`.
- 문의(`inquiries/`)와 공지(`notices/`)는 페르소나 기능(`inquiry`·`reply_inquiries`, `notices`·`manage_notices`)이 있을 때만 열린다. 문의의 관련 항목은 마지막 예약 대상 컬럼으로 이름 붙인다.

## 화면 (`frontend/src/booking/`)

`/<upload>/<personaId>`와 `/<upload>/DashBoard`. 상단 전환은 설정의 페르소나 제목으로 만들어진다. 각 페르소나의 메뉴는 기능에서 나온다.

- 예약하는 쪽: 대상 찾기(계층 탐색·검색·말단 상세·회차 목록) → 예약 대화상자(규칙의 시간 단위별 입력. 마감·휴무 날짜와 찬 시간대·시간 칸은 고를 수 없음) → 내 예약(취소). 문의·공지.
- 관리하는 쪽(사이드바): 예약 관리(필터·상태 처리·상세와 이력), 일정표(주간 전체 또는 항목 하나의 월간 달력과 날짜별 남은 자리), 회차·정원(회차 시트에서만), 예약 규칙, 대상 관리(등록·수정·속성·사용 중지·삭제), 문의 답변, 공지 관리, 대시보드, 필드 구성·선택지 관리·데이터 관리(기존 화면).
- `staff`·`org_manager`는 상단에서 담당 범위를 먼저 고른다.
- 대시보드: 시트에서 읽어낸 요약(대상·방식·역할), 예약 현황, 데이터 통계.

## 아직 없는 것

로그인·권한(지금은 역할 전환이 화면 모드일 뿐), 추첨 동작, 다중 테이블 참조, 10MB·50,000행을 넘는 시트, 시트의 상태 값이 12종을 넘을 때의 상태 검증, 지난 회차만 있는 회차 시트의 새 회차 자동 생성.
