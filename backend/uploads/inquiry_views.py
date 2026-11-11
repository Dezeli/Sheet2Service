"""Deterministic inquiry template; submissions never call a model."""
import re
import uuid

from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .booking_views import format_phone, mask_name
from .models import Inquiry, ManagedRow, Resource
from .reservation_service import phone_digits
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


PIN = re.compile(r"\d{4}")
TRIES = 5
LOCK_SECONDS = 600
OPENED = "opened_inquiries"  # session key: private inquiries this browser opened with their PIN


def payload(item):
    """Everything, for staff answering."""
    return {"id": str(item.id), "title": item.title, "body": item.body,
            "subject": item.subject_snapshot, "answer": item.answer, "status": item.status,
            "author": item.author, "phone": format_phone(item.phone), "is_private": item.is_private,
            "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}


def opened(item, request):
    """A public inquiry is open to all; a private one to the browser that gave its PIN (or wrote it before PINs)."""
    if not item.is_private or str(item.id) in request.session.get(OPENED, []):
        return True
    session_key = request.session.session_key or ""
    return bool(session_key) and item.created_by_session == session_key and not item.password


def board_payload(item, request):
    """The public board: the asker half hidden, and a private inquiry shows only its title until its PIN opens it."""
    shown = opened(item, request)
    return {"id": str(item.id), "title": item.title, "status": item.status, "author": mask_name(item.author),
            "is_private": item.is_private, "locked": not shown,
            "body": item.body if shown else "", "answer": item.answer if shown else "",
            "subject": item.subject_snapshot if shown else "",
            "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}


class InquiriesView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = inquiry_upload(request, pk)
        items = Inquiry.objects.filter(upload=upload)
        board = request.query_params.get("board") == "1"
        status = request.query_params.get("status")
        if status:
            if status not in Inquiry.Status.values:
                raise ValidationError({"detail": "처리 상태가 올바르지 않습니다."})
            items = items.filter(status=status)
        try:
            page = int(request.query_params.get("page", "1"))
        except ValueError as exc:
            raise ValidationError({"detail": "페이지 번호가 올바르지 않습니다."}) from exc
        size = 10 if request.query_params.get("size") == "10" else 20
        count = items.count()
        if page < 1 or page > max(1, (count + size - 1) // size):
            raise ValidationError({"detail": "페이지 번호가 범위를 벗어났습니다."})
        return Response({"page": page, "count": count, "size": size, "has_next": page * size < count,
                         "inquiries": [board_payload(item, request) if board else payload(item) for item in items[(page - 1) * size:page * size]]})

    def post(self, request, pk):
        upload = inquiry_upload(request, pk)
        data = request.data
        if not isinstance(data, dict) or not {"title", "body"} <= set(data) \
                or set(data) - {"title", "body", "row_id", "resource_id", "author", "phone", "is_private", "password"}:
            raise ValidationError({"detail": "문의 제목과 내용을 입력해 주세요."})
        title = text(data["title"], "제목", 120)
        body = text(data["body"], "내용", 5000)
        author = text(data.get("author", ""), "이름", 200)
        phone = phone_digits(data.get("phone"))
        if data.get("phone") and not phone:
            raise ValidationError({"detail": "전화번호를 010-1234-5678처럼 입력해 주세요."})
        private = data.get("is_private", True)
        if type(private) is not bool:
            raise ValidationError({"detail": "공개 여부가 올바르지 않습니다."})
        pin = str(data.get("password") or "")
        if pin and not PIN.fullmatch(pin):
            raise ValidationError({"detail": "비밀번호는 숫자 4자리로 입력해 주세요."})
        if private and not pin:
            raise ValidationError({"detail": "비공개 문의는 다시 열어 볼 비밀번호 숫자 4자리를 정해 주세요."})
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
        if not request.session.session_key:
            request.session.create()
        item = Inquiry.objects.create(upload=upload, title=title, body=body,
            subject_row=row, subject_snapshot=subject, author=author, phone=phone, is_private=private,
            password=make_password(pin) if pin else "", created_by_session=request.session.session_key)
        if private:  # the one who just wrote it may read it here without the PIN once more
            request.session[OPENED] = sorted({*request.session.get(OPENED, []), str(item.id)})[-200:]
        return Response(board_payload(item, request), status=201)


class InquiryUnlockView(SessionView):
    """The PIN chosen when asking opens a private inquiry, with its answer, in this browser."""
    parser_classes = [JSONParser]

    def post(self, request, pk, inquiry_id):
        upload = inquiry_upload(request, pk)
        item = get_object_or_404(Inquiry, pk=inquiry_id, upload=upload)
        pin = str((request.data if isinstance(request.data, dict) else {}).get("password") or "")
        if not PIN.fullmatch(pin):
            raise ValidationError({"detail": "문의할 때 정한 비밀번호 숫자 4자리를 입력해 주세요."})
        key = f"inquiry-unlock:{item.pk}"
        tries = cache.get(key, 0)
        if tries >= TRIES:
            raise ValidationError({"detail": "비밀번호를 여러 번 틀려 10분 동안 열 수 없습니다. 잠시 뒤 다시 시도해 주세요."})
        if not item.password or not check_password(pin, item.password):
            cache.set(key, tries + 1, LOCK_SECONDS)
            raise ValidationError({"detail": "비밀번호가 맞지 않습니다."})
        cache.delete(key)
        if not request.session.session_key:
            request.session.create()
        request.session[OPENED] = sorted({*request.session.get(OPENED, []), str(item.id)})[-200:]
        return Response(board_payload(item, request))


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
