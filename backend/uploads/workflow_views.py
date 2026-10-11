"""Review and apply a finite pair of user/admin flows for one uploaded service."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .models import ModelCall
from .template_registry import DASHBOARD, IMPLEMENTED
from .inference import InferenceError
from .views import SessionView, owned
from .workflow import (custom_approval_summary, custom_fingerprint, custom_request_body,
                       builtin_options, feature_catalog, flow_options, module_from_flow,
                       normalize_flow, run_custom_suggestion, selected_config)


def _selected(upload, reference, scope):
    if not isinstance(reference, dict) or set(reference) != {"model_call_id", "index"}:
        raise ValidationError({"detail": "선택한 플로우 후보가 올바르지 않습니다."})
    index = reference["index"]
    if type(index) is not int or index < 0 or index >= len(IMPLEMENTED):
        raise ValidationError({"detail": "선택한 플로우 번호가 올바르지 않습니다."})
    if reference["model_call_id"] == "builtin:inquiry" and index == 0:
        return next(option for option in builtin_options(upload)[scope]
                    if option["model_call_id"] == "builtin:inquiry")
    if reference["model_call_id"] == "builtin:reception" and index in (0, 1):
        return next(option for option in builtin_options(upload)[scope]
                    if option["model_call_id"] == "builtin:reception" and option["index"] == index)
    if reference["model_call_id"] == "builtin:catalog" and index == 0:
        return next(option for option in builtin_options(upload)[scope]
                    if option["model_call_id"] == "builtin:catalog")
    try:
        call = ModelCall.objects.get(pk=reference["model_call_id"], upload=upload,
                                     status=ModelCall.Status.SUCCEEDED)
        value = call.parsed_result[f"{scope}_flows"][index]
        return normalize_flow(value, scope, upload.analysis)
    except (ModelCall.DoesNotExist, DjangoValidationError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValidationError({"detail": "선택한 플로우 후보를 찾을 수 없습니다."}) from exc


class WorkflowView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = owned(request, pk)
        summary = ""
        generation_warning = ""
        latest = ModelCall.objects.filter(upload=upload, status=ModelCall.Status.SUCCEEDED).order_by("-started_at").first()
        if latest and isinstance(latest.parsed_result, dict) and latest.parsed_result.get("validation_error"):
            generation_warning = "AI 추천을 완성하지 못했습니다. 다시 생성해 주세요."
        for call in ModelCall.objects.filter(upload=upload, status=ModelCall.Status.SUCCEEDED).order_by("-started_at"):
            if isinstance(call.parsed_result, dict) and call.parsed_result.get("service_summary"):
                summary = call.parsed_result["service_summary"]
                break
        catalog = feature_catalog(upload)
        templates = {item["template"] for item in catalog["recommended"]}
        dashboard_ids = {"csv_statistics"} if templates else set()
        if templates & {"request_review", "request_auto"}:
            dashboard_ids.add("request_statistics")
        if "inquiry" in templates:
            dashboard_ids.add("inquiry_statistics")
        return Response({"service_summary": summary, "generation_warning": generation_warning, "options": flow_options(upload),
                         "selected": upload.workflow_config,
                         "dashboard": [item for item in DASHBOARD if item["template"] in dashboard_ids], **catalog})

    def post(self, request, pk):
        upload = owned(request, pk)
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "플로우 선택 형식이 올바르지 않습니다."})
        try:
            if "features" in request.data:
                references = request.data["features"]
                has_roles = "roles" in request.data
                if set(request.data) - {"features", "roles"} or not isinstance(references, list) \
                        or not (0 if has_roles else 1) <= len(references) <= len(IMPLEMENTED):
                    raise ValueError("등록된 서비스 기능을 선택해 주세요.")
                modules = []
                groups = set()
                for reference in references:
                    if not isinstance(reference, dict) or set(reference) != {"scope", "model_call_id", "index"} \
                            or reference["scope"] not in ("user", "admin"):
                        raise ValueError("선택한 기능이 올바르지 않습니다.")
                    flow = _selected(upload, {key: reference[key] for key in ("model_call_id", "index")}, reference["scope"])
                    module = module_from_flow(flow, reference["scope"], upload.analysis)
                    template = module["user"]["template"]
                    group = "reception" if template in ("request_review", "request_auto") else template
                    if group in groups:
                        raise ValueError("같은 기능은 한 번만 선택하고, 접수 모드는 하나만 선택해 주세요.")
                    groups.add(group)
                    module["selection"] = reference
                    modules.append(module)
                config = {**(modules[0] if modules else {"version": 1}), "modules": modules}
                if has_roles:
                    roles = request.data["roles"]
                    if not isinstance(roles, dict) or set(roles) != {"dashboard", "admin"}:
                        raise ValueError("대시보드와 관리자 선택이 올바르지 않습니다.")
                    for scope, allowed in (("dashboard", [item["template"] for item in DASHBOARD]),
                                           ("admin", ["manage_catalog"])):
                        values = roles[scope]
                        if not isinstance(values, list) or any(not isinstance(value, str) or value not in allowed for value in values) \
                                or len(values) != len(set(values)):
                            raise ValueError("지원되는 기능을 중복 없이 선택해 주세요.")
                    if not modules and not roles["dashboard"] and not roles["admin"]:
                        raise ValueError("기능을 하나 이상 선택해 주세요.")
                    config["role_selection"] = {
                        "dashboard": roles["dashboard"],
                        "user": [module["user"]["template"] for module in modules],
                        "admin": [*roles["admin"], *[module["admin"]["template"] for module in modules
                                                    if module["user"]["template"] != "browse_only"]],
                    }
            else:
                user = _selected(upload, request.data.get("user"), "user")
                admin = _selected(upload, request.data.get("admin"), "admin")
                config = selected_config(user, admin)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        upload.workflow_config = config
        upload.save(update_fields=["workflow_config"])
        return Response({"selected": config})


class CustomFlowPreviewView(SessionView):
    parser_classes = [JSONParser]

    def post(self, request, pk):
        upload = owned(request, pk)
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "설명 형식이 올바르지 않습니다."})
        try:
            summary = custom_approval_summary(upload, request.data.get("scope"),
                                               request.data.get("description"))
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(summary)


class CustomFlowRunView(SessionView):
    parser_classes = [JSONParser]

    def post(self, request, pk):
        upload = owned(request, pk)
        if not isinstance(request.data, dict) or request.data.get("approved") is not True:
            raise ValidationError({"detail": "Claude API 호출에는 명시적인 승인이 필요합니다."})
        scope = request.data.get("scope")
        description = request.data.get("description")
        approval_note = request.data.get("approval_note")
        if not isinstance(approval_note, str) or not approval_note.strip():
            raise ValidationError({"detail": "승인 기록이 필요합니다."})
        try:
            body = custom_request_body(upload.analysis, scope, description)
            summary = custom_approval_summary(upload, scope, description)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        if request.data.get("request_fingerprint") != custom_fingerprint(body) or not summary["pricing_estimate_available"]:
            raise ValidationError({"detail": "전송 내용을 다시 확인하고 승인해 주세요."})
        try:
            call, result = run_custom_suggestion(upload, scope, description, approval_note, timezone.now())
        except (ValueError, InferenceError) as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response({"model_call_id": str(call.id), "flow": result.get("flow"), "result": result, "usage": call.usage})
