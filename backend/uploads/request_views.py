"""Generic request lifecycle configured by the selected user/admin flows."""

import uuid

from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .managed import ensure_imported
from .models import ManagedRow, ServiceRequest
from .views import SessionView, owned


def _config(upload):
    config = upload.workflow_config
    if not isinstance(config, dict) or config.get("version") != 1:
        raise ValidationError({"detail": "먼저 유저·관리자 플로우를 선택해 주세요."})
    return config


def _request_payload(item):
    return {"id": str(item.id), "subject": item.subject_snapshot, "status": item.status,
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
        if not isinstance(request.data, dict) or set(request.data) != {"row_id"}:
            raise ValidationError({"detail": "신청할 항목을 선택해 주세요."})
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
        item = ServiceRequest.objects.create(upload=upload, subject_row=row,
            subject_snapshot=subject, status=status,
            created_by_session=request.session.session_key or "")
        return Response(_request_payload(item), status=201)


class ServiceRequestView(SessionView):
    parser_classes = [JSONParser]

    def patch(self, request, pk, request_id):
        upload = owned(request, pk)
        config = _config(upload)
        if config["admin"]["template"] != "review_requests":
            raise ValidationError({"detail": "이 서비스에는 승인·거절 동작이 없습니다."})
        if not isinstance(request.data, dict) or set(request.data) != {"status"} \
                or request.data["status"] not in (ServiceRequest.Status.APPROVED, ServiceRequest.Status.REJECTED):
            raise ValidationError({"detail": "승인 또는 거절을 선택해 주세요."})
        with transaction.atomic():
            item = get_object_or_404(ServiceRequest.objects.select_for_update(), pk=request_id, upload=upload)
            if item.status != ServiceRequest.Status.PENDING:
                raise ValidationError({"detail": "대기 중인 신청만 처리할 수 있습니다."})
            item.status = request.data["status"]
            item.save(update_fields=["status", "updated_at"])
        return Response(_request_payload(item))


class ServiceRequestStatsView(SessionView):
    def get(self, request, pk):
        upload = owned(request, pk)
        _config(upload)
        counts = dict(ServiceRequest.objects.filter(upload=upload).values_list("status")
                      .annotate(count=Count("id")))
        return Response({"total": sum(counts.values()),
                         "counts": {status: counts.get(status, 0) for status in ServiceRequest.Status.values}})
