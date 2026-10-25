"""Offline request construction for the sheet-understanding call."""
import hashlib
import json
from pathlib import Path

from django.conf import settings

from .preview_request_v2 import build_input
from .sheet_understanding import understanding_schema

SETTINGS_DIR = Path(__file__).resolve().parents[1] / "claude_api_settings"
MAX_REQUEST_BYTES = 100_000
PURPOSE = "시트 이해"
# The model thinks before answering and that counts against max_tokens: a 24-column sheet spent
# 6k+ tokens thinking and 1.5k on the JSON, so 8,000 cut it off (ModelCall fc8e9aaf).
UNDERSTANDING_MAX_TOKENS = 16000


def _render(filename, replacements):
    result = (SETTINGS_DIR / filename).read_text(encoding="utf-8")
    for key, value in replacements.items():
        result = result.replace("{{" + key + "}}", json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    if "{{" in result:
        raise ValueError("프롬프트에 채워지지 않은 항목이 있습니다.")
    return result


def fingerprint(body):
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def understanding_request_body(report, *, file_name=""):
    analysis = build_input(report)
    signals = report.get("signals") or {"schema_version": 1, "note": "운영 신호가 계산되지 않았습니다."}
    body = {"model": getattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-5") or "claude-sonnet-5",
            "max_tokens": max(getattr(settings, "ANTHROPIC_MAX_TOKENS", 8000), UNDERSTANDING_MAX_TOKENS),
            "system": (SETTINGS_DIR / "sheet_understanding_system.md").read_text(encoding="utf-8"),
            "messages": [{"role": "user", "content": _render("sheet_understanding_content.md", {
                "FILE_NAME_JSON": str(file_name)[:200], "CSV_ANALYSIS_JSON": analysis, "SIGNALS_JSON": signals})}],
            "output_config": {"format": {"type": "json_schema", "schema": understanding_schema(report)}}}
    if len(json.dumps(body, ensure_ascii=False).encode("utf-8")) > MAX_REQUEST_BYTES:
        raise ValueError("Claude 요청 크기가 허용 범위를 넘었습니다.")
    return body


def understanding_approval_summary(body):
    return {"purpose": PURPOSE, "model": body["model"], "planned_call_count": 1, "automatic_retries": 0,
            "transmitted_data": "파일 이름, CSV 컬럼 분석과 최대 10개 예시 행, 표본 5,000행에서 계산한 컬럼 간 운영 신호",
            "original_csv_file": False, "request_fingerprint": fingerprint(body)}
