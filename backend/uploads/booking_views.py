"""Resources, slots and bookings of a generated reservation service. Deterministic; no model call."""
import re
import uuid
from collections import Counter
from datetime import date as date_type

from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import transaction
from django.db.models import Case, Count, F, IntegerField, Max as models_max, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date as iso_date, parse_datetime as iso_datetime
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .booking_rules import (ACTIVE, WHOLE_DAY, RuleError, default_rules, ensure_capacity, ensure_per_person,  # noqa: F401
                            month_states, normalize_request, occupancy, one_day, rule_owners, rules_for, rules_of,
                            validate_rules)
from .models import Booking, BookingEvent, Resource, Slot
from .reservation_service import parse_int, phone_digits
from .service_access import REVIEW_PERSONAS, requested_persona, service_upload
from .views import SessionView

PAGE = 20
FLAT_PAGE = 50
# action -> (allowed from, to). Reviewers may take every action; bookers only cancel their own.
PAID = Q(payment__iregex=r"(완료|납부|결제됨|^y$|^yes$|^paid$|^true$)")
PAYMENT_ACTIONS = {"mark_paid": "결제완료", "mark_unpaid": "미결제"}
ACTIONS = {
    "approve": (("requested", "waiting"), "approved"),
    "reject": (("requested", "waiting"), "rejected"),
    "cancel": (("requested", "approved", "waiting", "won"), "cancelled"),
    "check_in": (("approved", "won"), "in_use"),
    "complete": (("approved", "in_use", "won"), "completed"),
    "reopen": (("rejected", "cancelled", "completed", "other", "lost"), "requested"),
}


def fail(message):
    raise ValidationError({"detail": message})


