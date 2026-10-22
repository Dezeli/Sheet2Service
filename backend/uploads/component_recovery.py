"""Revalidate the specific historical overlap error offline; never call Claude again."""

import json
import re

from django.db import transaction

from .claude import _extract_text
from .component_planning import parse_planned_revision
from .component_recording import record_revision_matches
from .models import ComponentMatch, ModelCall


OLD_ERROR = "관련 후보가 있어 생성 근거를 다시 검토해야 합니다."
CURRENT_BLUEPRINT = re.compile(r"<current_blueprint>\s*(.*?)\s*</current_blueprint>", re.DOTALL)


def revalidate_failed_component_call(call):
    """Read the saved provider response and original blueprint without any network request."""
    if call.status != ModelCall.Status.FAILED or call.error_message != OLD_ERROR \
            or call.http_status != 200 or call.purpose != "서비스 수정" or not call.upload_id:
        raise ValueError("이 호출은 해당 부품 판단 오류의 복구 대상이 아닙니다.")
    try:
        content = call.request_body["messages"][0]["content"]
        match = CURRENT_BLUEPRINT.search(content)
        if match is None:
            raise ValueError("기존 설정을 찾을 수 없습니다.")
        current = json.loads(match.group(1))
        provider = json.loads(call.response_body)
        raw = _extract_text(provider)
    except (KeyError, IndexError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError("저장된 호출을 읽을 수 없습니다.") from exc
    return parse_planned_revision(raw, call.upload.analysis, current)


def recover_failed_component_call(call_id):
    """Create candidates from a now-valid response; retain the original failed audit status."""
    with transaction.atomic():
        call = ModelCall.objects.select_for_update().get(pk=call_id)
        result = revalidate_failed_component_call(call)
        existing = list(ComponentMatch.objects.filter(model_call=call, candidate__isnull=False)
                        .values_list("candidate_id", flat=True))
        if existing:
            return sorted(set(existing))
        if result["status"] != "unsupported":
            raise ValueError("복구할 미구현 부품 계획이 없습니다.")
        record_revision_matches(call.upload, call, result)
        return [item["id"] for item in result["candidates"]]
