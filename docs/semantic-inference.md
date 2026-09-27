# 의미 추론 계약 v1 (로컬 준비 단계)

이 문서는 이전 v1 계약의 기록이다. 신규 추론에는 [Preview 설정 계약 v2](preview-config-v2.md)를 사용한다.

`backend/uploads/inference.py`는 기존 분석 JSON을 입력으로 받아 추론용 메시지를 만들고, 가짜 또는 추후 받은 응답을 검증합니다. 네트워크·키 접근·DB 저장·API 엔드포인트는 없습니다. 현재 결과는 사용자 검토용 Preview 설정 후보이며 확정된 서비스가 아닙니다. Preview 설정 계약은 `docs/preview-config.md`와 `backend/uploads/preview_config.py`에 고정합니다.

## 입력

- `build_input(report, include_samples=False)`: 분석 v1의 컬럼 ID·이름·타입 후보·전체 통계·확인 사항·경고만 명시적으로 선택합니다. 파일명, 업로드 ID, 세션, 파일 경로는 포함하지 않습니다.
- 샘플은 기본 제외입니다. `include_samples=True`를 명시하면 기존 미리보기의 앞 3개 비어 있지 않은 레코드를 포함합니다. 이는 외부 호출 승인이 아닙니다.
- 컬럼명과 샘플 셀은 각각 160자로 제한하며 잘린 위치를 `sampling.truncated_paths`에 표시합니다. 원본 분석은 변경하지 않습니다. 컬럼명 중복·공백과 행의 부족한 셀은 위치 ID와 `null`로 구분합니다.
- 앞부분 샘플은 대표 표본이 아니며 통계는 전체 레코드 기준입니다. 긴 설명의 뒤쪽 업무 규칙이 생략될 수 있습니다. 샘플 제외 상태에서도 컬럼명은 포함되며, 자동 개인정보 익명화 기능은 없습니다.
- 입력 JSON은 UTF-8 64,000바이트까지 허용합니다. 초과하면 컬럼을 조용히 누락하지 않고 오류를 반환합니다. 이는 토큰/요금 한도가 아니며 시스템 요청문은 별도입니다.
- `build_prompt`는 시스템 지시문과 입력 JSON 메시지만 반환합니다. CSV 내용은 지시가 아닌 데이터로 취급하도록 요청합니다. 이 요청문 자체가 모델의 지시 준수를 보장하지는 않습니다.

## 출력

정확한 필드 계약은 코드의 `OUTPUT_CONTRACT`에 정의합니다.

| 필드 | 내용 |
| --- | --- |
| `schema_version` | 정수 `1` |
| `summary` | Preview 후보 요약 |
| `preview` | `docs/preview-config.md`의 Preview 설정 v1 |
| `questions` | 사용자 확인 질문·관련 컬럼 ID·질문 이유 (최대 30개) |

현재 사용 가능한 템플릿은 `cards`, `detail`, `table`, `grouped`입니다. `map`, `calendar`, `form`은 카탈로그에는 있지만 Claude 출력으로는 허용하지 않습니다.

`validate_response(raw, inference_input)`는 순수 JSON 문자열만 받고 크기·필수 필드·추가 필드·타입·배열 수·문자열 길이·중복 ID·잘못된 참조를 검사합니다. 중복 JSON 키, NaN, 코드 펜스, 존재하지 않는 컬럼/페이지 참조를 거절합니다. Preview 설정은 `validate_preview_config`로 다시 검증합니다. 의미의 정확성·가장 좋은 화면 구성 여부는 검증하지 못하므로 사용자 확인이 필요합니다. 자동 보정·재요청은 없습니다.

## 로컬 검증

저장소 루트에서 다음을 실행합니다. 표준 라이브러리만 사용하고 키나 DB가 필요하지 않습니다.

```sh
python -m unittest discover -s backend/uploads -t backend -p test_inference.py
```

테스트는 합성 CSV와 가짜 응답만 사용합니다. 사용자 예시 CSV는 테스트에서 읽지 않습니다.

## 실제 호출 전 필수 절차

현재 사용자 지시에 따라 모델·목적·실제 전송 내용·예정 호출 횟수·예상 비용을 보고하고 명시적인 승인을 받은 후에만 호출합니다. 테스트·실패 후 재시도도 별도 승인이 필요합니다. 이전 연결 테스트 1회 승인은 소진되었습니다. 이번 계약 구현 승인은 API 호출 승인이 아닙니다.
