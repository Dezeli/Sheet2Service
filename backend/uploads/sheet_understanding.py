"""SheetUnderstanding v1: what a sheet is, why it exists and how it is operated.

The model answers only within fixed vocabularies; the server checks every column number,
state value and actor reference against the data and lowers what it cannot verify instead of
discarding a paid response. See docs/sheet-understanding.md.
"""
import re
from copy import deepcopy

KINDS = ("register", "catalog", "ledger", "schedule", "roster", "reference", "mixed")
ACTOR_KINDS = ("requester", "handler", "approver", "viewer", "system")
ROLES = ("identifier", "title", "category", "status", "owner", "actor_name", "contact", "date_created",
         "date_updated", "date_due", "date_event", "date_closed", "time", "duration", "amount", "quantity", "number",
         "location", "coordinate", "url", "image", "reference_code", "result", "note", "flag", "derived", "unknown")
CONFIDENCE = ("high", "medium", "low")
BASES = ("status_column", "milestone_dates", "flag_and_dates", "amount_balance", "inferred")
STATE_KINDS = ("start", "active", "waiting", "done", "cancelled")
QUESTION_ABOUT = ("purpose", "column", "process")
ACTOR_IDS = tuple(f"a{index}" for index in range(1, 7))
PROCESS_IDS = tuple(f"p{index}" for index in range(1, 6))
TRANSITION = re.compile(r"^(.+?)>(.+?)(?::(a\d))?$")
MAX_STATES = 8
MAX_TRANSITIONS = 16
MAX_QUESTIONS = 5


class UnderstandingError(ValueError):
    pass


