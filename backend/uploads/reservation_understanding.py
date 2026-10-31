"""ReservationUnderstanding v1: how a reservation sheet is shaped and operated.

The sheet is assumed to be about reservations of some kind. The model answers inside fixed
vocabularies only; the server checks every column number, state value and persona against the
data and lowers what it cannot verify instead of discarding a paid response.
See docs/reservation-understanding.md.
"""
import json
import re
from copy import deepcopy

SHEET_KINDS = ("booking_records", "resource_catalog", "schedule_slots", "wide_schedule", "aggregate", "policy",
               "unrelated")
ROLES = ("resource", "resource_group", "resource_attribute", "capacity", "location", "contact", "url",
         "date", "start", "end", "time_slot", "booker", "booker_attribute", "party_size", "purpose",
         "status", "approval", "payment", "amount", "cancel_flag", "lottery", "staff", "organization",
         "identifier", "created_at", "updated_at", "count", "wide_resource", "wide_time", "note", "other", "ignore")
BOOKING_MODES = ("approval", "instant", "lottery", "record_only", "none")
STATE_KINDS = ("requested", "approved", "rejected", "cancelled", "in_use", "completed", "waiting", "won", "lost", "other")
PERSONAS = ("booker", "admin", "staff", "org_manager", "finance", "viewer")
FEATURES = ("browse_resources", "make_reservation", "my_reservations", "inquiry", "notices",
            "manage_resources", "manage_schedule", "review_reservations", "reply_inquiries", "manage_notices",
            "manage_data", "dashboard")
PERSONA_FEATURES = {
    "booker": ("browse_resources", "make_reservation", "my_reservations", "inquiry", "notices"),
    "admin": ("manage_resources", "manage_schedule", "review_reservations", "reply_inquiries", "manage_notices",
              "manage_data", "dashboard", "browse_resources"),
    "staff": ("review_reservations", "manage_schedule", "browse_resources", "dashboard", "notices"),
    "org_manager": ("review_reservations", "manage_schedule", "manage_resources", "browse_resources", "dashboard",
                    "notices", "reply_inquiries"),
    "finance": ("review_reservations", "dashboard", "browse_resources"),
    "viewer": ("browse_resources", "notices", "dashboard"),
}
# Features every service of a kind gets even when the model leaves them out.
REQUIRED_FEATURES = {
    "booker": ("browse_resources", "make_reservation", "my_reservations"),
    "admin": ("manage_resources", "manage_schedule", "review_reservations", "manage_data", "dashboard"),
}
SCOPED_PERSONAS = ("staff", "org_manager")
STATUS_ROLES = ("status", "approval", "cancel_flag", "lottery", "payment")
RESOURCE_ROLES = ("resource", "resource_group")
RESERVABLE_KINDS = ("booking_records", "resource_catalog", "schedule_slots", "wide_schedule", "policy")
MAX_STATES = 12
MAX_QUESTIONS = 3
MAX_RESPONSE_BYTES = 64_000


class UnderstandingError(ValueError):
    pass


