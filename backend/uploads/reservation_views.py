"""Scheduled reservations with deterministic validation and serialized writes."""
import uuid

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .models import ManagedRow, Reservation, ReservationSlot, Upload
from .views import SessionView, owned
from .workflow import workflow_module


def reservation_upload(request, pk):
    upload = owned(request, pk)
    module = workflow_module(upload.workflow_config, ("reservation",))
    if not module or module.get("admin", {}).get("template") != "manage_reservations":
        raise ValidationError({"detail": "예약 기능을 먼저 선택해 주세요."})
    return upload, module


def fail(message):
    raise ValidationError({"detail": message})


def capacity(value):
    if type(value) is not int or not 1 <= value <= 10000:
        fail("정원은 1~10,000 사이 정수로 입력해 주세요.")
    return value


def instant(value):
    try:
        parsed = parse_datetime(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None or timezone.is_naive(parsed):
        fail("예약 시간은 시간대가 포함된 날짜·시간으로 입력해 주세요.")
    return parsed


def identifier(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        fail("선택한 항목이 올바르지 않습니다.")


def paginated(query, request):
    try:
        page = int(request.query_params.get("page", "1"))
    except ValueError:
        fail("페이지 번호가 올바르지 않습니다.")
    count = query.count()
    if page < 1 or page > max(1, (count + 19) // 20):
        fail("페이지 번호가 범위를 벗어났습니다.")
    return query[(page - 1) * 20:page * 20], {"page": page, "count": count, "has_next": page * 20 < count}


def slot_payload(slot, booked=None):
    if booked is None:
        booked = slot.reservations.filter(cancelled=False).count()
    return {"id": str(slot.id), "row_id": str(slot.subject_row_id) if slot.subject_row_id else None,
            "subject": slot.subject_snapshot, "starts_at": slot.starts_at.isoformat(),
            "ends_at": slot.ends_at.isoformat(), "capacity": slot.capacity,
            "booked": booked, "remaining": max(0, slot.capacity - booked), "closed": slot.closed}


def reservation_payload(item):
    return {"id": str(item.id), "slot": slot_payload(item.slot), "cancelled": item.cancelled,
            "created_at": item.created_at.isoformat()}


class ReservationSlotsView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload, _ = reservation_upload(request, pk)
        slots = ReservationSlot.objects.filter(upload=upload)
        if request.query_params.get("available") == "1":
            slots = slots.filter(closed=False, starts_at__gt=timezone.now(), subject_row__isnull=False)
        slots = slots.annotate(booked=Count("reservations", filter=Q(reservations__cancelled=False)))
        items, paging = paginated(slots, request)
        return Response({**paging, "slots": [slot_payload(slot, slot.booked) for slot in items]})

    def post(self, request, pk):
        upload, module = reservation_upload(request, pk)
        data = request.data
        if not isinstance(data, dict) or set(data) != {"row_id", "starts_at", "ends_at", "capacity"}:
            fail("항목, 시작·종료 시간, 정원을 입력해 주세요.")
        starts, ends = instant(data["starts_at"]), instant(data["ends_at"])
        size = capacity(data["capacity"])
        if starts <= timezone.now() or ends <= starts:
            fail("미래의 시작 시간과 그 이후의 종료 시간을 입력해 주세요.")
        with transaction.atomic():
            Upload.objects.select_for_update().get(pk=upload.pk)
            row = get_object_or_404(ManagedRow, pk=identifier(data["row_id"]), upload=upload)
            if ReservationSlot.objects.filter(upload=upload, subject_row=row,
                    starts_at__lt=ends, ends_at__gt=starts).exists():
                fail("이 항목에 시간이 겹치는 일정이 있습니다.")
            number = module["user"]["subjectColumn"]
            slot = ReservationSlot.objects.create(upload=upload, subject_row=row,
                subject_snapshot=str(row.values[number - 1] or f"항목 {row.row_number}"),
                starts_at=starts, ends_at=ends, capacity=size)
        return Response(slot_payload(slot), status=201)


class ReservationSlotView(SessionView):
    parser_classes = [JSONParser]

    def patch(self, request, pk, slot_id):
        upload, _ = reservation_upload(request, pk)
        data = request.data
        if not isinstance(data, dict) or not data or set(data) - {"capacity", "closed"}:
            fail("정원 또는 접수 마감 여부를 입력해 주세요.")
        if "closed" in data and type(data["closed"]) is not bool:
            fail("접수 마감 여부가 올바르지 않습니다.")
        if "capacity" in data:
            capacity(data["capacity"])
        with transaction.atomic():
            Upload.objects.select_for_update().get(pk=upload.pk)
            slot = get_object_or_404(ReservationSlot.objects.select_for_update(), pk=slot_id, upload=upload)
            if "capacity" in data:
                if data["capacity"] < slot.reservations.filter(cancelled=False).count():
                    fail("정원을 현재 예약 인원보다 줄일 수 없습니다.")
                slot.capacity = data["capacity"]
            if "closed" in data:
                slot.closed = data["closed"]
            slot.save(update_fields=list(data))
        return Response(slot_payload(slot))


class ReservationsView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload, _ = reservation_upload(request, pk)
        items = Reservation.objects.filter(slot__upload=upload).select_related("slot")
        if request.query_params.get("mine") == "1":
            items = items.filter(created_by_session=request.session.session_key)
        items, paging = paginated(items, request)
        return Response({**paging, "reservations": [reservation_payload(item) for item in items]})

    def post(self, request, pk):
        upload, _ = reservation_upload(request, pk)
        data = request.data
        if not isinstance(data, dict) or set(data) != {"slot_id"}:
            fail("예약 시간을 선택해 주세요.")
        with transaction.atomic():
            Upload.objects.select_for_update().get(pk=upload.pk)
            slot = get_object_or_404(ReservationSlot.objects.select_for_update(), pk=identifier(data["slot_id"]), upload=upload)
            if slot.closed or slot.starts_at <= timezone.now() or slot.subject_row_id is None:
                fail("예약할 수 없는 일정입니다.")
            if Reservation.objects.filter(slot__upload=upload, created_by_session=request.session.session_key,
                    cancelled=False, slot__starts_at__lt=slot.ends_at, slot__ends_at__gt=slot.starts_at).exists():
                fail("이미 같은 시간에 예약한 일정이 있습니다.")
            if slot.reservations.filter(cancelled=False).count() >= slot.capacity:
                fail("예약 정원이 마감되었습니다.")
            item = Reservation.objects.create(slot=slot, created_by_session=request.session.session_key)
        return Response(reservation_payload(item), status=201)


class ReservationView(SessionView):
    parser_classes = [JSONParser]

    def patch(self, request, pk, reservation_id):
        upload, _ = reservation_upload(request, pk)
        if not isinstance(request.data, dict) or set(request.data) != {"cancelled"} or request.data["cancelled"] is not True:
            fail("예약 취소 요청이 올바르지 않습니다.")
        with transaction.atomic():
            Upload.objects.select_for_update().get(pk=upload.pk)
            item = get_object_or_404(Reservation.objects.select_for_update().select_related("slot"),
                pk=reservation_id, slot__upload=upload, created_by_session=request.session.session_key)
            if item.slot.starts_at <= timezone.now():
                fail("시작된 예약은 취소할 수 없습니다.")
            item.cancelled = True
            item.save(update_fields=["cancelled"])
        return Response(reservation_payload(item))