def identifier(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        fail("선택한 항목이 올바르지 않습니다.")


PAGE_SIZES = (10, 20)


def page_size(request):
    """20 a page unless the screen asks for one of the other sizes it is allowed."""
    try:
        size = int(request.query_params.get("size", PAGE))
    except ValueError:
        size = PAGE
    return size if size in PAGE_SIZES else PAGE


def paginated(query, request):
    try:
        page = int(request.query_params.get("page", "1"))
    except ValueError:
        fail("페이지 번호가 올바르지 않습니다.")
    size = page_size(request)
    count = query.count()
    if page < 1 or page > max(1, (count + size - 1) // size):
        fail("페이지 번호가 범위를 벗어났습니다.")
    return query[(page - 1) * size:page * size], {"page": page, "count": count, "size": size, "has_next": page * size < count}


def text_field(data, key, maximum, *, required=False):
    value = data.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str) or len(value.strip()) > maximum or (required and not value.strip()):
        fail(f"{key}: {'1~' if required else '최대 '}{maximum}자로 입력해 주세요.")
    return value.strip()


def resource_payload(resource, children=None, bookings=None):
    return {"id": str(resource.id), "name": resource.name, "level": resource.level, "path": resource.path,
            "parent": str(resource.parent_id) if resource.parent_id else None, "capacity": resource.capacity,
            "attributes": resource.attributes, "active": resource.active,
            "children_count": children if children is not None else resource.children.count(),
            "booking_count": bookings if bookings is not None else resource.bookings.filter(status__in=ACTIVE).count()}


# A slot's capacity counts people, like the attendance the sheet recorded on it.
SLOT_PEOPLE = Sum(Coalesce("bookings__party_size", Value(1)), filter=Q(bookings__status__in=ACTIVE))


def slot_people(slot):
    return slot.bookings.filter(status__in=ACTIVE).aggregate(n=Sum(Coalesce("party_size", Value(1))))["n"] or 0


def slot_payload(slot, booked=None):
    if booked is None:
        booked = slot_people(slot)
    remaining = None if slot.capacity is None else max(0, slot.capacity - slot.imported_count - booked)
    return {"id": str(slot.id), "resource": str(slot.resource_id) if slot.resource_id else None,
            "resource_name": slot.resource.name if slot.resource_id else "",
            "date": slot.date.isoformat() if slot.date else None,
            "starts_at": slot.starts_at.isoformat() if slot.starts_at else None,
            "ends_at": slot.ends_at.isoformat() if slot.ends_at else None,
            "time_slot": slot.time_slot, "capacity": slot.capacity, "imported_count": slot.imported_count,
            "booked": booked, "remaining": remaining, "closed": slot.closed}


def format_phone(digits):
    if not digits:
        return ""
    head = 2 if digits.startswith("02") else 3
    return f"{digits[:head]}-{digits[head:-4]}-{digits[-4:]}"


def mask_phone(digits):
    if not digits:
        return ""
    head = 2 if digits.startswith("02") else 3
    return f"{digits[:head]}-{'*' * len(digits[head:-4])}-{digits[-4:]}"


def mask_name(name):
    """홍길동 → 홍*동, 홍길 → 홍*: enough to recognise one's own booking in a list, not to read someone else's."""
    name = (name or "").strip()
    if len(name) <= 1:
        return name
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


def hint_phone(digits):
    """010-5***-1231: the first digit of the middle group stays, so a booker can tell their numbers apart."""
    if not digits:
        return ""
    head = 2 if digits.startswith("02") else 3
    middle = digits[head:-4]
    return f"{digits[:head]}-{middle[:1]}{'*' * (len(middle) - 1)}-{digits[-4:]}"


PIN = re.compile(r"\d{4}")
LOOKUP_TRIES = 5
LOOKUP_LOCK_SECONDS = 600
VERIFIED = "verified_bookings"  # session key: bookings this browser proved it owns by name, phone and PIN


def verified_of(request):
    """Bookings this browser has opened with their name, phone number and PIN, besides the ones it made."""
    return set(request.session.get(VERIFIED, []))


def owns(booking, session_key, verified=None):
    """Opened with its PIN in this browser; a booking made here before PINs existed opens by the browser alone."""
    if str(booking.id) in (verified or ()):
        return True
    return bool(session_key) and booking.created_by_session == session_key and not booking.password


def booking_payload(item, session_key="", events=False, verified=None, reveal=False, masked=False):
    """reveal shows the whole phone number: to the booker for their own, to reviewers in the detail only.
    masked is a booker's list before the PIN: name and number half hidden, notes left out."""
    mine = owns(item, session_key, verified)
    payload = {"id": str(item.id),
               "resource": {"id": str(item.resource_id), "name": item.resource.name, "path": item.resource.path} if item.resource_id else None,
               "slot": str(item.slot_id) if item.slot_id else None,
               "booker": item.booker, "phone": format_phone(item.phone) if reveal else mask_phone(item.phone),
               "party_size": item.party_size,
               "date": item.date.isoformat() if item.date else None,
               "starts_at": item.starts_at.isoformat() if item.starts_at else None,
               "ends_at": item.ends_at.isoformat() if item.ends_at else None,
               "time_slot": item.time_slot, "status": item.status, "status_label": item.status_label,
               "purpose": item.purpose, "amount": str(item.amount) if item.amount is not None else None,
               "payment": item.payment, "staff": item.staff, "organization": item.organization,
               "attributes": item.attributes, "processing_note": item.processing_note,
               "requested_at": item.requested_at.isoformat() if item.requested_at else None,
               "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
               "imported": item.source_row_id is not None,
               "mine": mine}
    if masked and not mine:
        payload.update(booker=mask_name(item.booker), phone=hint_phone(item.phone), purpose="", processing_note="", attributes={},
                       amount=None, payment="", locked=True)
        return payload
    if events:
        payload["events"] = [{"from": event.from_status, "to": event.to_status, "persona": event.persona,
                              "note": event.note, "at": event.created_at.isoformat()} for event in item.events.all()]
    return payload


def scope_filter(config, persona, scope, bookings):
    """Restrict bookings to the persona's own range: a staff name, an organization, or a resource branch."""
    column = persona.get("scopeColumn") or 0
    if not column or not scope:
        return bookings
    booking_cfg = config["booking"]
    resource_columns = config["resources"]["columns"]
    if column in resource_columns:
        depth = resource_columns.index(column)
        prefix_filter = Q(resource__path__startswith=scope + " / ") | Q(resource__path=scope)
        if depth == 0:
            return bookings.filter(prefix_filter)
        return bookings.filter(Q(resource__path__contains=" / " + scope + " / ") | Q(resource__path__endswith=" / " + scope))
    if column == booking_cfg.get("staffColumn"):
        return bookings.filter(staff=scope)
    if column == booking_cfg.get("organizationColumn"):
        return bookings.filter(organization=scope)
    return bookings.filter(**{f"attributes__{column_label(config, column)}": scope})


def column_label(config, number):
    labels = config.get("columnLabels") or []
    return labels[number - 1] if 0 < number <= len(labels) else f"컬럼 {number}"


SUMMARY_KEYS = ("기록 건수", "기록 기준 금액", "자주 쓰인 시간대", "평균 인원", "평균 이용 기간", "원본 코드")
MAX_FACET_VALUES = 12
CLOCK_VALUE = re.compile(r"^\d{1,2}:\d{2}$")
MAX_GROUP_CHIPS = 20


def _number_of(text):
    cleaned = re.sub(r"[^\d.]", "", str(text).split("~")[0])
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def resource_facets(upload):
    """Filter choices from what the resources carry: small value sets, numeric ranges and top-level groups."""
    leaves = Resource.objects.filter(upload=upload, active=True).annotate(children_total=Count("children")).filter(children_total=0)
    values, numbers = {}, {}
    total = 0
    for attributes, capacity in leaves.values_list("attributes", "capacity"):
        total += 1
        if capacity is not None:
            numbers.setdefault("정원", []).append(float(capacity))
        for key, value in (attributes or {}).items():
            if key in SUMMARY_KEYS and key != "기록 기준 금액":
                continue
            text = str(value).strip()
            if not text:
                continue
            number = _number_of(text)
            if number is not None and (re.fullmatch(r"[\d,.]+\s*원?", text) or key == "기록 기준 금액" or key == "정원"):
                numbers.setdefault(key, []).append(number)
            values.setdefault(key, Counter())[text[:60]] += 1
    facets = []
    for key, counter in values.items():
        if all(CLOCK_VALUE.match(value) for value in counter):
            continue  # opening and closing hours describe the place; nobody filters by them
        if 2 <= len(counter) <= MAX_FACET_VALUES and sum(counter.values()) >= 2 and key not in numbers:
            facets.append({"label": key, "values": [{"value": value, "count": count} for value, count in counter.most_common()]})
    capacity_values = sorted(numbers.get("정원", []))
    ranges = [{"label": key, "min": min(items), "max": max(items)} for key, items in numbers.items()
              if len(items) >= 2 and min(items) < max(items)
              and (key == "정원" or sorted(items) != capacity_values)]  # the capacity's source column is the same facet
    groups = []
    tops = list(Resource.objects.filter(upload=upload, active=True, level=0).annotate(children_total=Count("children")).order_by("path"))
    if 1 < len(tops) <= MAX_GROUP_CHIPS and any(top.children_total for top in tops):
        groups = [{"id": str(top.id), "name": top.name, "count": top.children_total} for top in tops]
    return {"total": total, "facets": facets[:6], "ranges": ranges[:4], "groups": groups}


def _matches_numbers(resource, limits):
    for key, (low, high) in limits.items():
        raw = resource.capacity if key == "정원" else (resource.attributes or {}).get(key)
        number = _number_of(raw) if raw is not None else None
        if number is None or (low is not None and number < low) or (high is not None and number > high):
            return False
    return True


def resource_summary(upload, resource, with_slots):
    """What a booker wants on a card before opening it: how much sits under it, how busy it is, and the next open session."""
    under = Q(resource=resource) | Q(resource__path__startswith=resource.path + " / ")
    bookings = Booking.objects.filter(upload=upload).filter(under).exclude(status__in=("cancelled", "rejected", "lost"))
    today = timezone.localdate()
    leaves = Resource.objects.filter(upload=upload, active=True, path__startswith=resource.path + " / ") \
        .annotate(n=Count("children")).filter(n=0).count()
    summary = {"leaves": leaves, "booked": bookings.count(),
               "recent": (bookings.aggregate(last=models_max("date"))["last"] or None),
               "upcoming": bookings.filter(status__in=ACTIVE, date__gte=today).count(), "next_slot": None, "open_slots": 0}
    if summary["recent"]:
        summary["recent"] = summary["recent"].isoformat()
    if with_slots:
        slots = Slot.objects.filter(upload=upload, closed=False, date__gte=today) \
            .filter(Q(resource=resource) | Q(resource__path__startswith=resource.path + " / ")) \
            .select_related("resource").annotate(booked=SLOT_PEOPLE).order_by("date", "starts_at")
        summary["open_slots"] = slots.count()
        for slot in slots[:30]:
            item = slot_payload(slot, slot.booked or 0)
            if item["remaining"] is None or item["remaining"] > 0:
                summary["next_slot"] = item
                break
    return summary


class ResourceFacetsView(SessionView):
    def get(self, request, pk):
        upload = service_upload(request, pk)
        return Response(resource_facets(upload))


class ResourcesView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = service_upload(request, pk)
        params = request.query_params
        resources = Resource.objects.filter(upload=upload)
        if params.get("all") != "1":
            resources = resources.filter(active=True)
        if params.get("flat") in ("leaf", "any"):
            return Response(self.flat(upload, resources, params))
        query = (params.get("q") or "").strip()
        parent = params.get("parent")
        filters = [item.split(":", 1) for item in params.getlist("f") if ":" in item]
        limits = {}
        for item in params.getlist("min") + params.getlist("max"):
            if ":" not in item:
                continue
            key, raw = item.split(":", 1)
            try:
                number = float(raw)
            except ValueError:
                fail("범위 필터 값이 올바르지 않습니다.")
            low, high = limits.get(key, (None, None))
            limits[key] = (number, high) if item in params.getlist("min") else (low, number)
        filtering = bool(query or filters or limits or params.get("group"))
        if params.get("group"):
            group = get_object_or_404(Resource, pk=identifier(params["group"]), upload=upload)
            resources = resources.filter(path__startswith=group.path + " / ")
            if not (query or filters or limits):
                resources = resources.filter(parent=group)  # the group's own children, not every descendant
        if query:
            resources = resources.filter(path__icontains=query[:100])
        for key, value in filters[:8]:
            resources = resources.filter(**{f"attributes__{key[:60]}": value[:60]})
        if filtering:
            # filters describe leaves; a matching branch node only shows up when it carries the attribute itself
            resources = resources.annotate(children_total=Count("children", distinct=True))
            if filters or limits:
                resources = resources.filter(children_total=0)
        elif parent:
            resources = resources.filter(parent_id=identifier(parent))
        else:
            resources = resources.filter(level=0)
        resources = resources.annotate(children_total=Count("children", distinct=True),
                                       active_bookings=Count("bookings", filter=Q(bookings__status__in=ACTIVE), distinct=True)).order_by("path")
        if limits:
            matched = [item for item in resources[:5000] if _matches_numbers(item, limits)]
            try:
                page = int(params.get("page", "1"))
            except ValueError:
                fail("페이지 번호가 올바르지 않습니다.")
            size = page_size(request)
            if page < 1 or page > max(1, (len(matched) + size - 1) // size):
                fail("페이지 번호가 범위를 벗어났습니다.")
            items = matched[(page - 1) * size:page * size]
            paging = {"page": page, "count": len(matched), "size": size, "has_next": page * size < len(matched)}
        else:
            items, paging = paginated(resources, request)
        rows = [resource_payload(item, item.children_total, item.active_bookings) for item in items]
        if params.get("summary") == "1":
            with_slots = upload.service_config.get("sheetKind") == "schedule_slots"
            for row, item in zip(rows, items):
                row["summary"] = resource_summary(upload, item, with_slots)
        return Response({**paging, "levels": upload.service_config["resources"]["levels"], "filtering": filtering, "resources": rows})

    def flat(self, upload, resources, params):
        """Every resource (or only the bookable leaves) in path order, for a search-as-you-type dropdown."""
        query = (params.get("q") or "").strip()[:100]
        if query:
            resources = resources.filter(path__icontains=query)
        resources = resources.annotate(children_total=Count("children", distinct=True))
        if params.get("flat") == "leaf":
            resources = resources.filter(children_total=0)
        resources = resources.order_by("path")
        try:
            offset = max(0, int(params.get("offset", "0")))
        except ValueError:
            fail("시작 위치가 올바르지 않습니다.")
        count = resources.count()
        items = resources[offset:offset + FLAT_PAGE]
        return {"count": count, "offset": offset, "has_next": offset + FLAT_PAGE < count,
                "resources": [{"id": str(item.id), "name": item.name, "path": item.path, "level": item.level,
                               "capacity": item.capacity, "children_count": item.children_total} for item in items]}

    def post(self, request, pk):
        upload = service_upload(request, pk)
        requested_persona(request, upload.service_config, "manage_resources")
        data = request.data if isinstance(request.data, dict) else {}
        name = text_field(data, "name", 300, required=True)
        parent = None
        if data.get("parent_id"):
            parent = get_object_or_404(Resource, pk=identifier(data["parent_id"]), upload=upload)
        capacity = data.get("capacity")
        if capacity is not None and (type(capacity) is not int or not 1 <= capacity <= 100_000):
            fail("정원은 1 이상의 정수로 입력해 주세요.")
        attributes = data.get("attributes") or {}
        if not isinstance(attributes, dict) or any(not isinstance(k, str) or not isinstance(v, str) or len(v) > 500 for k, v in attributes.items()):
            fail("속성은 이름과 값이 모두 문자열이어야 합니다.")
        path = f"{parent.path} / {name}" if parent else name
        if Resource.objects.filter(upload=upload, path=path).exists():
            fail("같은 이름의 항목이 이미 있습니다.")
        resource = Resource.objects.create(upload=upload, parent=parent, level=parent.level + 1 if parent else 0,
                                           name=name, path=path, capacity=capacity, attributes=attributes)
        return Response(resource_payload(resource, 0, 0), status=201)


class ResourceView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk, resource_id):
        upload = service_upload(request, pk)
        resource = get_object_or_404(Resource, pk=resource_id, upload=upload)
        payload = resource_payload(resource)
        payload["ancestors"] = []
        node = resource.parent
        while node is not None:
            payload["ancestors"].insert(0, {"id": str(node.id), "name": node.name})
            node = node.parent
        return Response(payload)

    def patch(self, request, pk, resource_id):
        upload = service_upload(request, pk)
        requested_persona(request, upload.service_config, "manage_resources")
        data = request.data if isinstance(request.data, dict) else {}
        if not data or set(data) - {"name", "capacity", "attributes", "active", "persona"}:
            fail("이름, 정원, 속성 또는 사용 여부를 입력해 주세요.")
        with transaction.atomic():
            resource = get_object_or_404(Resource.objects.select_for_update(), pk=resource_id, upload=upload)
            if "name" in data:
                name = text_field(data, "name", 300, required=True)
                new_path = f"{resource.parent.path} / {name}" if resource.parent_id else name
                if new_path != resource.path and Resource.objects.filter(upload=upload, path=new_path).exists():
                    fail("같은 이름의 항목이 이미 있습니다.")
                old_prefix = resource.path + " / "
                resource.name, resource.path = name, new_path
                for child in Resource.objects.filter(upload=upload, path__startswith=old_prefix):
                    child.path = new_path + " / " + child.path[len(old_prefix):]
                    child.save(update_fields=["path"])
            if "capacity" in data:
                capacity = data["capacity"]
                if capacity is not None and (type(capacity) is not int or not 1 <= capacity <= 100_000):
                    fail("정원은 1 이상의 정수로 입력해 주세요.")
                resource.capacity = capacity
            if "attributes" in data:
                attributes = data["attributes"]
                if not isinstance(attributes, dict) or any(not isinstance(k, str) or not isinstance(v, str) or len(v) > 500 for k, v in attributes.items()):
                    fail("속성은 이름과 값이 모두 문자열이어야 합니다.")
                resource.attributes = attributes
            if "active" in data:
                if type(data["active"]) is not bool:
                    fail("사용 여부는 참·거짓이어야 합니다.")
                resource.active = data["active"]
            resource.save()
        return Response(resource_payload(resource))

    def delete(self, request, pk, resource_id):
        upload = service_upload(request, pk)
        requested_persona(request, upload.service_config, "manage_resources")
        with transaction.atomic():
            resource = get_object_or_404(Resource.objects.select_for_update(), pk=resource_id, upload=upload)
            if Booking.objects.filter(upload=upload, resource__path__startswith=resource.path).exists():
                resource.active = False
                resource.save(update_fields=["active"])
                Resource.objects.filter(upload=upload, path__startswith=resource.path + " / ").update(active=False)
                return Response({"deleted": False, "deactivated": True,
                                 "detail": "예약 기록이 있어 삭제하지 않고 사용 중지했습니다."})
            resource.delete()
        return Response({"deleted": True, "deactivated": False})


def _moment(value, label):
    if value in (None, ""):
        return None
    parsed = iso_datetime(value) if isinstance(value, str) else None
    if parsed is None:
        fail(f"{label}은 날짜·시간 형식으로 입력해 주세요.")
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _date(value, label):
    if value in (None, ""):
        return None
    parsed = iso_date(value) if isinstance(value, str) else None
    if parsed is None:
        fail(f"{label}은 YYYY-MM-DD 형식으로 입력해 주세요.")
    return parsed


class SlotsView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = service_upload(request, pk)
        slots = Slot.objects.filter(upload=upload).select_related("resource")
        if request.query_params.get("resource"):
            slots = slots.filter(resource_id=identifier(request.query_params["resource"]))
        if request.query_params.get("from"):
            slots = slots.filter(Q(date__gte=_date(request.query_params["from"], "시작일")) | Q(date__isnull=True))
        if request.query_params.get("available") == "1":
            today = timezone.localdate()
            slots = slots.filter(closed=False).filter(Q(date__gte=today) | Q(date__isnull=True, starts_at__gte=timezone.now()))
        slots = slots.annotate(active_people=SLOT_PEOPLE).order_by("date", "starts_at", "time_slot", "id")
        items, paging = paginated(slots, request)
        return Response({**paging, "slots": [slot_payload(slot, slot.active_people or 0) for slot in items]})

    def post(self, request, pk):
        upload = service_upload(request, pk)
        requested_persona(request, upload.service_config, "manage_schedule")
        data = request.data if isinstance(request.data, dict) else {}
        resource = None
        if data.get("resource_id"):
            resource = get_object_or_404(Resource, pk=identifier(data["resource_id"]), upload=upload)
        elif Resource.objects.filter(upload=upload).exists():
            fail("일정을 만들 항목을 선택해 주세요.")
        day = _date(data.get("date"), "날짜")
        starts, ends = _moment(data.get("starts_at"), "시작 시간"), _moment(data.get("ends_at"), "종료 시간")
        time_slot = text_field(data, "time_slot", 120)
        if day is None and starts is None:
            fail("날짜 또는 시작 시간을 입력해 주세요.")
        if starts and ends and ends <= starts:
            fail("종료 시간은 시작 시간 이후여야 합니다.")
        if day is None:
            day = timezone.localtime(starts).date()
        capacity = data.get("capacity")
        if capacity is not None and (type(capacity) is not int or not 1 <= capacity <= 100_000):
            fail("정원은 1 이상의 정수로 입력해 주세요.")
        if resource and starts and ends and Slot.objects.filter(upload=upload, resource=resource, starts_at__lt=ends,
                                                                ends_at__gt=starts).exists():
            fail("이 항목에 시간이 겹치는 일정이 있습니다.")
        slot = Slot.objects.create(upload=upload, resource=resource, date=day, starts_at=starts, ends_at=ends,
                                   time_slot=time_slot, capacity=capacity)
        return Response(slot_payload(slot, 0), status=201)


class SlotView(SessionView):
    parser_classes = [JSONParser]

    def patch(self, request, pk, slot_id):
        upload = service_upload(request, pk)
        requested_persona(request, upload.service_config, "manage_schedule")
        data = request.data if isinstance(request.data, dict) else {}
        if not data or set(data) - {"capacity", "closed", "persona"}:
            fail("정원 또는 마감 여부를 입력해 주세요.")
        with transaction.atomic():
            slot = get_object_or_404(Slot.objects.select_for_update(), pk=slot_id, upload=upload)
            if "capacity" in data:
                capacity = data["capacity"]
                if capacity is not None and (type(capacity) is not int or not 1 <= capacity <= 100_000):
                    fail("정원은 1 이상의 정수로 입력해 주세요.")
                slot.capacity = capacity
            if "closed" in data:
                if type(data["closed"]) is not bool:
                    fail("마감 여부는 참·거짓이어야 합니다.")
                slot.closed = data["closed"]
            slot.save()
        return Response(slot_payload(slot))

    def delete(self, request, pk, slot_id):
        upload = service_upload(request, pk)
        requested_persona(request, upload.service_config, "manage_schedule")
        slot = get_object_or_404(Slot, pk=slot_id, upload=upload)
        if slot.bookings.filter(status__in=ACTIVE).exists():
            fail("예약이 있는 일정은 삭제할 수 없습니다. 마감해 주세요.")
        slot.delete()
        return Response({"deleted": True})


def _slot_check(slot, party):
    if slot.closed:
        fail("마감된 일정입니다.")
    if slot.capacity is not None:
        remaining = slot.capacity - slot.imported_count - slot_people(slot)
        if (party or 1) > remaining:
            fail("이 일정은 정원이 가득 찼습니다." if remaining <= 0 else f"이 일정은 {remaining}명까지만 예약할 수 있습니다.")


def _reopen_check(upload, booking):
    """A booking coming back to life takes a place again, so it must still fit."""
    if booking.slot_id:
        _slot_check(Slot.objects.select_for_update().get(pk=booking.slot_id), booking.party_size)
        return
    if booking.resource_id is None:
        return
    rules, _ = rules_for(upload.service_config, booking.resource)
    held = occupancy(booking, rules)
    if held is None:
        return
    Resource.objects.select_for_update().get(pk=booking.resource_id)
    try:
        ensure_capacity(upload, booking.resource, rules, held[:3], booking.party_size)
    except RuleError as exc:
        fail(f"다시 열 수 없습니다. {exc}")


class BookingsView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk):
        upload = service_upload(request, pk)
        config = upload.service_config
        persona = requested_persona(request, config, "my_reservations", "review_reservations", "dashboard", "manage_payments")
        session_key = request.session.session_key or ""
        bookings = Booking.objects.filter(upload=upload).select_related("resource")
        verified = verified_of(request)
        masked = False
        if persona["id"] == "booker" or request.query_params.get("mine") == "1":
            # 비회원 예약 조회: made in this browser, or found by name and phone; either way shown masked until the PIN opens one
            masked = True
            mine = Q(id__in=verified)
            if session_key:
                mine |= Q(created_by_session=session_key)
            name = str(request.query_params.get("name") or "").strip()[:200]
            phone = phone_digits(request.query_params.get("phone"))
            if request.query_params.get("name") or request.query_params.get("phone"):
                if request.query_params.get("phone") and not phone:
                    fail("전화번호를 010-1234-5678처럼 입력해 주세요.")
                # either one finds them; the list stays masked and each still opens only with its PIN
                found = Q(phone=phone) if phone else Q()
                if name:
                    found &= Q(booker__iexact=name)
                mine = found & ~Q(password="")
            bookings = bookings.filter(mine)
        elif persona["id"] in ("staff", "org_manager"):
            scope = (request.query_params.get("scope") or "").strip()
            if not scope:
                fail("담당 범위를 선택해 주세요.")
            bookings = scope_filter(config, persona, scope, bookings)
        status = request.query_params.get("status")
        if status:
            if status not in Booking.Kind.values:
                fail("알 수 없는 상태입니다.")
            bookings = bookings.filter(status=status)
        if request.query_params.get("resource"):
            resource = get_object_or_404(Resource, pk=identifier(request.query_params["resource"]), upload=upload)
            bookings = bookings.filter(Q(resource=resource) | Q(resource__path__startswith=resource.path + " / "))
        payment = request.query_params.get("payment")
        if payment in ("paid", "unpaid"):
            bookings = bookings.filter(PAID) if payment == "paid" else bookings.exclude(PAID)
        if request.query_params.get("from"):
            bookings = bookings.filter(date__gte=_date(request.query_params["from"], "시작일"))
        if request.query_params.get("to"):
            bookings = bookings.filter(date__lte=_date(request.query_params["to"], "종료일"))
        query = (request.query_params.get("q") or "").strip()[:100]
        if query:
            matches = (Q(booker__icontains=query) | Q(purpose__icontains=query) | Q(resource__path__icontains=query)
                       | Q(staff__icontains=query) | Q(organization__icontains=query) | Q(status_label__icontains=query))
            digits = re.sub(r"\D", "", query)
            if len(digits) >= 4:
                matches |= Q(phone__contains=digits)
            bookings = bookings.filter(matches)
        if masked:  # a booker's own list: what is coming, soonest first, then what is over, latest first
            today = timezone.localdate()
            live = Q(status__in=ACTIVE, date__gte=today)
            bookings = bookings.annotate(over=Case(When(live, then=Value(0)), default=Value(1), output_field=IntegerField()),
                                         soon=Case(When(live, then=F("date")), default=None),
                                         late=Case(When(live, then=None), default=F("date"))).order_by("over", "soon", F("late").desc(nulls_last=True), "-created_at")
        items, paging = paginated(bookings, request)
        return Response({**paging, "bookings": [booking_payload(item, session_key, verified=verified, reveal=persona["id"] == "booker", masked=masked)
                                                for item in items]})

    def post(self, request, pk):
        upload = service_upload(request, pk)
        config = upload.service_config
        persona = requested_persona(request, config, "make_reservation", "review_reservations")
        if not config["booking"]["acceptsNew"]:
            fail("이 서비스는 새 예약을 받지 않습니다.")
        data = request.data if isinstance(request.data, dict) else {}
        if not request.session.session_key:
            request.session.create()
        booking_cfg = config["booking"]
        resource = slot = None
        if data.get("slot_id"):
            slot = get_object_or_404(Slot.objects.select_related("resource"), pk=identifier(data["slot_id"]), upload=upload)
            resource = slot.resource
        elif data.get("resource_id"):
            resource = get_object_or_404(Resource, pk=identifier(data["resource_id"]), upload=upload, active=True)
        elif Resource.objects.filter(upload=upload).exists():
            fail("예약할 항목을 선택해 주세요.")
        if resource is not None and slot is None:
            children = list(resource.children.filter(active=True).values_list("name", flat=True)[:4])
            if children:
                fail(f'"{resource.name}"은(는) 묶음입니다. 그 안의 {", ".join(children[:3])}{" 등" if len(children) > 3 else ""} 중 하나를 골라 예약해 주세요.')
        day = _date(data.get("date"), "날짜")
        end_day = _date(data.get("end_date"), "종료일")
        starts, ends = _moment(data.get("starts_at"), "시작 시간"), _moment(data.get("ends_at"), "종료 시간")
        time_slot = text_field(data, "time_slot", 120)
        party = data.get("party_size")
        if party is not None and (type(party) is not int or not 1 <= party <= 100_000):
            fail("인원은 1 이상의 정수로 입력해 주세요.")
        rules, owner = rules_for(config, resource)
        window = None
        if slot is not None:
            day, starts, ends, time_slot = slot.date, slot.starts_at, slot.ends_at, slot.time_slot
        else:
            try:
                moment = normalize_request(rules, day=day, end_day=end_day, starts=starts, ends=ends, time_slot=time_slot)
            except RuleError as exc:
                fail(str(exc))
            day, starts, ends, time_slot, window = (moment["date"], moment["starts_at"], moment["ends_at"], moment["time_slot"],
                                                    moment["window"])
            timed = rules["timeMode"] in ("time_range", "time_slot") and starts is not None
            if persona["id"] == "booker" and (day < timezone.localdate() or (timed and starts < timezone.now())):
                fail("지난 날짜·시간은 예약할 수 없습니다.")
        booker = text_field(data, "booker", 200, required=persona["id"] == "booker")
        phone = phone_digits(data.get("phone"))
        if data.get("phone") and not phone:
            fail("전화번호를 010-1234-5678처럼 입력해 주세요.")
        if persona["id"] == "booker" and not phone:
            fail("예약 확인과 1인 예약 수 확인을 위해 전화번호를 입력해 주세요.")
        pin = str(data.get("password") or "")
        if pin and not PIN.fullmatch(pin):
            fail("예약 비밀번호는 숫자 4자리로 입력해 주세요.")
        if persona["id"] == "booker" and not pin:
            fail("예약을 다시 확인할 때 쓸 비밀번호 숫자 4자리를 정해 주세요.")
        purpose = text_field(data, "purpose", 2000)
        with transaction.atomic():
            if resource is not None:
                Resource.objects.select_for_update().get(pk=resource.pk)
            try:
                ensure_per_person(upload, rules, owner, day, phone)
            except RuleError as exc:
                fail(str(exc))
            if slot is not None:
                _slot_check(Slot.objects.select_for_update().get(pk=slot.pk), party)
            else:
                try:
                    ensure_capacity(upload, resource, rules, window, party)
                except RuleError as exc:
                    fail(str(exc))
            status = "requested" if booking_cfg["approvalRequired"] else "approved"
            if persona["id"] != "booker":
                status = data.get("status", "approved") if data.get("status") in ("requested", "approved") else "approved"
            booking = Booking.objects.create(upload=upload, resource=resource, slot=slot, booker=booker, phone=phone,
                                             created_by_session=request.session.session_key, party_size=party, date=day,
                                             starts_at=starts, ends_at=ends, time_slot=time_slot, status=status,
                                             status_label="", purpose=purpose, requested_at=timezone.now(),
                                             password=make_password(pin) if pin else "")
            BookingEvent.objects.create(booking=booking, from_status="", to_status=status, persona=persona["id"])
        # the reply to the booker who just made it is theirs; opening it again later takes the PIN
        return Response(booking_payload(booking, request.session.session_key, events=True, verified={str(booking.id)}, reveal=True), status=201)


