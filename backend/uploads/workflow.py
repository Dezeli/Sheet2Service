"""Finite user/admin flow templates and offline model-output validation."""

import hashlib
import json

from django.conf import settings

from .inference import InferenceError, json_text
from .models import ModelCall
from .template_registry import IMPLEMENTED, PLANNED, REGISTRY, TEMPLATES, describe


FLOW_TEMPLATES = {
    "user": tuple(item["user_template"] for item in IMPLEMENTED),
    "admin": tuple(item["admin_template"] for item in IMPLEMENTED),
}
COMPATIBLE = {item["user_template"]: item["admin_template"] for item in IMPLEMENTED}
MAX_DESCRIPTION = 500


def subject_columns(report):
    populated = [index for index, column in enumerate(report["columns"], 1)
                 if column["non_empty_count"] > 0]
    return populated or list(range(1, len(report["columns"]) + 1))


def flow_schema(scope, report):
    schema = {
        "type": "object",
        "properties": {
            "template": {"type": "string", "enum": list(FLOW_TEMPLATES[scope])},
            "subjectColumn": {"type": "integer", "enum": [0, *subject_columns(report)]},
            "steps": {"type": "array", "items": {"type": "string"}},
            "titles": {"type": "object", "properties": {
                "user": {"type": "string"}, "admin": {"type": "string"}},
                "required": ["user", "admin"], "additionalProperties": False},
        },
        "required": ["template", "subjectColumn", "steps", "titles"],
        "additionalProperties": False,
    }
    # Keep one grammar branch; normalize_flow enforces that only inquiries
    # may use column zero. Duplicating titles across anyOf branches multiplies
    # the provider's compiled structured-output grammar.
    return schema


def normalize_flow(value, scope, report):
    if not isinstance(value, dict) or not {"template", "subjectColumn", "steps"} <= set(value) \
            or set(value) - {"template", "subjectColumn", "steps", "titles"}:
        raise ValueError("플로우 후보 형식이 올바르지 않습니다.")
    titles = value.get("titles")
    if titles is not None:
        if not isinstance(titles, dict) or set(titles) != {"user", "admin"} \
                or any(not isinstance(title, str) or not title.strip() or len(title.strip()) > 48
                       or '\n' in title or '\r' in title for title in titles.values()):
            raise ValueError("기능 제목은 대상과 동작을 명확히 담은 48자 이내 한 줄이어야 합니다.")
        titles = {role: title.strip() for role, title in titles.items()}
    allowed_columns = subject_columns(report)
    if value["template"] in ("inquiry", "reply_inquiries"):
        allowed_columns = [0, *allowed_columns]
    if value["template"] not in FLOW_TEMPLATES[scope] or type(value["subjectColumn"]) is not int \
            or value["subjectColumn"] not in allowed_columns:
        raise ValueError("지원하지 않는 플로우 후보입니다.")
    steps = value["steps"]
    if not isinstance(steps, list) or not 2 <= len(steps) <= 5 \
            or any(not isinstance(step, str) or not step.strip() or len(step) > 140 for step in steps):
        raise ValueError("플로우 단계는 2~5개의 짧은 문장이어야 합니다.")
    if value["template"] == "inquiry":
        steps = ["문의 작성·제출", "내 문의 상태·답변 확인"]
    elif value["template"] == "reply_inquiries":
        steps = ["문의 조회", "답변 작성·처리 상태 변경"]
    elif value["template"] == "request_review":
        steps = ["항목 선택·신청 내용 제출", "승인·거절 결과 확인", "처리 상태 조회·처리 전 취소"]
    elif value["template"] == "request_auto":
        steps = ["항목 선택·접수 내용 제출", "접수·처리 상태 조회", "처리 전 취소"]
    elif value["template"] == "review_requests":
        steps = ["신청 내용 확인", "승인·거절 및 사유 입력", "처리 시작·완료"]
    elif value["template"] == "monitor_requests":
        steps = ["접수 내용 확인", "처리 시작·완료 및 메모 입력"]
    elif value["template"] == "browse_only":
        steps = ["항목 목록 조회", "항목 정보 확인"]
    elif value["template"] == "manage_catalog":
        steps = ["목록 데이터 관리", "필드·선택지 관리"]
    elif value["template"] == "reservation":
        steps = ["시간·잔여 정원 조회", "예약·내 예약 확인·시작 전 취소"]
    elif value["template"] == "manage_reservations":
        steps = ["예약 일정·정원 설정", "접수 마감·예약 내역 관리"]
    elif value["template"] == "notice":
        steps = ["게시된 공지 목록 조회", "공지 내용 확인"]
    elif value["template"] == "manage_notices":
        steps = ["공지 작성·수정", "게시·게시 해제"]
    elif value["template"] == "rental":
        steps = ["항목·수량 선택·대여 신청", "내 상태 확인·대여 시작 전 취소"]
    elif value["template"] == "manage_rentals":
        steps = ["항목별 재고 설정·승인·거절", "대여 시작·전량 반납 처리"]
    elif value["template"] == "quote":
        steps = ["항목·요청 조건 제출", "견적 확인·수락·거절·진행 상태 조회"]
    elif value["template"] == "manage_quotes":
        steps = ["견적 초안 작성·전달·요청 거절", "수락 후 진행·완료 처리"]
    return {"template": value["template"], "subjectColumn": value["subjectColumn"],
            "steps": [step.strip() for step in steps], **({"titles": titles} if titles else {})}


