"""Deterministic step from a ReservationUnderstanding to a running service: no model call.

derive_service() turns the understanding into the service configuration (which columns play
which part, how time is expressed, which personas exist, what the dashboard shows).
apply_service() materializes resources, slots and bookings from the managed rows so the
sheet's own records become the service's data. Both are repeatable.
"""
import re
from collections import Counter
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .analysis import missing
from .managed import ensure_imported
from .models import Booking, ManagedRow, Resource, Slot
from .operational_signals import parse_date

MAX_CHARTS = 4
MAX_TABLE_COLUMNS = 14
RANGE = re.compile(r"^\s*(.+?)\s*(?:~|–|—|\s-\s)\s*(.+?)\s*$")  # bare hyphens belong to dates
TIME_TEXT = re.compile(r"^(오전|오후|AM|PM|am|pm)?\s*(\d{1,2})\s*(?::|시)\s*(\d{1,2})?\s*분?\s*(?::\d{2})?\s*(AM|PM|am|pm)?$")
DATETIME_TEXT = re.compile(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?$")
TRUE_WORDS = {"y", "yes", "o", "true", "1", "예", "승인", "완료", "당첨", "사용", "확정", "있음", "유"}
FALSE_WORDS = {"n", "no", "x", "false", "0", "아니오", "아니요", "미승인", "미당첨", "없음", "무", "대기"}
BOOKING_STATUSES = tuple(Booking.Kind.values)


# ----------------------------------------------------------------------------- derivation

def _columns_by_role(understanding):
    by_role = {}
    for index, role in enumerate(understanding["columnRoles"], 1):
        by_role.setdefault(role, []).append(index)
    return by_role


def time_model(by_role):
    """How a booking's moment is written on this sheet."""
    if by_role.get("start") and by_role.get("end"):
        return "range"
    if by_role.get("start"):
        return "start"
    if by_role.get("date") and by_role.get("time_slot"):
        return "date_slot"
    if by_role.get("date"):
        return "date"
    if by_role.get("time_slot"):
        return "slot"
    return "none"


def _first(by_role, role):
    return (by_role.get(role) or [0])[0]


def derive_dashboard(understanding, report, by_role):
    """A v2 preview config the existing dashboard renders: one table and up to four count charts."""
    columns = report["columns"]
    count = len(columns)
    roles = understanding["columnRoles"]
    kept = [n for n in range(1, count + 1) if roles[n - 1] != "ignore"]
    table = kept[:MAX_TABLE_COLUMNS] or list(range(1, min(count, MAX_TABLE_COLUMNS) + 1))
    charts = []

    def groupable(number):
        column = columns[number - 1]
        return 1 < column["unique_count"] <= max(20, min(60, report["row_count"] // 10 or 2)) and column["non_empty_count"] > 0

    for role, kind in (("status", "donut"), ("approval", "donut"), ("payment", "donut"), ("lottery", "donut"),
                       ("cancel_flag", "donut"), ("resource_group", "bar"), ("resource", "bar"),
                       ("booker_attribute", "bar"), ("staff", "bar"), ("time_slot", "bar"), ("organization", "bar")):
        for number in by_role.get(role, []):
            if groupable(number) and all(chart["groupColumn"] != number for chart in charts):
                charts.append({"type": kind, "groupColumn": number, "aggregate": "count"})
            if len(charts) >= MAX_CHARTS:
                break
        if len(charts) >= MAX_CHARTS:
            break
    view = {"template": "table", "columns": table}
    if charts:
        view["charts"] = charts
    return {"version": 2, "views": [view]}


STAY_WORDS = ("숙박", "객실", "캠핑", "체크인", "입실", "퇴실", "야영", "글램핑", "카라반", "펜션", "휴양림", "텐트")


def booking_unit(understanding, report, by_role):
    """The model's unit when it gave one; otherwise what the columns and the subject suggest."""
    unit = understanding["booking"].get("unit") or ""
    if unit:
        return unit
    columns = report["columns"]
    labels = " ".join(column.get("label") or column["name"] for column in columns) + " " + understanding["subject"]
    stay_like = any(word in labels for word in STAY_WORDS)
    if understanding["sheetKind"] == "wide_schedule":
        return "time_slot"  # a date row with a time text per resource column
    if understanding["sheetKind"] in ("resource_catalog", "policy"):
        # catalog rows describe the resource (check-in hours, fees); they say nothing about a booking's length
        return "stay" if stay_like else "time_slot" if by_role.get("time_slot") else "day"

    def kind_of(number):
        return columns[number - 1]["candidate"] if number else ""
    start, end = (by_role.get("start") or [0])[0], (by_role.get("end") or [0])[0]
    if start and end and ("datetime" in (kind_of(start), kind_of(end)) or "time" in (kind_of(start), kind_of(end))):
        return "time_range"
    if start and end:
        return "stay" if stay_like else "period"
    if by_role.get("time_slot"):
        return "time_slot"
    if by_role.get("date") and stay_like:
        return "stay"
    return "day"


def derive_service(understanding, report):
    """The whole service configuration, from the understanding alone."""
    by_role = _columns_by_role(understanding)
    kind = understanding["sheetKind"]
    booking = understanding["booking"]
    labels = [column.get("label") or column["name"] for column in report["columns"]]
    resources = list(understanding["resourceColumns"])
    wide_pairs = []
    if kind == "wide_schedule":
        times = by_role.get("wide_time", [])
        for number in resources:
            partner = next((t for t in times if t > number and t not in [p[1] for p in wide_pairs]), 0)
            wide_pairs.append([number, partner])
    implicit = kind in ("booking_records", "schedule_slots") and not resources
    reservable = kind in ("booking_records", "resource_catalog", "schedule_slots", "wide_schedule", "policy") \
        and (bool(resources) or implicit) and booking["mode"] != "none"
    # A sheet of finished records (record_only) still takes new bookings: that is the point of the service.
    accepts_new = reservable
    config = {
        "version": 1,
        "sheetKind": kind,
        "subject": understanding["subject"],
        "summary": understanding["summary"],
        "columnRoles": list(understanding["columnRoles"]),
        "columnLabels": labels,
        "resources": {"columns": resources, "levels": [labels[n - 1] for n in resources] if not implicit else [understanding["subject"]],
                      "widePairs": wide_pairs, "implicit": implicit},
        "booking": {
            "mode": booking["mode"],
            "unit": booking_unit(understanding, report, by_role),
            "acceptsNew": accepts_new,
            "approvalRequired": booking["mode"] in ("approval", "lottery"),  # record_only and instant confirm at once
            "statusColumn": booking["statusColumn"],
            "states": list(booking["states"]),
            # Catalog rows describe the resource (check-in hours, fees); bookings against them are by date.
            "timeModel": "date" if kind in ("resource_catalog", "policy") else "date_slot" if kind == "wide_schedule"
            else time_model(by_role),
            "dateColumn": _first(by_role, "date"),
            "startColumn": _first(by_role, "start"),
            "endColumn": _first(by_role, "end"),
            "startColumns": by_role.get("start", []),  # a date column and a time column may both be "start"
            "endColumns": by_role.get("end", []),
            "slotColumn": _first(by_role, "time_slot"),
            "bookerColumn": _first(by_role, "booker"),
            "partySizeColumns": by_role.get("party_size", []),
            "purposeColumn": _first(by_role, "purpose"),
            "amountColumn": _first(by_role, "amount"),
            "paymentColumn": _first(by_role, "payment"),
            "approvalColumn": _first(by_role, "approval"),
            "cancelColumn": _first(by_role, "cancel_flag"),
            "lotteryColumn": _first(by_role, "lottery"),
            "staffColumn": _first(by_role, "staff"),
            "organizationColumn": _first(by_role, "organization"),
            "requestedAtColumn": _first(by_role, "created_at"),
            "capacityColumn": _first(by_role, "capacity"),
            "attributeColumns": by_role.get("booker_attribute", []),
        },
        "personas": [dict(persona) for persona in understanding["personas"]],
        "valueLabels": list(understanding.get("valueLabels", [])),
        "dashboard": {"preview": derive_dashboard(understanding, report, by_role)},
        "notes": [],
    }
    if not reservable:
        for persona in config["personas"]:
            persona["features"] = [f for f in persona["features"]
                                   if f not in ("make_reservation", "my_reservations", "manage_schedule", "review_reservations")]
        config["notes"].append("예약 대상이 없어 예약 기능은 두지 않았습니다.")
    elif implicit:
        config["notes"].append(f'예약 대상 컬럼이 없어 "{understanding["subject"]}" 하나를 대상으로 두었습니다.')
        for persona in config["personas"]:
            if persona["id"] == "booker":
                for feature in ("browse_resources", "make_reservation", "my_reservations"):
                    if feature not in persona["features"]:
                        persona["features"].append(feature)
    return config


# ----------------------------------------------------------------------------- parsing helpers

def _text(value):
    return "" if value is None else str(value).strip()


def parse_time(text):
    match = TIME_TEXT.match(_text(text))
    if not match:
        return None
    prefix, hour, minute, suffix = match.group(1), int(match.group(2)), int(match.group(3) or 0), match.group(4)
    marker = (prefix or suffix or "").lower()
    if marker in ("오후", "pm") and hour < 12:
        hour += 12
    if marker in ("오전", "am") and hour == 12:
        hour = 0
    if not (0 <= hour <= 24 and 0 <= minute < 60):
        return None
    return time(23, 59) if hour == 24 else time(hour, minute)


def parse_datetime_text(text):
    match = DATETIME_TEXT.match(_text(text))
    if not match:
        return None
    try:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4)),
                        int(match.group(5)), int(match.group(6) or 0))
    except ValueError:
        return None


