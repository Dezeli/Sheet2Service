"""Derive a service configuration from an understanding, deterministically and without a model call.

Column roles decide the catalog; flows decide row workflows. Excluded flows are skipped and
low-confidence flows count only once the user confirmed them. See docs/sheet-understanding.md,
"이해 → 서비스 설정 도출".
"""
from .service_blueprint import validate_blueprint

VISIBLE_ORDER = ("title", "identifier", "status", "category", "owner", "actor_name", "date_created", "date_event",
                 "date_due", "date_closed", "date_updated", "amount", "quantity", "number", "derived", "location",
                 "contact", "flag", "result", "time", "duration", "reference_code")
SEARCH_ROLES = ("title", "identifier", "actor_name", "note", "result", "location", "contact", "category", "owner")
FILTER_ROLES = ("status", "category", "flag", "owner", "location")
CHART_ROLES = ("status", "category", "owner", "flag")
FORM_ROLES = ("actor_name", "contact", "category", "note", "date_event", "quantity", "amount", "location", "title")
MAX_FILTER_VALUES = 50
MAX_CHART_VALUES = 30
MAX_ROW_WORKFLOWS = 5
TICKED = {"y", "o", "예", "true", "완료", "유", "있음", "여", "v", "✓", "1", "yes"}


def _by_role(roles):
    result = {}
    for index, role in enumerate(roles, 1):
        result.setdefault(role, []).append(index)
    return result


def _unique(report, column):
    return report["columns"][column - 1].get("unique_count", 0)


def _label(report, column):
    item = report["columns"][column - 1]
    return item.get("label") or item.get("name") or f"컬럼 {column}"


def derive_catalog(understanding, report):
    roles = understanding["columnRoles"]
    by_role = _by_role(roles)
    count = len(roles)
    notes = []
    title = (by_role.get("title") or by_role.get("identifier") or [None])[0]
    if title is None:
        title = next((number for number, role in enumerate(roles, 1)
                      if report["columns"][number - 1].get("candidate") == "text"), 1)
        notes.append(f"제목 컬럼이 없어 {_label(report, title)}을(를) 제목으로 씁니다.")
    visible = [title]
    for role in VISIBLE_ORDER:
        for number in by_role.get(role, []):
            if number not in visible and len(visible) < 12:
                visible.append(number)
    search = [n for role in SEARCH_ROLES for n in by_role.get(role, [])][:12]
    filters = [n for role in FILTER_ROLES for n in by_role.get(role, []) if 1 < _unique(report, n) <= MAX_FILTER_VALUES][:5]
    charts = [{"kind": "count_by", "groupColumn": n} for role in CHART_ROLES for n in by_role.get(role, [])
              if 1 < _unique(report, n) <= MAX_CHART_VALUES][:4]
    catalog = {"titleColumn": title, "visibleColumns": visible, "searchColumns": search or [title],
               "filterColumns": filters, "charts": charts}
    sort_column = (by_role.get("date_created") or by_role.get("date_event") or [None])[0]
    if sort_column:
        catalog["sort"] = {"column": sort_column, "direction": "desc"}
        notes.append(f"{_label(report, sort_column)} 최신순으로 정렬합니다.")
    if count and not filters:
        notes.append("값이 몇 종 안 되는 상태·분류 컬럼이 없어 필터를 두지 않았습니다.")
    return catalog, notes


def _done_value(report, flag, states):
    """The value the sheet really writes when the flag is set (Y, O, …), not the model's stage name."""
    observed = []
    for item in (report.get("signals") or {}).get("flags", []) + (report.get("signals") or {}).get("value_sets", []):
        if item["column"] == flag:
            observed = [entry["value"] for entry in item["values"]]
            break
    done = next((state["value"] for state in states if state["kind"] == "done"), None)
    if done in observed:  # the model named the states with the sheet's own values (N → Y)
        return done
    for value in observed:
        if value.strip().lower() in TICKED:
            return value
    return observed[0] if len(observed) == 1 else (observed[-1] if observed else "Y")


