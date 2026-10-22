# 조합형 서비스 구성안: 첫 증분

## 이번 증분의 위치

기존 서비스는 [기능 조합 계약](service-features.md)의 등록된 업무 템플릿을 선택해 실행한다. 새 업로드의 기본 생성 버튼은 이 문서의 `service_blueprint` v1을 생성해 바로 사용자 화면으로 이동한다. 생성 모달의 접힌 `기존 템플릿 방식 사용`에서는 이전 추론·기능 선택 흐름을 계속 실행할 수 있다. 기존 업로드의 템플릿 기반 Preview v2 설정과 저장된 호출 결과도 그대로 읽는다.

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

검증 코드는 [`service_blueprint.py`](../backend/uploads/service_blueprint.py)에 있다. 응답의 추가 키, 존재하지 않는 컬럼·상태, 중복 ID, 지원하지 않는 필드·차트 타입을 거절한다. 코드·SQL 같은 임의 실행 필드도 허용하지 않는다. 표시용 컬럼 목록은 **모든 컬럼 번호를 검증한 뒤** 중복을 제거하고 앞에서부터 표시 상한까지만 취한다. 업무 흐름·상태 전환은 자르지 않고 엄격히 검증한다. 검증 오류가 나면 기존 서비스 설정은 유지하며 자동 Claude 재호출은 하지 않는다. 요청의 저장·상태 변경은 [`service_blueprint_views.py`](../backend/uploads/service_blueprint_views.py)에서 검증된 설정과 서버의 세션 범위를 적용한다.

## Claude 생성 및 수정 입출력

생성 요청의 시스템 지침은 [`service_blueprint_create_system.md`](../backend/claude_api_settings/service_blueprint_create_system.md), 본문 틀은 [`service_blueprint_create_content.md`](../backend/claude_api_settings/service_blueprint_create_content.md)에 있다. [`service_blueprint_request.py`](../backend/uploads/service_blueprint_request.py)가 이 파일들을 읽고 CSV별 컬럼 번호 enum을 가진 JSON Schema를 만든다. 업무 흐름·입력 필드·상태의 내부 ID와 필드 유형·상태 변경 역할도 enum으로 제한한다. 배열 길이는 모델 스키마만으로 보장하지 않으므로 프롬프트에 상한을 적고 서버에서 표시용 배열을 결정적으로 정리한다. 전송 데이터는 현재 v2 분석 입력의 허용 목록이다: 행 수, 컬럼 번호·이름·형식·통계·경고, 최대 10개 예시 행과 절단 정보. 원본 CSV 전체, 파일 경로, 업로드 ID, 키는 보내지 않는다. 전체 요청은 100,000바이트로 제한한다.

수정 요청은 [`service_blueprint_revision_system.md`](../backend/claude_api_settings/service_blueprint_revision_system.md)와 [`service_blueprint_revision_content.md`](../backend/claude_api_settings/service_blueprint_revision_content.md)를 사용하도록 설계했다. 입력은 같은 CSV 분석 허용 목록, **현재 검증된 전체 설정**, 요청을 입력한 화면, 사용자의 짧은 수정 요청이다. `current_page`는 “이 화면” 같은 표현을 해석하는 데 사용한다. 응답은 [`service_blueprint_revision_response.example.json`](../backend/claude_api_settings/service_blueprint_revision_response.example.json)처럼 `status`, `message`, `blueprint` 세 필드를 가진다.

- `applied`: 수정된 전체 설정과 한 문장 요약. 실제 변경이 있어야 한다.
- `unsupported`: 현재 기능으로 실행할 수 없는 이유와 변경 없는 설정.
- `needs_input`: 반드시 필요한 경우 사용자에게 보여줄 질문 한 개와 변경 없는 설정.

