현재 적용 중인 서비스 설정을 사용자의 요청에 맞게 수정하세요. `status`, `message`, `blueprint`를 반환하세요.

<csv_analysis>
{{CSV_ANALYSIS_JSON}}
</csv_analysis>

<current_blueprint>
{{CURRENT_BLUEPRINT_JSON}}
</current_blueprint>

<current_page>
{{CURRENT_PAGE_JSON}}
</current_page>

<user_request>
{{USER_REQUEST_JSON}}
</user_request>

현재 설정은 서버 검증을 통과한 값입니다. `current_page`는 사용자가 요청을 입력한 화면이며, "이 화면" 같은 표현을 해석하는 데 사용하세요. 사용자는 대시보드·사용자·관리자 화면 중 어느 화면의 변경도 요청할 수 있습니다. 관련 없는 부분은 유지하세요. 지원하지 않거나 추가 정보가 필요한 경우 `blueprint`는 현재 설정과 완전히 같아야 합니다. 응답 구조와 허용 값은 JSON Schema를 따르세요.