def _object(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _enum(values):
    return {"type": "string", "enum": list(values)}


def understanding_schema(report):
    """Grammar-cheap on purpose: per-column answers are parallel arrays, transitions are strings."""
    count = len(report["columns"])
    if not 1 <= count <= 200:
        raise UnderstandingError("지원하지 않는 CSV 컬럼 수입니다.")
    text = {"type": "string"}
    any_column = {"type": "integer"}
    return _object({
        "version": {"type": "integer", "enum": [1]},
        "kind": _enum(KINDS),
        "subject": text,
        "purpose": text,
        "actors": {"type": "array", "items": _object({"id": _enum(ACTOR_IDS), "label": text, "kind": _enum(ACTOR_KINDS)})},
        "columnRoles": {"type": "array", "items": _enum(ROLES)},
        "columnConfidence": {"type": "array", "items": _enum(CONFIDENCE)},
        "columnEvidence": {"type": "array", "items": text},
        "processes": {"type": "array", "items": _object({
            "id": _enum(PROCESS_IDS), "title": text, "basis": _enum(BASES),
            "columns": {"type": "array", "items": any_column},
            "states": {"type": "array", "items": _object({"value": text, "kind": _enum(STATE_KINDS)})},
            "transitions": {"type": "array", "items": text},
            "evidence": text,
            "confidence": _enum(CONFIDENCE),
            "after": _enum(("",) + PROCESS_IDS)})},
        "lifecycle": _object({"rowCreated": text, "rowUpdated": text, "rowClosed": text}),
        "questions": {"type": "array", "items": _object({"about": _enum(QUESTION_ABOUT), "column": any_column, "text": text})},
    })


def _clean(value, maximum):
    if not isinstance(value, str):
        return ""
    value = " ".join(value.split())
    return value if len(value) <= maximum else value[:maximum - 1].rstrip() + "…"


def _value_set(report, column):
    """Distinct values the signals saw in a column, or None when the column was not small-valued."""
    for item in (report.get("signals") or {}).get("value_sets", []):
        if item["column"] == column:
            return {entry["value"] for entry in item["values"]}
    for item in (report.get("signals") or {}).get("flags", []):
        if item["column"] == column:
            return {entry["value"] for entry in item["values"]}
    return None


def validate_understanding(value, report):
    """Return a normalized understanding and the notes explaining each lowered item."""
    if not isinstance(value, dict):
        raise UnderstandingError("이해 응답이 객체가 아닙니다.")
    count = len(report["columns"])
    notes = []
    result = {"version": 1}
    result["kind"] = value.get("kind") if value.get("kind") in KINDS else "mixed"
    if result["kind"] != value.get("kind"):
        notes.append("시트 종류가 허용 값이 아니어서 mixed로 두었습니다.")
    result["subject"] = _clean(value.get("subject"), 40)
    result["purpose"] = _clean(value.get("purpose"), 300)

    actors, seen = [], set()
    for item in value.get("actors") if isinstance(value.get("actors"), list) else ():
        if not isinstance(item, dict) or item.get("id") not in ACTOR_IDS or item["id"] in seen \
                or item.get("kind") not in ACTOR_KINDS:
            notes.append("행위자 항목 하나를 형식 오류로 제외했습니다.")
            continue
        seen.add(item["id"])
        actors.append({"id": item["id"], "label": _clean(item.get("label"), 40) or item["id"], "kind": item["kind"]})
    result["actors"] = actors[:len(ACTOR_IDS)]

    for key, allowed, fallback, limit in (("columnRoles", ROLES, "unknown", None),
                                          ("columnConfidence", CONFIDENCE, "low", None),
                                          ("columnEvidence", None, "", 120)):
        items = value.get(key) if isinstance(value.get(key), list) else []
        if len(items) != count:
            notes.append(f"{key} 길이가 컬럼 수({count})와 달라 맞췄습니다.")
        fixed = []
        for index in range(count):
            item = items[index] if index < len(items) else fallback
            if allowed is not None:
                fixed.append(item if item in allowed else fallback)
            else:
                fixed.append(_clean(item, limit))
        result[key] = fixed

    processes, seen = [], set()
    for item in value.get("processes") if isinstance(value.get("processes"), list) else ():
        if not isinstance(item, dict) or item.get("id") not in PROCESS_IDS or item["id"] in seen \
                or item.get("basis") not in BASES:
            notes.append("업무 흐름 하나를 형식 오류로 제외했습니다.")
            continue
        seen.add(item["id"])
        columns = [c for c in (item.get("columns") or []) if isinstance(c, int) and 1 <= c <= count]
        columns = list(dict.fromkeys(columns))
        if len(columns) != len(item.get("columns") or []):
            notes.append(f'{item["id"]}: 존재하지 않는 컬럼 번호를 제외했습니다.')
        basis = item["basis"]
        states = []
        for state in item.get("states") if isinstance(item.get("states"), list) else ():
            if isinstance(state, dict) and isinstance(state.get("value"), str) and state["value"].strip() \
                    and state.get("kind") in STATE_KINDS:
                states.append({"value": _clean(state["value"], 40), "kind": state["kind"]})
        if basis == "status_column":
            observed = _value_set(report, columns[0]) if columns else None
            if observed is None:
                notes.append(f'{item["id"]}: 상태 컬럼의 값 집합을 확인할 수 없어 추정으로 낮췄습니다.')
                basis = "inferred"
            else:
                kept = [state for state in states if state["value"] in observed]
                if len(kept) < len(states):
                    notes.append(f'{item["id"]}: 데이터에 없는 상태 값 {len(states) - len(kept)}개를 제외했습니다.')
                states = kept
                if len(states) < 2:
                    notes.append(f'{item["id"]}: 확인된 상태가 2개 미만이라 추정으로 낮췄습니다.')
                    basis = "inferred"
        if basis == "flag_and_dates" and len(states) == 1 and columns:
            # The model listed only the ticked state (ModelCall batch of 2026-10-25, 강의실 사용확인);
            # the unticked value is the waiting state and comes from the flag's own value set.
            observed = _value_set(report, columns[0]) or set()
            other = next((value for value in observed if value != states[0]["value"]), "") or "미표시"
            states.insert(0, {"value": other, "kind": "waiting"})
            notes.append(f'{item["id"]}: 여부 흐름의 대기 상태 "{other}"를 보충했습니다.')
        if not columns and basis != "inferred":
            notes.append(f'{item["id"]}: 관여 컬럼이 없어 추정으로 낮췄습니다.')
            basis = "inferred"
        names = {state["value"] for state in states}
        transitions = []
        if basis == "flag_and_dates" and len(states) == 2 and not item.get("transitions"):
            item = {**item, "transitions": [f'{states[0]["value"]}>{states[1]["value"]}']}
        for raw in item.get("transitions") if isinstance(item.get("transitions"), list) else ():
            match = TRANSITION.match(raw) if isinstance(raw, str) else None
            if not match or match.group(1).strip() not in names or match.group(2).strip() not in names:
                notes.append(f'{item["id"]}: 상태에 없는 전이 하나를 제외했습니다.')
                continue
            actor = match.group(3) if match.group(3) in {a["id"] for a in actors} else ""
            transitions.append({"from": match.group(1).strip(), "to": match.group(2).strip(), "actor": actor})
        processes.append({"id": item["id"], "title": _clean(item.get("title"), 60) or item["id"], "basis": basis,
                          "columns": columns, "states": states[:MAX_STATES], "transitions": transitions[:MAX_TRANSITIONS],
                          "evidence": _clean(item.get("evidence"), 200),
                          "confidence": item.get("confidence") if item.get("confidence") in CONFIDENCE else "low",
                          "after": item.get("after") if item.get("after") in PROCESS_IDS else ""})
    ids = {process["id"] for process in processes}
    for process in processes:
        if process["after"] and (process["after"] not in ids or process["after"] == process["id"]):
            notes.append(f'{process["id"]}: 선행 흐름 참조가 잘못되어 비웠습니다.')
            process["after"] = ""
    for process in processes:
        if not process["after"]:
            process["after"] = _follows(process, processes, report)
    result["processes"] = processes[:len(PROCESS_IDS)]

    lifecycle = value.get("lifecycle") if isinstance(value.get("lifecycle"), dict) else {}
    result["lifecycle"] = {key: _clean(lifecycle.get(key), 200) for key in ("rowCreated", "rowUpdated", "rowClosed")}

    questions = []
    for item in value.get("questions") if isinstance(value.get("questions"), list) else ():
        if not isinstance(item, dict) or item.get("about") not in QUESTION_ABOUT or not _clean(item.get("text"), 200):
            continue
        column = item.get("column") if isinstance(item.get("column"), int) and 1 <= item["column"] <= count else 0
        questions.append({"about": item["about"], "column": column, "text": _clean(item["text"], 200)})
    result["questions"] = questions[:MAX_QUESTIONS]
    return result, notes


def _follows(process, processes, report):
    """A flow whose every progressively filled column is only filled after another flow's columns follows it.

    The model set `after` itself on both evaluation sheets (ModelCalls cc260276, 1f36c452); this
    fills it from the fill chain when a response leaves it empty or the reference was dropped.
    """
    chain = (report.get("signals") or {}).get("fill_chain", [])
    presence = (report.get("signals") or {}).get("presence", [])
    own = [c for c in process["columns"] if c - 1 < len(presence) and presence[c - 1] < 0.98]
    if not own:
        return ""
    for other in processes:
        if other is process or not other["columns"]:
            continue
        earlier = set(other["columns"]) - set(process["columns"])
        if earlier and all(any(item["later"] == c and item["earlier"] in earlier for item in chain) for c in own):
            return other["id"]
    return ""


def parse_understanding_response(raw, report):
    from .service_blueprint import _parse_json  # same strict JSON reader as the blueprint contract
    return validate_understanding(_parse_json(raw), report)


MAX_ANSWER = 300


def validate_overrides(value, report, understanding):
    """Normalize the user's corrections: only known vocabularies, columns, flows and questions survive."""
    if not isinstance(value, dict):
        raise UnderstandingError("수정 내용이 객체가 아닙니다.")
    count = len(report["columns"])
    flow_ids = {process["id"] for process in understanding.get("processes", [])}
    result = {}
    if value.get("kind") in KINDS:
        result["kind"] = value["kind"]
    roles = value.get("columnRoles") if isinstance(value.get("columnRoles"), dict) else {}
    kept = {}
    for key, role in roles.items():
        try:
            column = int(key)
        except (TypeError, ValueError):
            continue
        if 1 <= column <= count and role in ROLES:
            kept[str(column)] = role
    if kept:
        result["columnRoles"] = kept
    processes = value.get("processes") if isinstance(value.get("processes"), dict) else {}
    flows = {}
    for key, item in processes.items():
        if key in flow_ids and isinstance(item, dict):
            flow = {name: bool(item[name]) for name in ("excluded", "confirmed") if name in item}
            if flow:
                flows[key] = flow
    if flows:
        result["processes"] = flows
    answers = value.get("answers") if isinstance(value.get("answers"), dict) else {}
    kept_answers = {}
    for key, text in answers.items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(understanding.get("questions", [])) and isinstance(text, str) and text.strip():
            kept_answers[str(index)] = _clean(text, MAX_ANSWER)
    if kept_answers:
        result["answers"] = kept_answers
    return result


def apply_overrides(understanding, overrides):
    """The effective understanding: the model's reading with the user's corrections on top."""
    if not understanding:
        return understanding
    result = deepcopy(understanding)
    if overrides.get("kind"):
        result["kind"] = overrides["kind"]
    for key, role in overrides.get("columnRoles", {}).items():
        index = int(key) - 1
        if 0 <= index < len(result["columnRoles"]):
            result["columnRoles"][index] = role
            result["columnConfidence"][index] = "high"
            result["columnEvidence"][index] = "사용자가 지정"
    for process in result["processes"]:
        flow = overrides.get("processes", {}).get(process["id"], {})
        process["excluded"] = bool(flow.get("excluded"))
        if flow.get("confirmed"):
            process["confidence"] = "high"
            process["confirmed"] = True
    for index, question in enumerate(result["questions"]):
        question["answer"] = overrides.get("answers", {}).get(str(index), "")
    return result


def summary_lines(understanding, report):
    """Plain sentences for logs and the chat panel; no model call."""
    labels = [column.get("label") or column.get("name") or f"컬럼 {index}" for index, column in enumerate(report["columns"], 1)]
    lines = [f'[{understanding["kind"]}] {understanding["subject"]}: {understanding["purpose"]}']
    for actor in understanding["actors"]:
        lines.append(f'행위자 {actor["id"]} {actor["label"]} ({actor["kind"]})')
    for index, (role, confidence) in enumerate(zip(understanding["columnRoles"], understanding["columnConfidence"])):
        if role != "unknown":
            lines.append(f"{index + 1}. {labels[index]} → {role} ({confidence})")
    for process in understanding["processes"]:
        states = " → ".join(state["value"] for state in process["states"])
        lines.append(f'흐름 {process["id"]} {process["title"]} [{process["basis"]}] 컬럼 {process["columns"]}: {states}')
        for transition in process["transitions"]:
            lines.append(f'   {transition["from"]} > {transition["to"]} ({transition["actor"] or "?"})')
    for question in understanding["questions"]:
        lines.append(f'질문: {question["text"]}')
    return lines