def normalize_flows(values, scope, report):
    if not isinstance(values, list) or not 1 <= len(values) <= len(FLOW_TEMPLATES[scope]):
        raise ValueError("기능 후보는 등록된 템플릿 수 이내여야 합니다.")
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
    if not isinstance(value, dict) or not {"serviceSummary", "userFlows", "adminFlows"} <= set(value) \
            or set(value) - {"serviceSummary", "serviceSubject", "userFlows", "adminFlows"}:
        raise ValueError("서비스 제안 형식이 올바르지 않습니다.")
    summary = value["serviceSummary"]
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 600:
        raise ValueError("서비스 요약은 600자 이내여야 합니다.")
    subject = value.get("serviceSubject", "")
    if not isinstance(subject, str) or len(subject.strip()) > 24 or '\n' in subject or '\r' in subject \
            or ("serviceSubject" in value and not subject.strip()):
        raise ValueError("서비스 대상은 24자 이내 한 줄이어야 합니다.")
    return {"service_summary": summary.strip(), "service_subject": subject.strip(),
            "user_flows": normalize_flows(value["userFlows"], "user", report),
            "admin_flows": normalize_flows(value["adminFlows"], "admin", report)}


def builtin_options(upload):
    result = {"user": [], "admin": []}
    for scope, template in (("user", "inquiry"), ("admin", "reply_inquiries")):
        flow = normalize_flow({"template": template, "subjectColumn": 0,
                               "steps": ["문의", "처리"]}, scope, upload.analysis)
        result[scope].append({"model_call_id": "builtin:inquiry", "index": 0, **flow})
    for scope, templates in (("user", ("request_review", "request_auto")),
                             ("admin", ("review_requests", "monitor_requests"))):
        for index, template in enumerate(templates):
            flow = normalize_flow({"template": template, "subjectColumn": subject_columns(upload.analysis)[0],
                                   "steps": ["Submit", "Process"]}, scope, upload.analysis)
            result[scope].append({"model_call_id": "builtin:reception", "index": index, **flow})
    for scope, template in (("user", "browse_only"), ("admin", "manage_catalog")):
        flow = normalize_flow({"template": template, "subjectColumn": subject_columns(upload.analysis)[0],
                               "steps": ["Browse", "Manage"]}, scope, upload.analysis)
        result[scope].append({"model_call_id": "builtin:catalog", "index": 0, **flow})
    return result


def recommended_options(upload):
    """Latest complete proposal plus newer custom proposals; no historical accumulation."""
    result = {"user": [], "admin": []}
    found_custom = set()
    calls = ModelCall.objects.filter(upload=upload, status=ModelCall.Status.SUCCEEDED).order_by("-started_at", "-id")
    for call in calls:
        parsed = call.parsed_result
        if not isinstance(parsed, dict):
            continue
        complete = bool(parsed.get("user_flows")) and bool(parsed.get("admin_flows"))
        for scope in ("user", "admin"):
            if scope in found_custom:
                continue
            flows = []
            seen = set()
            for index, value in enumerate(parsed.get(f"{scope}_flows", [])[:len(FLOW_TEMPLATES[scope])]):
                try:
                    flow = normalize_flow(value, scope, upload.analysis)
                except ValueError:
                    continue
                if flow["template"] not in seen:
                    flows.append({"model_call_id": str(call.id), "index": index, "custom": not complete, **flow})
                    seen.add(flow["template"])
            if flows:
                result[scope] = flows
                if not complete:
                    found_custom.add(scope)
        if complete:
            break
    return result


def flow_options(upload):
    return recommended_options(upload)


