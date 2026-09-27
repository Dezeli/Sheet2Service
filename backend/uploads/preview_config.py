"""Validated configuration for the React Preview runtime."""


class PreviewConfigError(ValueError):
    pass


TEMPLATE_CATALOG = {
    "cards": {
        "ready": True,
        "required": ("title",),
        "optional": ("subtitle", "image", "badge"),
        "lists": ("fields",),
    },
    "detail": {
        "ready": True,
        "required": ("title",),
        "optional": ("image", "badge", "link", "phone"),
        "lists": ("fields",),
    },
    "table": {
        "ready": True,
        "required": (),
        "optional": (),
        "lists": ("fields",),
    },
    "map": {
        "ready": False,
        "required": ("title", "latitude", "longitude"),
        "optional": (),
        "lists": ("fields",),
    },
    "calendar": {
        "ready": False,
        "required": ("title", "start"),
        "optional": ("end",),
        "lists": ("fields",),
    },
    "grouped": {
        "ready": True,
        "required": ("title", "group"),
        "optional": ("subtitle", "image", "badge"),
        "lists": ("fields",),
    },
    "form": {
        "ready": False,
        "required": (),
        "optional": (),
        "lists": ("fields",),
    },
}

CHART_TYPES = ("bar", "donut")
CHART_AGGREGATES = ("count",)
LIST_TEMPLATES = ("cards", "table", "grouped")
DETAIL_LINK_TEMPLATES = ("cards", "grouped")


def _fail(message):
    raise PreviewConfigError(message)


def _object(value, allowed_keys, message):
    if not isinstance(value, dict) or any(key not in allowed_keys for key in value):
        _fail(message)


def _non_empty_text(value, max_length, message):
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        _fail(message)


def _page_id(value, seen):
    _non_empty_text(value, 64, "페이지 ID가 잘못되었거나 중복되었습니다.")
    if not value[0].islower() or any(not (char.islower() or char.isdigit() or char == "_") for char in value):
        _fail("페이지 ID가 잘못되었거나 중복되었습니다.")
    if value in seen:
        _fail("페이지 ID가 잘못되었거나 중복되었습니다.")


def _column_ids(columns):
    ids = set()
    for column in columns:
        if not isinstance(column, dict) or not isinstance(column.get("id"), str):
            _fail("컬럼 목록이 올바르지 않습니다.")
        ids.add(column["id"])
    return ids


def _validate_binding_refs(value, *, list_slot, column_ids):
    refs = value if list_slot else [value]
    if (not isinstance(refs, list) or not refs or len(refs) > 200
            or len(set(refs)) != len(refs)
            or any(not isinstance(ref, str) or ref not in column_ids for ref in refs)):
        _fail("컬럼 연결이 비어 있거나 잘못되었습니다.")


def _validate_charts(charts, page_template, column_ids):
    if page_template not in LIST_TEMPLATES or not isinstance(charts, list) or len(charts) > 4:
        _fail("그래프는 목록 페이지에 최대 4개까지 설정할 수 있습니다.")
    for chart in charts:
        _object(chart, ("type", "title", "groupBy", "aggregate"), "그래프 설정이 올바르지 않습니다.")
        if chart.get("type") not in CHART_TYPES:
            _fail("그래프 종류·집계·컬럼 설정이 올바르지 않습니다.")
        if chart.get("aggregate") not in CHART_AGGREGATES:
            _fail("그래프 종류·집계·컬럼 설정이 올바르지 않습니다.")
        if chart.get("groupBy") not in column_ids:
            _fail("그래프 종류·집계·컬럼 설정이 올바르지 않습니다.")
        _non_empty_text(chart.get("title"), 120, "그래프 제목이 필요합니다.")



def _normalize_column_ref(value, column_ids):
    if not isinstance(value, str):
        return value
    trimmed = value.strip().strip(",.;:??")
    return trimmed if trimmed in column_ids else value


