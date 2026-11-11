"""Deterministic inquiry template; submissions never call a model."""
import uuid

from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .models import Inquiry, ManagedRow, Resource
from .service_access import has_feature, service_upload
from .views import SessionView, owned


def inquiry_upload(request, pk):
    upload = service_upload(request, pk)
    if not has_feature(upload.service_config, "inquiry", "reply_inquiries"):
        raise ValidationError({"detail": "이 서비스에는 문의 기능이 없습니다."})
    return upload


def subject_column(upload):
    """Inquiries may point at a sheet row; the row is named by its last resource column."""
    columns = upload.service_config["resources"]["columns"]
    return columns[-1] if columns else 0


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
        status = request.query_params.get("status")
        if status:
            if status not in Inquiry.Status.values:
                raise ValidationError({"detail": "처리 상태가 올바르지 않습니다."})
            items = items.filter(status=status)
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
                or set(data) - {"title", "body", "row_id", "resource_id"}:
            raise ValidationError({"detail": "문의 제목과 내용을 입력해 주세요."})
        title = text(data["title"], "제목", 120)
        body = text(data["body"], "내용", 5000)
        row = None
        subject = ""
        number = subject_column(upload)
        if data.get("row_id") is not None:
            if number == 0:
                raise ValidationError({"detail": "이 문의 양식에는 관련 항목을 연결하지 않습니다."})
            try:
                row_id = uuid.UUID(str(data["row_id"]))
            except ValueError as exc:
                raise ValidationError({"detail": "관련 항목이 올바르지 않습니다."}) from exc
            row = get_object_or_404(ManagedRow, pk=row_id, upload=upload)
            subject = str(row.values[number - 1] or f"항목 {row.row_number}")
        elif data.get("resource_id") is not None:  # a reservation service names the subject by its resource
            try:
                resource_id = uuid.UUID(str(data["resource_id"]))
            except ValueError as exc:
                raise ValidationError({"detail": "관련 항목이 올바르지 않습니다."}) from exc
            subject = get_object_or_404(Resource, pk=resource_id, upload=upload).path
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

    def delete(self, request, pk, inquiry_id):
        upload = inquiry_upload(request, pk)
        get_object_or_404(Inquiry, pk=inquiry_id, upload=upload).delete()
        return Response(status=204)


class InquiryStatsView(SessionView):
    def get(self, request, pk):
        upload = service_upload(request, pk)
        counts = dict(Inquiry.objects.filter(upload=upload).values_list("status").annotate(count=Count("id")))
        return Response({"total": sum(counts.values()),
                         "counts": {status: counts.get(status, 0) for status in Inquiry.Status.values}})