def parse_range(text):
    """'2022-07-29(금)~2022-11-25(금)' or '10:00~12:00' -> (left, right) texts, else None."""
    match = RANGE.match(_text(text))
    if not match or not any(ch.isdigit() for ch in match.group(2)):
        return None
    return match.group(1), match.group(2)


def _strip_weekday(text):
    return re.sub(r"\([^)]*\)", "", _text(text)).strip()


def _aware(value):
    if value is None:
        return None
    return value if timezone.is_aware(value) else timezone.make_aware(value)


def parse_moment(text, base_date=None):
    """A datetime from a full datetime text, a date text (midnight) or a time text on base_date."""
    cleaned = _strip_weekday(text)
    moment = parse_datetime_text(cleaned)
    if moment:
        return _aware(moment)
    day = parse_date(cleaned)
    if day:
        return _aware(datetime.combine(day, time(0, 0)))
    clock = parse_time(cleaned)
    if clock and base_date:
        return _aware(datetime.combine(base_date, clock))
    return None


def parse_int(text):
    cleaned = re.sub(r"[^\d-]", "", _text(text))
    if not cleaned or cleaned == "-":
        return None
    try:
        value = int(cleaned)
    except ValueError:
        return None
    return value if 0 <= value <= 10_000_000 else None


def parse_amount(text):
    cleaned = re.sub(r"[^\d.\-]", "", _text(text))
    if not cleaned or cleaned in ("-", "."):
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return value if abs(value) < Decimal("1e12") else None


