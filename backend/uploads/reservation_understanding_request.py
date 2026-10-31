"""Offline request construction and the single approved call for reservation-sheet understanding."""
import hashlib
import json
from pathlib import Path

from django.conf import settings

from .call_records import finish_call, start_call
from .claude import InferenceError
from .models import ModelCall
from .analysis_input import build_input
from .reservation_understanding import UnderstandingError, parse_understanding_response, understanding_schema

SETTINGS_DIR = Path(__file__).resolve().parents[1] / "claude_api_settings"
MAX_REQUEST_BYTES = 100_000
PURPOSE = "예약 시트 이해"
# The model thinks before answering and that counts against max_tokens; a 24-column sheet spent
# 6k+ tokens thinking and 1.5k on the JSON, so 8,000 cut it off on the previous line.
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
            "system": (SETTINGS_DIR / "reservation_understanding_system.md").read_text(encoding="utf-8"),
            "messages": [{"role": "user", "content": _render("reservation_understanding_content.md", {
                "FILE_NAME_JSON": str(file_name)[:200], "CSV_ANALYSIS_JSON": analysis, "SIGNALS_JSON": signals})}],
            "output_config": {"format": {"type": "json_schema", "schema": understanding_schema(report)}}}
    if len(json.dumps(body, ensure_ascii=False).encode("utf-8")) > MAX_REQUEST_BYTES:
        raise ValueError("Claude 요청 크기가 허용 범위를 넘었습니다.")
    return body


def understanding_approval_summary(body):
    return {"purpose": PURPOSE, "model": body["model"], "planned_call_count": 1, "automatic_retries": 0,
            "max_output_tokens": body["max_tokens"],
            "transmitted_data": "파일 이름, CSV 컬럼 분석과 최대 10개 예시 행, 표본 5,000행에서 계산한 컬럼 간 운영 신호",
            "original_csv_file": False, "request_fingerprint": fingerprint(body)}


def run_understanding(upload, *, approval_note, approved_at):
    """Exactly one network call, only after the caller has checked explicit approval.

    Returns (call, understanding, notes). The raw provider response is kept on the ModelCall even
    when validation lowers or rejects parts of it.
    """
    from .claude import _extract_text, _post_message

    body = understanding_request_body(upload.analysis, file_name=upload.original_name)
    call = start_call(upload=upload, purpose=PURPOSE, request_body=body, approval_note=approval_note,
                      approved_at=approved_at)
    http_status, headers, response_text, usage = None, {}, "", {}
    try:
        http_status, headers, response_text = _post_message(body)
        provider = json.loads(response_text)
        usage = provider.get("usage", {})
        if not 200 <= http_status < 300:
            finish_call(call, status=ModelCall.Status.FAILED, response_body=response_text, http_status=http_status,
                        provider_request_id=headers.get("request-id", ""), usage=usage,
                        error_type=provider.get("error", {}).get("type", "http_error"),
                        error_message=provider.get("error", {}).get("message", ""))
            raise InferenceError("Claude API 호출이 실패했습니다.")
        if provider.get("stop_reason") == "max_tokens":
            raise InferenceError("Claude 응답이 길이 제한으로 중단되었습니다. 다시 시도해 주세요.")
        understanding, notes = parse_understanding_response(_extract_text(provider), upload.analysis)
        finish_call(call, status=ModelCall.Status.SUCCEEDED, response_body=response_text, http_status=http_status,
                    provider_request_id=headers.get("request-id", ""),
                    parsed_result={"understanding": understanding, "notes": notes}, usage=usage)
        upload.understanding = understanding
        upload.save(update_fields=["understanding"])
        return call, understanding, notes
    except (ValueError, InferenceError, UnderstandingError) as exc:
        if ModelCall.objects.filter(pk=call.pk, status=ModelCall.Status.STARTED).exists():
            finish_call(call, status=ModelCall.Status.FAILED, response_body=response_text, http_status=http_status,
                        provider_request_id=headers.get("request-id", ""), usage=usage,
                        error_type=exc.__class__.__name__, error_message=str(exc), validation_error=str(exc))
        raise
