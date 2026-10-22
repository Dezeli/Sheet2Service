현재 적용 중인 서비스 설정을 사용자의 요청에 맞게 수정하세요. `status`, `message`, `blueprint`를 반환하세요.

<csv_analysis>
{{CSV_ANALYSIS_JSON}}
</csv_analysis>

<current_blueprint>
{{CURRENT_BLUEPRINT_JSON}}
</current_blueprint>

<user_request>
{{USER_REQUEST_JSON}}
</user_request>

현재 설정은 서버 검증을 통과한 값입니다. 사용자 요청과 무관한 부분은 유지하세요. 지원하지 않거나 추가 정보가 필요한 경우 `blueprint`는 현재 설정과 완전히 같아야 합니다. 응답 구조와 허용 값은 JSON Schema를 따르세요.
