"""Quantity-based rentals; inventory is reserved on approval and freed on return."""
import uuid

from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .models import ManagedRow, Rental, RentalStock, Upload
from .views import SessionView, owned
from .workflow import workflow_module

HELD_STATUSES = (Rental.Status.APPROVED, Rental.Status.LOANED)
ACTIVE_STATUSES = (Rental.Status.PENDING, *HELD_STATUSES)
ADMIN_ACTIONS = {"pending": ["approved", "rejected"], "approved": ["loaned"], "loaned": ["returned"]}


def fail(message):
    raise ValidationError({"detail": message})


def rental_upload(request, pk):
    upload = owned(request, pk)
    module = workflow_module(upload.workflow_config, ("rental",))
    if not module or module.get("admin", {}).get("template") != "manage_rentals":
        fail("대여 기능을 먼저 선택해 주세요.")
    return upload, module


def number(value, minimum):
    if type(value) is not int or not minimum <= value <= 10000:
        fail(f"수량은 {minimum}~10,000 사이 정수로 입력해 주세요.")
    return value


def identifier(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        fail("선택한 항목이 올바르지 않습니다.")


def text(value):
    if not isinstance(value, str) or len(value.strip()) > 2000:
        fail("내용·처리 메모는 2,000자 이내로 입력해 주세요.")
    return value.strip()


def page_of(query, request):
    try:
        page = int(request.query_params.get("page", "1"))
    except ValueError:
        fail("페이지 번호가 올바르지 않습니다.")
    count = query.count()
    if page < 1 or page > max(1, (count + 19) // 20):
        fail("페이지 번호가 범위를 벗어났습니다.")
    return query[(page - 1) * 20:page * 20], {"page": page, "count": count, "has_next": page * 20 < count}


def held(stock):
    return stock.rentals.filter(status__in=HELD_STATUSES).aggregate(amount=Sum("quantity"))["amount"] or 0


def stock_payload(stock, occupied=None):
    occupied = held(stock) if occupied is None else occupied
    return {"id": str(stock.id), "subject": stock.subject_snapshot, "total": stock.total,
            "held": occupied, "available": max(0, stock.total - occupied), "active": stock.active,
            "row_id": str(stock.subject_row_id) if stock.subject_row_id else None}


def rental_payload(item):
    return {"id": str(item.id), "stock_id": str(item.stock_id), "subject": item.stock.subject_snapshot,
            "quantity": item.quantity, "status": item.status, "content": item.content,
            "processing_note": item.processing_note, "admin_actions": ADMIN_ACTIONS.get(item.status, []),
            "can_cancel": item.status in ("pending", "approved"),
            "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}


class RentalStocksView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload, _ = rental_upload(request, pk)
        stocks = RentalStock.objects.filter(upload=upload)
        if request.query_params.get("available") == "1":
            stocks = stocks.filter(active=True, subject_row__isnull=False)
        stocks = stocks.annotate(occupied=Sum("rentals__quantity", filter=Q(rentals__status__in=HELD_STATUSES)))
        items, paging = page_of(stocks, request)
        return Response({**paging, "stocks": [stock_payload(stock, stock.occupied or 0) for stock in items]})

    def post(self, request, pk):
        upload, module = rental_upload(request, pk)
        data = request.data
        if not isinstance(data, dict) or set(data) != {"row_id", "total"}:
            fail("항목과 총 재고를 입력해 주세요.")
        total = number(data["total"], 0)
        with transaction.atomic():
            Upload.objects.select_for_update().get(pk=upload.pk)
            row = get_object_or_404(ManagedRow, pk=identifier(data["row_id"]), upload=upload)
            if RentalStock.objects.filter(subject_row=row).exists():
                fail("이미 등록된 항목입니다. 기존 재고를 수정해 주세요.")
            column = module["user"]["subjectColumn"]
            stock = RentalStock.objects.create(upload=upload, subject_row=row, total=total,
                subject_snapshot=str(row.values[column - 1] or f"항목 {row.row_number}"))
        return Response(stock_payload(stock), status=201)


class RentalStockView(SessionView):
    parser_classes = [JSONParser]

    def patch(self, request, pk, stock_id):
        upload, _ = rental_upload(request, pk)
        data = request.data
        if not isinstance(data, dict) or not data or set(data) - {"total", "active"}:
            fail("총 재고 또는 접수 여부를 입력해 주세요.")
        if "total" in data:
            number(data["total"], 0)
        if "active" in data and type(data["active"]) is not bool:
            fail("접수 여부가 올바르지 않습니다.")
        with transaction.atomic():
            Upload.objects.select_for_update().get(pk=upload.pk)
            stock = get_object_or_404(RentalStock.objects.select_for_update(), pk=stock_id, upload=upload)
            if "total" in data and data["total"] < held(stock):
                fail("재고를 승인·대여 중인 수량보다 줄일 수 없습니다.")
            for field, value in data.items():
                setattr(stock, field, value)
            stock.save(update_fields=list(data))
        return Response(stock_payload(stock))


class RentalsView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload, _ = rental_upload(request, pk)
        items = Rental.objects.filter(stock__upload=upload).select_related("stock")
        if request.query_params.get("mine") == "1":
            items = items.filter(created_by_session=request.session.session_key)
        items, paging = page_of(items, request)
        return Response({**paging, "rentals": [rental_payload(item) for item in items]})

    def post(self, request, pk):
        upload, _ = rental_upload(request, pk)
        data = request.data
        if not isinstance(data, dict) or not {"stock_id", "quantity"} <= set(data) or set(data) - {"stock_id", "quantity", "content"}:
            fail("대여 항목과 수량을 입력해 주세요.")
        quantity, content = number(data["quantity"], 1), text(data.get("content", ""))
        with transaction.atomic():
            Upload.objects.select_for_update().get(pk=upload.pk)
            stock = get_object_or_404(RentalStock.objects.select_for_update(), pk=identifier(data["stock_id"]), upload=upload)
            if not stock.active or stock.subject_row_id is None:
                fail("현재 신청을 받지 않는 항목입니다.")
            if stock.rentals.filter(created_by_session=request.session.session_key, status__in=ACTIVE_STATUSES).exists():
                fail("이미 진행 중인 대여 신청이 있습니다.")
            if quantity > stock.total - held(stock):
                fail("신청 수량이 현재 가능한 재고보다 많습니다.")
            item = Rental.objects.create(stock=stock, quantity=quantity, content=content,
                created_by_session=request.session.session_key)
        return Response(rental_payload(item), status=201)


class RentalView(SessionView):
    parser_classes = [JSONParser]

    def patch(self, request, pk, rental_id):
        upload, _ = rental_upload(request, pk)
        data = request.data
        if not isinstance(data, dict) or "status" not in data or set(data) - {"status", "processing_note"} \
                or not isinstance(data["status"], str) or data["status"] not in Rental.Status.values:
            fail("올바른 처리 상태를 입력해 주세요.")
        note = text(data["processing_note"]) if "processing_note" in data else None
        with transaction.atomic():
            Upload.objects.select_for_update().get(pk=upload.pk)
            item = get_object_or_404(Rental.objects.select_for_update().select_related("stock"), pk=rental_id, stock__upload=upload)
            target = data["status"]
            if target == "cancelled":
                if item.created_by_session != request.session.session_key or item.status not in ("pending", "approved"):
                    fail("대여 시작 전 본인 신청만 취소할 수 있습니다.")
                if note is not None:
                    fail("취소 요청에는 관리자 처리 메모를 변경할 수 없습니다.")
            elif target not in ADMIN_ACTIONS.get(item.status, []):
                fail("현재 상태에서 허용되지 않는 처리입니다.")
            if target == "approved":
                if not item.stock.active or item.stock.subject_row_id is None:
                    fail("접수가 중지되었거나 삭제된 항목입니다.")
                if item.quantity > item.stock.total - held(item.stock):
                    fail("승인 가능한 재고가 부족합니다.")
            item.status = target
            if note is not None:
                item.processing_note = note
            item.save(update_fields=["status", "processing_note", "updated_at"])
        return Response(rental_payload(item))
