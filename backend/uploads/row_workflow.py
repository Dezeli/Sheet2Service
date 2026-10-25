"""Row workflows: the sheet's own columns carry the state, and transitions edit the row.

A register sheet's rows are the cases. Unlike `submission` workflows, which create records
outside the CSV, a row workflow changes ManagedRow.values in place (status value, stage date,
flag + companions) and leaves a RowHistory entry. No model calls.
"""
from datetime import date

from .service_blueprint import BlueprintError, _column, _text

MAX_ROW_WORKFLOWS = 5
MAX_STATES = 8
MAX_TRANSITIONS = 16
STATE_KINDS = ("start", "active", "waiting", "done", "cancelled")
BASES = ("status_column", "milestone_dates", "flag_and_dates")
ACTORS = ("user", "admin")
MAX_FORM_COLUMNS = 8


def _optional_column(value, allowed):
    return None if value is None else _column(value, allowed)


def validate_row_workflows(flows, report):
    """Strict shape check for the `rowWorkflows` list stored in a blueprint."""
    allowed = set(range(1, len(report.get("columns", [])) + 1))
    if not isinstance(flows, list) or len(flows) > MAX_ROW_WORKFLOWS:
        raise BlueprintError("행 흐름 목록이 올바르지 않습니다.")
    ids = set()
    for flow in flows:
        if not isinstance(flow, dict) or flow.get("basis") not in BASES or not isinstance(flow.get("id"), str):
            raise BlueprintError("행 흐름 형식이 올바르지 않습니다.")
        if flow["id"] in ids:
            raise BlueprintError("행 흐름 ID가 중복되었습니다.")
        ids.add(flow["id"])
        _text(flow.get("title"), 80)
        states = flow.get("states")
        if not isinstance(states, list) or not 1 <= len(states) <= MAX_STATES:
            raise BlueprintError("행 흐름의 상태가 올바르지 않습니다.")
        names = set()
        for state in states:
            if not isinstance(state, dict) or state.get("kind") not in STATE_KINDS:
                raise BlueprintError("행 흐름의 상태 종류가 올바르지 않습니다.")
            _text(state.get("value"), 48)
            names.add(state["value"])
        if flow.get("initialState") not in names:
            raise BlueprintError("행 흐름의 시작 상태가 상태 목록에 없습니다.")
        transitions = flow.get("transitions")
        if not isinstance(transitions, list) or len(transitions) > MAX_TRANSITIONS:
            raise BlueprintError("행 흐름의 상태 변경이 올바르지 않습니다.")
        for step in transitions:
            if not isinstance(step, dict) or step.get("from") not in names or step.get("to") not in names \
                    or step.get("actor") not in ACTORS or step["from"] == step["to"]:
                raise BlueprintError("행 흐름의 상태 변경이 올바르지 않습니다.")
        for key in ("ownerColumn", "dueColumn", "closedColumn", "resultColumn"):
            _optional_column(flow.get(key), allowed)
        if flow["basis"] == "status_column":
            _column(flow.get("statusColumn"), allowed)
        elif flow["basis"] == "milestone_dates":
            columns = flow.get("dateColumns")
            if not isinstance(columns, list) or len(columns) != len(states) or len(set(columns)) != len(columns):
                raise BlueprintError("단계 날짜 컬럼은 상태 수와 같아야 합니다.")
            for number in columns:
                _column(number, allowed)
        else:
            _column(flow.get("flagColumn"), allowed)
            _text(flow.get("doneValue"), 48)
            companions = flow.get("companionColumns")
            if not isinstance(companions, list) or flow["flagColumn"] in companions:
                raise BlueprintError("여부 흐름의 함께 채울 컬럼이 올바르지 않습니다.")
            for number in companions:
                _column(number, allowed)
            if not set(flow.get("companionDates", [])) <= set(companions):
                raise BlueprintError("여부 흐름의 날짜 컬럼이 함께 채울 컬럼에 없습니다.")
        if flow.get("after", "") not in ids | {""} or flow.get("after") == flow["id"]:
            raise BlueprintError("행 흐름의 선행 흐름이 올바르지 않습니다.")
    return flows


def validate_create_form(form, report):
    if form is None:
        return None
    allowed = set(range(1, len(report.get("columns", [])) + 1))
    if not isinstance(form, dict) or form.get("actor") not in ACTORS or not isinstance(form.get("columns"), list) \
            or not 1 <= len(form["columns"]) <= MAX_FORM_COLUMNS or len(set(form["columns"])) != len(form["columns"]):
        raise BlueprintError("접수 폼 설정이 올바르지 않습니다.")
    for number in form["columns"]:
        _column(number, allowed)
    return form