def _actor_role(actor_id, actors):
    kind = next((actor["kind"] for actor in actors if actor["id"] == actor_id), "")
    return "user" if kind == "requester" else "admin"


def _usable(process):
    if process.get("excluded"):
        return False, "사용자가 제외"
    if process["basis"] == "inferred" and not process.get("confirmed"):
        return False, "데이터 근거 없는 추정이라 확인 전에는 만들지 않음"
    if process.get("confidence") == "low" and not process.get("confirmed"):
        return False, "확신이 낮아 확인 전에는 만들지 않음"
    if process["basis"] == "amount_balance":
        return False, "장부형 흐름은 행 상태가 아니라 기록 추가라 다음 단계에서 다룸"
    return True, ""


def derive_row_workflows(understanding, report):
    """One row workflow per usable flow; the row's own columns carry the state."""
    roles = understanding["columnRoles"]
    by_role = _by_role(roles)
    actors = understanding["actors"]
    workflows, notes, ids = [], [], {}
    for process in understanding["processes"]:
        usable, reason = _usable(process)
        if not usable:
            notes.append(f'{process["title"]}: {reason}')
            continue
        if len(workflows) >= MAX_ROW_WORKFLOWS:
            notes.append(f'{process["title"]}: 행 흐름은 최대 {MAX_ROW_WORKFLOWS}개라 제외')
            continue
        flow_id = f"row_{len(workflows) + 1}"
        ids[process["id"]] = flow_id
        related = {roles[c - 1]: c for c in reversed(process["columns"]) if 1 <= c <= len(roles)}
        if "date_due" not in related and not process.get("after") and len(by_role.get("date_due", [])) == 1:
            related["date_due"] = by_role["date_due"][0]  # a single deadline column belongs to the row, not one flow
        states = [{"value": s["value"], "kind": s["kind"]} for s in process["states"]]
        transitions = [{"from": t["from"], "to": t["to"], "actor": _actor_role(t["actor"], actors)} for t in process["transitions"]]
        flow = {"id": flow_id, "title": process["title"], "basis": process["basis"], "states": states,
                "initialState": next((s["value"] for s in states if s["kind"] == "start"), states[0]["value"] if states else ""),
                "transitions": transitions,
                "ownerColumn": related.get("owner"), "dueColumn": related.get("date_due"),
                "closedColumn": related.get("date_closed"), "resultColumn": related.get("result"),
                "after": process.get("after", "")}
        if process["basis"] == "status_column":
            flow["statusColumn"] = process["columns"][0]
        elif process["basis"] == "milestone_dates":
            flow["dateColumns"] = [c for c in process["columns"] if roles[c - 1].startswith("date_")]
            if len(flow["dateColumns"]) < 2:
                notes.append(f'{process["title"]}: 단계 날짜 컬럼이 2개 미만이라 제외')
                workflows_pop = ids.pop(process["id"])
                continue
            if len(states) != len(flow["dateColumns"]):
                # Stage names are the model's; the dates are the truth. One stage per date column.
                states = [{"value": _label(report, c), "kind": "done" if i == len(flow["dateColumns"]) - 1 else "active"}
                          for i, c in enumerate(flow["dateColumns"])]
                states[0]["kind"] = "start"
                flow["states"], flow["initialState"] = states, states[0]["value"]
                flow["transitions"] = [{"from": a["value"], "to": b["value"], "actor": "admin"} for a, b in zip(states, states[1:])]
                notes.append(f'{process["title"]}: 단계를 날짜 컬럼 기준으로 다시 맞췄습니다.')
        elif process["basis"] == "flag_and_dates":
            flag = next((c for c in process["columns"] if roles[c - 1] == "flag"), process["columns"][0])
            flow["flagColumn"] = flag
            flow["doneValue"] = _done_value(report, flag, states)
            flow["companionColumns"] = [c for c in process["columns"] if c != flag]
            flow["companionDates"] = [c for c in flow["companionColumns"] if roles[c - 1].startswith("date_")]
        workflows.append(flow)
    for flow in workflows:
        flow["after"] = ids.get(flow["after"], "")
    return workflows, notes