def _object(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _enum(values):
    return {"type": "string", "enum": list(values)}


def understanding_schema(report):
    """Grammar-cheap on purpose: per-column answers are parallel arrays, states are parallel arrays."""
    count = len(report["columns"])
    if not 1 <= count <= 200:
        raise UnderstandingError("지원하지 않는 CSV 컬럼 수입니다.")
    text = {"type": "string"}
    column = {"type": "integer"}
    return _object({
        "version": {"type": "integer", "enum": [1]},
        "sheetKind": _enum(SHEET_KINDS),
        "subject": text,
        "summary": text,
        "columnRoles": {"type": "array", "items": _enum(ROLES)},
        "columnEvidence": {"type": "array", "items": text},
        "resourceColumns": {"type": "array", "items": column},
        "booking": _object({
            "mode": _enum(BOOKING_MODES),
            "statusColumn": column,
            "stateValues": {"type": "array", "items": text},
            "stateKinds": {"type": "array", "items": _enum(STATE_KINDS)},
            "evidence": text,
        }),
        "personas": {"type": "array", "items": _object({
            "id": _enum(PERSONAS), "title": text, "scopeColumn": column,
            "features": {"type": "array", "items": _enum(FEATURES)}, "evidence": text})},
        "questions": {"type": "array", "items": text},
    })


def _clean(value, maximum):
    if not isinstance(value, str):
        return ""
    value = " ".join(value.split())
    return value if len(value) <= maximum else value[:maximum - 1].rstrip() + "…"


def observed_values(report, column):
    """Distinct values the signals saw in a column, or None when the column was not small-valued."""
    signals = report.get("signals") or {}
    for key in ("value_sets", "flags"):
        for item in signals.get(key, []):
            if item["column"] == column:
                return {entry["value"] for entry in item["values"]}
    return None


def _column(value, count):
    return value if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= count else 0


STATE_KEYWORDS = (("미당첨", "lost"), ("낙첨", "lost"), ("당첨", "won"), ("취소", "cancelled"), ("환불", "cancelled"),
                  ("거절", "rejected"), ("반려", "rejected"), ("체크아웃", "completed"), ("수료", "completed"),
                  ("완료", "completed"), ("종료", "completed"), ("체크인", "in_use"), ("사용중", "in_use"),
                  ("이용중", "in_use"), ("대기", "requested"), ("신청", "requested"), ("접수", "requested"),
                  ("승인", "approved"), ("확정", "approved"), ("예약", "approved"))
SCOPE_ROLES = ("staff", "organization", "resource_group", "resource", "booker_attribute", "location")


def guess_state_kind(text):
    """A kind for a status value the model did not mention, from its wording alone."""
    lowered = str(text).replace(" ", "").lower()
    for keyword, kind in STATE_KEYWORDS:
        if keyword in lowered:
            return kind
    return "other"


def validate_understanding(value, report):
    """Return a normalized understanding and the notes explaining each lowered item."""
    if not isinstance(value, dict):
        raise UnderstandingError("이해 응답이 객체가 아닙니다.")
    count = len(report["columns"])
    notes = []
    result = {"version": 1}
    kind = value.get("sheetKind")
    if kind not in SHEET_KINDS:
        notes.append("시트 종류가 허용 값이 아니어서 booking_records로 두었습니다.")
        kind = "booking_records"
    result["sheetKind"] = kind
    result["subject"] = _clean(value.get("subject"), 40) or "예약 항목"
    result["summary"] = _clean(value.get("summary"), 600)

    roles = value.get("columnRoles") if isinstance(value.get("columnRoles"), list) else []
    evidence = value.get("columnEvidence") if isinstance(value.get("columnEvidence"), list) else []
    if len(roles) != count:
        notes.append(f"columnRoles 길이가 컬럼 수({count})와 달라 맞췄습니다.")
    result["columnRoles"] = [roles[i] if i < len(roles) and roles[i] in ROLES else "other" for i in range(count)]
    result["columnEvidence"] = [_clean(evidence[i], 120) if i < len(evidence) else "" for i in range(count)]
    for index, role in enumerate(result["columnRoles"]):
        if role in ("wide_resource", "wide_time") and kind != "wide_schedule":
            notes.append(f"{index + 1}번 컬럼: 가로형 역할은 wide_schedule 시트에만 쓰여 other로 바꿨습니다.")
            result["columnRoles"][index] = "other"

    resources = []
    for item in value.get("resourceColumns") if isinstance(value.get("resourceColumns"), list) else ():
        number = _column(item, count)
        if number and number not in resources:
            resources.append(number)
    if len(resources) != len(value.get("resourceColumns") or []):
        notes.append("resourceColumns에서 존재하지 않거나 중복된 컬럼을 제외했습니다.")
    if not resources:
        wanted = ("wide_resource",) if kind == "wide_schedule" else ("resource_group", "resource")
        resources = [i + 1 for role_name in wanted for i, role in enumerate(result["columnRoles"]) if role == role_name]
        if resources:
            notes.append("resourceColumns가 비어 있어 컬럼 역할에서 채웠습니다.")
    resource_role = "wide_resource" if kind == "wide_schedule" else "resource"
    allowed_resource_roles = ("wide_resource",) if kind == "wide_schedule" else RESOURCE_ROLES
    for number in resources:
        if result["columnRoles"][number - 1] not in allowed_resource_roles:
            notes.append(f"{number}번 컬럼: 예약 대상으로 지정되어 역할을 {resource_role}로 맞췄습니다.")
            result["columnRoles"][number - 1] = resource_role
    result["resourceColumns"] = resources

    booking = value.get("booking") if isinstance(value.get("booking"), dict) else {}
    mode = booking.get("mode") if booking.get("mode") in BOOKING_MODES else None
    status_column = _column(booking.get("statusColumn"), count)
    if status_column and result["columnRoles"][status_column - 1] not in STATUS_ROLES:
        notes.append(f"{status_column}번 컬럼: 상태 컬럼으로 지정되어 역할을 status로 맞췄습니다.")
        result["columnRoles"][status_column - 1] = "status"
    values = booking.get("stateValues") if isinstance(booking.get("stateValues"), list) else []
    kinds = booking.get("stateKinds") if isinstance(booking.get("stateKinds"), list) else []
    states = []
    seen = set()
    for index, raw in enumerate(values[:MAX_STATES]):
        text = _clean(raw, 40)
        state_kind = kinds[index] if index < len(kinds) and kinds[index] in STATE_KINDS else "other"
        if text and text not in seen:
            seen.add(text)
            states.append({"value": text, "kind": state_kind})
    if len(values) != len(kinds):
        notes.append("stateValues와 stateKinds 길이가 달라 짝이 없는 상태는 other로 두었습니다.")
    if status_column:
        observed = observed_values(report, status_column)
        if observed is not None:
            kept = [state for state in states if state["value"] in observed]
            if len(kept) < len(states):
                notes.append(f"데이터에 없는 상태 값 {len(states) - len(kept)}개를 제외했습니다.")
            states = kept
            for missing in sorted(observed - {state["value"] for state in states})[:MAX_STATES - len(states)]:
                kind_guess = guess_state_kind(missing)
                states.append({"value": missing, "kind": kind_guess})
                notes.append(f'상태 컬럼에 있지만 응답에 없던 값 "{missing}"을 {kind_guess}로 추가했습니다.')
        else:
            notes.append("상태 컬럼의 값 집합이 12종을 넘어 상태 값을 확인할 수 없습니다.")
    else:
        if states:
            notes.append("상태 컬럼이 없어 상태 값을 비웠습니다.")
        states = []
    if mode is None:
        mode = "approval" if kind in RESERVABLE_KINDS else "none"
        notes.append(f"예약 방식이 허용 값이 아니어서 {mode}로 두었습니다.")
    if kind in ("aggregate", "unrelated") and mode != "none":
        notes.append("예약 대상이 없는 시트라 예약 방식을 none으로 두었습니다.")
        mode = "none"
    if mode == "lottery" and not any(state["kind"] in ("won", "lost") for state in states) \
            and not any(role == "lottery" for role in result["columnRoles"]):
        notes.append("추첨 근거 컬럼이 없어 예약 방식을 approval로 낮췄습니다.")
        mode = "approval"
    result["booking"] = {"mode": mode, "statusColumn": status_column, "states": states,
                         "evidence": _clean(booking.get("evidence"), 200)}

    personas = []
    seen = set()
    for item in value.get("personas") if isinstance(value.get("personas"), list) else ():
        if not isinstance(item, dict) or item.get("id") not in PERSONAS or item["id"] in seen:
            notes.append("페르소나 항목 하나를 형식 오류나 중복으로 제외했습니다.")
            continue
        persona_id = item["id"]
        scope = _column(item.get("scopeColumn"), count)
        if persona_id in SCOPED_PERSONAS and not scope:
            notes.append(f"{persona_id}: 담당 범위 컬럼이 없어 제외했습니다.")
            continue
        if persona_id in SCOPED_PERSONAS and result["columnRoles"][scope - 1] not in SCOPE_ROLES:
            notes.append(f'{persona_id}: 담당 범위 컬럼({scope}번)의 역할이 {result["columnRoles"][scope - 1]}라 범위로 쓸 수 없어 제외했습니다.')
            continue
        if persona_id not in SCOPED_PERSONAS:
            scope = 0
        features = []
        for feature in item.get("features") if isinstance(item.get("features"), list) else ():
            if feature in PERSONA_FEATURES[persona_id] and feature not in features:
                features.append(feature)
            elif feature in FEATURES:
                notes.append(f"{persona_id}: 이 역할에 없는 기능 {feature}를 제외했습니다.")
        seen.add(persona_id)
        personas.append({"id": persona_id, "title": _clean(item.get("title"), 40) or persona_id,
                         "scopeColumn": scope, "features": features, "evidence": _clean(item.get("evidence"), 200)})
    # A records or slots sheet about one thing (a single stage, one exhibition) has no resource column;
    # the service then gets one implicit resource named after the subject, so bookings still work.
    reservable = kind in RESERVABLE_KINDS and (resources or kind in ("wide_schedule", "booking_records", "schedule_slots"))
    defaults = {"booker": "예약자", "admin": "관리자", "viewer": "조회자"}
    for persona_id in (("booker", "admin") if reservable else ("admin",)):
        if persona_id not in seen:
            notes.append(f"{persona_id} 페르소나가 없어 기본으로 추가했습니다.")
            personas.append({"id": persona_id, "title": defaults[persona_id], "scopeColumn": 0, "features": [],
                             "evidence": ""})
            seen.add(persona_id)
    if not reservable and "booker" in seen:
        notes.append("예약 대상이 없는 시트라 booker 페르소나를 viewer로 바꿨습니다.")
        for persona in personas:
            if persona["id"] == "booker":
                persona["id"], persona["title"] = "viewer", defaults["viewer"]
                persona["features"] = [f for f in persona["features"] if f in PERSONA_FEATURES["viewer"]]
    for persona in personas:
        if not reservable:
            persona["features"] = [f for f in persona["features"]
                                   if f not in ("make_reservation", "my_reservations", "manage_schedule", "review_reservations")]
            if persona["id"] == "admin":
                for feature in ("manage_data", "dashboard"):
                    if feature not in persona["features"]:
                        persona["features"].append(feature)
            continue
        for feature in REQUIRED_FEATURES.get(persona["id"], ()):
            if feature not in persona["features"]:
                persona["features"].append(feature)
        if persona["id"] in SCOPED_PERSONAS and "review_reservations" not in persona["features"]:
            persona["features"].insert(0, "review_reservations")
    if mode == "none" and reservable:
        for persona in personas:
            persona["features"] = [f for f in persona["features"] if f not in ("make_reservation", "my_reservations")]
    order = {persona_id: index for index, persona_id in enumerate(PERSONAS)}
    result["personas"] = sorted(personas, key=lambda persona: order[persona["id"]])

    questions = []
    for item in value.get("questions") if isinstance(value.get("questions"), list) else ():
        text = _clean(item, 200)
        if text:
            questions.append(text)
    result["questions"] = questions[:MAX_QUESTIONS]
    return result, notes


def _unique_object(pairs):
    result = {}
    for key, item in pairs:
        if key in result:
            raise UnderstandingError("중복된 JSON 키가 있습니다.")
        result[key] = item
    return result


def parse_json(raw):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise UnderstandingError("응답은 64,000바이트 이하의 JSON 문자열이어야 합니다.")
    fenced = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", raw.strip(), re.DOTALL)
    try:
        return json.loads(fenced.group(1) if fenced else raw, object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(UnderstandingError("유효하지 않은 JSON 상수입니다.")))
    except (ValueError, RecursionError) as exc:
        raise UnderstandingError("유효한 JSON 응답이 아닙니다.") from exc


def parse_understanding_response(raw, report):
    return validate_understanding(parse_json(raw), report)


def summary_lines(understanding, report):
    """Plain sentences for logs and tests; no model call."""
    labels = [column.get("label") or column.get("name") or f"컬럼 {index}" for index, column in enumerate(report["columns"], 1)]
    lines = [f'[{understanding["sheetKind"]}] {understanding["subject"]}: {understanding["summary"]}']
    lines.append("예약 대상 컬럼: " + (" > ".join(labels[number - 1] for number in understanding["resourceColumns"]) or "없음"))
    for index, role in enumerate(understanding["columnRoles"]):
        if role not in ("other", "ignore"):
            lines.append(f"{index + 1}. {labels[index]} → {role}")
    booking = understanding["booking"]
    states = ", ".join(f'{state["value"]}({state["kind"]})' for state in booking["states"])
    lines.append(f'예약 방식 {booking["mode"]}' + (f' / 상태 컬럼 {labels[booking["statusColumn"] - 1]}: {states}'
                                                  if booking["statusColumn"] else ""))
    for persona in understanding["personas"]:
        scope = f' (범위: {labels[persona["scopeColumn"] - 1]})' if persona["scopeColumn"] else ""
        lines.append(f'페르소나 {persona["id"]} {persona["title"]}{scope}: {", ".join(persona["features"])}')
    for question in understanding["questions"]:
        lines.append(f"질문: {question}")
    return lines


def copy_understanding(understanding):
    return deepcopy(understanding)