class BookingView(SessionView):
    parser_classes = [JSONParser]

    def get(self, request, pk, booking_id):
        upload = service_upload(request, pk)
        persona = requested_persona(request, upload.service_config, "my_reservations", "review_reservations", "manage_payments")
        booking = get_object_or_404(Booking.objects.select_related("resource"), pk=booking_id, upload=upload)
        session_key = request.session.session_key or ""
        verified = verified_of(request)
        if persona["id"] == "booker" and not owns(booking, session_key, verified):
            fail("예약 비밀번호를 입력해야 상세 내용을 볼 수 있습니다.")
        return Response(booking_payload(booking, session_key, events=True, verified=verified, reveal=True))

    def patch(self, request, pk, booking_id):
        upload = service_upload(request, pk)
        persona = requested_persona(request, upload.service_config, "my_reservations", "review_reservations", "manage_payments")
        data = request.data if isinstance(request.data, dict) else {}
        action = data.get("action")
        if action in PAYMENT_ACTIONS:
            if "manage_payments" not in persona["features"]:
                fail("이 역할에서는 결제를 처리할 수 없습니다.")
            note = text_field(data, "note", 2000)
            with transaction.atomic():
                booking = get_object_or_404(Booking.objects.select_for_update(of=("self",)).select_related("resource"),
                                            pk=booking_id, upload=upload)
                booking.payment = PAYMENT_ACTIONS[action]
                if note:
                    booking.processing_note = note
                booking.save(update_fields=["payment", "processing_note", "updated_at"])
                BookingEvent.objects.create(booking=booking, from_status=booking.status, to_status=booking.status,
                                            persona=persona["id"], note=PAYMENT_ACTIONS[action] + (f" · {note}" if note else ""))
            return Response(booking_payload(booking, request.session.session_key or "", events=True, reveal=True))
        if action == "edit":
            return _edit(request, upload, persona, booking_id, data)
        if action not in ACTIONS:
            fail("승인·거절·취소·이용 시작·완료 중 하나를 선택해 주세요.")
        note = text_field(data, "note", 2000, required=action == "reject")
        allowed_from, target = ACTIONS[action]
        session_key = request.session.session_key or ""
        verified = verified_of(request)
        with transaction.atomic():
            booking = get_object_or_404(Booking.objects.select_for_update(of=("self",)).select_related("resource"),
                                        pk=booking_id, upload=upload)
            if persona["id"] == "booker":
                if not owns(booking, session_key, verified):
                    fail("예약 비밀번호를 입력한 뒤에 바꿀 수 있습니다.")
                if action != "cancel":
                    fail("예약자는 취소만 할 수 있습니다.")
            elif persona["id"] not in REVIEW_PERSONAS:
                fail("이 역할에서는 예약을 처리할 수 없습니다.")
            if booking.status not in allowed_from:
                fail("현재 상태에서는 할 수 없는 처리입니다.")
            if action == "reopen":
                _reopen_check(upload, booking)
            previous = booking.status
            booking.status = target
            booking.status_label = ""
            if note:
                booking.processing_note = note
            booking.save(update_fields=["status", "status_label", "processing_note", "updated_at"])
            BookingEvent.objects.create(booking=booking, from_status=previous, to_status=target, persona=persona["id"], note=note)
        return Response(booking_payload(booking, session_key, events=True, verified=verified, reveal=True))


