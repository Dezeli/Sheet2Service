"""How a reservation service offers time and how many bookings one resource takes at once. Deterministic.

The service's rules live in service_config["booking"]["rules"]; services built before the rules existed get
them from rules_of(), derived from what the sheet showed. A resource may carry its own rules, which its
whole branch books under (rules_for), because one sheet often mixes hourly rentals with classes. Every check reduces a booking to a time interval on
one resource and asks for the peak load inside the requested interval, so the reservation form, the
calendar and the server agree on what is still free.
"""
import re
from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from .models import Booking, Resource
from .reservation_service import parse_range, parse_time

TIME_MODES = ("day", "time_slot", "time_range", "stay", "period")
CAPACITY_BY = ("bookings", "people")
STEPS = (10, 15, 20, 30, 60, 90, 120, 180, 240)
ACTIVE = ("requested", "approved", "in_use", "waiting", "won")
WHOLE_DAY = ("전일", "종일", "하루", "전체", "1일")
WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")  # Python's weekday(): Monday is 0
MAX_SESSIONS = 24
PER_PERSON = ("day", "upcoming")
MAX_LIMIT = 100_000
MAX_DAYS = 60
CLOCK = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$|^24:00$")
PEOPLE_WORDS = ("정원", "인원", "수용", "명")
DEFAULT_SESSIONS = ({"label": "오전", "start": "09:00", "end": "12:00"}, {"label": "오후", "start": "13:00", "end": "18:00"})


class RuleError(ValueError):
    pass


def _minutes(clock):
    hours, minutes = clock.split(":")
    return int(hours) * 60 + int(minutes)


