다음 예약 관련 스프레드시트에서 무엇이 예약되고, 누가 예약하며, 어떤 상태를 거치고, 누가 관리하는지 `ReservationUnderstanding` JSON으로 답하세요. 컬럼 번호는 1부터 시작합니다.

<file_name>
{{FILE_NAME_JSON}}
</file_name>

<csv_analysis>
{{CSV_ANALYSIS_JSON}}
</csv_analysis>

<operational_signals>
{{SIGNALS_JSON}}
</operational_signals>

`csv_analysis`는 컬럼별 통계와 예시 행입니다. `operational_signals`는 최대 5,000행 표본에서 계산한 사실입니다: `presence`는 컬럼별 채워진 비율, `value_sets`는 값이 12종 이하인 컬럼의 값과 건수, `flags`는 두 값짜리 여부 컬럼, `conditional_missing`은 `given` 컬럼의 값별로 `column`이 비어 있는 비율, `fill_chain`은 `later`가 채워진 행에서는 `earlier`도 채워져 있다는 관계, `co_filled`는 같은 행에서 함께 채워지고 함께 비는 컬럼 쌍, `flow_clusters`는 그렇게 서로 얽힌 컬럼 묶음, `date_order`·`date_gaps`는 같은 행에서 날짜의 선후와 간격(일), `numeric_relations`·`cumulative`는 숫자 관계, `identifiers`·`patterns`·`free_text`는 값의 모양, `fill_patterns`는 함께 비어 있는 컬럼 조합입니다. 신호는 사실만 말하며 해석은 당신이 합니다. 신호가 없는 항목은 그런 패턴이 관찰되지 않았다는 뜻입니다.
