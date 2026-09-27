"""Offline normalization and validation of Preview config v2 responses."""

import json

from .preview_request_v2 import PreviewRequestError, build_schema


MAX_RESPONSE_BYTES = 64_000
MAX_VIEWS = 7
MAX_CHARTS = 4


class InvalidPreviewResponse(ValueError):
    pass


def _fail(message):
    raise InvalidPreviewResponse(message)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("중복 JSON 키가 있습니다.")
        result[key] = value
    return result


def _keys(value, allowed, required):
    if not isinstance(value, dict) or not set(required) <= set(value) or not set(value) <= set(allowed):
        _fail("응답 객체의 속성이 계약과 다릅니다.")


def _number(value, permitted):
    if type(value) is not int or value not in permitted:
        _fail("허용되지 않은 컬럼 번호입니다.")
    return value


def _numbers(values, permitted, *, required=False):
    if not isinstance(values, list):
        _fail("컬럼 배열이 아닙니다.")
    result = []
    seen = set()
    for value in values:
        number = _number(value, permitted)
        if number not in seen:
            result.append(number)
            seen.add(number)
    if required and not result:
        _fail("표에 표시할 컬럼이 없습니다.")
    return result[:len(permitted)]


def _charts(charts, candidates):
    if not isinstance(charts, list):
        _fail("차트 배열이 아닙니다.")
    result = []
    seen = set()
    for chart in charts:
        _keys(chart, ("type", "groupColumn", "aggregate"),
              ("type", "groupColumn", "aggregate"))
        if chart["type"] not in ("bar", "donut") or chart["aggregate"] != "count":
            _fail("허용되지 않은 차트 설정입니다.")
        group = _number(chart["groupColumn"], candidates)
        signature = (chart["type"], group, chart["aggregate"])
        if signature not in seen:
            result.append({"type": signature[0], "groupColumn": group,
                           "aggregate": signature[2]})
            seen.add(signature)
    return result[:MAX_CHARTS]


def _normalize_view(view, branches, definitions):
    if not isinstance(view, dict) or not isinstance(view.get("template"), str):
        _fail("템플릿 선택이 없습니다.")
    branch = branches.get(view["template"])
    if branch is None:
        _fail("지원하지 않는 템플릿입니다.")
    _keys(view, branch["properties"], branch["required"])
    result = {"template": view["template"]}
    for key, value in view.items():
        if key == "template":
            continue
        if key in ("fields", "columns"):
            result[key] = _numbers(value, definitions["allColumns"]["enum"],
                                   required=key == "columns")
        elif key == "charts":
            result[key] = _charts(value, definitions["chartGroupColumn"]["enum"])
        else:
            role = definitions[key]["enum"]
            result[key] = _number(value, role)
    if "fields" in result:
        dedicated = {value for key, value in result.items() if key.endswith("Column") and key != "groupColumn"}
        if "groupColumn" in result:
            dedicated.add(result["groupColumn"])
        result["fields"] = [number for number in result["fields"] if number not in dedicated]
    return result


def _normalize(raw, report):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_RESPONSE_BYTES:
        _fail("응답은 64,000바이트 이하의 JSON 문자열이어야 합니다.")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object,
                           parse_constant=lambda _: _fail("유효하지 않은 JSON 상수입니다."))
    except (ValueError, RecursionError) as exc:
        raise InvalidPreviewResponse("유효한 JSON 응답이 아닙니다.") from exc
    _keys(value, ("version", "views"), ("version", "views"))
    if type(value["version"]) is not int or value["version"] != 2:
        _fail("지원하지 않는 Preview 설정 버전입니다.")
    if not isinstance(value["views"], list) or not value["views"]:
        _fail("목록 화면이 없습니다.")
    schema = build_schema(report)
    definitions = schema["$defs"]
    branches = {branch["properties"]["template"]["enum"][0]: branch
                for branch in schema["properties"]["views"]["items"]["anyOf"]}
    views = []
    seen = set()
    for view in value["views"]:
        normalized = _normalize_view(view, branches, definitions)
        signature = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
        if signature not in seen:
            views.append(normalized)
            seen.add(signature)
    return {"version": 2, "views": views[:MAX_VIEWS]}


def prepare_preview_response(raw, report):
    """Return a validated config, falling back to a full-column table on failure.

    The caller may record validation_error and the original provider response.
    This function makes no API call and never mutates the input report.
    """
    try:
        preview = _normalize(raw, report)
        return {"preview": preview, "used_fallback": False, "validation_error": ""}
    except InvalidPreviewResponse as exc:
        columns = report.get("columns", [])
        if not columns or len(columns) > 200:
            raise PreviewRequestError("기본 표를 구성할 수 없는 분석 결과입니다.") from exc
        return {"preview": {"version": 2, "views": [
            {"template": "table", "columns": list(range(1, len(columns) + 1))}
        ]}, "used_fallback": True, "validation_error": str(exc)}