def truthy(text):
    lowered = _text(text).lower()
    if lowered in TRUE_WORDS:
        return True
    if lowered in FALSE_WORDS or lowered == "":
        return False
    return None


def _normalize_label(text):
    return re.sub(r"\s+", "", re.sub(r"\([^)]*\)", "", _text(text))).lower()


def status_kind(value, states, *, approval=None, cancelled=None, lottery=None, default):
    """Map the sheet's own wording to one of the booking kinds; prefixes cover '예약완료(등록:23번)'."""
    text = _text(value)
    if cancelled is True:
        return "cancelled"
    if text and states:
        for state in states:
            if state["value"] == text:
                return state["kind"]
        normalized = _normalize_label(text)
        for state in states:
            candidate = _normalize_label(state["value"])
            if candidate and normalized and (normalized.startswith(candidate) or candidate.startswith(normalized)):
                return state["kind"]
    if lottery is not None:
        return "won" if lottery else "lost"
    if approval is not None:
        return "approved" if approval else "requested"
    if text and not states:
        normalized = _normalize_label(text)
        for keyword, kind in (("취소", "cancelled"), ("환불", "cancelled"), ("거절", "rejected"), ("반려", "rejected"),
                              ("체크아웃", "completed"), ("수료", "completed"), ("완료", "completed"), ("종료", "completed"),
                              ("체크인", "in_use"), ("사용중", "in_use"), ("이용중", "in_use"),
                              ("대기", "requested"), ("신청", "requested"), ("접수", "requested"),
                              ("승인", "approved"), ("확정", "approved"), ("예약", "approved")):
            if keyword in normalized:
                return kind
        return "other"
    return default


