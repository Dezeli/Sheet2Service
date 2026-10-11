"""Plain-text notices, with explicit draft/published visibility in Preview."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .models import Notice
from .views import SessionView, owned
from .workflow import workflow_module


def notice_upload(request, pk):
    upload = owned(request, pk)
    module = workflow_module(upload.workflow_config, ("notice",))
    if not module or module.get("admin", {}).get("template") != "manage_notices":
        raise ValidationError({"detail": "공지 기능을 먼저 선택해 주세요."})
    return upload


def payload(item):
    return {"id": str(item.id), "title": item.title, "body": item.body,
            "is_published": item.is_published,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}


def validated(data, *, creating=False):
    if not isinstance(data, dict) or not data or set(data) - {"title", "body", "is_published"} \
            or (creating and not {"title", "body"} <= set(data)):
        raise ValidationError({"detail": "공지 제목·내용·게시 여부를 입력해 주세요."})
    values = {}
    for field, label, maximum in (("title", "제목", 120), ("body", "내용", 10000)):
        if field in data:
            value = data[field]
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
                raise ValidationError({"detail": f"{label}은 1~{maximum}자로 입력해 주세요."})
            values[field] = value.strip()
    if "is_published" in data:
        if type(data["is_published"]) is not bool:
            raise ValidationError({"detail": "게시 여부가 올바르지 않습니다."})
        values["is_published"] = data["is_published"]
    return values


def visible(upload, request):
    query = Notice.objects.filter(upload=upload)
    # Existing Preview uses the upload owner's session for both role screens.
    # This flag chooses presentation, and is not an administrator credential.
    if request.query_params.get("admin") != "1":
        query = query.filter(is_published=True).order_by("-published_at", "-id")
    return query


class NoticesView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = notice_upload(request, pk)
        query = visible(upload, request)
        try:
            page = int(request.query_params.get("page", "1"))
        except ValueError as exc:
            raise ValidationError({"detail": "페이지 번호가 올바르지 않습니다."}) from exc
        count = query.count()
        if page < 1 or page > max(1, (count + 19) // 20):
            raise ValidationError({"detail": "페이지 번호가 범위를 벗어났습니다."})
        return Response({"page": page, "count": count, "has_next": page * 20 < count,
                         "notices": [payload(item) for item in query[(page - 1) * 20:page * 20]]})

    def post(self, request, pk):
        upload = notice_upload(request, pk)
        values = validated(request.data, creating=True)
        if values.get("is_published"):
            values["published_at"] = timezone.now()
        item = Notice.objects.create(upload=upload, **values)
        return Response(payload(item), status=201)


class NoticeView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk, notice_id):
        upload = notice_upload(request, pk)
        return Response(payload(get_object_or_404(visible(upload, request), pk=notice_id)))

    def patch(self, request, pk, notice_id):
        upload = notice_upload(request, pk)
        values = validated(request.data)
        with transaction.atomic():
            item = get_object_or_404(Notice.objects.select_for_update(), upload=upload, pk=notice_id)
            if "is_published" in values:
                if values["is_published"] and not item.is_published:
                    item.published_at = timezone.now()
                elif not values["is_published"]:
                    item.published_at = None
            for field, value in values.items():
                setattr(item, field, value)
            item.save(update_fields=[*values, "published_at", "updated_at"])
        return Response(payload(item))
