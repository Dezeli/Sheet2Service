"""Finite user/admin flow templates and offline model-output validation."""

import hashlib
import json

from django.conf import settings

from .inference import InferenceError, json_text
from .models import ModelCall


FLOW_TEMPLATES = {
    "user": ("request_review", "request_auto", "browse_only"),
    "admin": ("review_requests", "monitor_requests", "manage_catalog"),
}
COMPATIBLE = {
    "request_review": "review_requests",
    "request_auto": "monitor_requests",
    "browse_only": "manage_catalog",
}
MAX_DESCRIPTION = 500


def subject_columns(report):
    populated = [index for index, column in enumerate(report["columns"], 1)
                 if column["non_empty_count"] > 0]
    return populated or list(range(1, len(report["columns"]) + 1))


def flow_schema(scope, report):
    return {
        "type": "object",
        "properties": {
            "template": {"type": "string", "enum": list(FLOW_TEMPLATES[scope])},
            "subjectColumn": {"type": "integer", "enum": subject_columns(report)},
            "steps": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["template", "subjectColumn", "steps"],
        "additionalProperties": False,
    }


def normalize_flow(value, scope, report):
    if not isinstance(value, dict) or set(value) != {"template", "subjectColumn", "steps"}:
        raise ValueError("플로우 후보 형식이 올바르지 않습니다.")
    if value["template"] not in FLOW_TEMPLATES[scope] or type(value["subjectColumn"]) is not int \
            or value["subjectColumn"] not in subject_columns(report):
        raise ValueError("지원하지 않는 플로우 후보입니다.")
    steps = value["steps"]
    if not isinstance(steps, list) or not 2 <= len(steps) <= 5 \
            or any(not isinstance(step, str) or not step.strip() or len(step) > 140 for step in steps):
        raise ValueError("플로우 단계는 2~5개의 짧은 문장이어야 합니다.")
    return {"template": value["template"], "subjectColumn": value["subjectColumn"],
            "steps": [step.strip() for step in steps]}


def normalize_flows(values, scope, report):
    if not isinstance(values, list) or not 1 <= len(values) <= 3:
        raise ValueError("플로우 후보는 1~3개여야 합니다.")
    result = []
    seen = set()
    for value in values:
        flow = normalize_flow(value, scope, report)
        if flow["template"] in seen:
            raise ValueError("같은 플로우 템플릿을 중복 제안할 수 없습니다.")
        seen.add(flow["template"])
        result.append(flow)
    return result


def normalize_proposal(value, report):
    if not isinstance(value, dict) or set(value) != {"serviceSummary", "userFlows", "adminFlows"}:
        raise ValueError("서비스 제안 형식이 올바르지 않습니다.")
    summary = value["serviceSummary"]
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 180:
        raise ValueError("서비스 한 줄 요약이 올바르지 않습니다.")
    return {"service_summary": summary.strip(),
            "user_flows": normalize_flows(value["userFlows"], "user", report),
            "admin_flows": normalize_flows(value["adminFlows"], "admin", report)}


def flow_options(upload):
    result = {"user": [], "admin": []}
    calls = ModelCall.objects.filter(upload=upload, status=ModelCall.Status.SUCCEEDED).order_by("-started_at")
    for call in calls:
        if not isinstance(call.parsed_result, dict):
            continue
        for scope in ("user", "admin"):
            for index, value in enumerate(call.parsed_result.get(f"{scope}_flows", [])):
                try:
                    flow = normalize_flow(value, scope, upload.analysis)
                except ValueError:
                    continue
                result[scope].append({"model_call_id": str(call.id), "index": index, **flow})
    return result


def selected_config(user, admin):
    if COMPATIBLE[user["template"]] != admin["template"]:
        raise ValueError("선택한 유저·관리자 플로우가 서로 맞지 않습니다.")
    return {"version": 1,
            "user": {"template": user["template"], "subjectColumn": user["subjectColumn"],
                     "steps": user["steps"]},
            "admin": {"template": admin["template"], "subjectColumn": admin["subjectColumn"],
                      "steps": admin["steps"]}}


def custom_request_body(report, scope, description):
    if scope not in FLOW_TEMPLATES:
        raise ValueError("유저 또는 관리자 플로우를 선택해 주세요.")
    if not isinstance(description, str) or not 10 <= len(description.strip()) <= MAX_DESCRIPTION:
        raise ValueError("원하는 흐름을 10~500자로 설명해 주세요.")
    columns = [{"number": number, "name": column["name"][:160], "type": column["candidate"]}
               for number, column in enumerate(report["columns"], 1)]
    content = {"scope": scope, "user_description": description.strip(), "columns": columns,
               "row_count": report["row_count"]}
    schema = {"type": "object", "properties": {
        "version": {"type": "integer", "enum": [1]}, "flow": flow_schema(scope, report),
    }, "required": ["version", "flow"], "additionalProperties": False}
    return {
        "model": getattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-5") or "claude-sonnet-5",
        "max_tokens": 600,
        "system": ("Choose one supported flow template matching the user's request. "
                   "A CSV is one table, so do not claim that applications already exist. "
                   "Requests are a new entity when the template supports them. "
                   "Return JSON only; never generate code, SQL, or unsupported actions."),
        "messages": [{"role": "user", "content": json_text(content)}],
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
    }


def custom_fingerprint(body):
    return hashlib.sha256(json_text(body).encode("utf-8")).hexdigest()


def custom_approval_summary(upload, scope, description):
    body = custom_request_body(upload.analysis, scope, description)
    request_bytes = len(json_text(body).encode("utf-8"))
    if body["model"] == "claude-sonnet-5":
        low = (request_bytes / 3 * 2 + body["max_tokens"] * 10) / 1_000_000
        high = (request_bytes * 0.75 * 2 + body["max_tokens"] * 10) / 1_000_000
        cost_note = f"예상 비용(출력 600토큰 가정): 약 US${low:.3f}~${high:.3f}. 실제 사용량에 따라 달라집니다."
        priced = True
    else:
        cost_note = "모델 단가를 확인할 수 없어 예상 비용을 계산하지 못했습니다."
        priced = False
    return {
        "purpose": f"사용자가 설명한 {scope} 흐름을 지원되는 템플릿 하나로 제안",
        "model": body["model"], "planned_call_count": 1, "automatic_retries": 0,
        "max_output_tokens": body["max_tokens"], "request_fingerprint": custom_fingerprint(body),
        "transmitted_data": {"user_description": description.strip(),
                             "column_names_and_types": [column["name"][:160] for column in upload.analysis["columns"]],
                             "row_count": upload.analysis["row_count"], "sample_rows": 0,
                             "original_csv_file": False, "request_bytes": request_bytes},
        "cost_note": cost_note, "pricing_estimate_available": priced,
    }


def parse_custom_response(raw, scope, report):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 8_000:
        raise ValueError("플로우 응답이 너무 깁니다.")
    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("중복된 플로우 응답 항목이 있습니다.")
            value[key] = item
        return value
    def invalid_constant(_):
        raise ValueError("유효하지 않은 숫자입니다.")
    value = json.loads(raw, object_pairs_hook=unique_object,
                       parse_constant=invalid_constant)
    if not isinstance(value, dict) or set(value) != {"version", "flow"} or type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("플로우 응답 형식이 올바르지 않습니다.")
    return normalize_flow(value["flow"], scope, report)


def run_custom_suggestion(upload, scope, description, approval_note, approved_at):
    """Exactly one network call, only after the caller checks explicit approval."""
    from .call_records import finish_call, start_call
    from .claude import _extract_text, _post_message

    body = custom_request_body(upload.analysis, scope, description)
    call = start_call(upload=upload, purpose=f"{scope} 맞춤 플로우 후보 제안", request_body=body,
                      approval_note=approval_note, approved_at=approved_at)
    response_text = ""
    http_status = None
    headers = {}
    usage = {}
    try:
        http_status, headers, response_text = _post_message(body)
        provider = json.loads(response_text)
        usage = provider.get("usage", {})
        if not 200 <= http_status < 300:
            raise InferenceError("Claude API 호출이 실패했습니다.")
        flow = parse_custom_response(_extract_text(provider), scope, upload.analysis)
        finish_call(call, status=ModelCall.Status.SUCCEEDED, response_body=response_text,
                    http_status=http_status, provider_request_id=headers.get("request-id", ""),
                    parsed_result={f"{scope}_flows": [flow]}, usage=usage)
        return call, flow
    except (ValueError, InferenceError) as exc:
        if ModelCall.objects.filter(pk=call.pk, status=ModelCall.Status.STARTED).exists():
            finish_call(call, status=ModelCall.Status.FAILED, response_body=response_text,
                        http_status=http_status, provider_request_id=headers.get("request-id", ""),
                        usage=usage, error_type=exc.__class__.__name__, error_message=str(exc))
        raise