EDITABLE = ("requested", "approved", "waiting", "won")


def _edit(request, upload, persona, booking_id, data):
    """A booker changes the party size or the request of an open booking; a bigger party must still fit."""
    if persona["id"] != "booker":
        fail("예약자만 예약 내용을 수정할 수 있습니다.")
    if set(data) - {"persona", "action", "party_size", "purpose"}:
        fail("인원과 요청 사항만 수정할 수 있습니다. 날짜를 바꾸려면 취소하고 다시 예약해 주세요.")
    party = data.get("party_size")
    if party is not None and (type(party) is not int or not 1 <= party <= 100_000):
        fail("인원은 1 이상의 정수로 입력해 주세요.")
    purpose = text_field(data, "purpose", 2000) if "purpose" in data else None
    session_key = request.session.session_key or ""
    verified = verified_of(request)
    with transaction.atomic():
        booking = get_object_or_404(Booking.objects.select_for_update(of=("self",)).select_related("resource"), pk=booking_id, upload=upload)
        if not owns(booking, session_key, verified):
            fail("예약 비밀번호를 입력한 뒤에 수정할 수 있습니다.")
        if booking.status not in EDITABLE or (booking.date and booking.date < timezone.localdate()):
            fail("진행 중인 예약만 수정할 수 있습니다.")
        changes = []
        if party is not None and party != (booking.party_size or 1):
            if party > (booking.party_size or 1):  # only growing can overfill
                if booking.slot_id:
                    _slot_check(Slot.objects.select_for_update().get(pk=booking.slot_id), party - (booking.party_size or 1))
                elif booking.resource_id:
                    rules, _ = rules_for(upload.service_config, booking.resource)
                    held = occupancy(booking, rules)
                    if held is not None:
                        Resource.objects.select_for_update().get(pk=booking.resource_id)
                        try:
                            ensure_capacity(upload, booking.resource, rules, held[:3], party, exclude=booking.pk)
                        except RuleError as exc:
                            fail(str(exc))
            changes.append(f"인원 {booking.party_size or 1}→{party}명")
            booking.party_size = party
        if purpose is not None and purpose != booking.purpose:
            changes.append("요청 사항")
            booking.purpose = purpose
        if not changes:
            fail("바뀐 내용이 없습니다.")
        booking.save(update_fields=["party_size", "purpose", "updated_at"])
        BookingEvent.objects.create(booking=booking, from_status=booking.status, to_status=booking.status,
                                    persona=persona["id"], note="예약 수정 · " + ", ".join(changes))
    return Response(booking_payload(booking, session_key, events=True, verified=verified, reveal=True))


