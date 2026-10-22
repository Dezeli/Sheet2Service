# 조합형 서비스 구성안: 첫 증분

## 이번 증분의 위치

현재 서비스는 [기능 조합 계약](service-features.md)의 등록된 업무 템플릿을 선택해 실행한다. 화면 미리보기 설정은 별도 v2 계약으로 동작한다. 이 문서의 `service_blueprint` v1은 다음 구조를 검토하기 위한 **독립적인 오프라인 계약**이다. 현재 업로드, 생성 버튼, Preview, DB, Claude 요청에는 연결하지 않았다. 기존 설정과 저장된 호출 결과를 변경하지 않는다.

첫 범위는 CSV 목록·검색·정확한 값 필터·개수 집계와 CSV 항목을 대상으로 하는 간단한 입력·상태 흐름이다. 문의·신청처럼 공통화 가능한 부분을 먼저 표현한다. 예약 정원, 대여 재고, 견적 금액처럼 별도 실행 규칙이 필요한 기능은 아직 표현하지 않는다. 이 제한을 생성 프롬프트에도 명시했다.

## 설정과 실행 의미

전체 응답 예시는 [`service_blueprint_response.example.json`](../backend/claude_api_settings/service_blueprint_response.example.json)에 있다. 필드는 다음과 같다.

| 필드 | 의미 | 검증 |
| --- | --- | --- |
| `version`, `title`, `summary` | 계약 버전과 사용자에게 보일 짧은 설명 | 버전 1, 길이 제한 |
| `catalog.titleColumn` | CSV 행을 가리키는 대표 컬럼 | 이번 CSV의 1부터 시작하는 컬럼 번호 |
| `visibleColumns`, `searchColumns`, `filterColumns` | 목록 표시·전체 데이터 검색·정확한 값 필터에 쓸 컬럼 | 실제 컬럼 번호, 중복·개수 제한 |
| `charts` | `count_by` 집계 | 실제 그룹 컬럼, 최대 4개 |
| `workflows[]` | 항목별로 생성할 새 요청의 입력·상태 | 최대 3개, 고유 ID |
| `fields[]` | 새 요청에서 받을 값 | text·number·date, 최대 6개 |
| `states`, `initialState`, `transitions` | 요청의 상태와 허용 상태 변경 | 상태 참조·역할·중복 검증 |

`owner`는 요청을 만든 브라우저 세션, `admin`은 관리자 역할이다. 현재 앱의 관리자 화면은 업로드 소유 세션 안의 Preview이므로 이 구성안만으로 외부 사용자 인증이나 실서비스 관리자 권한이 생기지는 않는다. 후속 실행 엔진은 조회 범위와 각 전환의 역할을 서버에서 강제해야 한다. 화면은 설정의 목록·업무 흐름에서 조립하고, 사용자에게 이 JSON을 검토하도록 요구하지 않는다.

검증 코드는 [`service_blueprint.py`](../backend/uploads/service_blueprint.py)에 있다. 응답의 추가 키, 존재하지 않는 컬럼·상태, 중복 ID, 지원하지 않는 필드·차트 타입, 과도한 배열을 거절한다. 코드·SQL 같은 임의 실행 필드도 허용하지 않는다. 검증 오류가 나면 기존 서비스 설정은 유지하며 자동 Claude 재호출은 하지 않는다. 현재 코드는 **계약만 검증**하며 입력 저장과 화면 실행은 아직 구현하지 않았다.

## Claude 생성 및 수정 입출력

생성 요청의 시스템 지침은 [`service_blueprint_create_system.md`](../backend/claude_api_settings/service_blueprint_create_system.md), 본문 틀은 [`service_blueprint_create_content.md`](../backend/claude_api_settings/service_blueprint_create_content.md)에 있다. 전송할 데이터는 현재 v2 분석 입력과 같은 허용 목록을 기준으로 설계한다: 행 수, 컬럼 번호·이름·형식·통계·경고, 최대 10개 예시 행과 절단 정보. 원본 CSV 전체, 파일 경로, 업로드 ID, 키는 보내지 않는다. 실제 호출 연결 전에 요청 크기 상한과 컬럼별 응답 스키마를 구현·검증해야 한다.

수정 요청은 [`service_blueprint_revision_system.md`](../backend/claude_api_settings/service_blueprint_revision_system.md)와 [`service_blueprint_revision_content.md`](../backend/claude_api_settings/service_blueprint_revision_content.md)를 사용하도록 설계했다. 입력은 같은 CSV 분석 허용 목록, **현재 검증된 전체 설정**, 사용자의 짧은 수정 요청이다. 응답은 [`service_blueprint_revision_response.example.json`](../backend/claude_api_settings/service_blueprint_revision_response.example.json)처럼 `status`, `message`, `blueprint` 세 필드를 가진다.

- `applied`: 수정된 전체 설정과 한 문장 요약. 실제 변경이 있어야 한다.
- `unsupported`: 현재 기능으로 실행할 수 없는 이유와 변경 없는 설정.
- `needs_input`: 반드시 필요한 경우 사용자에게 보여줄 질문 한 개와 변경 없는 설정.

서버는 전체 설정을 다시 검증한다. `unsupported` 또는 `needs_input`인데 설정이 변경되었거나, `applied`인데 변화가 없으면 응답을 거절한다. 수정 이력의 저장과 이전 버전 복원은 후속 증분에서 설계한다. 프롬프트나 예시 파일은 **현재 실행 경로에 연결되지 않았으므로** 파일을 수정해도 실제 Claude 요청은 바뀌지 않는다.

## 다음 증분 후보

1. 이 계약이 현재 문의·신청을 표현하는지 대조하고, 업무 흐름 엔진의 저장·권한·상태 전환을 구현한다.
2. 기존 목록 화면과 조회 API를 설정 기반으로 연결해 읽기 전용 CSV에서 먼저 검증한다.
3. 생성·수정용 컬럼별 JSON Schema, 요청 크기 제한, 승인 정보, 호출 기록을 연결한다. 사용자에게는 생성된 Preview와 짧은 변경 결과만 보여준다.
4. 정원·재고·견적처럼 독립 검증 규칙이 필요한 부품을 추가한 뒤 기존 템플릿을 단계적으로 옮긴다.
