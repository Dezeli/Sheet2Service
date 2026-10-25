"""Validated service configuration: the catalog and row workflows a sheet understanding derives.

Nothing here calls a model; the configuration is produced by understanding_derivation.py and
checked strictly before it is stored.
"""
import json
import re
from copy import deepcopy


MAX_RESPONSE_BYTES = 32_000
MAX_WORKFLOWS = 3
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
SORT_TEXT = re.compile(r"^(\d{1,3}):(asc|desc)$")
WORKFLOW_IDS = tuple(f"flow_{index}" for index in range(1, MAX_WORKFLOWS + 1))
FIELD_IDS = tuple(f"field_{index}" for index in range(1, 7))
STATE_IDS = tuple(f"state_{index}" for index in range(1, 7))


class BlueprintError(ValueError):
    pass


def _object(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise BlueprintError("설정의 필수 항목이나 허용 항목이 올바르지 않습니다.")


def _text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\n" in value or "\r" in value:
        raise BlueprintError("설정의 문구가 올바르지 않습니다.")
    return value.strip()


def _id(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise BlueprintError("설정 ID가 올바르지 않습니다.")
    return value


def _known_id(value, allowed):
    if not isinstance(value, str) or value not in allowed:
        raise BlueprintError("참조한 상태 ID가 존재하지 않습니다.")
    return value


def _column(value, allowed):
    if type(value) is not int or value not in allowed:
        raise BlueprintError("CSV에 없는 컬럼 번호입니다.")
    return value


def _columns(values, allowed, maximum, *, required=False):
    if not isinstance(values, list) or len(values) > maximum or (required and not values):
        raise BlueprintError("컬럼 목록이 올바르지 않습니다.")
    result = [_column(value, allowed) for value in values]
    if len(set(result)) != len(result):
        raise BlueprintError("컬럼을 중복 지정할 수 없습니다.")
    return result


def validate_blueprint(value, report):
    """Validate a complete proposal; never silently alter a workflow or CSV binding."""
    _object(value, ("version", "title", "summary", "catalog", "workflows"), optional=("rowWorkflows", "createForm"))
    if type(value["version"]) is not int or value["version"] != 1:
        raise BlueprintError("지원하지 않는 서비스 설정 버전입니다.")
    _text(value["title"], 80)
    _text(value["summary"], 300)
    allowed = set(range(1, len(report.get("columns", [])) + 1))
    if not allowed or len(allowed) > 200:
        raise BlueprintError("지원하지 않는 CSV 컬럼 수입니다.")

    catalog = value["catalog"]
    _object(catalog, ("titleColumn", "visibleColumns", "searchColumns", "filterColumns", "charts"),
            optional=("sort", "labels", "valueLabels"))
    if "valueLabels" in catalog:
        mappings = catalog["valueLabels"]
        if not isinstance(mappings, list) or len(mappings) > 10:
            raise BlueprintError("값 표시 이름 목록이 올바르지 않습니다.")
        seen_columns = set()
        for item in mappings:
            _object(item, ("column", "values"))
            number = _column(item["column"], allowed)
            if number in seen_columns or not isinstance(item["values"], dict) or not item["values"] \
                    or len(item["values"]) > 30:
                raise BlueprintError("값 표시 이름이 중복되거나 비어 있습니다.")
            seen_columns.add(number)
            for raw, shown in item["values"].items():
                if not isinstance(raw, str) or len(raw) > 200:
                    raise BlueprintError("값 표시 이름의 원래 값이 올바르지 않습니다.")
                _text(shown, 60)
    if "labels" in catalog:
        labels = catalog["labels"]
        if not isinstance(labels, list) or len(labels) > 24:
            raise BlueprintError("표시 이름 목록이 올바르지 않습니다.")
        seen_labels = set()
        for item in labels:
            _object(item, ("column", "label"))
            number = _column(item["column"], allowed)
            if number in seen_labels:
                raise BlueprintError("같은 컬럼의 표시 이름이 중복되었습니다.")
            seen_labels.add(number)
            _text(item["label"], 120)
    _column(catalog["titleColumn"], allowed)
    if "sort" in catalog:
        sort = catalog["sort"]
        _object(sort, ("column", "direction"))
        if sort["direction"] not in ("asc", "desc"):
            raise BlueprintError("정렬 방향이 올바르지 않습니다.")
        _column(sort["column"], allowed)
    _columns(catalog["visibleColumns"], allowed, 12, required=True)
    _columns(catalog["searchColumns"], allowed, 12)
    _columns(catalog["filterColumns"], allowed, 5)
    charts = catalog["charts"]
    if not isinstance(charts, list) or len(charts) > 4:
        raise BlueprintError("차트는 최대 4개까지 설정할 수 있습니다.")
    for chart in charts:
        _object(chart, ("kind", "groupColumn"))
        if chart["kind"] != "count_by":
            raise BlueprintError("지원하지 않는 차트입니다.")
        _column(chart["groupColumn"], allowed)

    workflows = value["workflows"]
    if not isinstance(workflows, list) or len(workflows) > MAX_WORKFLOWS:
        raise BlueprintError("업무 흐름은 최대 3개까지 설정할 수 있습니다.")
    workflow_ids = set()
    for workflow in workflows:
        _object(workflow, ("id", "title", "subjectColumn", "fields", "states", "initialState", "transitions"))
        workflow_id = _id(workflow["id"])
        if workflow_id not in WORKFLOW_IDS or workflow_id in workflow_ids:
            raise BlueprintError("업무 흐름 ID가 허용 범위 밖이거나 중복되었습니다.")
        workflow_ids.add(workflow_id)
        _text(workflow["title"], 80)
        _column(workflow["subjectColumn"], allowed)

        fields = workflow["fields"]
        if not isinstance(fields, list) or len(fields) > 6:
            raise BlueprintError("입력 필드는 최대 6개까지 설정할 수 있습니다.")
        field_ids = set()
        for field in fields:
            _object(field, ("id", "label", "type", "required"))
            field_id = _id(field["id"])
            if field_id not in FIELD_IDS or field_id in field_ids \
                    or field["type"] not in ("text", "number", "date") or type(field["required"]) is not bool:
                raise BlueprintError("입력 필드 설정이 올바르지 않습니다.")
            field_ids.add(field_id)
            _text(field["label"], 48)

        states = workflow["states"]
        if not isinstance(states, list) or not 1 <= len(states) <= 6:
            raise BlueprintError("상태는 1~6개여야 합니다.")
        state_ids = set()
        for state in states:
            _object(state, ("id", "label"))
            state_id = _id(state["id"])
            if state_id not in STATE_IDS or state_id in state_ids:
                raise BlueprintError("상태 ID가 중복되었습니다.")
            state_ids.add(state_id)
            _text(state["label"], 48)
        _known_id(workflow["initialState"], state_ids)

        transitions = workflow["transitions"]
        if not isinstance(transitions, list) or len(transitions) > 12:
            raise BlueprintError("상태 변경은 최대 12개까지 설정할 수 있습니다.")
        seen = set()
        for transition in transitions:
            _object(transition, ("from", "to", "actor", "label"))
            source = _known_id(transition["from"], state_ids)
            target = _known_id(transition["to"], state_ids)
            if source == target or transition["actor"] not in ("owner", "admin"):
                raise BlueprintError("상태 변경의 출발·도착·역할이 올바르지 않습니다.")
            signature = (source, target, transition["actor"])
            if signature in seen:
                raise BlueprintError("같은 상태 변경이 중복되었습니다.")
            seen.add(signature)
            _text(transition["label"], 48)
    if "rowWorkflows" in value or "createForm" in value:
        from .row_workflow import validate_create_form, validate_row_workflows  # row flows build on this module
        validate_row_workflows(value.get("rowWorkflows", []), report)
        validate_create_form(value.get("createForm"), report)
    return value


def catalog_labels(blueprint):
    """{"<column number>": label} as Upload.field_labels stores it."""
    labels = blueprint.get("catalog", {}).get("labels", []) if isinstance(blueprint, dict) else []
    return {str(item["column"]): item["label"] for item in labels}


def catalog_sort(catalog):
    """(column number, direction) or None; stored configs from before sorting have no key."""
    sort = catalog.get("sort") if isinstance(catalog, dict) else None
    if isinstance(sort, dict) and isinstance(sort.get("column"), int) and sort["column"] > 0:
        return sort["column"], sort.get("direction", "asc")
    return None


def _parse_json(raw, *, max_bytes=MAX_RESPONSE_BYTES):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > max_bytes:
        raise BlueprintError("응답 크기가 허용 범위를 벗어났습니다.")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise BlueprintError("중복된 JSON 키입니다.")
            result[key] = value
        return result

    def invalid_constant(_):
        raise BlueprintError("잘못된 JSON 숫자입니다.")

    try:
        value = json.loads(raw, object_pairs_hook=unique_object,
                           parse_constant=invalid_constant)
    except (ValueError, RecursionError) as exc:
        raise BlueprintError("유효한 JSON 응답이 아닙니다.") from exc
    return value
