"""Explicitly approved, single-call source drafting; generated code is never executed."""

import json

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .call_records import finish_call, start_call
from .claude import _extract_text, _post_message
from .component_drafts import draft_request_body, validate_component_draft
from .component_recovery import revalidate_failed_component_call
from .inference import InferenceError
from .models import ComponentCandidate, ComponentDraft, ComponentMatch, ModelCall
from .service_blueprint import _parse_json
from .service_blueprint_request import fingerprint
from .views import SessionView, owned


def _candidate(upload, value):
    try:
        candidate_id = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"detail": "부품 후보 번호가 올바르지 않습니다."}) from exc
    candidate = get_object_or_404(ComponentCandidate, pk=candidate_id)
    match = ComponentMatch.objects.filter(
        upload=upload, candidate=candidate, model_call__isnull=False
    ).select_related("model_call").first()
    if match is None:
        raise Http404
    call = match.model_call
    result = call.parsed_result if call.status == ModelCall.Status.SUCCEEDED \
        else revalidate_failed_component_call(call)
    for reference in result.get("candidates", []):
        if reference.get("id") == candidate.pk:
            index = reference.get("plan_index")
            if isinstance(index, int) and 0 <= index < len(result.get("plans", [])):
                return candidate, result["plans"][index]
    for plan in result.get("plans", []):
        required = sorted(plan["knownCapabilities"] + (["request.unclassified"] if plan["newRequirement"].strip() else []))
        if plan["surface"] == match.surface and required == match.requested_capabilities:
            return candidate, plan
    raise Http404


def _existing(upload, candidate):
    return ComponentDraft.objects.filter(upload=upload, candidate=candidate).first()


def _response(draft, *, already_generated):
    return {"id": str(draft.pk), "candidate_id": draft.candidate_id,
            "status": draft.status, "content": draft.content,
            "already_generated": already_generated}


class ComponentCandidatesView(SessionView):
    def get(self, request, pk):
        upload = owned(request, pk)
        matches = ComponentMatch.objects.filter(upload=upload, candidate__isnull=False)
        ids = sorted(set(matches.values_list("candidate_id", flat=True)))
        candidates = ComponentCandidate.objects.filter(pk__in=ids).order_by("pk")
        return Response({"items": [{"id": item.pk, "surface": item.surface,
                                    "capabilities": item.capabilities, "decision": item.decision}
                                   for item in candidates]})


class ComponentDraftApprovalView(SessionView):
    parser_classes = [JSONParser]

    def post(self, request, pk):
        upload = owned(request, pk)
        candidate, source_plan = _candidate(upload, request.data.get("candidate_id") if isinstance(request.data, dict) else None)
        existing = _existing(upload, candidate)
        if existing:
            return Response({"already_generated": True, "draft": _response(existing, already_generated=True)})
        try:
            body = draft_request_body(candidate, source_plan=source_plan)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response({"purpose": "미구현 부품의 실행 전 소스 초안 생성",
                         "transmitted_data": "부품 후보의 기능·미등록 요구·짧은 판단 근거와 관련 후보 ID·기능 메타데이터",
                         "original_csv_file": False, "planned_call_count": 1, "automatic_retries": 0,
                         "model": body["model"], "request_fingerprint": fingerprint(body),
                         "already_generated": False})


class ComponentDraftGenerateView(SessionView):
    parser_classes = [JSONParser]

    def post(self, request, pk):
        upload = owned(request, pk)
        candidate, source_plan = _candidate(upload, request.data.get("candidate_id") if isinstance(request.data, dict) else None)
        existing = _existing(upload, candidate)
        if existing:
            return Response(_response(existing, already_generated=True))
        try:
            body = draft_request_body(candidate, source_plan=source_plan)
            if request.data.get("approved") is not True \
                    or request.data.get("request_fingerprint") != fingerprint(body) \
                    or not isinstance(request.data.get("approval_note"), str) \
                    or not request.data["approval_note"].strip():
                raise ValueError("전송 내용과 Claude 1회 호출 안내를 확인해 주세요.")
            call = start_call(upload=upload, purpose="미구현 부품 소스 초안 생성",
                              request_body=body, approval_note=request.data["approval_note"],
                              approved_at=timezone.now())
            response_text = ""
            status = None
            headers = {}
            usage = {}
            try:
                status, headers, response_text = _post_message(body)
                provider = json.loads(response_text)
                if not isinstance(provider, dict):
                    raise ValueError("Claude 응답 형식이 올바르지 않습니다.")
                usage = provider.get("usage", {})
                if not 200 <= status < 300:
                    raise InferenceError("Claude API 요청이 실패했습니다.")
                if provider.get("stop_reason") == "max_tokens":
                    raise ValueError("Claude 응답이 길이 제한으로 중단되었습니다.")
                raw = _extract_text(provider)
                content = validate_component_draft(_parse_json(raw, max_bytes=120_000), candidate)
                with transaction.atomic():
                    finish_call(call, status=ModelCall.Status.SUCCEEDED, response_body=response_text,
                                http_status=status, provider_request_id=headers.get("request-id", ""),
                                parsed_result=content, usage=usage)
                    draft = ComponentDraft.objects.create(
                        candidate=candidate, upload=upload, model_call=call,
                        status=content["status"], content=content)
                return Response(_response(draft, already_generated=False))
            except (ValueError, InferenceError) as exc:
                if ModelCall.objects.filter(pk=call.pk, status=ModelCall.Status.STARTED).exists():
                    finish_call(call, status=ModelCall.Status.FAILED, response_body=response_text,
                                http_status=status, provider_request_id=headers.get("request-id", ""),
                                usage=usage, error_type=type(exc).__name__, error_message=str(exc))
                raise
        except (ValueError, InferenceError) as exc:
            raise ValidationError({"detail": str(exc)}) from exc