def derive_create_form(understanding, report, flow_columns=()):
    """A requester may add rows to a register; columns a flow fills later stay out of the form."""
    if understanding["kind"] not in ("register", "schedule"):
        return None
    if not any(actor["kind"] == "requester" for actor in understanding["actors"]):
        return None
    by_role = _by_role(understanding["columnRoles"])
    columns = [n for role in FORM_ROLES for n in by_role.get(role, []) if n not in flow_columns][:8]
    return {"actor": "user", "columns": columns} if columns else None


def derive_submission_workflow(understanding, report, row_workflows):
    """Items people apply for (예약·이용 신청) get one application flow whose records live outside the sheet.

    Only catalog-like sheets with a requester actor; opened per item by the row's own status flow
    when one exists, so 접수중 facilities take bookings and 접수종료 ones do not.
    """
    if understanding["kind"] not in ("catalog", "schedule"):
        return None
    if not any(actor["kind"] == "requester" for actor in understanding["actors"]):
        return None
    by_role = _by_role(understanding["columnRoles"])
    subject = (by_role.get("title") or by_role.get("identifier") or [1])[0]
    subject_name = understanding["subject"] or "항목"
    title = f"{subject_name} 신청" if len(subject_name) <= 16 else "이용 신청"  # keeps buttons and tabs readable
    workflow = {"id": "flow_1", "title": title, "subjectColumn": subject,
                "fields": [{"id": "field_1", "label": "신청자 이름", "type": "text", "required": True},
                           {"id": "field_2", "label": "연락처", "type": "text", "required": True},
                           {"id": "field_3", "label": "요청 내용", "type": "text", "required": False}],
                "states": [{"id": "state_1", "label": "접수"}, {"id": "state_2", "label": "승인"},
                           {"id": "state_3", "label": "거절"}, {"id": "state_4", "label": "취소"}],
                "initialState": "state_1",
                "transitions": [{"from": "state_1", "to": "state_2", "actor": "admin", "label": "승인"},
                                {"from": "state_1", "to": "state_3", "actor": "admin", "label": "거절"},
                                {"from": "state_1", "to": "state_4", "actor": "owner", "label": "취소"}]}
    gate = next((flow for flow in row_workflows if flow["basis"] == "status_column"
                 and any(state["kind"] == "active" for state in flow["states"])), None)
    if gate:
        workflow["openWhen"] = {"flow": gate["id"], "kinds": ["active"]}
    return workflow


def derive_blueprint(understanding, report):
    """Return {blueprint, rowWorkflows, createForm, notes}; the blueprint part passes validate_blueprint."""
    catalog, notes = derive_catalog(understanding, report)
    workflows, flow_notes = derive_row_workflows(understanding, report)
    create_form = derive_create_form(understanding, report, {c for p in understanding["processes"] for c in p["columns"]})
    submission = derive_submission_workflow(understanding, report, workflows)
    blueprint = {"version": 1, "title": (understanding["subject"] or "서비스")[:80],
                 "summary": (understanding["purpose"] or "")[:300] or "시트를 바탕으로 만든 서비스입니다.",
                 "catalog": catalog, "workflows": [submission] if submission else [],
                 "rowWorkflows": workflows, **({"createForm": create_form} if create_form else {})}
    validate_blueprint(blueprint, report)
    if submission and submission.get("openWhen"):
        gate = next(flow for flow in workflows if flow["id"] == submission["openWhen"]["flow"])
        notes.append(f'{submission["title"]}은(는) {gate["title"]} 상태가 진행 중인 항목에만 열립니다.')
    return {"blueprint": blueprint, "rowWorkflows": workflows, "createForm": create_form, "notes": notes + flow_notes}
