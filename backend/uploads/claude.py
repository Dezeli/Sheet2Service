"""Claude API transport. Network calls require explicit caller approval recorded on a ModelCall."""
import json
import urllib.error
import urllib.request

from django.conf import settings

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
STRUCTURED_OUTPUTS_BETA = "structured-outputs-2025-11-13"
DEFAULT_MODEL = "claude-sonnet-5"
TIMEOUT_SECONDS = 180  # understanding calls on wide sheets take over a minute


class InferenceError(ValueError):
    pass


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


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
