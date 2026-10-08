"""Review and apply a finite pair of user/admin flows for one uploaded service."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .models import ModelCall
from .inference import InferenceError
from .views import SessionView, owned
from .workflow import (custom_approval_summary, custom_fingerprint, custom_request_body,
                       flow_options, normalize_flow, run_custom_suggestion, selected_config)


def _selected(upload, reference, scope):
    if not isinstance(reference, dict) or set(reference) != {"model_call_id", "index"}:
        raise ValidationError({"detail": "선택한 플로우 후보가 올바르지 않습니다."})
    index = reference["index"]
    if type(index) is not int or index < 0 or index > 2:
        raise ValidationError({"detail": "선택한 플로우 번호가 올바르지 않습니다."})
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
        for call in ModelCall.objects.filter(upload=upload, status=ModelCall.Status.SUCCEEDED).order_by("-started_at"):
            if isinstance(call.parsed_result, dict) and call.parsed_result.get("service_summary"):
                summary = call.parsed_result["service_summary"]
                break
        return Response({"service_summary": summary, "options": flow_options(upload),
                         "selected": upload.workflow_config})

    def post(self, request, pk):
        upload = owned(request, pk)
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "플로우 선택 형식이 올바르지 않습니다."})
        user = _selected(upload, request.data.get("user"), "user")
        admin = _selected(upload, request.data.get("admin"), "admin")
        try:
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
            call, flow = run_custom_suggestion(upload, scope, description, approval_note, timezone.now())
        except (ValueError, InferenceError) as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response({"model_call_id": str(call.id), "flow": flow, "usage": call.usage})
