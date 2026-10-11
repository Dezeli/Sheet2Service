"""Generic request lifecycle configured by the selected user/admin flows."""

import uuid

from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .managed import ensure_imported
from .models import ManagedRow, ServiceRequest, Upload
from .views import SessionView, owned
from .workflow import workflow_module


def _config(upload):
    config = upload.workflow_config
    if not isinstance(config, dict) or config.get("version") != 1:
        raise ValidationError({"detail": "먼저 유저·관리자 플로우를 선택해 주세요."})
    return workflow_module(config, ("request_review", "request_auto")) or {
        "version": 1, "user": {"template": "browse_only"}, "admin": {"template": "manage_catalog"}}


def admin_actions(item):
    if item.approval_mode == "required" and item.status == "pending":
        return ["approved", "rejected"]
    if item.status == ("approved" if item.approval_mode == "required" else "submitted"):
        return ["in_progress"]
    if item.status == "in_progress":
        return ["completed"]
    return []


def _request_payload(item):
    return {"id": str(item.id), "subject": item.subject_snapshot, "status": item.status,
            "content": item.content, "processing_note": item.processing_note,
            "approval_mode": item.approval_mode, "admin_actions": admin_actions(item),
            "can_cancel": item.status in ("pending", "submitted", "approved"),
            "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}


class ServiceRequestsView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = owned(request, pk)
        _config(upload)
        items = ServiceRequest.objects.filter(upload=upload)
        if request.query_params.get("mine") == "1":
            items = items.filter(created_by_session=request.session.session_key or "")
        try:
            page = int(request.query_params.get("page", "1"))
        except ValueError as exc:
            raise ValidationError({"detail": "페이지 번호가 올바르지 않습니다."}) from exc
        count = items.count()
        if page < 1 or page > max(1, (count + 19) // 20):
            raise ValidationError({"detail": "페이지 번호가 범위를 벗어났습니다."})
        return Response({"page": page, "count": count,
                         "requests": [_request_payload(item) for item in items[(page - 1) * 20:page * 20]],
                         "has_next": page * 20 < count})

    def post(self, request, pk):
        upload = owned(request, pk)
        ensure_imported(upload)
        config = _config(upload)
        if config["user"]["template"] == "browse_only":
            raise ValidationError({"detail": "이 서비스는 신청을 받지 않습니다."})
        if config["user"]["template"] not in ("request_review", "request_auto"):
            raise ValidationError({"detail": "선택한 템플릿의 접수 양식을 사용해 주세요."})
        if not isinstance(request.data, dict) or "row_id" not in request.data \
                or set(request.data) - {"row_id", "content"}:
            raise ValidationError({"detail": "신청할 항목을 선택해 주세요."})
        content = request.data.get("content", "")
        if not isinstance(content, str) or len(content.strip()) > 5000:
            raise ValidationError({"detail": "신청 내용은 최대 5,000자로 입력해 주세요."})
        try:
            row_id = uuid.UUID(str(request.data["row_id"]))
        except ValueError as exc:
            raise ValidationError({"detail": "신청할 항목이 올바르지 않습니다."}) from exc
        row = get_object_or_404(ManagedRow, pk=row_id, upload=upload)
        subject_number = config["user"]["subjectColumn"]
        subject = row.values[subject_number - 1]
        if not isinstance(subject, str) or not subject.strip():
            subject = f"항목 {row.row_number}"
        status = (ServiceRequest.Status.PENDING if config["user"]["template"] == "request_review"
                  else ServiceRequest.Status.SUBMITTED)
        with transaction.atomic():
            # Serialize submissions for one service to reject concurrent duplicates.
            Upload.objects.select_for_update().get(pk=upload.pk)
            if ServiceRequest.objects.filter(upload=upload, subject_row=row,
                    created_by_session=request.session.session_key,
                    status__in=["pending", "submitted", "approved", "in_progress"]).exists():
                raise ValidationError({"detail": "이미 진행 중인 신청이 있습니다."})
            item = ServiceRequest.objects.create(upload=upload, subject_row=row,
                subject_snapshot=subject, status=status, content=content.strip(),
                approval_mode="required" if status == "pending" else "none",
                created_by_session=request.session.session_key or "")
        return Response(_request_payload(item), status=201)


class ServiceRequestView(SessionView):
    parser_classes = [JSONParser]

    def patch(self, request, pk, request_id):
        upload = owned(request, pk)
        config = _config(upload)
        if config["admin"]["template"] not in ("review_requests", "monitor_requests"):
            raise ValidationError({"detail": "이 서비스에는 신청 처리 동작이 없습니다."})
        if not isinstance(request.data, dict) or "status" not in request.data \
                or set(request.data) - {"status", "processing_note"}:
            raise ValidationError({"detail": "처리 상태가 올바르지 않습니다."})
        status = request.data["status"]
        note = request.data.get("processing_note", "")
        if not isinstance(note, str) or len(note.strip()) > 5000:
            raise ValidationError({"detail": "처리 사유는 최대 5,000자로 입력해 주세요."})
        if status == "rejected" and not note.strip():
            raise ValidationError({"detail": "거절 사유를 입력해 주세요."})
        with transaction.atomic():
            item = get_object_or_404(ServiceRequest.objects.select_for_update(), pk=request_id, upload=upload)
            if status == "cancelled":
                if item.created_by_session != request.session.session_key \
                        or item.status not in ("pending", "submitted", "approved") \
                        or set(request.data) != {"status"}:
                    raise ValidationError({"detail": "본인의 처리 전 신청만 취소할 수 있습니다."})
            elif status not in admin_actions(item):
                raise ValidationError({"detail": "현재 상태에서 가능한 처리를 선택해 주세요."})
            item.status = status
            if status != "cancelled":
                item.processing_note = note.strip()
            item.save(update_fields=["status", "processing_note", "updated_at"])
        return Response(_request_payload(item))


class ServiceRequestStatsView(SessionView):
    def get(self, request, pk):
        upload = owned(request, pk)
        _config(upload)
        counts = dict(ServiceRequest.objects.filter(upload=upload).values_list("status")
                      .annotate(count=Count("id")))
        return Response({"total": sum(counts.values()),
                         "counts": {status: counts.get(status, 0) for status in ServiceRequest.Status.values}})
