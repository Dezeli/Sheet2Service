다음은 이번에 업로드한 단일 CSV 테이블의 분석 결과입니다.

컬럼 번호는 헤더의 왼쪽부터 1로 시작하며, 응답 스키마의 컬럼 번호와 같습니다. `sample_rows`의 `values`도 같은 컬럼 순서입니다. 같은 행에 함께 나타난 값들을 비교하면 컬럼의 실제 의미와 관계를 판단하는 데 도움이 됩니다. 예시 행은 일부이며 전체 분포를 대표하지 않습니다. 잘린 값은 원래 값으로 복원할 수 없습니다.

<csv_analysis>
{
  "row_count": {{ROW_COUNT}},
  "columns": {{COLUMNS_JSON}},
  "warnings": {{WARNINGS_JSON}},
  "sample_rows": {{SAMPLE_ROWS_JSON}},
  "sampling": {{SAMPLING_JSON}}
}
</csv_analysis>