서버는 전체 설정을 다시 검증한다. `unsupported` 또는 `needs_input`인데 설정이 변경되었거나, `applied`인데 변화가 없으면 응답을 거절한다. 수정 전후의 전체 요청·응답은 `ModelCall`에 기록하며, 이미 신청 내역이 있는 업무의 ID 삭제·변경은 막는다. 과거 신청은 생성 당시 업무 설정의 스냅샷을 보존한다. 이전 서비스 설정으로 되돌리는 UI는 후속 범위다. 프롬프트 파일 변경은 **새로 실행하는 호출부터** 적용된다.

## 현재 연결된 사용자 흐름

1. CSV를 올리면 `GET /api/uploads/{id}/blueprint/approval/`가 전송 목적·범위·모델·1회 호출·요청 지문을 반환한다. 이 단계는 Claude를 호출하지 않는다.
2. 생성 모달에서 범위와 1회 호출을 읽고 `서비스 생성`을 누르면 `POST /blueprint/generate/`가 지문을 재검증하고 Claude를 **한 번** 호출한다. 유효한 설정만 `Upload.service_blueprint`에 저장한다. 성공 시 `/User`로 바로 이동한다.
3. 사용자 화면은 구성된 CSV 목록·검색·필터와 입력 폼을 보여주며, 대시보드는 전체 행 개수 집계, 관리자 화면은 신청 처리와 기존 원본 데이터 관리를 제공한다. 신청은 `BlueprintSubmission`에 저장한다. 상태 변경은 저장 당시의 허용 전환과 `owner`·`admin` 역할을 검사한다.
4. 세 화면 공통 우측 `서비스 수정 요청` 패널에서 사용자가 글을 입력하고 명시된 Claude 1회 호출 버튼을 누르면, 내부 사전 조회 후 `POST /blueprint/revise/`를 호출한다. 요청에는 현재 설정 전체와 입력 화면이 포함되어 다른 화면도 수정할 수 있다. 정상 변경은 즉시 화면에 반영하며, 지원 불가·추가 정보 필요는 대화 메시지로 안내한다. 대화 표시 기록은 브라우저 세션 저장소에만 보관하고 모델에는 직전 요청 하나만 보낸다.

관리자 화면에는 기존 필드 구성·선택지 관리·데이터 관리 사이드바를 다시 사용한다. 현재 수정 범위는 `service_blueprint` 계약이 표현하는 목록·필터·차트·업무 흐름·제목/설명이다. 화면의 임의 CSS나 레이아웃 변경은 이 계약에 포함되지 않는다.

조합형 사용자 화면은 기존 템플릿의 목록/내 신청 현황 2열 구성, 목록 스크롤, 상세·신청 대화상자, 역할별 버튼 스타일을 재사용한다. 관리자 업무 내역은 기존 신청 관리와 같은 표·상세 펼침 형태로 표시한다. 업무 제목과 폼 필드·상태 전환은 생성된 설정을 사용한다. `예약 신청`이라는 제목이 생성되어도 현재는 일반 신청 기록·상태 전환만 실행한다. 예약 시간·정원·중복 예약 검증은 별도 예약 실행 규칙이 도입되기 전까지 제공하지 않는다.

현재 `admin`은 업로드 소유 세션의 관리자 Preview 역할이다. 별도 관리자 계정 인증이 도입된 상태는 아니다. 사용자 브라우저에서의 화면 검증과 실제 Claude 응답의 의미 정확도는 아직 확인하지 않았다.

## 다음 증분 후보

1. 사용자가 체육시설과 다른 CSV로 생성 화면과 수정 요청을 확인한다. 실제 호출은 사용자가 명시적인 앱 버튼을 클릭할 때만 1회씩 실행된다.
2. 이 계약이 현재 문의·신청의 세부 동작을 충분히 표현하는지 비교하고, 사용자 피드백에 따라 공통 부품을 조정한다.
3. 정원·재고·견적처럼 독립 검증 규칙이 필요한 부품을 추가한 뒤 기존 템플릿을 단계적으로 옮긴다.
