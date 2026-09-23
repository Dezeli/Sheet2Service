"""Claude API integration. Network calls require explicit caller approval."""
import json
import urllib.error
import urllib.request

from django.conf import settings

from .call_records import finish_call, start_call
from .inference import InferenceError, build_input, build_prompt, json_text, validate_response
from .models import ModelCall

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
STRUCTURED_OUTPUTS_BETA = "structured-outputs-2025-11-13"
DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MAX_TOKENS = 4000
TIMEOUT_SECONDS = 60


def inference_request_body(report, *, include_samples=True):
    prompt = build_prompt(report, include_samples=include_samples)
    return {
        "model": getattr(settings, "ANTHROPIC_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL,
        "max_tokens": getattr(settings, "ANTHROPIC_MAX_TOKENS", DEFAULT_MAX_TOKENS),
        "system": prompt["system"],
        "messages": prompt["messages"],
        "output_config": prompt["output_config"],
    }


def approval_summary(upload, *, include_samples=True):
    inference_input = build_input(upload.analysis, include_samples=include_samples)
    request_body = inference_request_body(upload.analysis, include_samples=include_samples)
    return {
        "requires_approval": True,
        "approved": False,
        "purpose": "CSV 분석 결과를 바탕으로 서비스 Preview 설정 JSON 후보를 생성합니다.",
        "provider": "anthropic",
        "model": request_body["model"],
        "planned_call_count": 1,
        "automatic_retries": 0,
        "max_output_tokens": request_body["max_tokens"],
        "local_upload_id": str(upload.id),
        "transmitted_data": {
            "original_csv_file": False,
            "row_count": inference_input["row_count"],
            "column_count": len(inference_input["columns"]),
            "columns": [column["id"] for column in inference_input["columns"]],
            "samples_included": inference_input["sampling"]["included"],
            "sample_count": len(inference_input["samples"]),
            "max_sample_rows": inference_input["sampling"]["max_rows"],
            "max_text_chars": inference_input["sampling"]["max_text_chars"],
            "request_bytes": len(json_text(request_body).encode("utf-8")),
        },
        "cost_note": "실제 비용은 Claude 응답 usage의 입력/출력 토큰에 따라 정해집니다. 호출은 승인 후 1회만 실행합니다.",
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


def run_inference(upload, *, approval_note, approved_at, include_samples=True):
    inference_input = build_input(upload.analysis, include_samples=include_samples)
    request_body = inference_request_body(upload.analysis, include_samples=include_samples)
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
        parsed = validate_response(raw_output, inference_input)
        finish_call(
            call,
            status=ModelCall.Status.SUCCEEDED,
            response_body=response_text,
            http_status=http_status,
            provider_request_id=headers.get("request-id", ""),
            parsed_result=parsed,
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
