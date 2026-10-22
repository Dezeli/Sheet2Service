"""Create, revise and run validated service blueprints for one upload session."""

import json
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .call_records import finish_call, start_call
from .claude import _extract_text, _post_message
from .inference import InferenceError
from .managed import ensure_imported
from .models import BlueprintSubmission, ManagedRow, ModelCall, Upload
from .service_blueprint import BlueprintError, parse_blueprint_response, parse_revision_response
from .service_blueprint_request import approval_summary, fingerprint, request_body
from .views import SessionView, owned


def _run_model(upload, body, *, revision, approval_note):
    """Exactly one provider request. A bad response never changes active config."""
    call = start_call(upload=upload, purpose="서비스 수정" if revision else "조합형 서비스 생성",
                      request_body=body, approval_note=approval_note, approved_at=timezone.now())
    response_text = ""
    http_status = None
    headers = {}
    usage = {}
    try:
        http_status, headers, response_text = _post_message(body)
        provider = json.loads(response_text)
        if not isinstance(provider, dict):
            raise BlueprintError("Claude 응답 형식이 올바르지 않습니다.")
        usage = provider.get("usage", {})
        if not 200 <= http_status < 300:
            raise InferenceError("Claude API 요청이 실패했습니다.")
        if provider.get("stop_reason") == "max_tokens":
            raise BlueprintError("Claude 응답이 길이 제한으로 중단되었습니다.")
        raw = _extract_text(provider)
        result = (parse_revision_response(raw, upload.analysis, upload.service_blueprint)
                  if revision else parse_blueprint_response(raw, upload.analysis))
        finish_call(call, status=ModelCall.Status.SUCCEEDED, response_body=response_text,
                    http_status=http_status, provider_request_id=headers.get("request-id", ""),
                    parsed_result=result, usage=usage)
        return result
    except (ValueError, InferenceError, BlueprintError) as exc:
        if ModelCall.objects.filter(pk=call.pk, status=ModelCall.Status.STARTED).exists():
            finish_call(call, status=ModelCall.Status.FAILED, response_body=response_text,
                        http_status=http_status, provider_request_id=headers.get("request-id", ""),
                        usage=usage, error_type=type(exc).__name__, error_message=str(exc))
        raise


def _approved(request, body):
    if not isinstance(request.data, dict) or request.data.get("approved") is not True \
            or request.data.get("request_fingerprint") != fingerprint(body) \
            or not isinstance(request.data.get("approval_note"), str) \
            or not request.data["approval_note"].strip():
        raise ValidationError({"detail": "전송 내용과 Claude 1회 호출 안내를 확인한 뒤 다시 요청해 주세요."})


class BlueprintApprovalView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = owned(request, pk)
        try:
            return Response(approval_summary(request_body(upload.analysis)))
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

    def post(self, request, pk):
        upload = owned(request, pk)
        if not upload.service_blueprint or not isinstance(request.data, dict):
            raise ValidationError({"detail": "수정할 서비스 설정이 없습니다."})
        try:
            body = request_body(upload.analysis, current=upload.service_blueprint,
                                user_request=request.data.get("request"),
                                current_page=request.data.get("current_page"))
            return Response(approval_summary(body, revision=True))
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc


class BlueprintGenerateView(SessionView):
    parser_classes = [JSONParser]

    def post(self, request, pk):
        upload = owned(request, pk)
        if upload.service_blueprint:
            return Response({"blueprint": upload.service_blueprint, "already_created": True})
        try:
            body = request_body(upload.analysis)
            _approved(request, body)
            result = _run_model(upload, body, revision=False, approval_note=request.data["approval_note"])
        except (ValueError, InferenceError) as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        upload.service_blueprint = result
        upload.save(update_fields=["service_blueprint"])
        return Response({"blueprint": result, "already_created": False})


