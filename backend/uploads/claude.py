"""Claude API integration. Network calls require explicit caller approval."""
import json
import urllib.error
import urllib.request

from django.conf import settings

from .call_records import finish_call, start_call
from .inference import InferenceError, json_text
from .models import ModelCall
from .preview_request_v2 import build_input, build_prompt
from .preview_response_v2 import prepare_preview_response

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
STRUCTURED_OUTPUTS_BETA = "structured-outputs-2025-11-13"
DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MAX_TOKENS = 4000
TIMEOUT_SECONDS = 60


def inference_request_body(report):
    prompt = build_prompt(report)
    return {
        "model": getattr(settings, "ANTHROPIC_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL,
        "max_tokens": getattr(settings, "ANTHROPIC_MAX_TOKENS", DEFAULT_MAX_TOKENS),
        "system": prompt["system"],
        "messages": prompt["messages"],
        "output_config": prompt["output_config"],
    }


def approval_summary(upload):
    inference_input = build_input(upload.analysis)
    request_body = inference_request_body(upload.analysis)
    request_bytes = len(json_text(request_body).encode("utf-8"))
    if request_body["model"] == "claude-sonnet-5":
        # Approximate input tokens from UTF-8 size; provider usage is authoritative.
        low = (request_bytes / 3 * 2 + request_body["max_tokens"] * 10) / 1_000_000
        high = (request_bytes * 0.75 * 2 + request_body["max_tokens"] * 10) / 1_000_000
        cost_note = (f"2026-09-27 확인한 Sonnet 5 기본 단가(입력 $2/백만 토큰, 출력 $10/백만 토큰)와 "
                     f"최대 출력 기준 예상 비용은 약 US${low:.3f}~${high:.3f}입니다. "
                     "입력 토큰 수는 본문 크기로 추정했으며 실제 비용이나 상한은 아닙니다.")
    else:
        cost_note = "현재 모델의 단가를 확인한 뒤 예상 비용을 계산해야 합니다."
    return {
        "requires_approval": True,
        "approved": False,
        "purpose": "CSV 분석 결과를 바탕으로 서비스 Preview 설정 JSON 후보를 생성합니다.",
        "provider": "anthropic",
        "model": request_body["model"],
        "pricing_estimate_available": request_body["model"] == "claude-sonnet-5",
        "planned_call_count": 1,
        "automatic_retries": 0,
        "max_output_tokens": request_body["max_tokens"],
        "local_upload_id": str(upload.id),
        "transmitted_data": {
            "original_csv_file": False,
            "row_count": inference_input["row_count"],
            "column_count": len(inference_input["columns"]),
            "columns": [column["number"] for column in inference_input["columns"]],
            "samples_included": bool(inference_input["sample_rows"]),
            "sample_count": len(inference_input["sample_rows"]),
            "max_sample_rows": inference_input["sampling"]["max_rows"],
            "max_text_chars": inference_input["sampling"]["max_text_chars"],
            "truncated_value_count": len(inference_input["sampling"]["truncated_paths"]),
            "sampling_strategy": inference_input["sampling"]["strategy"],
            "request_bytes": request_bytes,
        },
        "cost_note": cost_note,
    }


def _extract_text(response_body):
    content = response_body.get("content")
    if isinstance(content, list):
        return "".join(block.get("text", "") for block in content
                       if isinstance(block, dict) and block.get("type") == "text")
    return ""


def _post_message(request_body):
    if not settings.ANTHROPIC_API_KEY:
        raise InferenceError("ANTHROPIC_API_KEY가 설정되어 있지 않습니다.")
    encoded = json_text(request_body).encode("utf-8")
    request = urllib.request.Request(
        ANTHROPIC_MESSAGES_URL,
        data=encoded,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.ANTHROPIC_API_KEY}",
            "anthropic-version": ANTHROPIC_VERSION,
            "anthropic-beta": STRUCTURED_OUTPUTS_BETA,
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
            return response.status, dict(response.headers), body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, dict(exc.headers), body
    except urllib.error.URLError as exc:
        raise InferenceError(str(exc.reason)) from exc


def run_inference(upload, *, approval_note, approved_at):
    request_body = inference_request_body(upload.analysis)
    call = start_call(
        upload=upload,
        purpose="서비스 Preview 설정 JSON 후보 생성",
        request_body=request_body,
        approval_note=approval_note,
        approved_at=approved_at,
    )
    http_status = None
    headers = {}
    response_text = ""
    usage = {}
    try:
        http_status, headers, response_text = _post_message(request_body)
        response_json = json.loads(response_text)
        usage = response_json.get("usage", {})
        raw_output = _extract_text(response_json)
        if not 200 <= http_status < 300:
            finish_call(
                call,
                status=ModelCall.Status.FAILED,
                response_body=response_text,
                http_status=http_status,
                provider_request_id=headers.get("request-id", ""),
                usage=usage,
                error_type=response_json.get("error", {}).get("type", "http_error"),
                error_message=response_json.get("error", {}).get("message", ""),
            )
            raise InferenceError("Claude API 호출이 실패했습니다.")
        parsed = prepare_preview_response(raw_output, upload.analysis)
        finish_call(
            call,
            status=ModelCall.Status.SUCCEEDED,
            response_body=response_text,
            http_status=http_status,
            provider_request_id=headers.get("request-id", ""),
            parsed_result=parsed,
            validation_error=parsed["validation_error"],
            usage=usage,
        )
        return call, parsed
    except (ValueError, InferenceError) as exc:
        if ModelCall.objects.filter(pk=call.pk, status=ModelCall.Status.STARTED).exists():
            finish_call(
                call,
                status=ModelCall.Status.FAILED,
                response_body=response_text,
                http_status=http_status,
                provider_request_id=headers.get("request-id", ""),
                usage=usage,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
                validation_error=str(exc) if isinstance(exc, InferenceError) else "",
            )
        raise
