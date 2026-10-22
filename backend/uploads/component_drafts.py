"""Offline contract for generated component source; never imports or executes it."""

import ast
import json
from pathlib import Path

from django.conf import settings

from .component_candidates import related_component_candidates
from .models import ComponentCandidate


SETTINGS = Path(__file__).resolve().parents[1] / "claude_api_settings"
ROLES = ("backend", "frontend", "style", "backend_test", "frontend_test")
MAX_SOURCE_BYTES = 40_000
MAX_TOTAL_BYTES = 100_000
MAX_REQUEST_BYTES = 100_000


def draft_schema(candidate):
    """Provider-friendly enums; lengths and cross-field rules are checked locally."""
    text = {"type": "string"}
    file_schema = {"type": "object", "properties": {
        "role": {"type": "string", "enum": list(ROLES)}, "source": text},
        "required": ["role", "source"], "additionalProperties": False}
    return {"type": "object", "properties": {
        "status": {"type": "string", "enum": ["draft", "needs_input"]},
        "surface": {"type": "string", "enum": [candidate.surface]},
        "capabilities": {"type": "array", "items": {
            "type": "string", "enum": candidate.capabilities or ["request.unclassified"]}},
        "baseComponent": {"type": "string", "enum": [
            candidate.base_component.key if candidate.base_component else "none"]},
        "summary": text,
        "question": text,
        "files": {"type": "array", "items": file_schema},
    }, "required": ["status", "surface", "capabilities", "baseComponent", "summary", "question", "files"],
        "additionalProperties": False}


def draft_prompt(candidate, *, source_plan=None):
    """Build one prospective call without CSV data, secrets, or related-candidate text."""
    if candidate.status not in (ComponentCandidate.Status.OPEN, ComponentCandidate.Status.IN_PROGRESS):
        raise ValueError("열린 부품 후보만 초안을 만들 수 있습니다.")
    plan = {"surface": candidate.surface, "knownCapabilities": candidate.capabilities,
            "newRequirement": candidate.new_requirement,
            "baseComponent": candidate.base_component.key if candidate.base_component else "none"}
    context = {"candidate_id": candidate.pk, "surface": candidate.surface,
               "capabilities": candidate.capabilities,
               "new_requirement": source_plan["newRequirement"] if source_plan else candidate.new_requirement,
               "decision": candidate.decision, "base_component": plan["baseComponent"],
               "blocker": candidate.blocker, "reason": source_plan["reason"] if source_plan else candidate.reason,
               "related_candidates": related_component_candidates(plan, exclude_id=candidate.pk)}
    content = (SETTINGS / "component_draft_content.md").read_text(encoding="utf-8")
    return {"system": (SETTINGS / "component_draft_system.md").read_text(encoding="utf-8"),
            "content": content.replace("{{CANDIDATE_JSON}}", json.dumps(context, ensure_ascii=False)),
            "schema": draft_schema(candidate)}


def draft_request_body(candidate, *, source_plan=None):
    materials = draft_prompt(candidate, source_plan=source_plan)
    body = {"model": getattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-5") or "claude-sonnet-5",
            "max_tokens": getattr(settings, "ANTHROPIC_MAX_TOKENS", 8000),
            "system": materials["system"],
            "messages": [{"role": "user", "content": materials["content"]}],
            "output_config": {"format": {"type": "json_schema", "schema": materials["schema"]}}}
    if len(json.dumps(body, ensure_ascii=False).encode("utf-8")) > MAX_REQUEST_BYTES:
        raise ValueError("부품 초안 요청 크기가 허용 범위를 넘었습니다.")
    return body


def validate_component_draft(value, candidate):
    """Validate only the response contract and Python syntax, not runtime safety."""
    fields = {"status", "surface", "capabilities", "baseComponent", "summary", "question", "files"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("부품 초안 응답 필드가 올바르지 않습니다.")
    if value["status"] not in ("draft", "needs_input") or value["surface"] != candidate.surface \
            or not isinstance(value["capabilities"], list) or value["capabilities"] != candidate.capabilities \
            or value["baseComponent"] != (candidate.base_component.key if candidate.base_component else "none") \
            or not isinstance(value["summary"], str) or len(value["summary"]) > 300 \
            or not isinstance(value["question"], str) or len(value["question"]) > 300 \
            or not isinstance(value["files"], list) or len(value["files"]) > len(ROLES):
        raise ValueError("부품 초안 응답 값이 올바르지 않습니다.")
    if value["status"] == "needs_input":
        if not value["question"].strip() or value["files"]:
            raise ValueError("추가 질문 응답이 올바르지 않습니다.")
        return value
    if value["question"] or not value["summary"].strip():
        raise ValueError("부품 초안 요약 또는 질문이 올바르지 않습니다.")
    seen = set()
    total = 0
    for item in value["files"]:
        if not isinstance(item, dict) or set(item) != {"role", "source"} \
                or not isinstance(item["role"], str) or item["role"] not in ROLES \
                or item["role"] in seen or not isinstance(item["source"], str):
            raise ValueError("부품 초안 파일이 올바르지 않습니다.")
        seen.add(item["role"])
        try:
            size = len(item["source"].encode("utf-8"))
        except UnicodeError as exc:
            raise ValueError("부품 초안 텍스트 인코딩이 올바르지 않습니다.") from exc
        if not 1 <= size <= MAX_SOURCE_BYTES:
            raise ValueError("부품 초안 파일 크기가 올바르지 않습니다.")
        total += size
        if item["role"] in ("backend", "backend_test"):
            try:
                ast.parse(item["source"])
            except (SyntaxError, ValueError) as exc:
                raise ValueError("부품 초안 Python 구문이 올바르지 않습니다.") from exc
    if total > MAX_TOTAL_BYTES or not seen & {"backend", "frontend"} \
            or candidate.surface == "platform" and not {"backend", "frontend"} <= seen:
        raise ValueError("부품 초안 실행 부품이 부족합니다.")
    return value