class BlueprintRevisionView(SessionView):
    parser_classes = [JSONParser]

    def post(self, request, pk):
        upload = owned(request, pk)
        if not upload.service_blueprint:
            raise Http404
        current = upload.service_blueprint
        try:
            body = request_body(upload.analysis, current=current,
                                user_request=request.data.get("request"),
                                current_page=request.data.get("current_page"))
            _approved(request, body)
            result = _run_model(upload, body, revision=True, approval_note=request.data["approval_note"])
        except (ValueError, InferenceError) as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        if result["status"] == "applied":
            with transaction.atomic():
                locked = Upload.objects.select_for_update().get(pk=upload.pk)
                if locked.service_blueprint != current:
                    raise ValidationError({"detail": "다른 수정이 먼저 적용되었습니다. 현재 화면을 새로고침해 주세요."})
                saved_ids = set(BlueprintSubmission.objects.filter(upload=locked).values_list("workflow_id", flat=True))
                new_ids = {flow["id"] for flow in result["blueprint"]["workflows"]}
                if not saved_ids <= new_ids:
                    raise ValidationError({"detail": "이미 신청 내역이 있는 업무는 삭제하거나 ID를 바꿀 수 없습니다."})
                locked.service_blueprint = result["blueprint"]
                locked.save(update_fields=["service_blueprint"])
        return Response(result)


def _workflow(upload, workflow_id):
    if not upload.service_blueprint:
        raise Http404
    return next((item for item in upload.service_blueprint["workflows"] if item["id"] == workflow_id), None)


def _values(workflow, submitted):
    if not isinstance(submitted, dict) or set(submitted) - {field["id"] for field in workflow["fields"]}:
        raise ValidationError({"detail": "입력 필드가 설정과 다릅니다."})
    result = {}
    for field in workflow["fields"]:
        value = submitted.get(field["id"])
        if value in (None, ""):
            if field["required"]:
                raise ValidationError({"detail": f'{field["label"]}을(를) 입력해 주세요.'})
            result[field["id"]] = None
        elif field["type"] == "text":
            if not isinstance(value, str) or len(value) > 5000:
                raise ValidationError({"detail": f'{field["label"]} 값이 올바르지 않습니다.'})
            result[field["id"]] = value
        elif field["type"] == "number":
            try:
                number = Decimal(str(value))
            except (InvalidOperation, ValueError) as exc:
                raise ValidationError({"detail": f'{field["label"]}에 숫자를 입력해 주세요.'}) from exc
            if isinstance(value, bool) or not number.is_finite() or len(str(value)) > 40:
                raise ValidationError({"detail": f'{field["label"]} 값이 올바르지 않습니다.'})
            result[field["id"]] = str(number)
        else:
            try:
                result[field["id"]] = date.fromisoformat(value).isoformat()
            except (TypeError, ValueError) as exc:
                raise ValidationError({"detail": f'{field["label"]}에 날짜를 입력해 주세요.'}) from exc
    return result


def _submission(item):
    return {"id": str(item.id), "workflow_id": item.workflow_id,
            "subject": item.subject_snapshot, "values": item.values, "status": item.status,
            "workflow": item.workflow_snapshot, "created_at": item.created_at.isoformat()}