# ----------------------------------------------------------------------------- materialization

def _value(values, number):
    return values[number - 1] if number and number - 1 < len(values) else None


def _label(report, number):
    column = report["columns"][number - 1]
    return column.get("label") or column["name"]


def _display_map(config):
    return {(item["column"], item["value"]): item["label"] for item in config.get("valueLabels", [])}


def _names(values, columns, display):
    """The resource path for one row, with code-like values shown by their display name."""
    result = []
    for number in columns:
        raw = _text(_value(values, number)) or "미지정"
        result.append(display.get((number, raw), raw))
    return result


def _resource_tree(upload, rows, columns, labels, *, catalog, display=None):
    """Resources for every distinct prefix of the resource columns; catalog rows also carry attributes."""
    display = display or {}
    nodes = {}
    order = []
    for row in rows:
        raws = [_text(_value(row.values, number)) for number in columns]
        if not raws or not raws[-1] and not any(raws):
            continue
        names = _names(row.values, columns, display)
        prefix = []
        for level, name in enumerate(names):
            prefix.append(name)
            key = tuple(prefix)
            if key not in nodes:
                nodes[key] = {"level": level, "name": name, "row": None,
                              "code": raws[level] if display.get((columns[level], raws[level])) else ""}
                order.append(key)
            if catalog and level == len(names) - 1:
                nodes[key]["row"] = row
    created = {}
    for key in order:
        node = nodes[key]
        parent = created.get(key[:-1])
        attributes = {"원본 코드": node["code"]} if node["code"] else {}
        capacity = None
        if node["row"] is not None:
            values = node["row"].values
            for number, role in enumerate(labels["roles"], 1):
                text = _text(_value(values, number))
                if not text or number in columns:
                    continue
                if role == "capacity" and capacity is None:
                    capacity = parse_int(text)
                if role in ("resource_attribute", "capacity", "amount", "location", "contact", "url", "start", "end",
                            "time_slot", "date", "payment", "organization", "note", "purpose"):
                    attributes[labels["names"][number - 1]] = text[:500]
        resource = Resource(upload=upload, parent=parent, level=node["level"], name=node["name"][:300],
                            path=" / ".join(key)[:2000], source_row=node["row"], capacity=capacity, attributes=attributes)
        created[key] = resource
    Resource.objects.bulk_create(list(created.values()), batch_size=500)
    return created


def _combine_texts(values, columns):
    """One text for a moment that may be split over a date column and a time column ('2024-01-01' + '12:00')."""
    texts = [_text(_value(values, number)) for number in columns]
    texts = [text for text in texts if text]
    if len(texts) <= 1:
        return texts[0] if texts else ""
    day = next((text for text in texts if parse_date(_strip_weekday(text)) and not parse_datetime_text(text)), "")
    clock = next((text for text in texts if parse_time(text) and not parse_date(_strip_weekday(text))), "")
    if day and clock:
        return f"{_strip_weekday(day)} {clock}"
    return texts[0]


