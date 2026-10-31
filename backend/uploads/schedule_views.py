"""A week (or any window) of bookings per resource, with overbooked days marked. Deterministic."""
from datetime import timedelta

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date as iso_date
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .booking_views import ACTIVE, WHOLE_DAY, identifier, scope_filter
from .models import Booking, Resource
from .service_access import requested_persona, service_upload
from .views import SessionView

PAGE = 20
MAX_DAYS = 31


def fail(message):
    raise ValidationError({"detail": message})


def _days_of(booking):
    """Every calendar day a booking occupies: one for a dated booking, several for a stay or period."""
    if booking.starts_at and booking.ends_at:
        start, end = timezone.localtime(booking.starts_at), timezone.localtime(booking.ends_at)
        if start.date() != end.date() and (start.hour, start.minute) == (0, 0) and (end.hour, end.minute) == (0, 0):
            day = start.date()
            while day < end.date():
                yield day
                day += timedelta(days=1)
            return
    if booking.date:
        yield booking.date
    elif booking.starts_at:
        yield timezone.localtime(booking.starts_at).date()


def _timed(booking):
    if not (booking.starts_at and booking.ends_at):
        return None
    start, end = timezone.localtime(booking.starts_at), timezone.localtime(booking.ends_at)
    if start.date() == end.date() and ((start.hour, start.minute) != (0, 0) or (end.hour, end.minute) != (0, 0)):
        return start, end
    return None


def overbooked(items, capacity):
    """How many bookings exceed the capacity on one day: by clock overlap, by slot, or by plain count."""
    active = [item for item in items if item.status in ACTIVE]
    if len(active) <= capacity:
        return 0
    timed = [_timed(item) for item in active]
    if all(timed):
        events = sorted([(start, 1) for start, _ in timed] + [(end, -1) for _, end in timed], key=lambda e: (e[0], e[1]))
        peak = current = 0
        for _, delta in events:
            current += delta
            peak = max(peak, current)
        return max(0, peak - capacity)
    if any(item.time_slot for item in active):
        whole = sum(1 for item in active if not item.time_slot or item.time_slot in WHOLE_DAY)
        worst = whole
        for slot in {item.time_slot for item in active if item.time_slot and item.time_slot not in WHOLE_DAY}:
            worst = max(worst, whole + sum(1 for item in active if item.time_slot == slot))
        return max(0, worst - capacity)
    return len(active) - capacity


def brief(booking):
    return {"id": str(booking.id), "booker": booking.booker, "status": booking.status, "time_slot": booking.time_slot,
            "starts_at": booking.starts_at.isoformat() if booking.starts_at else None,
            "ends_at": booking.ends_at.isoformat() if booking.ends_at else None,
            "party_size": booking.party_size, "purpose": booking.purpose[:80], "imported": booking.source_row_id is not None}


class ScheduleView(SessionView):
    def get(self, request, pk):
        upload = service_upload(request, pk)
        config = upload.service_config
        persona = requested_persona(request, config, "review_reservations", "manage_schedule")
        params = request.query_params
        start = iso_date(params.get("from") or "") if params.get("from") else None
        if params.get("from") and start is None:
            fail("시작일은 YYYY-MM-DD 형식으로 입력해 주세요.")
        if start is None:
            today = timezone.localdate()
            start = today - timedelta(days=today.weekday())
        try:
            days = max(1, min(MAX_DAYS, int(params.get("days", "7"))))
        except ValueError:
            fail("기간은 정수 일수로 입력해 주세요.")
        end = start + timedelta(days=days)
        window = [start + timedelta(days=i) for i in range(days)]

        resources = Resource.objects.filter(upload=upload, active=True).annotate(children_total=Count("children")).filter(children_total=0)
        if params.get("q"):
            resources = resources.filter(path__icontains=params["q"][:100])
        if params.get("group"):
            group = get_object_or_404(Resource, pk=identifier(params["group"]), upload=upload)
            resources = resources.filter(Q(path__startswith=group.path + " / ") | Q(pk=group.pk))
        if persona["id"] in ("staff", "org_manager"):
            scope = (params.get("scope") or "").strip()
            if not scope:
                fail("담당 범위를 선택해 주세요.")
            scoped_ids = scope_filter(config, persona, scope, Booking.objects.filter(upload=upload)).values_list("resource_id", flat=True)
            resources = resources.filter(pk__in=scoped_ids)
        resources = resources.order_by("path")

        bookings = (Booking.objects.filter(upload=upload, resource__in=resources)
                    .filter(Q(date__gte=start, date__lt=end) | Q(starts_at__lt=timezone.make_aware(timezone.datetime.combine(end, timezone.datetime.min.time())),
                                                                 ends_at__gt=timezone.make_aware(timezone.datetime.combine(start, timezone.datetime.min.time()))))
                    .exclude(status__in=("rejected", "cancelled", "lost")).select_related("resource").order_by("starts_at", "time_slot", "created_at"))
        per_resource = {}
        for booking in bookings:
            for day in _days_of(booking):
                if start <= day < end:
                    per_resource.setdefault(booking.resource_id, {}).setdefault(day, []).append(booking)
        capacities = {resource.pk: resource.capacity or 1 for resource in resources}
        conflicts = {}
        for resource_id, by_day in per_resource.items():
            for day, items in by_day.items():
                extra = overbooked(items, capacities.get(resource_id, 1))
                if extra:
                    conflicts[(resource_id, day)] = extra
        if params.get("conflicts_only") == "1":
            wanted = {resource_id for resource_id, _ in conflicts}
            resources = resources.filter(pk__in=wanted)
        try:
            page = int(params.get("page", "1"))
        except ValueError:
            fail("페이지 번호가 올바르지 않습니다.")
        total = resources.count()
        if page < 1 or page > max(1, (total + PAGE - 1) // PAGE):
            fail("페이지 번호가 범위를 벗어났습니다.")
        rows = []
        for resource in resources[(page - 1) * PAGE:page * PAGE]:
            by_day = per_resource.get(resource.pk, {})
            rows.append({"id": str(resource.id), "name": resource.name, "path": resource.path, "capacity": resource.capacity,
                         "days": {day.isoformat(): [brief(item) for item in by_day.get(day, [])] for day in window if by_day.get(day)},
                         "conflicts": {day.isoformat(): conflicts[(resource.pk, day)] for day in window if (resource.pk, day) in conflicts}})
        names = {resource.pk: resource for resource in resources} if conflicts else {}
        conflict_list = [{"resource": str(resource_id), "name": names[resource_id].name if resource_id in names else "", "path": names[resource_id].path if resource_id in names else "",
                          "date": day.isoformat(), "extra": extra, "capacity": capacities.get(resource_id, 1)}
                         for (resource_id, day), extra in sorted(conflicts.items(), key=lambda item: (item[0][1], str(item[0][0])))]
        return Response({"from": start.isoformat(), "days": [day.isoformat() for day in window], "page": page, "count": total,
                         "has_next": page * PAGE < total, "resources": rows, "conflicts": conflict_list[:200],
                         "conflict_total": len(conflicts)})