class BlueprintSubmissionsView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = owned(request, pk)
        if not upload.service_blueprint:
            raise Http404
        workflow = _workflow(upload, request.query_params.get("workflow", ""))
        if not workflow:
            raise ValidationError({"detail": "업무 흐름을 찾을 수 없습니다."})
        role = request.query_params.get("role", "owner")
        if role not in ("owner", "admin"):
            raise ValidationError({"detail": "조회 역할이 올바르지 않습니다."})
        items = BlueprintSubmission.objects.filter(upload=upload, workflow_id=workflow["id"])
        if role == "owner":
            items = items.filter(created_by_session=request.session.session_key)
        return Response({"items": [_submission(item) for item in items[:100]]})

    def post(self, request, pk):
        upload = owned(request, pk)
        ensure_imported(upload)
        if not isinstance(request.data, dict) or set(request.data) != {"workflow_id", "row_id", "values"}:
            raise ValidationError({"detail": "신청 형식이 올바르지 않습니다."})
        workflow = _workflow(upload, request.data["workflow_id"])
        if not workflow:
            raise ValidationError({"detail": "업무 흐름을 찾을 수 없습니다."})
        try:
            row_id = uuid.UUID(str(request.data["row_id"]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValidationError({"detail": "신청할 항목이 올바르지 않습니다."}) from exc
        row = get_object_or_404(ManagedRow, upload=upload, pk=row_id)
        values = _values(workflow, request.data["values"])
        item = BlueprintSubmission.objects.create(
            upload=upload, workflow_id=workflow["id"], subject_row=row,
            subject_snapshot=str(row.values[workflow["subjectColumn"] - 1] or f'항목 {row.row_number}'),
            values=values, status=workflow["initialState"], workflow_snapshot=workflow,
            created_by_session=request.session.session_key)
        return Response(_submission(item), status=201)


class BlueprintRowsView(SessionView):
    def get(self, request, pk):
        upload = owned(request, pk)
        if not upload.service_blueprint:
            raise Http404
        ensure_imported(upload)
        catalog = upload.service_blueprint["catalog"]
        try:
            page = int(request.query_params.get("page", "1"))
        except ValueError as exc:
            raise ValidationError({"detail": "페이지 번호가 올바르지 않습니다."}) from exc
        query = request.query_params.get("q", "").strip()
        if len(query) > 200:
            raise ValidationError({"detail": "검색어는 200자 이하여야 합니다."})
        rows = ManagedRow.objects.filter(upload=upload)
        if query:
            if not catalog["searchColumns"]:
                raise ValidationError({"detail": "이 서비스에는 검색이 설정되지 않았습니다."})
            conditions = Q()
            for number in catalog["searchColumns"]:
                conditions |= Q(**{f"values__{number - 1}__icontains": query})
            rows = rows.filter(conditions)
        raw_column = request.query_params.get("filter_column", "")
        filter_value = request.query_params.get("filter_value", "")
        if raw_column:
            try:
                number = int(raw_column)
            except ValueError as exc:
                raise ValidationError({"detail": "필터 컬럼이 올바르지 않습니다."}) from exc
            if number not in catalog["filterColumns"] or len(filter_value) > 1000:
                raise ValidationError({"detail": "허용되지 않은 필터입니다."})
            if filter_value:
                rows = rows.filter(**{f"values__{number - 1}": filter_value})
        elif filter_value:
            raise ValidationError({"detail": "필터 컬럼을 선택해 주세요."})
        count = rows.count()
        if page < 1 or page > max(1, (count + 19) // 20):
            raise ValidationError({"detail": "페이지 번호가 범위를 벗어났습니다."})
        items = rows.order_by("row_number")[(page - 1) * 20:page * 20]
        return Response({"page": page, "row_count": count,
                         "rows": [{"id": str(row.id), "row_number": row.row_number,
                                   "values": row.values} for row in items]})


class BlueprintSubmissionView(SessionView):
    parser_classes = [JSONParser]

    def patch(self, request, pk, submission_id):
        upload = owned(request, pk)
        if not upload.service_blueprint or not isinstance(request.data, dict) \
                or set(request.data) != {"actor", "to"}:
            raise ValidationError({"detail": "상태 변경 형식이 올바르지 않습니다."})
        actor = request.data["actor"]
        if actor not in ("owner", "admin"):
            raise ValidationError({"detail": "변경 역할이 올바르지 않습니다."})
        with transaction.atomic():
            item = get_object_or_404(BlueprintSubmission.objects.select_for_update(),
                                     upload=upload, pk=submission_id)
            if actor == "owner" and item.created_by_session != request.session.session_key:
                raise ValidationError({"detail": "본인 신청만 변경할 수 있습니다."})
            allowed = any(step["from"] == item.status and step["to"] == request.data["to"]
                          and step["actor"] == actor for step in item.workflow_snapshot["transitions"])
            if not allowed:
                raise ValidationError({"detail": "허용되지 않은 상태 변경입니다."})
            item.status = request.data["to"]
            item.save(update_fields=["status", "updated_at"])
        return Response(_submission(item))