def normalize_preview_config(config, columns):
    """Deterministically remove provider noise before strict validation.

    This never invents pages, bindings, or columns. It drops unusable binding
    slots and blank optional detail links, and trims simple punctuation around
    a column ID when the result is an existing input column.
    """
    if not isinstance(config, dict) or not isinstance(config.get("pages"), list):
        return config
    column_ids = _column_ids(columns)
    normalized = dict(config)
    pages = []
    for page in config["pages"]:
        if not isinstance(page, dict):
            pages.append(page)
            continue
        copied = dict(page)
        if isinstance(copied.get("detailPage"), str) and not copied["detailPage"].strip():
            copied.pop("detailPage")
        spec = TEMPLATE_CATALOG.get(page.get("template"))
        bindings = page.get("bindings")
        if spec is not None and isinstance(bindings, dict):
            allowed = set((*spec["required"], *spec["optional"], *spec["lists"]))
            copied_bindings = {}
            for slot, value in bindings.items():
                if slot not in allowed:
                    continue
                if slot in spec["lists"] and isinstance(value, list):
                    copied_bindings[slot] = [_normalize_column_ref(item, column_ids) for item in value]
                else:
                    copied_bindings[slot] = _normalize_column_ref(value, column_ids)
            copied["bindings"] = copied_bindings
        if isinstance(copied.get("charts"), list):
            copied["charts"] = [
                {**chart, "groupBy": _normalize_column_ref(chart.get("groupBy"), column_ids)}
                if isinstance(chart, dict) else chart
                for chart in copied["charts"]
            ]
        pages.append(copied)
    referenced_detail_pages = {
        page.get("detailPage") for page in pages
        if isinstance(page, dict) and isinstance(page.get("detailPage"), str)
    }
    filtered_pages = []
    for page in pages:
        if not isinstance(page, dict):
            filtered_pages.append(page)
            continue
        spec = TEMPLATE_CATALOG.get(page.get("template"))
        bindings = page.get("bindings")
        if spec is None or not isinstance(bindings, dict) or page.get("id") in referenced_detail_pages:
            filtered_pages.append(page)
            continue
        placeholder_like = (
            page.get("id") == "placeholder"
            or str(page.get("id", "")).startswith("placeholder_")
            or str(page.get("title", "")).strip().lower() == "placeholder"
        )
        empty_bindings = not bindings
        if placeholder_like and empty_bindings:
            continue
        filtered_pages.append(page)
    normalized["pages"] = filtered_pages or pages
    return normalized


def validate_preview_config(config, columns, *, require_ready=True):
    """Return config when it is safe for the Preview runtime."""
    _object(config, ("version", "title", "pages"), "지원하지 않는 설정입니다.")
    if type(config.get("version")) is not int or config["version"] != 1:
        _fail("Preview 이름 또는 버전이 올바르지 않습니다.")
    _non_empty_text(config.get("title"), 120, "Preview 이름 또는 버전이 올바르지 않습니다.")
    pages = config.get("pages")
    if not isinstance(pages, list) or not pages or len(pages) > 7:
        _fail("페이지는 1~7개여야 합니다.")

    column_ids = _column_ids(columns)
    pages_by_id = {}
    for page in pages:
        _object(page, ("id", "template", "title", "bindings", "detailPage", "charts"), "지원하지 않는 설정입니다.")
        _page_id(page.get("id"), pages_by_id)
        template = page.get("template")
        spec = TEMPLATE_CATALOG.get(template)
        if spec is None:
            _fail("지원하지 않는 템플릿입니다.")
        if require_ready and not spec["ready"]:
            _fail("아직 준비되지 않은 템플릿입니다.")
        _non_empty_text(page.get("title"), 120, "페이지 이름이 필요합니다.")

        allowed_bindings = (*spec["required"], *spec["optional"], *spec["lists"])
        bindings = page.get("bindings")
        _object(bindings, allowed_bindings, "지원하지 않는 설정입니다.")
        for slot in spec["required"]:
            if slot not in bindings:
                _fail(f"{slot} 컬럼 연결이 필요합니다.")
        for slot, value in bindings.items():
            _validate_binding_refs(value, list_slot=slot in spec["lists"], column_ids=column_ids)
        if template in ("table", "form") and not bindings.get("fields"):
            _fail("표시할 필드가 필요합니다.")
        if "detailPage" in page and template not in DETAIL_LINK_TEMPLATES:
            _fail("상세 연결은 카드 또는 그룹 목록에서만 지원합니다.")
        if "charts" in page:
            _validate_charts(page["charts"], template, column_ids)
        pages_by_id[page["id"]] = page

    for page in pages:
        detail_page = page.get("detailPage")
        if detail_page is not None and pages_by_id.get(detail_page, {}).get("template") != "detail":
            _fail("상세 페이지 연결이 올바르지 않습니다.")
    return config