def _clock(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def clock_range(text):
    """'오후2시~4시' or '10:00~12:00' -> (start, end) minutes of one day, else None."""
    pair = parse_range(text)
    first, second = (parse_time(pair[0]), parse_time(pair[1])) if pair else (None, None)
    if not (first and second):
        return None
    start, end = first.hour * 60 + first.minute, second.hour * 60 + second.minute
    if end <= start and end + 720 > start and end + 720 <= 1440:
        end += 720  # the afternoon marker covers both ends: 오후2시~4시
    return (start, end) if end > start else None


# ----------------------------------------------------------------------------- rules

def default_rules(config):
    """Rules from what the sheet showed: its unit, its recorded time slots and hours, its capacity column."""
    booking = config["booking"]
    mode = booking.get("unit") if booking.get("unit") in TIME_MODES else "day"
    sessions = []
    for text in booking.get("slotOptions") or []:
        label = str(text).strip()[:40]
        if not label or label in WHOLE_DAY or any(item["label"] == label for item in sessions):
            continue
        minutes = clock_range(label)
        if minutes:
            sessions.append({"label": label, "start": _clock(minutes[0]), "end": _clock(minutes[1])})
        else:
            sessions.append({"label": label, "start": "", "end": ""})
    sessions.sort(key=lambda item: (item["start"] or "99", item["label"]))
    low, high = booking.get("hourRange") or [8, 22]
    labels = config.get("columnLabels") or []
    column = booking.get("capacityColumn") or 0
    capacity_label = labels[column - 1] if 0 < column <= len(labels) else ""
    by = "people" if config.get("sheetKind") == "schedule_slots" or any(word in capacity_label for word in PEOPLE_WORDS) else "bookings"
    return {
        "timeMode": mode,
        "sessions": sessions[:MAX_SESSIONS] or [dict(item) for item in DEFAULT_SESSIONS],
        "hourly": {"open": _clock(low * 60), "close": "24:00" if high >= 24 else _clock(high * 60),
                   "step": 60, "minSteps": 1, "maxSteps": 0},
        "capacityBy": by,
        "limit": max(1, booking.get("partySizeMax") or 10) if by == "people" else 1,
        "closedWeekdays": [],
        "perPerson": {"limit": 0, "per": "day"},
    }


def rules_of(config):
    stored = config["booking"].get("rules")
    return stored if stored else default_rules(config)


def rule_owners(upload):
    """path -> resource carrying its own rules, for every such resource of the upload."""
    return {item["path"]: item for item in Resource.objects.filter(upload=upload, rules__isnull=False)
            .values("id", "name", "path", "rules")}


def rules_for(config, resource, owners=None):
    """(rules, owner) a resource books under: its own, its nearest ancestor's, or the service's (owner None)."""
    if resource is None:
        return rules_of(config), None
    owners = rule_owners(resource.upload_id) if owners is None else owners
    parts = resource.path.split(" / ")
    for depth in range(len(parts), 0, -1):
        owner = owners.get(" / ".join(parts[:depth]))
        if owner:
            return owner["rules"], owner
    return rules_of(config), None


def _integer(value, low, high, message):
    if type(value) is not int or not low <= value <= high:
        raise RuleError(message)
    return value


def validate_rules(data):
    """A clean copy of admin-edited rules, or RuleError naming the first problem."""
    if not isinstance(data, dict):
        raise RuleError("예약 규칙 형식이 올바르지 않습니다.")
    mode = data.get("timeMode")
    if mode not in TIME_MODES:
        raise RuleError("시간 단위를 선택해 주세요.")

    sessions = data.get("sessions") or []
    if not isinstance(sessions, list) or len(sessions) > MAX_SESSIONS:
        raise RuleError(f"시간대는 {MAX_SESSIONS}개까지 둘 수 있습니다.")
    clean_sessions = []
    for item in sessions:
        if not isinstance(item, dict):
            raise RuleError("시간대 형식이 올바르지 않습니다.")
        label = item.get("label")
        start, end = item.get("start") or "", item.get("end") or ""
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > 40:
            raise RuleError("시간대 이름은 1~40자로 입력해 주세요.")
        label = label.strip()
        if any(other["label"] == label for other in clean_sessions):
            raise RuleError(f'시간대 "{label}"이(가) 두 번 있습니다.')
        if not isinstance(start, str) or not isinstance(end, str) or bool(start) != bool(end):
            raise RuleError(f'"{label}"의 시작과 종료 시각을 함께 입력하거나 둘 다 비워 주세요.')
        if start and (not CLOCK.match(start) or not CLOCK.match(end) or _minutes(end) <= _minutes(start)):
            raise RuleError(f'"{label}"의 종료 시각은 시작 시각 이후여야 합니다.')
        clean_sessions.append({"label": label, "start": start, "end": end})
    if mode == "time_slot" and not clean_sessions:
        raise RuleError("시간대 방식에는 시간대가 하나 이상 있어야 합니다.")

    hourly = data.get("hourly")
    if not isinstance(hourly, dict):
        raise RuleError("시간 단위 설정이 올바르지 않습니다.")
    opening, closing = hourly.get("open"), hourly.get("close")
    if not isinstance(opening, str) or not isinstance(closing, str) or not CLOCK.match(opening) or not CLOCK.match(closing) \
            or _minutes(closing) <= _minutes(opening):
        raise RuleError("운영 종료 시각은 시작 시각 이후여야 합니다.")
    step = hourly.get("step")
    if step not in STEPS:
        raise RuleError("예약 간격을 목록에서 선택해 주세요.")
    blocks = (_minutes(closing) - _minutes(opening)) // step
    if blocks < 1:
        raise RuleError("운영 시간이 예약 간격보다 짧습니다.")
    min_steps = _integer(hourly.get("minSteps"), 1, blocks, "최소 이용 길이가 운영 시간을 넘습니다.")
    max_steps = _integer(hourly.get("maxSteps"), 0, blocks, "최대 이용 길이가 운영 시간을 넘습니다.")
    if max_steps and max_steps < min_steps:
        raise RuleError("최대 이용 길이는 최소 이용 길이 이상이어야 합니다.")

    by = data.get("capacityBy")
    if by not in CAPACITY_BY:
        raise RuleError("수용 기준을 선택해 주세요.")
    limit = _integer(data.get("limit"), 1, MAX_LIMIT, "기본 한도는 1 이상의 정수로 입력해 주세요.")
    closed = data.get("closedWeekdays") or []
    if not isinstance(closed, list) or any(type(day) is not int or not 0 <= day <= 6 for day in closed):
        raise RuleError("휴무 요일이 올바르지 않습니다.")
    if len(set(closed)) == 7:
        raise RuleError("모든 요일을 휴무로 둘 수는 없습니다.")
    per_person = data.get("perPerson") or {"limit": 0, "per": "day"}
    if not isinstance(per_person, dict) or per_person.get("per") not in PER_PERSON:
        raise RuleError("1인 예약 제한 기준을 선택해 주세요.")
    person_limit = _integer(per_person.get("limit"), 0, 100, "1인 예약 수는 0(제한 없음)~100 사이로 입력해 주세요.")
    return {"timeMode": mode, "sessions": clean_sessions,
            "hourly": {"open": opening, "close": closing, "step": step, "minSteps": min_steps, "maxSteps": max_steps},
            "capacityBy": by, "limit": limit, "closedWeekdays": sorted(set(closed)),
            "perPerson": {"limit": person_limit, "per": per_person["per"]}}


# ----------------------------------------------------------------------------- intervals

def _at(day, minutes):
    return timezone.make_aware(datetime.combine(day, time(0, 0))) + timedelta(minutes=minutes)


def day_window(day):
    return _at(day, 0), _at(day, 1440)


def session_of(rules, label):
    return next((item for item in rules["sessions"] if item["label"] == label), None)


def session_window(day, session):
    """A session with clock times is an interval; a named-only one holds its label for the whole day."""
    if session["start"] and session["end"]:
        return _at(day, _minutes(session["start"])), _at(day, _minutes(session["end"])), ""
    start, end = day_window(day)
    return start, end, session["label"]


def weight_of(rules, party):
    return (party or 1) if rules["capacityBy"] == "people" else 1


def occupancy(booking, rules):
    """(start, end, label, weight) a booking holds; a label means only its slot name is known."""
    weight = weight_of(rules, booking.party_size)
    if booking.starts_at and booking.ends_at and booking.ends_at > booking.starts_at:
        return booking.starts_at, booking.ends_at, "", weight
    day = booking.date or (timezone.localtime(booking.starts_at).date() if booking.starts_at else None)
    if day is None:
        return None
    slot = booking.time_slot
    if slot and slot not in WHOLE_DAY:
        session = session_of(rules, slot)
        if session:
            return (*session_window(day, session), weight)
        minutes = clock_range(slot)
        if minutes:
            return _at(day, minutes[0]), _at(day, minutes[1]), "", weight
        return (*day_window(day), slot, weight)
    return (*day_window(day), "", weight)


def _sweep(start, end, items):
    events = []
    for item_start, item_end, _, weight in items:
        events.append((max(item_start, start), weight))
        events.append((min(item_end, end), -weight))
    events.sort(key=lambda event: (event[0], event[1]))  # an end frees its place before a start at the same moment
    highest = current = 0
    for _, delta in events:
        current += delta
        highest = max(highest, current)
    return highest


def peak(start, end, label, items):
    """Highest load inside [start, end). Named-only slots conflict with their own name and with timed items."""
    overlapping = [item for item in items if item[0] < end and item[1] > start]
    groups = {label} if label else ({item[2] for item in overlapping if item[2]} or {""})
    return max(_sweep(start, end, [item for item in overlapping if not item[2] or item[2] == group]) for group in groups)


def limit_of(resource, rules):
    return (resource.capacity if resource is not None and resource.capacity else None) or rules["limit"]


def load_items(upload, resource, start, end, rules, exclude=None):
    """Occupancies of a resource's live bookings that may touch [start, end)."""
    first, last = timezone.localtime(start).date(), timezone.localtime(end - timedelta(microseconds=1)).date()
    bookings = (Booking.objects.filter(upload=upload, resource=resource, status__in=ACTIVE)
                .filter(Q(starts_at__lt=end, ends_at__gt=start) | Q(date__gte=first, date__lte=last))
                .only("party_size", "starts_at", "ends_at", "date", "time_slot"))
    if exclude is not None:
        bookings = bookings.exclude(pk=exclude)
    return [item for item in (occupancy(booking, rules) for booking in bookings) if item]


# ----------------------------------------------------------------------------- requests

def covered_days(mode, day, end_day):
    if mode == "stay":
        return [day + timedelta(days=offset) for offset in range((end_day - day).days)]
    if mode == "period":
        return [day + timedelta(days=offset) for offset in range((end_day - day).days + 1)]
    return [day]


def normalize_request(rules, *, day, end_day, starts, ends, time_slot):
    """The moment fields to store and the window to check, following the rules' time mode."""
    mode = rules["timeMode"]
    label = ""
    if mode == "time_range":
        if starts is None or ends is None:
            raise RuleError("시작과 종료 시각을 선택해 주세요.")
        local_start, local_end = timezone.localtime(starts), timezone.localtime(ends)
        day = local_start.date()
        start_minute = local_start.hour * 60 + local_start.minute
        if local_end.date() == day:
            end_minute = local_end.hour * 60 + local_end.minute
        elif local_end.date() == day + timedelta(days=1) and (local_end.hour, local_end.minute) == (0, 0):
            end_minute = 1440
        else:
            raise RuleError("시작과 종료는 같은 날이어야 합니다.")
        hourly = rules["hourly"]
        opening, closing, step = _minutes(hourly["open"]), _minutes(hourly["close"]), hourly["step"]
        if end_minute <= start_minute:
            raise RuleError("종료 시각은 시작 시각 이후여야 합니다.")
        if start_minute < opening or end_minute > closing:
            raise RuleError(f"운영 시간({hourly['open']}~{hourly['close']}) 안에서 선택해 주세요.")
        if (start_minute - opening) % step or (end_minute - start_minute) % step:
            raise RuleError(f"{step}분 단위로 선택해 주세요.")
        blocks = (end_minute - start_minute) // step
        if blocks < hourly["minSteps"]:
            raise RuleError(f"최소 {hourly['minSteps'] * step}분 이상 예약해 주세요.")
        if hourly["maxSteps"] and blocks > hourly["maxSteps"]:
            raise RuleError(f"한 번에 {hourly['maxSteps'] * step}분까지 예약할 수 있습니다.")
        starts, ends, time_slot = _at(day, start_minute), _at(day, end_minute), ""
        end_day = day
    else:
        if day is None and starts is not None:
            day = timezone.localtime(starts).date()
        if day is None:
            raise RuleError("예약 날짜를 선택해 주세요.")
        if mode in ("stay", "period"):
            if end_day is None and mode == "period":
                end_day = day
            if end_day is None or end_day < day or (mode == "stay" and end_day == day):
                raise RuleError("퇴실일은 입실일 다음 날 이후여야 합니다." if mode == "stay" else "종료일은 시작일 이후여야 합니다.")
            if (end_day - day).days > MAX_DAYS:
                raise RuleError(f"한 번에 {MAX_DAYS}일을 넘는 기간은 예약할 수 없습니다.")
            starts = _at(day, 0)
            ends = _at(end_day, 0) if mode == "stay" else _at(end_day, 1440)  # a stay ends at checkout morning
            time_slot = ""
        elif mode == "time_slot":
            session = session_of(rules, time_slot)
            if session is None:
                raise RuleError("제공하는 시간대 중에서 선택해 주세요.")
            starts, ends, label = session_window(day, session)
            if label:
                starts = ends = None
            end_day = day
        else:
            starts = ends = None
            time_slot = ""
            end_day = day
    for covered in covered_days(mode, day, end_day):
        if covered.weekday() in rules["closedWeekdays"]:
            raise RuleError(f"{WEEKDAYS[covered.weekday()]}요일은 휴무일이라 예약할 수 없습니다.")
    window_start, window_end = (starts, ends) if starts and ends else day_window(day)
    return {"date": day, "end_date": end_day, "starts_at": starts, "ends_at": ends, "time_slot": time_slot,
            "window": (window_start, window_end, label)}


def ensure_capacity(upload, resource, rules, window, party):
    """RuleError when one more booking of this size does not fit anywhere inside the window."""
    if resource is None:
        return
    limit = limit_of(resource, rules)
    weight = weight_of(rules, party)
    if weight > limit:
        raise RuleError(f"한 번에 {limit}명까지 예약할 수 있습니다.")
    start, end, label = window
    used = peak(start, end, label, load_items(upload, resource, start, end, rules))
    if used + weight > limit:
        if rules["capacityBy"] == "people" and used < limit:
            raise RuleError(f"선택한 시간에는 {limit - used}명까지만 예약할 수 있습니다.")
        raise RuleError("선택한 시간은 이미 예약이 가득 찼습니다. 다른 시간을 선택해 주세요.")


def ensure_per_person(upload, rules, owner, day, phone):
    """RuleError when this phone number already holds as many bookings as the rules allow one person.

    Without sign-in a person is their phone number. The count covers the branch the rules belong to
    (owner), or the whole service for the service's own rules.
    """
    per_person = rules.get("perPerson") or {}
    allowed = per_person.get("limit") or 0
    if not allowed or not phone:
        return
    bookings = Booking.objects.filter(upload=upload, status__in=ACTIVE, phone=phone)
    if owner:
        bookings = bookings.filter(Q(resource__path=owner["path"]) | Q(resource__path__startswith=owner["path"] + " / "))
    scope = f'"{owner["name"]}"에서 ' if owner else ""
    if per_person["per"] == "day":
        if bookings.filter(date=day).count() >= allowed:
            raise RuleError(f"{scope}한 사람이 하루에 {allowed}건까지 예약할 수 있습니다. 내 예약에서 이미 예약한 내역을 확인해 주세요.")
    elif bookings.filter(date__gte=timezone.localdate()).count() >= allowed:
        raise RuleError(f"{scope}한 사람이 {allowed}건까지 예약해 둘 수 있습니다. 이용을 마치거나 취소한 뒤 다시 예약해 주세요.")


# ----------------------------------------------------------------------------- availability

def _option(start, end, label, items, limit, now):
    used = peak(start, end, label, items)
    remaining = max(0, limit - used)
    return remaining, remaining > 0 and start >= now


def day_state(rules, limit, items, day, now):
    """What is still free on one day: per session, per time block, or the whole day."""
    mode = rules["timeMode"]
    closed = day.weekday() in rules["closedWeekdays"]
    start, end = day_window(day)
    items = [item for item in items if item[0] < end and item[1] > start]
    state = {"date": day.isoformat(), "closed": closed, "count": len(items)}
    if mode == "time_slot":
        sessions = []
        for session in rules["sessions"]:
            begin, finish, label = session_window(day, session)
            # a named-only session has no clock time, so it stays open for the whole of today
            opens_from = day_window(timezone.localdate(now))[0] if label else now
            remaining, available = _option(begin, finish, label, items, limit, opens_from)
            sessions.append({"label": session["label"], "start": session["start"], "end": session["end"],
                             "remaining": remaining, "available": available and not closed})
        state["sessions"] = sessions
        state["full"] = closed or not any(item["available"] for item in sessions)
    elif mode == "time_range":
        hourly = rules["hourly"]
        step = hourly["step"]
        blocks = []
        for minute in range(_minutes(hourly["open"]), _minutes(hourly["close"]) - step + 1, step):
            begin, finish = _at(day, minute), _at(day, minute + step)
            remaining, available = _option(begin, finish, "", items, limit, now)
            blocks.append({"start": _clock(minute), "end": _clock(minute + step), "remaining": remaining,
                           "available": available and not closed})
        state["blocks"] = blocks
        run = longest = 0
        for block in blocks:
            run = run + 1 if block["available"] else 0
            longest = max(longest, run)
        state["full"] = closed or longest < hourly["minSteps"]
    else:
        remaining = max(0, limit - peak(start, end, "", items))
        state["remaining"] = remaining
        state["full"] = closed or remaining < 1
    return state


def month_states(upload, resource, rules, first, following):
    """day_state for every day in [first, following), from one query."""
    limit = limit_of(resource, rules)
    start, end = day_window(first)[0], day_window(following)[0]
    items = load_items(upload, resource, start, end, rules)
    now = timezone.now()
    days = {}
    day = first
    while day < following:
        days[day.isoformat()] = day_state(rules, limit, items, day, now)
        day += timedelta(days=1)
    return limit, days


def one_day(upload, resource, rules, day):
    limit = limit_of(resource, rules)
    start, end = day_window(day)
    return limit, day_state(rules, limit, load_items(upload, resource, start, end, rules), day, timezone.now())
