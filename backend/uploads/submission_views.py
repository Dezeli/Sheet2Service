"""Applications about catalog rows (예약·이용 신청); the status lives on the submission, not in the sheet."""
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .managed import ensure_imported
from .models import BlueprintSubmission, ManagedRow
from .row_workflow import flow_payload
from .views import SessionView, owned


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


def submission_open(workflow, blueprint, row_values):
    """Applications may be gated on the row's own state (e.g. only 접수중 facilities take bookings)."""
    gate = workflow.get("openWhen")
    if not gate:
        return True, ""
    flows = blueprint.get("rowWorkflows", [])
    flow = next((item for item in flows if item["id"] == gate["flow"]), None)
    if flow is None:
        return True, ""
    state = flow_payload(flows, row_values)[flow["id"]]
    if state["kind"] in gate["kinds"]:
        return True, ""
    return False, f'{flow["title"]} 상태가 "{state["state"]}"인 항목은 지금 신청할 수 없습니다.'


def _submission(item):
    return {"id": str(item.id), "workflow_id": item.workflow_id, "subject": item.subject_snapshot,
            "values": item.values, "status": item.status, "workflow": item.workflow_snapshot,
            "created_at": item.created_at.isoformat()}


class BlueprintSubmissionsView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = owned(request, pk)
        workflow = _workflow(upload, request.query_params.get("workflow", ""))
        if not workflow:
            raise ValidationError({"detail": "업무 흐름을 찾을 수 없습니다."})
        role = request.query_params.get("role", "owner")
        if role not in ("owner", "admin"):
            raise ValidationError({"detail": "조회 역할이 올바르지 않습니다."})
        items = BlueprintSubmission.objects.filter(upload=upload, workflow_id=workflow["id"])
        if role == "owner":
            items = items.filter(created_by_session=request.session.session_key or "")
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
        allowed, reason = submission_open(workflow, upload.service_blueprint, row.values)
        if not allowed:
            raise ValidationError({"detail": reason})
        values = _values(workflow, request.data["values"])
        if not request.session.session_key:
            request.session.create()
        subject = str(row.values[workflow["subjectColumn"] - 1] or f"항목 {row.row_number}")
        item = BlueprintSubmission.objects.create(
            upload=upload, workflow_id=workflow["id"], subject_row=row, subject_snapshot=subject,
            values=values, status=workflow["initialState"], workflow_snapshot=workflow,
            created_by_session=request.session.session_key)
        return Response(_submission(item), status=201)


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
            item = get_object_or_404(BlueprintSubmission.objects.select_for_update(), upload=upload, pk=submission_id)
            if actor == "owner" and item.created_by_session != (request.session.session_key or ""):
                raise ValidationError({"detail": "본인 신청만 변경할 수 있습니다."})
            step = next((step for step in item.workflow_snapshot["transitions"]
                         if step["from"] == item.status and step["to"] == request.data["to"] and step["actor"] == actor), None)
            if step is None:
                raise ValidationError({"detail": "허용되지 않은 상태 변경입니다."})
            item.status = request.data["to"]
            item.save(update_fields=["status", "updated_at"])
        return Response(_submission(item))