def _moment_fields(values, booking_config):
    """date, starts_at, ends_at, time_slot for one row following the derived time model."""
    cfg = booking_config
    day = parse_date(_strip_weekday(_value(values, cfg["dateColumn"]))) if cfg["dateColumn"] else None
    start_text = _combine_texts(values, cfg.get("startColumns") or ([cfg["startColumn"]] if cfg["startColumn"] else []))
    end_text = _combine_texts(values, cfg.get("endColumns") or ([cfg["endColumn"]] if cfg["endColumn"] else []))
    slot_text = _text(_value(values, cfg["slotColumn"])) if cfg["slotColumn"] else ""
    starts_at = ends_at = None
    if start_text and not end_text:
        pair = parse_range(start_text)
        if pair:
            start_text, end_text = pair
    if not start_text and day is None and slot_text:
        pair = parse_range(slot_text)
        if pair and parse_date(_strip_weekday(pair[0])):
            start_text, end_text, slot_text = pair[0], pair[1], ""
    if start_text:
        starts_at = parse_moment(start_text, day)
    if end_text:
        ends_at = parse_moment(end_text, (starts_at.date() if starts_at else day))
    if day is None and starts_at is not None:
        day = timezone.localtime(starts_at).date()
    if slot_text and day and starts_at is None:
        pair = parse_range(slot_text)
        if pair:
            first, second = parse_time(pair[0]), parse_time(pair[1])
            if first and second:
                starts_at = _aware(datetime.combine(day, first))
                ends_at = _aware(datetime.combine(day, second))
                if ends_at <= starts_at:
                    ends_at += timedelta(hours=12)
    if ends_at and starts_at and ends_at < starts_at:
        ends_at = None
    return day, starts_at, ends_at, slot_text[:120]


