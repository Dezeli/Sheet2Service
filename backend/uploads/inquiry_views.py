"""Deterministic inquiry template; submissions never call a model."""
import uuid

from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .models import Inquiry, ManagedRow
from .views import SessionView, owned
from .workflow import workflow_module


def inquiry_upload(request, pk):
    upload = owned(request, pk)
    config = workflow_module(upload.workflow_config, ("inquiry",)) or {}
    if config.get("user", {}).get("template") != "inquiry" \
            or config.get("admin", {}).get("template") != "reply_inquiries":
        raise ValidationError({"detail": "문의 접수 템플릿을 먼저 선택해 주세요."})
    return upload


def text(value, label, maximum, required=True):
    if not isinstance(value, str) or len(value.strip()) > maximum or (required and not value.strip()):
        raise ValidationError({"detail": f"{label}: {'1~' if required else '최대 '}{maximum}자로 입력해 주세요."})
    return value.strip()


def payload(item):
    return {"id": str(item.id), "title": item.title, "body": item.body,
            "subject": item.subject_snapshot, "answer": item.answer, "status": item.status,
            "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}


class InquiriesView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = inquiry_upload(request, pk)
        items = Inquiry.objects.filter(upload=upload)
        if request.query_params.get("mine") == "1":
            items = items.filter(created_by_session=request.session.session_key or "")
        try:
            page = int(request.query_params.get("page", "1"))
        except ValueError as exc:
            raise ValidationError({"detail": "페이지 번호가 올바르지 않습니다."}) from exc
        count = items.count()
        if page < 1 or page > max(1, (count + 19) // 20):
            raise ValidationError({"detail": "페이지 번호가 범위를 벗어났습니다."})
        return Response({"page": page, "count": count, "has_next": page * 20 < count,
                         "inquiries": [payload(item) for item in items[(page - 1) * 20:page * 20]]})

    def post(self, request, pk):
        upload = inquiry_upload(request, pk)
        data = request.data
        if not isinstance(data, dict) or not {"title", "body"} <= set(data) \
                or set(data) - {"title", "body", "row_id"}:
            raise ValidationError({"detail": "문의 제목과 내용을 입력해 주세요."})
        title = text(data["title"], "제목", 120)
        body = text(data["body"], "내용", 5000)
        row = None
        subject = ""
        number = workflow_module(upload.workflow_config, ("inquiry",))["user"]["subjectColumn"]
        if data.get("row_id") is not None:
            if number == 0:
                raise ValidationError({"detail": "이 문의 양식에는 관련 항목을 연결하지 않습니다."})
            try:
                row_id = uuid.UUID(str(data["row_id"]))
            except ValueError as exc:
                raise ValidationError({"detail": "관련 항목이 올바르지 않습니다."}) from exc
            row = get_object_or_404(ManagedRow, pk=row_id, upload=upload)
            subject = str(row.values[number - 1] or f"항목 {row.row_number}")
        item = Inquiry.objects.create(upload=upload, title=title, body=body,
            subject_row=row, subject_snapshot=subject,
            created_by_session=request.session.session_key)
        return Response(payload(item), status=201)


class InquiryView(SessionView):
    parser_classes = [JSONParser]

    def patch(self, request, pk, inquiry_id):
        upload = inquiry_upload(request, pk)
        data = request.data
        if not isinstance(data, dict) or set(data) != {"answer", "status"} \
                or data["status"] not in Inquiry.Status.values:
            raise ValidationError({"detail": "답변과 올바른 처리 상태를 입력해 주세요."})
        answer = text(data["answer"], "답변", 5000, required=data["status"] == Inquiry.Status.RESOLVED)
        with transaction.atomic():
            item = get_object_or_404(Inquiry.objects.select_for_update(), pk=inquiry_id, upload=upload)
            item.answer = answer
            item.status = data["status"]
            item.save(update_fields=["answer", "status", "updated_at"])
        return Response(payload(item))


class InquiryStatsView(SessionView):
    def get(self, request, pk):
        upload = owned(request, pk)
        if not upload.workflow_config:
            raise ValidationError({"detail": "먼저 서비스 기능을 선택해 주세요."})
        counts = dict(Inquiry.objects.filter(upload=upload).values_list("status").annotate(count=Count("id")))
        return Response({"total": sum(counts.values()),
                         "counts": {status: counts.get(status, 0) for status in Inquiry.Status.values}})