def _cell(values, number):
    value = values[number - 1] if number and number - 1 < len(values) else None
    return "" if value is None else str(value).strip()


def row_state(flow, values):
    """The row's current state in this flow, read from its own columns."""
    if flow["basis"] == "status_column":
        value = _cell(values, flow["statusColumn"])
        return value if value in {state["value"] for state in flow["states"]} else flow["initialState"]
    if flow["basis"] == "milestone_dates":
        filled = [index for index, number in enumerate(flow["dateColumns"]) if _cell(values, number)]
        return flow["states"][filled[-1]]["value"] if filled else flow["initialState"]
    done = _cell(values, flow["flagColumn"]) == str(flow["doneValue"]).strip()
    return next((s["value"] for s in flow["states"] if s["kind"] == "done"), flow["states"][-1]["value"]) if done \
        else flow["initialState"]


def _kind(flow, value):
    return next((state["kind"] for state in flow["states"] if state["value"] == value), "active")


def flow_payload(flows, values):
    """Per-row states for the API: {flow_id: {state, kind, blocked}}."""
    states = {flow["id"]: row_state(flow, values) for flow in flows}
    result = {}
    for flow in flows:
        blocked = bool(flow.get("after")) and _kind(next(f for f in flows if f["id"] == flow["after"]),
                                                    states[flow["after"]]) != "done"
        result[flow["id"]] = {"state": states[flow["id"]], "kind": _kind(flow, states[flow["id"]]), "blocked": blocked}
    return result


class TransitionError(ValueError):
    pass


def apply_transition(flow, flows, values, *, to, actor, inputs, today=None):
    """Return (new values, changes) for one transition; raises TransitionError when not allowed."""
    today = (today or date.today()).isoformat()
    state = row_state(flow, values)
    step = next((s for s in flow["transitions"] if s["from"] == state and s["to"] == to), None)
    if step is None:
        raise TransitionError("지금 상태에서 할 수 없는 변경입니다.")
    if step["actor"] != actor:
        raise TransitionError("이 변경을 할 수 있는 역할이 아닙니다.")
    if flow_payload(flows, values)[flow["id"]]["blocked"]:
        raise TransitionError("선행 업무가 끝난 뒤에 진행할 수 있습니다.")
    new_values = list(values) + [None] * max(0, _width(flow) - len(values))
    changes = {}

    def put(number, value):
        if number:
            new_values[number - 1] = value
            changes[str(number)] = value
    if flow["basis"] == "status_column":
        put(flow["statusColumn"], to)
    elif flow["basis"] == "milestone_dates":
        index = next(i for i, s in enumerate(flow["states"]) if s["value"] == to)
        put(flow["dateColumns"][index], today)
    else:
        if _kind(flow, to) == "done":
            put(flow["flagColumn"], flow["doneValue"])
            for number in flow["companionColumns"]:
                given = inputs.get(str(number))
                put(number, given if isinstance(given, str) and given.strip() else today
                    if _looks_like_date(number, flow) else given or "")
        else:
            put(flow["flagColumn"], "")
    if _kind(flow, to) == "done" and flow.get("closedColumn") and not _cell(new_values, flow["closedColumn"]):
        put(flow["closedColumn"], today)
    for key in ("ownerColumn", "resultColumn"):
        number = flow.get(key)
        given = inputs.get(str(number)) if number else None
        if isinstance(given, str) and given.strip():
            put(number, given.strip()[:1000])
    return new_values, changes


def _width(flow):
    numbers = [flow.get(k) for k in ("statusColumn", "flagColumn", "ownerColumn", "dueColumn", "closedColumn", "resultColumn")]
    numbers += flow.get("dateColumns", []) + flow.get("companionColumns", [])
    return max(n for n in numbers if n) if any(numbers) else 0


def _looks_like_date(number, flow):
    return number in flow.get("dateColumns", []) or number in flow.get("companionDates", [])         or number in (flow.get("closedColumn"), flow.get("dueColumn"))


def create_row_values(form, blueprint, width, inputs, today=None):
    """Values for a new row from the user form: form columns from input, flow columns at their start."""
    today = (today or date.today()).isoformat()
    values = [None] * width
    for number in form["columns"]:
        given = inputs.get(str(number))
        if not isinstance(given, str) or len(given) > 5000:
            raise TransitionError("입력 값이 올바르지 않습니다.")
        values[number - 1] = given.strip()
    for flow in blueprint.get("rowWorkflows", []):
        if flow["basis"] == "status_column":
            values[flow["statusColumn"] - 1] = flow["initialState"]
        elif flow["basis"] == "milestone_dates":
            values[flow["dateColumns"][0] - 1] = today
    return values