def module_from_flow(flow, scope, report):
    """A chosen feature always includes its deterministic counterpart."""
    if scope == "user":
        user = flow
        admin = normalize_flow({"template": COMPATIBLE[flow["template"]],
                                "subjectColumn": flow["subjectColumn"], "steps": ["View", "Process"],
                                **({"titles": flow["titles"]} if flow.get("titles") else {})}, "admin", report)
    else:
        admin = flow
        template = next(user for user, admin in COMPATIBLE.items() if admin == flow["template"])
        user = normalize_flow({"template": template, "subjectColumn": flow["subjectColumn"],
                               "steps": ["View", "Submit"],
                               **({"titles": flow["titles"]} if flow.get("titles") else {})}, "user", report)
    return selected_config(user, admin)


def feature_catalog(upload):
    subject = ""
    for call in ModelCall.objects.filter(upload=upload, status=ModelCall.Status.SUCCEEDED).order_by("-started_at", "-id"):
        if isinstance(call.parsed_result, dict) and call.parsed_result.get("service_subject"):
            subject = call.parsed_result["service_subject"]
            break
    def labels(template):
        metadata = describe(template)
        if subject:
            metadata["user_title"] = f'{subject} {metadata["user_title"]}'
            metadata["admin_title"] = f'{subject} {metadata["admin_title"]}'
        return metadata
    recommended = []
    seen = set()
    options = [(scope, option) for scope, items in recommended_options(upload).items() for option in items]
    options.sort(key=lambda pair: not pair[1]["custom"])
    for scope, option in options:
        module = module_from_flow(option, scope, upload.analysis)
        template = module["user"]["template"]
        if template in seen:
            continue
        seen.add(template)
        recommended.append({"template": template, **labels(template),
            **({"user_title": option["titles"]["user"], "admin_title": option["titles"]["admin"]} if option.get("titles") else {}),
            "user": module["user"], "admin": module["admin"],
            "reference": {"scope": scope, "model_call_id": option["model_call_id"], "index": option["index"]}})
    return {"recommended": recommended, "templates": [], "service_subject": subject,
            "data_title": f"{subject} 데이터 관리".strip()}


def workflow_modules(config):
    if not isinstance(config, dict) or config.get("version") != 1:
        return []
    return config.get("modules", [config])


def workflow_module(config, templates):
    return next((module for module in workflow_modules(config)
                 if module.get("user", {}).get("template") in templates), None)


def selected_config(user, admin):
    if COMPATIBLE[user["template"]] != admin["template"]:
        raise ValueError("선택한 유저·관리자 플로우가 서로 맞지 않습니다.")
    if user["template"] == "inquiry":
        admin = {**admin, "subjectColumn": user["subjectColumn"]}
    config = {"version": 1,
            "user": {"template": user["template"], "subjectColumn": user["subjectColumn"],
                     "steps": user["steps"]},
            "admin": {"template": admin["template"], "subjectColumn": admin["subjectColumn"],
                      "steps": admin["steps"]}}
    if user["template"] in ("request_review", "request_auto"):
        config["reception"] = {"template": "reception",
                               "approval": "required" if user["template"] == "request_review" else "none"}
    for scope, flow in (("user", user), ("admin", admin)):
        if flow.get("titles"):
            config[scope]["title"] = flow["titles"][scope]
    return config