class BookingUnlockView(SessionView):
    """The PIN chosen when booking opens that one booking in this browser: its details, changes and cancelling."""
    parser_classes = [JSONParser]

    def post(self, request, pk, booking_id):
        upload = service_upload(request, pk)
        booking = get_object_or_404(Booking.objects.select_related("resource"), pk=booking_id, upload=upload)
        pin = str((request.data if isinstance(request.data, dict) else {}).get("password") or "")
        if not PIN.fullmatch(pin):
            fail("예약할 때 정한 비밀번호 숫자 4자리를 입력해 주세요.")
        tries_key = f"booking-unlock:{booking.pk}"
        tries = cache.get(tries_key, 0)
        if tries >= LOOKUP_TRIES:
            fail("비밀번호를 여러 번 틀려 10분 동안 열 수 없습니다. 잠시 뒤 다시 시도해 주세요.")
        if not booking.password or not check_password(pin, booking.password):
            cache.set(tries_key, tries + 1, LOOKUP_LOCK_SECONDS)
            left = LOOKUP_TRIES - tries - 1
            fail("비밀번호가 맞지 않습니다." + (f" {left}번 더 틀리면 10분 동안 열 수 없습니다." if 0 < left <= 2 else ""))
        cache.delete(tries_key)
        if not request.session.session_key:
            request.session.create()
        request.session[VERIFIED] = sorted(verified_of(request) | {str(booking.id)})[-200:]
        return Response(booking_payload(booking, request.session.session_key, events=True, verified=verified_of(request), reveal=True))


