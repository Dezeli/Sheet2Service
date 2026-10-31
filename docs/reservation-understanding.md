# 예약 시트 이해 계약 (ReservationUnderstanding v1)

2026-10-31. 브랜치 `feat/reservation-sheets`는 10-11 커밋(`d3b43de`)에서 분기했고, 입력을 **예약 관련 시트**로 한정한다. 사람이 템플릿을 고르는 단계는 없다. 업로드 → Claude 호출 1회(이 계약) → 서버가 결정론적으로 서비스 설정을 만들고 바로 서비스 화면으로 간다.

## 입력

`backend/uploads/reservation_understanding_request.py`가 요청 본문을 만든다. 보내는 것은 파일 이름, 컬럼별 분석(`preview_request_v2.build_input`: 이름·추정 형식·빈 값·고유값·형식 분포, 예시 행 최대 10개, 값은 160자에서 잘림), 그리고 `operational_signals`(`backend/uploads/operational_signals.py`, 표본 5,000행에서 계산한 컬럼 간 사실: 값 집합·여부 컬럼·조건부 결측·채움 사슬·날짜 선후·숫자 관계·식별자 모양). 원본 파일은 보내지 않는다. 시스템 프롬프트는 `backend/claude_api_settings/reservation_understanding_system.md`, 사용자 메시지 틀은 `reservation_understanding_content.md`. 응답은 JSON Schema로 강제한다(`understanding_schema`). `max_tokens`는 16,000(모델의 사고 토큰이 포함된다).

## 출력

| 항목 | 뜻 |
| --- | --- |
| `sheetKind` | 행 하나가 무엇인지: `booking_records`(예약 한 건), `resource_catalog`(예약 가능한 대상), `schedule_slots`(회차·시간대), `wide_schedule`(대상이 컬럼 머리글), `policy`(규칙·요금 정책), `aggregate`(집계값), `unrelated`(예약 업무와 무관·부속 표) |
| `subject`, `summary` | 예약 대상 명사구(24자), 세 문장 요약 |
| `columnRoles`, `columnEvidence` | 컬럼 수와 같은 길이의 역할·근거 배열. 역할 어휘는 `reservation_understanding.ROLES` (대상·시간·예약자·상태·운영 네 묶음, `wide_resource`/`wide_time`은 가로형 전용) |
| `resourceColumns` | 사용자가 예약 때 고르는 것을 상위→하위 순서로 적은 컬럼 번호. 기록형 시트에서는 이 조합의 고유값이 대상 목록이 된다 |
| `booking` | `mode`(`approval`/`instant`/`lottery`/`record_only`/`none`), `statusColumn`(없으면 0), 상태 값과 뜻(`stateValues`/`stateKinds` 병렬 배열), 근거 |
| `personas` | `booker`·`admin`이 기본. 시트에 근거가 있을 때 `staff`(담당자 컬럼 범위), `org_manager`(기관 컬럼 범위), `finance`, `viewer`. 각 페르소나의 `features`는 고정 템플릿 목록(`FEATURES`)에서만 고른다 |
| `questions` | 답에 따라 서비스 모양이 달라지는 의문 최대 3개. 현재 UI에는 쓰지 않고 기록만 한다 |

## 서버 검증 (`validate_understanding`)

응답은 버리지 않고 낮춘다. 각 보정은 `notes`에 한 줄로 남고 ModelCall의 `parsed_result.notes`에 저장된다.

- 길이가 다른 병렬 배열은 컬럼 수에 맞추고 모르는 역할은 `other`. 가로형이 아닌 시트의 `wide_*` 역할은 `other`.
- `resourceColumns`의 없는 컬럼은 제외하고, 비어 있으면 `resource_group`·`resource` 역할 컬럼으로 채운다. 지정된 대상 컬럼의 역할은 `resource`로 맞춘다.
- 상태 값은 운영 신호가 실제로 본 값(`value_sets`·`flags`)만 남기고, 응답에 없던 실제 값은 `other`로 보충한다. 상태 컬럼이 없으면 상태 값은 비운다.
- 예약 대상이 없는 시트(`aggregate`·`unrelated`)는 `mode`가 `none`이 되고 `booker`는 `viewer`로 바뀐다. 추첨 근거가 없는 `lottery`는 `approval`로 낮춘다.
- `staff`·`org_manager`는 범위 컬럼이 없으면 제외. `booker`·`admin`이 없으면 기본으로 추가한다. 페르소나별 허용 밖의 기능은 제외하고, 필수 기능(booker: 대상 찾기·예약·내 예약, admin: 대상 관리·예약 처리·데이터 관리·대시보드)은 보충한다.

## 실행

- `GET /api/uploads/{id}/understanding/`: 승인 요약(목적·모델·전송 범위·지문)과 저장된 이해. 호출하지 않는다.
- `POST` 같은 경로, `{"approved": true, "approval_note": "...", "request_fingerprint": "..."}`: 호출 1회. 결과는 `Upload.understanding`(마이그레이션 0014)과 ModelCall에 저장된다. 길이 제한으로 끊긴 응답과 JSON 오류는 실패로 기록하고 저장하지 않는다.
- `python manage.py understand_csv <경로> [--approve "문구"] [--json] [--keep]`: 로컬 CSV로 같은 호출을 실행한다. `--approve`가 없으면 승인 요약과 신호만 출력하고 호출하지 않는다.

이해 결과를 서비스 설정으로 바꾸는 결정론 도출과 실행기는 다음 단계(`docs/handoff.md` 참고)다.
