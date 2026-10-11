"""Manual quotes: exact decimal amounts and immutable offers after sending."""
import re
import uuid
from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .models import ManagedRow, QuoteRequest
from .views import SessionView, owned
from .workflow import workflow_module

ADMIN_ACTIONS = {"pending": ["save", "send", "reject"], "accepted": ["start"], "in_progress": ["complete"]}
USER_ACTIONS = {"pending": ["cancel"], "quoted": ["accept", "decline", "cancel"], "accepted": ["cancel"]}
TARGETS = {"send": "quoted", "reject": "unavailable", "start": "in_progress", "complete": "completed",
           "accept": "accepted", "decline": "declined", "cancel": "cancelled"}
CURRENCIES = ("KRW", "USD", "EUR", "JPY")


def fail(message):
    raise ValidationError({"detail": message})


def quote_upload(request, pk):
    upload = owned(request, pk)
    module = workflow_module(upload.workflow_config, ("quote",))
    if not module or module.get("admin", {}).get("template") != "manage_quotes":
        fail("견적 요청 기능을 먼저 선택해 주세요.")
    return upload, module


def text(value, label, required=True):
    if not isinstance(value, str) or len(value.strip()) > 5000 or (required and not value.strip()):
        fail(f"{label}은 {'1~' if required else '최대 '}5,000자로 입력해 주세요.")
    return value.strip()


def offer(values):
    amount = values["amount"]
    if not isinstance(amount, str) or re.fullmatch(r"(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?", amount) is None:
        fail("금액은 0 이상, 정수부 12자리·소수부 2자리 이내 숫자로 입력해 주세요.")
    if not isinstance(values["currency"], str) or values["currency"] not in CURRENCIES:
        fail("지원되는 통화를 선택해 주세요.")
    return {"amount": Decimal(amount), "currency": values["currency"],
            "proposal": text(values["proposal"], "제안 내용")}


def payload(item, admin=False):
    # Draft quote amounts/content are never shown in the user presentation.
    show_offer = admin or item.sent_at is not None
    return {"id": str(item.id), "subject": item.subject_snapshot, "content": item.content,
            "status": item.status, "amount": format(item.amount, ".2f") if show_offer and item.amount is not None else None,
            "currency": item.currency if show_offer else None, "proposal": item.proposal if show_offer else "",
            "processing_note": item.processing_note, "admin_actions": ADMIN_ACTIONS.get(item.status, []),
            "user_actions": USER_ACTIONS.get(item.status, []),
            "sent_at": item.sent_at.isoformat() if item.sent_at else None,
            "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}


class QuoteRequestsView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload, _ = quote_upload(request, pk)
        admin = request.query_params.get("admin") == "1"
        items = QuoteRequest.objects.filter(upload=upload)
        if not admin:
            items = items.filter(created_by_session=request.session.session_key)
        try:
            page = int(request.query_params.get("page", "1"))
        except ValueError:
            fail("페이지 번호가 올바르지 않습니다.")
        count = items.count()
        if page < 1 or page > max(1, (count + 19) // 20):
            fail("페이지 번호가 범위를 벗어났습니다.")
        return Response({"page": page, "count": count, "has_next": page * 20 < count,
                         "quotes": [payload(item, admin) for item in items[(page - 1) * 20:page * 20]]})

    def post(self, request, pk):
        upload, module = quote_upload(request, pk)
        data = request.data
        if not isinstance(data, dict) or set(data) != {"row_id", "content"}:
            fail("견적을 요청할 항목과 조건을 입력해 주세요.")
        content = text(data["content"], "요청 조건")
        try:
            row_id = uuid.UUID(str(data["row_id"]))
        except (ValueError, TypeError, AttributeError):
            fail("선택한 항목이 올바르지 않습니다.")
        row = get_object_or_404(ManagedRow, pk=row_id, upload=upload)
        column = module["user"]["subjectColumn"]
        item = QuoteRequest.objects.create(upload=upload, subject_row=row,
            subject_snapshot=str(row.values[column - 1] or f"항목 {row.row_number}"),
            content=content, created_by_session=request.session.session_key)
        return Response(payload(item), status=201)


class QuoteRequestView(SessionView):
    parser_classes = [JSONParser]

    def patch(self, request, pk, quote_id):
        upload, _ = quote_upload(request, pk)
        data = request.data
        if not isinstance(data, dict) or "action" not in data or not isinstance(data["action"], str):
            fail("견적 처리 동작을 선택해 주세요.")
        action = data["action"]
        quote_fields = {"amount", "currency", "proposal"}
        allowed = {"action"} | (quote_fields if action in ("save", "send") else {"processing_note"} if action in ("reject", "start", "complete") else set())
        if set(data) - allowed or action not in ("save", *TARGETS):
            fail("견적 처리 형식이 올바르지 않습니다.")
        if (action == "save" and not quote_fields <= set(data)) or (set(data) & quote_fields and not quote_fields <= set(data)):
            fail("금액·통화·제안 내용을 함께 입력해 주세요.")
        values = offer(data) if quote_fields <= set(data) else {}
        note = text(data["processing_note"], "처리 메모", required=False) if "processing_note" in data else None
        user_action = action in ("accept", "decline", "cancel")
        with transaction.atomic():
            items = QuoteRequest.objects.select_for_update().filter(upload=upload)
            if user_action:
                items = items.filter(created_by_session=request.session.session_key)
            item = get_object_or_404(items, pk=quote_id)
            actions = USER_ACTIONS if user_action else ADMIN_ACTIONS
            if action not in actions.get(item.status, []):
                fail("현재 상태에서는 이 처리를 할 수 없습니다.")
            for field, value in values.items():
                setattr(item, field, value)
            if action == "send":
                if item.amount is None or not item.proposal.strip():
                    fail("전달할 금액과 제안 내용을 먼저 작성해 주세요.")
                item.sent_at = timezone.now()
            if action != "save":
                item.status = TARGETS[action]
            if note is not None:
                item.processing_note = note
            item.save(update_fields=[*values, "status", "sent_at", "processing_note", "updated_at"])
        return Response(payload(item, admin=not user_action))