BULK_LIMIT = 100


class BookingBulkView(SessionView):
    """One status step over many bookings; a booking the step does not fit is skipped, not an error."""
    parser_classes = [JSONParser]

    def post(self, request, pk):
        upload = service_upload(request, pk)
        persona = requested_persona(request, upload.service_config, "review_reservations")
        if persona["id"] not in REVIEW_PERSONAS:
            fail("이 역할에서는 예약을 처리할 수 없습니다.")
        data = request.data if isinstance(request.data, dict) else {}
        action = data.get("action")
        if action not in ACTIONS:
            fail("승인·거절·취소·이용 시작·완료 중 하나를 선택해 주세요.")
        ids = data.get("ids")
        if not isinstance(ids, list) or not ids or len(ids) > BULK_LIMIT:
            fail(f"처리할 예약을 1~{BULK_LIMIT}건 골라 주세요.")
        ids = {identifier(value) for value in ids}
        note = text_field(data, "note", 2000, required=action == "reject")
        allowed_from, target = ACTIONS[action]
        done = skipped = 0
        with transaction.atomic():
            for booking in Booking.objects.select_for_update(of=("self",)).filter(upload=upload, pk__in=ids).order_by("date", "id"):
                if booking.status not in allowed_from:
                    skipped += 1
                    continue
                try:
                    with transaction.atomic():
                        if action == "reopen":
                            _reopen_check(upload, booking)
                        previous = booking.status
                        booking.status = target
                        booking.status_label = ""
                        if note:
                            booking.processing_note = note
                        booking.save(update_fields=["status", "status_label", "processing_note", "updated_at"])
                        BookingEvent.objects.create(booking=booking, from_status=previous, to_status=target,
                                                    persona=persona["id"], note=note)
                except ValidationError:
                    skipped += 1
                    continue
                done += 1
        return Response({"done": done, "skipped": len(ids) - done})