def apply_service(upload, config=None):
    """Create resources, slots and bookings from the sheet; replaces any earlier materialization."""
    config = config or upload.service_config
    report = upload.analysis
    ensure_imported(upload)
    names = [column.get("label") or column["name"] for column in report["columns"]]
    labels = {"roles": config["columnRoles"], "names": names}
    booking_cfg = config["booking"]
    kind = config["sheetKind"]
    with transaction.atomic():
        Booking.objects.filter(upload=upload).delete()
        Slot.objects.filter(upload=upload).delete()
        Resource.objects.filter(upload=upload).delete()
        rows = list(ManagedRow.objects.filter(upload=upload).order_by("row_number"))
        columns = config["resources"]["columns"]
        counts = Counter()
        if kind == "wide_schedule":
            resources = {}
            for number in columns:
                resources[number] = Resource(upload=upload, level=0, name=names[number - 1][:300],
                                             path=names[number - 1][:2000])
            Resource.objects.bulk_create(list(resources.values()))
            partners = {pair[0]: pair[1] for pair in config["resources"]["widePairs"]}
            bookings = []
            for row in rows:
                day = parse_date(_strip_weekday(_value(row.values, booking_cfg["dateColumn"]))) if booking_cfg["dateColumn"] else None
                for number in columns:
                    text = _text(_value(row.values, number))
                    if not text:
                        continue
                    slot_text = _text(_value(row.values, partners.get(number, 0))) if partners.get(number) else ""
                    starts_at = ends_at = None
                    pair = parse_range(slot_text) if slot_text and day else None
                    if pair and parse_time(pair[0]) and parse_time(pair[1]):
                        starts_at = _aware(datetime.combine(day, parse_time(pair[0])))
                        ends_at = _aware(datetime.combine(day, parse_time(pair[1])))
                    bookings.append(Booking(upload=upload, resource=resources[number], source_row=row, purpose=text[:2000],
                                            date=day, starts_at=starts_at, ends_at=ends_at, time_slot=slot_text[:120],
                                            status="approved", status_label="기록"))
                    counts["bookings"] += 1
            Booking.objects.bulk_create(bookings, batch_size=500)
            counts["resources"] = len(resources)
            return dict(counts)
        implicit = None
        if config["resources"].get("implicit"):
            implicit = Resource.objects.create(upload=upload, level=0, name=config["subject"][:300], path=config["subject"][:2000])
            counts["resources"] = 1
        elif not columns:
            return dict(counts)
        else:
            display = _display_map(config)
            tree = _resource_tree(upload, rows, columns, labels, catalog=kind in ("resource_catalog", "policy"), display=display)
            counts["resources"] = len(tree)
            if kind in ("resource_catalog", "policy"):
                return dict(counts)

        def leaf_for(values):
            if implicit is not None:
                return implicit
            return tree.get(tuple(_names(values, columns, display)))

        if kind == "schedule_slots":
            slots = []
            for row in rows:
                day, starts_at, ends_at, slot_text = _moment_fields(row.values, booking_cfg)
                attendance = sum(parse_int(_value(row.values, n)) or 0 for n in booking_cfg["partySizeColumns"])
                count_columns = [n for n, role in enumerate(config["columnRoles"], 1) if role == "count"]
                if not booking_cfg["partySizeColumns"] and count_columns:
                    attendance = parse_int(_value(row.values, count_columns[0])) or 0
                capacity = parse_int(_value(row.values, booking_cfg["capacityColumn"])) if booking_cfg["capacityColumn"] else None
                slots.append(Slot(upload=upload, resource=leaf_for(row.values), date=day, starts_at=starts_at, ends_at=ends_at,
                                  time_slot=slot_text, capacity=capacity, imported_count=attendance, source_row=row))
            Slot.objects.bulk_create(slots, batch_size=500)
            counts["slots"] = len(slots)
            return dict(counts)

        # booking_records: every row is one booking
        states = booking_cfg["states"]
        default_kind = "completed" if booking_cfg["mode"] == "record_only" else "approved"
        bookings = []
        for row in rows:
            values = row.values
            day, starts_at, ends_at, slot_text = _moment_fields(values, booking_cfg)
            approval = truthy(_value(values, booking_cfg["approvalColumn"])) if booking_cfg["approvalColumn"] else None
            cancelled = truthy(_value(values, booking_cfg["cancelColumn"])) if booking_cfg["cancelColumn"] else None
            lottery = truthy(_value(values, booking_cfg["lotteryColumn"])) if booking_cfg["lotteryColumn"] else None
            status_text = _text(_value(values, booking_cfg["statusColumn"])) if booking_cfg["statusColumn"] else ""
            kind_ = status_kind(status_text, states, approval=approval, cancelled=cancelled, lottery=lottery, default=default_kind)
            if kind_ not in BOOKING_STATUSES:
                kind_ = "other"
            party = None
            if booking_cfg["partySizeColumns"]:
                sizes = [parse_int(_value(values, n)) for n in booking_cfg["partySizeColumns"]]
                sizes = [size for size in sizes if size is not None]
                party = sum(sizes) if sizes else None
            requested_at = parse_moment(_value(values, booking_cfg["requestedAtColumn"])) if booking_cfg["requestedAtColumn"] else None
            attributes = {names[n - 1]: _text(_value(values, n))[:300] for n in booking_cfg["attributeColumns"]
                          if not missing(_value(values, n))}
            bookings.append(Booking(
                upload=upload, resource=leaf_for(values), source_row=row,
                booker=_text(_value(values, booking_cfg["bookerColumn"]))[:200] if booking_cfg["bookerColumn"] else "",
                party_size=party, date=day, starts_at=starts_at, ends_at=ends_at, time_slot=slot_text,
                status=kind_, status_label=(status_text or ("" if not booking_cfg["statusColumn"] else ""))[:120],
                purpose=_text(_value(values, booking_cfg["purposeColumn"]))[:2000] if booking_cfg["purposeColumn"] else "",
                amount=parse_amount(_value(values, booking_cfg["amountColumn"])) if booking_cfg["amountColumn"] else None,
                payment=_text(_value(values, booking_cfg["paymentColumn"]))[:120] if booking_cfg["paymentColumn"] else "",
                staff=_text(_value(values, booking_cfg["staffColumn"]))[:200] if booking_cfg["staffColumn"] else "",
                organization=_text(_value(values, booking_cfg["organizationColumn"]))[:200] if booking_cfg["organizationColumn"] else "",
                attributes=attributes, requested_at=requested_at))
        Booking.objects.bulk_create(bookings, batch_size=500)
        counts["bookings"] = len(bookings)
        _summarize_resources(upload, config)
    return dict(counts)


