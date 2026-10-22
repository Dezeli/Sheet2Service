"""Offline Claude request construction for composable service generation and revision."""

import hashlib
import json
from pathlib import Path

from django.conf import settings

from .preview_request_v2 import build_input
from .service_blueprint import FIELD_IDS, STATE_IDS, WORKFLOW_IDS, validate_blueprint


SETTINGS_DIR = Path(__file__).resolve().parents[1] / "claude_api_settings"
MAX_REQUEST_BYTES = 100_000
MAX_USER_REQUEST = 500
PAGE_LABELS = {"DashBoard": "대시보드", "User": "사용자", "Admin": "관리자"}


def _object(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def blueprint_schema(report):
    """Only column references vary between CSV files; all executable parts are finite."""
    count = len(report["columns"])
    if not 1 <= count <= 200:
        raise ValueError("지원하지 않는 CSV 컬럼 수입니다.")
    column = {"type": "integer", "enum": list(range(1, count + 1))}
    columns = {"type": "array", "items": column}
    text = {"type": "string"}
    state_id = {"type": "string", "enum": list(STATE_IDS)}
    state = _object({"id": state_id, "label": text})
    transition = _object({"from": state_id, "to": state_id,
                          "actor": {"type": "string", "enum": ["owner", "admin"]}, "label": text})
    field = _object({"id": {"type": "string", "enum": list(FIELD_IDS)}, "label": text,
                     "type": {"type": "string", "enum": ["text", "number", "date"]},
                     "required": {"type": "boolean"}})
    workflow = _object({"id": {"type": "string", "enum": list(WORKFLOW_IDS)}, "title": text, "subjectColumn": column,
                        "fields": {"type": "array", "items": field},
                        "states": {"type": "array", "items": state},
                        "initialState": state_id,
                        "transitions": {"type": "array", "items": transition}})
    return _object({"version": {"type": "integer", "enum": [1]},
                    "title": text, "summary": text,
                    "catalog": _object({"titleColumn": column, "visibleColumns": columns,
                                        "searchColumns": columns, "filterColumns": columns,
                                        "charts": {"type": "array", "items": _object({
                                            "kind": {"type": "string", "enum": ["count_by"]},
                                            "groupColumn": column})}}),
                    "workflows": {"type": "array", "items": workflow}})


def _render(filename, replacements):
    result = (SETTINGS_DIR / filename).read_text(encoding="utf-8")
    for key, value in replacements.items():
        result = result.replace("{{" + key + "}}", json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    if "{{" in result:
        raise ValueError("프롬프트에 채워지지 않은 항목이 있습니다.")
    return result


def request_body(report, *, current=None, user_request=None, current_page=None):
    analysis = build_input(report)
    replacements = {"CSV_ANALYSIS_JSON": analysis}
    if current is None:
        system = "service_blueprint_create_system.md"
        content = "service_blueprint_create_content.md"
        schema = blueprint_schema(report)
    else:
        validate_blueprint(current, report)
        if not isinstance(user_request, str) or not 10 <= len(user_request.strip()) <= MAX_USER_REQUEST:
            raise ValueError("수정 요청은 10~500자로 입력해 주세요.")
        if current_page not in PAGE_LABELS:
            raise ValueError("현재 화면이 올바르지 않습니다.")
        replacements.update(CURRENT_BLUEPRINT_JSON=current, USER_REQUEST_JSON=user_request.strip(),
                            CURRENT_PAGE_JSON=PAGE_LABELS[current_page])
        system = "service_blueprint_revision_system.md"
        content = "service_blueprint_revision_content.md"
        schema = _object({"status": {"type": "string", "enum": ["applied", "unsupported", "needs_input"]},
                          "message": {"type": "string"}, "blueprint": blueprint_schema(report)})
    body = {"model": getattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-5") or "claude-sonnet-5",
            "max_tokens": getattr(settings, "ANTHROPIC_MAX_TOKENS", 8000),
            "system": (SETTINGS_DIR / system).read_text(encoding="utf-8"),
            "messages": [{"role": "user", "content": _render(content, replacements)}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}}}
    if len(json.dumps(body, ensure_ascii=False).encode("utf-8")) > MAX_REQUEST_BYTES:
        raise ValueError("Claude 요청 크기가 허용 범위를 넘었습니다.")
    return body


def fingerprint(body):
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def approval_summary(body, *, revision=False):
    return {"purpose": "서비스 수정" if revision else "CSV에 맞는 서비스 생성",
            "model": body["model"], "planned_call_count": 1, "automatic_retries": 0,
            "transmitted_data": "CSV 컬럼 분석과 최대 10개 예시 행, 수정 시 현재 서비스 설정과 입력한 요청",
            "original_csv_file": False, "request_fingerprint": fingerprint(body)}