class AvailabilityView(SessionView):
    """What is still free on one resource: per day for a month, or per session or time block for one date."""

    def get(self, request, pk):
        upload = service_upload(request, pk)
        config = upload.service_config
        requested_persona(request, config, "make_reservation", "review_reservations", "browse_resources")
        resource = get_object_or_404(Resource, pk=identifier(request.query_params.get("resource")), upload=upload)
        rules, _ = rules_for(config, resource)
        basics = {"timeMode": rules["timeMode"], "capacityBy": rules["capacityBy"]}
        if request.query_params.get("date"):
            limit, state = one_day(upload, resource, rules, _date(request.query_params["date"], "날짜"))
            return Response({**basics, "limit": limit, **state})
        month = request.query_params.get("month") or timezone.localdate().strftime("%Y-%m")
        try:
            first = date_type.fromisoformat(month + "-01")
        except ValueError:
            fail("월은 YYYY-MM 형식으로 입력해 주세요.")
        following = (first.replace(day=28) + timezone.timedelta(days=4)).replace(day=1)
        limit, days = month_states(upload, resource, rules, first, following)
        return Response({**basics, "month": month, "limit": limit, "days": days})


def _owner_payload(owner):
    return {"id": str(owner["id"]), "name": owner["name"], "path": owner["path"]} if owner else None


