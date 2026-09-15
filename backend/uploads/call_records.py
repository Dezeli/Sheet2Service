"""Persistence only. Callers must obtain approval before any network request."""
import json

from django.conf import settings
from django.utils import timezone

from .models import ModelCall


def _clean(value):
    """Never persist auth headers or the configured API key."""
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()
                if key.lower().replace("_", "-") not in {
                    "authorization", "x-api-key", "api-key", "anthropic-api-key"}}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, str) and settings.ANTHROPIC_API_KEY:
        return value.replace(settings.ANTHROPIC_API_KEY, "[REDACTED]")
    return value


def start_call(*, purpose, request_body, approval_note, approved_at, upload=None):
    if not purpose.strip() or not approval_note.strip() or approved_at is None:
        raise ValueError("호출 목적과 명시적 승인 기록이 필요합니다.")
    if not isinstance(request_body.get("model"), str) or not request_body["model"].strip():
        raise ValueError("요청 본문에 모델이 필요합니다.")
    # Save before the caller sends anything; a database failure prevents progress.
    return ModelCall.objects.create(
        upload=upload, purpose=_clean(purpose), model=_clean(request_body["model"]),
        request_body=_clean(request_body), approval_note=_clean(approval_note),
        approved_at=approved_at,
    )


def finish_call(call, *, status, response_body="", http_status=None,
                provider_request_id="", parsed_result=None, validation_error="",
                usage=None, error_type="", error_message=""):
    if status not in (ModelCall.Status.SUCCEEDED, ModelCall.Status.FAILED, ModelCall.Status.UNKNOWN):
        raise ValueError("완료 상태가 필요합니다.")
    # Preserve raw provider text, including malformed JSON, except secret redaction.
    try:
        decoded = json.loads(response_body)
        cleaned = _clean(decoded)
        if cleaned != decoded:
            response_body = json.dumps(cleaned, ensure_ascii=False)
    except (ValueError, TypeError):
        response_body = _clean(response_body)
    completed_at = timezone.now()
    values = dict(
        status=status, response_body=response_body, http_status=http_status,
        provider_request_id=_clean(provider_request_id), parsed_result=_clean(parsed_result),
        validation_error=_clean(validation_error), usage=_clean(usage or {}),
        error_type=_clean(error_type), error_message=_clean(error_message),
        completed_at=completed_at,
        duration_ms=max(0, int((completed_at - call.started_at).total_seconds() * 1000)),
    )
    if not ModelCall.objects.filter(pk=call.pk, status=ModelCall.Status.STARTED).update(**values):
        raise ValueError("이미 완료된 호출 기록은 덮어쓰지 않습니다.")
    call.refresh_from_db()
    return call