def custom_request_body(report, scope, description):
    if scope not in FLOW_TEMPLATES:
        raise ValueError("유저 또는 관리자 플로우를 선택해 주세요.")
    if not isinstance(description, str) or not 10 <= len(description.strip()) <= MAX_DESCRIPTION:
        raise ValueError("원하는 흐름을 10~500자로 설명해 주세요.")
    columns = [{"number": number, "name": column["name"][:160], "type": column["candidate"]}
               for number, column in enumerate(report["columns"], 1)]
    content = {"scope": scope, "user_description": description.strip(), "columns": columns,
               "row_count": report["row_count"], "template_registry": list(TEMPLATES)}
    def outcome(properties):
        return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
    schema = {"type": "object", "properties": {
        "version": {"type": "integer", "enum": [1]}, "result": {"anyOf": [
            outcome({"status": {"type": "string", "enum": ["supported"]}, "flow": flow_schema(scope, report)}),
            outcome({"status": {"type": "string", "enum": ["unimplemented"]},
                     "template": {"type": "string", "enum": list(PLANNED)}}),
            outcome({"status": {"type": "string", "enum": ["unsupported"]}}),
        ]},
    }, "required": ["version", "result"], "additionalProperties": False}
    return {
        "model": getattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-5") or "claude-sonnet-5",
        "max_tokens": 600,
        "system": ("Classify the entire user's feature request against the provided template_registry. "
                   "Return supported only if the complete request fits an implemented template's stated capabilities. "
                   "Provide titles.user and titles.admin as concise one-line labels including the actual subject and action inferred from CSV columns or the user's description. "
                   "For example: 체육시설 이용 신청 / 체육시설 신청 승인, 상품 문의 접수 / 상품 문의 답변. Never use a vague 이용 신청 label alone or invent a domain. Keep each title within 48 characters. "
                   "Return unimplemented for a matching planned template, or unsupported if no registry template can fulfill it. "
                   "Do not substitute an approximate implemented template that omits requested capabilities. "
                   "Simple reservation applications can use request_review; time-slot, capacity and conflict enforcement requires reservation. "
                   "reservation/manage_reservations is implemented: admin creates future non-overlapping slots per CSV item, changes capacity or closes booking; "
                   "users view remaining capacity, book one seat, view own reservations and cancel before start. "
                   "Capacity overflow and overlapping bookings by the same user are rejected. Recurrence, booking approval and waitlists are unimplemented. "
                   "notice/manage_notices supports separate plain-text announcements: admin creates and edits title/body, publishes or unpublishes; "
                   "users see only published notices. Scheduled publication, attachments and notifications are unsupported. "
                   "rental/manage_rentals supports per-item integer stock, quantity requests, approval/rejection, handover and full return. "
                   "Requests do not hold stock; approval reserves stock, cancellation before handover or full return releases it. "
                   "Users view own status and cancel before handover; admins set stock and intake, manage lifecycle and processing notes. "
                   "Rental dates, partial returns, fees, deposits and payments are unsupported. "
                   "quote/manage_quotes supports per-item conditions, manually drafted amount/currency/proposal, sending an immutable offer, "
                   "user acceptance/decline/cancellation before work starts, and admin start/completion after acceptance. "
                   "Supported currencies are KRW/USD/EUR/JPY; no conversion, automatic pricing, offer revision after sending, or payment. "
                   "Payments, notifications, attachments and custom form fields are unsupported. "
                   "A CSV is one table, so do not claim that applications already exist. "
                   "Requests are a new entity when the template supports them. "
                   "inquiry/reply_inquiries supports title and body submission, own inquiry and answer lookup, "
                   "admin answers, and received/in_progress/resolved states only. "
                   "subjectColumn 0 means general inquiry; positive columns optionally link a catalog item. "
                   "Only inquiry/reply_inquiries may use subjectColumn 0; all other templates require a permitted positive CSV column number. "
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
        "purpose": "추가 기능 요청을 등록된 템플릿과 비교해 지원·미구현·미지원 여부를 확인",
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
    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1:
        raise ValueError("플로우 응답 형식이 올바르지 않습니다.")
    # Accept the prior format for stored fixtures and in-flight requests.
    if set(value) == {"version", "flow"}:
        result = {"status": "supported", "flow": normalize_flow(value["flow"], scope, report)}
    elif set(value) == {"version", "result"} and isinstance(value["result"], dict):
        result = value["result"]
    else:
        raise ValueError("기능 응답 형식이 올바르지 않습니다.")
    status = result.get("status")
    if status == "supported" and set(result) == {"status", "flow"}:
        result = {"status": status, "flow": normalize_flow(result["flow"], scope, report)}
        template = result["flow"]["template"]
        if scope == "admin":
            template = next(user for user, admin in COMPATIBLE.items() if admin == template)
        result["template"] = template
        result["message"] = f'{REGISTRY[template]["name"]} 기능을 추가할 수 있습니다.'
    elif status == "unimplemented" and set(result) == {"status", "template"} and result["template"] in PLANNED:
        result = {**result, "message": f'{REGISTRY[result["template"]]["name"]} 기능은 아직 미구현이라 선택할 수 없습니다.'}
    elif status == "unsupported" and set(result) == {"status"}:
        result = {"status": status, "message": "현재 지원하는 템플릿으로는 이 기능을 제공할 수 없습니다."}
    else:
        raise ValueError("등록된 템플릿의 구현 상태와 맞지 않는 응답입니다.")
    return result


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
        result = parse_custom_response(_extract_text(provider), scope, upload.analysis)
        parsed = {"custom_result": result}
        if result["status"] == "supported":
            parsed[f"{scope}_flows"] = [result["flow"]]
        finish_call(call, status=ModelCall.Status.SUCCEEDED, response_body=response_text,
                    http_status=http_status, provider_request_id=headers.get("request-id", ""),
                    parsed_result=parsed, usage=usage)
        return call, result
    except (ValueError, InferenceError) as exc:
        if ModelCall.objects.filter(pk=call.pk, status=ModelCall.Status.STARTED).exists():
            finish_call(call, status=ModelCall.Status.FAILED, response_body=response_text,
                        http_status=http_status, provider_request_id=headers.get("request-id", ""),
                        usage=usage, error_type=exc.__class__.__name__, error_message=str(exc))
        raise
