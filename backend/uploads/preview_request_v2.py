"""Offline CSV-specific Claude request construction for Preview config v2."""

import copy
import json
from pathlib import Path


SETTINGS_DIR = Path(__file__).resolve().parents[1] / "claude_api_settings"
MAX_INPUT_BYTES = 64_000
MAX_SAMPLE_ROWS = 10
MAX_TEXT_CHARS = 160


class PreviewRequestError(ValueError):
    pass


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _clip(value, path, truncated):
    if isinstance(value, str) and len(value) > MAX_TEXT_CHARS:
        truncated.append(path)
        return value[:MAX_TEXT_CHARS]
    return value


def _column_candidates(columns, row_count, samples):
    populated = [number for number, col in enumerate(columns, 1) if col["non_empty_count"] > 0]
    title = [number for number in populated if columns[number - 1]["candidate"] not in ("date", "datetime", "time", "formula")]
    if not title:
        title = populated or list(range(1, len(columns) + 1))
    group = [number for number in populated if row_count > 1 and
             1 < columns[number - 1]["unique_count"] < row_count and
             columns[number - 1]["unique_count"] <= max(20, row_count // 2)]
    badge = group.copy()
    image_terms = ("image", "photo", "picture", "thumbnail", "이미지", "사진", "썸네일")
    image = []
    for number in populated:
        name = columns[number - 1]["name"].lower()
        observed = [row["values"][number - 1] for row in samples]
        url_image = any(isinstance(value, str) and value.lower().split("?", 1)[0].endswith(
            (".jpg", ".jpeg", ".png", ".gif", ".webp")) and value.startswith(("https://", "http://"))
            for value in observed)
        if any(term in name for term in image_terms) or url_image:
            image.append(number)
    return {"allColumns": list(range(1, len(columns) + 1)),
            "titleColumn": title, "subtitleColumn": populated,
            "imageColumn": image, "badgeColumn": badge,
            "groupColumn": group, "chartGroupColumn": group}


def _object(properties, required):
    return {"type": "object", "properties": properties,
            "required": required, "additionalProperties": False}


def _column_ref(role):
    return {"$ref": f"#/$defs/{role}"}


def _view(template, candidates):
    properties = {"template": {"type": "string", "enum": [template]}}
    required = ["template"]
    if template == "table":
        properties["columns"] = _column_ref("tableColumns")
        required.append("columns")
    else:
        if template == "grouped":
            properties["groupColumn"] = _column_ref("groupColumn")
            required.append("groupColumn")
        properties["titleColumn"] = _column_ref("titleColumn")
        required.append("titleColumn")
        for attribute, role in (("subtitleColumn", "subtitleColumn"),
                                ("imageColumn", "imageColumn"),
                                ("badgeColumn", "badgeColumn")):
            if template == "grouped" and attribute == "imageColumn":
                continue
            if candidates[role]:
                properties[attribute] = _column_ref(role)
        properties["fields"] = _column_ref("fieldList")
        required.append("fields")
    if candidates["chartGroupColumn"]:
        properties["charts"] = _column_ref("charts")
    return _object(properties, required)


def build_schema(report):
    """Restrict every model-selected value to this CSV's observed columns."""
    columns = report["columns"]
    if not columns or len(columns) > 200:
        raise PreviewRequestError("컬럼 수가 v2 요청 범위를 벗어났습니다.")
    candidates = _column_candidates(columns, report["row_count"], report.get("inference_samples", []))
    definitions = {role: {"type": "integer", "enum": numbers}
                   for role, numbers in candidates.items() if numbers}
    definitions["fieldList"] = {"type": "array", "items": _column_ref("allColumns")}
    definitions["tableColumns"] = {"type": "array", "minItems": 1,
                                   "items": _column_ref("allColumns")}
    if candidates["chartGroupColumn"]:
        definitions["charts"] = {"type": "array", "items": _object({
            "type": {"type": "string", "enum": ["bar", "donut"]},
            "groupColumn": _column_ref("chartGroupColumn"),
            "aggregate": {"type": "string", "enum": ["count"]},
        }, ["type", "groupColumn", "aggregate"])}
    templates = ["cards", "table"]
    if candidates["groupColumn"]:
        templates.append("grouped")
    return _object({
        "version": {"type": "integer", "enum": [2]},
        "views": {"type": "array", "minItems": 1,
                  "items": {"anyOf": [_view(template, candidates) for template in templates]}},
    }, ["version", "views"]) | {"$defs": definitions}


def build_input(report):
    """Use an explicit allowlist; never send the raw file or upload metadata."""
    if report.get("schema_version") != 1:
        raise PreviewRequestError("지원하지 않는 분석 버전입니다.")
    columns = report["columns"]
    samples = report.get("inference_samples")
    if not isinstance(samples, list) or len(samples) > MAX_SAMPLE_ROWS:
        raise PreviewRequestError("v2 요청에 필요한 예시 행이 없습니다. CSV를 다시 분석하거나 업로드해 주세요.")
    truncated = []
    allowed = ("name", "candidate", "non_empty_count", "missing_count",
               "unique_count", "type_counts", "number_ratio", "date_ratio", "issues")
    supplied_columns = []
    for number, column in enumerate(columns, 1):
        item = {"number": number}
        for key in allowed:
            value = copy.deepcopy(column[key])
            if key == "name":
                value = _clip(value, f"columns.{number}.name", truncated)
            elif key == "issues":
                value = [_clip(issue, f"columns.{number}.issues.{index}", truncated)
                         for index, issue in enumerate(value)]
            item[key] = value
        supplied_columns.append(item)
    sample_rows = []
    for row in samples:
        if len(row["values"]) != len(columns):
            raise PreviewRequestError("예시 행과 컬럼 수가 다릅니다.")
        sample_rows.append({"row_number": row["row_number"],
                            "values": [_clip(value, f'sample_rows.{row["row_number"]}.{number}', truncated)
                                       for number, value in enumerate(row["values"], 1)]})
    result = {"row_count": report["row_count"], "columns": supplied_columns,
              "warnings": [_clip(value, f"warnings.{index}", truncated)
                           for index, value in enumerate(report["warnings"])],
              "sample_rows": sample_rows,
              "sampling": {"strategy": "first_2_middle_2_last_2_and_4_seeded_stratified_random_nonblank_rows",
                           "max_rows": MAX_SAMPLE_ROWS, "max_text_chars": MAX_TEXT_CHARS,
                           "truncated_paths": truncated, "representative": False}}
    if len(_json(result).encode("utf-8")) > MAX_INPUT_BYTES:
        raise PreviewRequestError("v2 추론 입력이 64,000바이트를 초과했습니다.")
    return result


def build_prompt(report):
    """Prepare a request fragment without credentials, persistence or network."""
    content = build_input(report)
    schema = build_schema(report)
    template = (SETTINGS_DIR / "content_template.md").read_text(encoding="utf-8")
    replacements = {"ROW_COUNT": content["row_count"], "COLUMNS_JSON": content["columns"],
                    "WARNINGS_JSON": content["warnings"], "SAMPLE_ROWS_JSON": content["sample_rows"],
                    "SAMPLING_JSON": content["sampling"]}
    for key, value in replacements.items():
        template = template.replace("{{" + key + "}}", _json(value))
    if "{{" in template:
        raise PreviewRequestError("채워지지 않은 콘텐츠 템플릿 항목이 있습니다.")
    return {"system": (SETTINGS_DIR / "system_prompt.md").read_text(encoding="utf-8"),
            "messages": [{"role": "user", "content": template}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}}}