class BookingRulesView(SessionView):
    """Booking rules of the service, or of one resource's branch (?resource= gives what that resource books under)."""
    parser_classes = [JSONParser]

    def payload(self, upload, resource=None):
        config = upload.service_config
        owners = rule_owners(upload)
        rules, owner = rules_for(config, resource, owners)
        return {"rules": rules, "source": _owner_payload(owner), "defaults": default_rules(config), "service": rules_of(config),
                "sheetKind": config["sheetKind"],
                "overrides": [_owner_payload(item) for item in sorted(owners.values(), key=lambda item: item["path"])]}

    def get(self, request, pk):
        upload = service_upload(request, pk)
        resource = None
        if request.query_params.get("resource"):
            resource = get_object_or_404(Resource, pk=identifier(request.query_params["resource"]), upload=upload)
        return Response(self.payload(upload, resource))

    def patch(self, request, pk):
        """rules for the service, or with resource_id for that branch; rules null with resource_id removes the branch's own."""
        upload = service_upload(request, pk)
        config = upload.service_config
        requested_persona(request, config, "manage_schedule", "manage_resources")
        data = request.data if isinstance(request.data, dict) else {}
        resource = None
        if data.get("resource_id"):
            resource = get_object_or_404(Resource, pk=identifier(data["resource_id"]), upload=upload)
        rules = None
        if not (resource is not None and data.get("rules") is None):
            try:
                rules = validate_rules(data.get("rules"))
            except RuleError as exc:
                fail(str(exc))
        with transaction.atomic():
            if resource is not None:
                Resource.objects.filter(pk=resource.pk).update(rules=rules)
                resource.refresh_from_db()
            else:
                upload = type(upload).objects.select_for_update().get(pk=upload.pk)
                upload.service_config["booking"]["rules"] = rules
                upload.service_config["booking"]["unit"] = rules["timeMode"]
                upload.save(update_fields=["service_config"])
        return Response(self.payload(upload, resource))


VOID = ("cancelled", "rejected", "lost")


def payment_summary(bookings):
    """What the payment desk owes attention: live bookings not yet paid, and the money still to collect."""
    live = bookings.exclude(status__in=VOID)
    unpaid = live.exclude(PAID)
    return {"paid": live.filter(PAID).count(), "unpaid": unpaid.count(),
            "unpaid_amount": float(unpaid.aggregate(total=Coalesce(Sum("amount"), Value(0, output_field=Booking._meta.get_field("amount"))))["total"])}


class BookingStatsView(SessionView):
    def get(self, request, pk):
        upload = service_upload(request, pk)
        config = upload.service_config
        persona = requested_persona(request, config, "dashboard", "review_reservations", "manage_payments")
        bookings = Booking.objects.filter(upload=upload)
        if persona["id"] in ("staff", "org_manager") and request.query_params.get("scope"):
            bookings = scope_filter(config, persona, request.query_params["scope"].strip(), bookings)
        counts = dict(bookings.values_list("status").annotate(n=Count("id")).values_list("status", "n"))
        today = timezone.localdate()
        top = (bookings.filter(resource__isnull=False).values("resource_id", "resource__name", "resource__path").annotate(n=Count("id")).order_by("-n")[:8])
        return Response({
            "total": sum(counts.values()),
            "counts": {status: counts.get(status, 0) for status in Booking.Kind.values},
            "upcoming": bookings.filter(status__in=ACTIVE, date__gte=today).count(),
            "today": bookings.filter(status__in=ACTIVE, date=today).count(),
            "imported": bookings.filter(source_row__isnull=False).count(),
            "new": bookings.filter(source_row__isnull=True).count(),
            "resources": Resource.objects.filter(upload=upload, active=True).count(),
            "top_resources": [{"id": str(item["resource_id"]), "name": item["resource__name"], "path": item["resource__path"], "count": item["n"]}
                              for item in top],
            "payments": payment_summary(bookings),
        })


class ScopesView(SessionView):
    """Distinct values a staff or organization persona can pick as its range."""

    def get(self, request, pk):
        upload = service_upload(request, pk)
        config = upload.service_config
        persona = requested_persona(request, config)
        column = persona.get("scopeColumn") or 0
        if not column:
            return Response({"column": 0, "label": "", "values": []})
        label = upload.analysis["columns"][column - 1].get("label") or upload.analysis["columns"][column - 1]["name"]
        resource_columns = config["resources"]["columns"]
        booking_cfg = config["booking"]
        if column in resource_columns:
            depth = resource_columns.index(column)
            values = list(Resource.objects.filter(upload=upload, level=depth, active=True).values_list("name", flat=True).distinct()[:200])
        elif column == booking_cfg.get("staffColumn"):
            values = list(Booking.objects.filter(upload=upload).exclude(staff="").values_list("staff", flat=True).distinct().order_by("staff")[:200])
        elif column == booking_cfg.get("organizationColumn"):
            values = list(Booking.objects.filter(upload=upload).exclude(organization="").values_list("organization", flat=True).distinct().order_by("organization")[:200])
        else:
            values = [choice for choice in upload.field_choices.filter(column_number=column, active=True).values_list("value", flat=True)[:200]]
        return Response({"column": column, "label": label, "values": values})
