"""Finite user/admin flow templates and offline model-output validation."""

from .models import ModelCall
from .template_registry import DASHBOARD, IMPLEMENTED, describe


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


def auto_config(upload):
    """Every recommended feature, one reception mode, data management and matching dashboards."""
    modules = []
    groups = set()
    for option in feature_catalog(upload)["recommended"]:
        group = "reception" if option["template"] in ("request_review", "request_auto") else option["template"]
        if group in groups:
            continue
        groups.add(group)
        modules.append({**selected_config(option["user"], option["admin"]), "selection": option["reference"]})
    templates = {module["user"]["template"] for module in modules}
    dashboard = ["csv_statistics"]
    if templates & {"request_review", "request_auto"}:
        dashboard.append("request_statistics")
    if "inquiry" in templates:
        dashboard.append("inquiry_statistics")
    return {**(modules[0] if modules else {"version": 1}), "modules": modules,
            "role_selection": {"dashboard": [item["template"] for item in DASHBOARD if item["template"] in dashboard],
                               "user": [module["user"]["template"] for module in modules],
                               "admin": ["manage_catalog", *[module["admin"]["template"] for module in modules
                                                            if module["user"]["template"] != "browse_only"]]}}
