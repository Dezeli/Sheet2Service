# Preview 설정 계약 v1

이 문서는 CSV 분석 결과와 Preview 런타임 사이의 설정 JSON을 고정합니다. 이 설정은 실행 코드가 아니며, React 런타임이 이미 가진 템플릿에 컬럼 ID를 연결하는 선언형 데이터입니다.

## 최상위 구조

```json
{
  "version": 1,
  "title": "시설·서비스 둘러보기",
  "pages": []
}
```

- `version`: 정수 `1`
- `title`: 1~120자 문자열
- `pages`: 1~7개 페이지 설정

`pages` 외부에 업로드 ID, 세션, 원본 파일 경로, 실행 코드, SQL, CSS, HTML 조각은 포함하지 않습니다.

## 페이지 구조

```json
{
  "id": "services",
  "template": "cards",
  "title": "서비스 목록",
  "bindings": {},
  "detailPage": "service_detail",
  "charts": []
}
```

- `id`: 소문자로 시작하고 소문자·숫자·`_`만 쓰는 1~64자 문자열, 페이지 안에서 중복 불가
- `template`: 지원 템플릿 ID
- `title`: 1~120자 문자열
- `bindings`: 템플릿 슬롯과 CSV 분석 컬럼 ID의 연결
- `detailPage`: 선택값, `cards`와 `grouped`에서만 허용하며 대상은 `detail` 페이지여야 함
- `charts`: 선택값, `cards`·`table`·`grouped`에서만 최대 4개

## 현재 사용 가능한 템플릿

| 템플릿 | 상태 | 필수 바인딩 | 선택 바인딩 | 목록 바인딩 |
| --- | --- | --- | --- | --- |
| `cards` | 사용 가능 | `title` | `subtitle`, `image`, `badge` | `fields` |
| `detail` | 사용 가능 | `title` | `image`, `badge`, `link`, `phone` | `fields` |
| `table` | 사용 가능 | 없음 | 없음 | `fields` |
| `grouped` | 사용 가능 | `title`, `group` | `subtitle`, `image`, `badge` | `fields` |
| `map` | 예약 | `title`, `latitude`, `longitude` | 없음 | `fields` |
| `calendar` | 예약 | `title`, `start` | `end` | `fields` |
| `form` | 예약 | 없음 | 없음 | `fields` |

예약 템플릿은 카탈로그에는 남기지만 현재 Preview 실행에는 사용할 수 없습니다.

## 바인딩 규칙

단일 바인딩은 컬럼 ID 문자열입니다.

```json
{ "title": "column_1" }
```

목록 바인딩은 컬럼 ID 배열입니다.

```json
{ "fields": ["column_1", "column_2"] }
```

모든 컬럼 ID는 현재 CSV 분석 결과의 `columns[].id`에 존재해야 합니다. 목록 바인딩은 비어 있을 수 없고, 중복 컬럼을 허용하지 않으며, 최대 200개까지 허용합니다. `table`과 `form`은 `fields`가 반드시 필요합니다.

## 그래프

```json
{
  "type": "bar",
  "title": "종목별 서비스 수",
  "groupBy": "column_5",
  "aggregate": "count"
}
```

- `type`: `bar` 또는 `donut`
- `title`: 1~120자 문자열
- `groupBy`: 현재 CSV 분석 결과에 존재하는 컬럼 ID
- `aggregate`: 현재는 `count`만 허용

그래프 집계는 Claude가 계산하지 않습니다. Preview 런타임이 현재 표시 레코드에서 계산합니다.

## 검증 위치

- 프론트엔드: `frontend/src/preview/config.js`의 `validateConfig`
- 백엔드: `backend/uploads/preview_config.py`의 `validate_preview_config`

Claude 출력과 사용자 저장 설정은 백엔드 검증을 통과한 뒤 Preview 런타임에 전달합니다. 검증기는 구조, 허용 키, 템플릿 상태, 컬럼 참조, 페이지 참조를 확인합니다. 의미적으로 가장 좋은 화면인지 여부는 검증하지 못하므로 사용자 확인이 필요합니다.