def _summarize_resources(upload, config):
    """What the sheet's own records say about each resource: typical amount, slots, party, length, count.

    Catalog sheets carry this on the row; records sheets only have it in the bookings, and a booker
    deciding what to reserve needs it.
    """
    unit = config["booking"].get("unit", "day")
    stats = {}
    for booking in Booking.objects.filter(upload=upload, resource__isnull=False).values(
            "resource_id", "amount", "time_slot", "party_size", "starts_at", "ends_at", "date").iterator(chunk_size=1000):
        item = stats.setdefault(booking["resource_id"], {"count": 0, "amounts": [], "slots": Counter(), "parties": [], "days": []})
        item["count"] += 1
        if booking["amount"] is not None and booking["amount"] > 0:
            item["amounts"].append(booking["amount"])
        if booking["time_slot"]:
            item["slots"][booking["time_slot"]] += 1
        if booking["party_size"]:
            item["parties"].append(booking["party_size"])
        if booking["starts_at"] and booking["ends_at"]:
            length = (timezone.localtime(booking["ends_at"]).date() - timezone.localtime(booking["starts_at"]).date()).days
            item["days"].append(length if unit == "stay" else length + 1)
    if not stats:
        return
    changed = []
    for resource in Resource.objects.filter(upload=upload, pk__in=list(stats)):
        item = stats[resource.pk]
        summary = {"기록 건수": f'{item["count"]:,}건'}
        if item["amounts"]:
            low, high = min(item["amounts"]), max(item["amounts"])
            summary["기록 기준 금액"] = f"{low:,.0f}원" if low == high else f"{low:,.0f}~{high:,.0f}원"
        if item["slots"]:
            summary["자주 쓰인 시간대"] = " · ".join(value for value, _ in item["slots"].most_common(4))
        if item["parties"]:
            summary["평균 인원"] = f"{sum(item['parties']) / len(item['parties']):.1f}명"
        if item["days"] and max(item["days"]) > 1:
            summary["평균 이용 기간"] = f"{sum(item['days']) / len(item['days']):.1f}{'박' if unit == 'stay' else '일'}"
        resource.attributes = {**summary, **resource.attributes}
        changed.append(resource)
    Resource.objects.bulk_update(changed, ["attributes"], batch_size=500)


def _choice_options(upload, config):
    """Button choices for the reservation form, from what the sheet actually contains."""
    booking_cfg = config["booking"]
    slots = Counter()
    for value in Booking.objects.filter(upload=upload).exclude(time_slot="").values_list("time_slot", flat=True)[:5000]:
        slots[value] += 1
    for value in Slot.objects.filter(upload=upload).exclude(time_slot="").values_list("time_slot", flat=True)[:5000]:
        slots[value] += 1
    booking_cfg["slotOptions"] = [value for value, _ in slots.most_common(8)]
    parties = sorted(Booking.objects.filter(upload=upload, party_size__isnull=False).values_list("party_size", flat=True)[:5000])
    if parties:
        typical = parties[min(len(parties) - 1, int(len(parties) * 0.95))]
        booking_cfg["partySizeMax"] = max(1, min(50, typical))
    else:
        booking_cfg["partySizeMax"] = 10
    # Working hours from the records' clock times; midnight marks a date-only value and says nothing.
    starts = [timezone.localtime(m) for m in Booking.objects.filter(upload=upload, starts_at__isnull=False).values_list("starts_at", flat=True)[:2000]]
    ends = [timezone.localtime(m) for m in Booking.objects.filter(upload=upload, ends_at__isnull=False).values_list("ends_at", flat=True)[:2000]]
    hours = [m.hour for m in starts if (m.hour, m.minute) != (0, 0)]
    end_hours = [m.hour + (1 if m.minute else 0) for m in ends if (m.hour, m.minute) != (0, 0)]
    low, high = (min(hours) if hours else 8), (max(end_hours) if end_hours else 22)
    booking_cfg["hourRange"] = [low, min(24, high)] if high - low >= 2 else [8, 22]


def build_service(upload, understanding=None):
    """Derive the configuration, save it and materialize the data. Returns (config, counts)."""
    understanding = understanding or upload.understanding
    config = derive_service(understanding, upload.analysis)
    upload.service_config = config
    upload.save(update_fields=["service_config"])
    counts = apply_service(upload, config)
    _choice_options(upload, config)
    upload.service_config = config
    upload.save(update_fields=["service_config"])
    return config, counts
