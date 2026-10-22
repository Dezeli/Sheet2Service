"""Offline Claude decision contract. This module never calls a model or executes a part."""

import json
from pathlib import Path

from .component_contract import Capability, Surface
from .component_matching import match_components
from .models import ComponentVersion


SETTINGS = Path(__file__).resolve().parent.parent / "claude_api_settings"
MAX_CATALOG = 100
MAX_PLANS = 4
MAX_REASON = 500
DECISIONS = ("reuse", "compose", "extend", "create", "needs_input")
BLOCKERS = ("none", "missing_behavior", "no_related_component", "incompatible_contract")
FIELDS = ("surface", "knownCapabilities", "newRequirement", "decision", "baseComponent",
          "blocker", "reason", "question")


def catalog_snapshot(*, registry=None):
    """Send only bounded, public component metadata, never user data or implementation code."""
    items = list(ComponentVersion.objects.select_related("parent").all() if registry is None else registry)
    items = [item for item in items if item.status in (
        ComponentVersion.Status.AVAILABLE, ComponentVersion.Status.DEPRECATED)]
    if len(items) > MAX_CATALOG:
        raise ValueError("부품 등록부가 판단 상한을 초과했습니다.")
    items.sort(key=lambda item: (item.family, item.version, item.key))
    return [{"key": item.key, "family": item.family, "version": item.version,
             "parent": item.parent.key if item.parent_id else "none", "title": item.title,
             "description": item.description, "capabilities": item.capabilities,
             "surfaces": item.surfaces, "status": item.status} for item in items]


def decision_schema(*, catalog=None):
    catalog = catalog_snapshot() if catalog is None else catalog
    keys = [item["key"] for item in catalog if item["status"] == ComponentVersion.Status.AVAILABLE]
    string = {"type": "string"}

    def enum(values):
        return {"type": "string", "enum": list(values)}
    properties = {
        "surface": enum(Surface),
        "knownCapabilities": {"type": "array", "items": enum(Capability)},
        "newRequirement": string,
        "decision": enum(DECISIONS),
        "baseComponent": enum(("none", *keys)),
        "blocker": enum(BLOCKERS),
        "reason": string,
        "question": string,
    }
    return {"type": "object", "properties": {"plans": {"type": "array", "items": {
        "type": "object", "properties": properties, "required": list(FIELDS),
        "additionalProperties": False}}}, "required": ["plans"], "additionalProperties": False}


def planning_extension(*, registry=None):
    """Materials to append to the existing revision call in a later integration step."""
    catalog = catalog_snapshot(registry=registry)
    system = (SETTINGS / "component_decision_system.md").read_text(encoding="utf-8")
    content = (SETTINGS / "component_decision_content.md").read_text(encoding="utf-8")
    content = content.replace("{{COMPONENT_CATALOG_JSON}}", json.dumps(catalog, ensure_ascii=False))
    return {"system": system, "content": content, "schema": decision_schema(catalog=catalog)}


def validate_decision(value, *, registry=None):
    """Reject impossible model claims using the same snapshot used for prompting."""
    items = list(ComponentVersion.objects.all() if registry is None else registry)
    catalog_snapshot(registry=items)
    available = {item.key: item for item in items if item.status == ComponentVersion.Status.AVAILABLE}
    if not isinstance(value, dict) or set(value) != {"plans"} or not isinstance(value["plans"], list) \
            or not 1 <= len(value["plans"]) <= MAX_PLANS:
        raise ValueError("부품 판단 목록이 올바르지 않습니다.")
    results = []
    seen = set()
    for plan in value["plans"]:
        if not isinstance(plan, dict) or set(plan) != set(FIELDS):
            raise ValueError("부품 판단 필드가 올바르지 않습니다.")
        surface, capabilities, requirement = plan["surface"], plan["knownCapabilities"], plan["newRequirement"]
        decision, base, blocker = plan["decision"], plan["baseComponent"], plan["blocker"]
        reason, question = plan["reason"], plan["question"]
        if not isinstance(surface, str) or surface not in Surface._value2member_map_ \
                or not isinstance(decision, str) or decision not in DECISIONS \
                or not isinstance(blocker, str) or blocker not in BLOCKERS \
                or not isinstance(capabilities, list) or len(capabilities) > 16 \
                or any(not isinstance(key, str) or key not in Capability._value2member_map_ for key in capabilities) \
                or len(set(capabilities)) != len(capabilities) \
                or not isinstance(requirement, str) or len(requirement) > 300 \
                or not isinstance(reason, str) or not reason.strip() or len(reason) > MAX_REASON \
                or not isinstance(question, str) or len(question) > 300 \
                or not isinstance(base, str):
            raise ValueError("부품 판단 값이 올바르지 않습니다.")
        if not capabilities and not requirement.strip() and decision != "needs_input":
            raise ValueError("판단할 기능이 없습니다.")
        identity = (surface, tuple(sorted(capabilities)), requirement.strip())
        if identity in seen:
            raise ValueError("같은 기능 판단이 중복되었습니다.")
        seen.add(identity)
        if decision == "needs_input":
            if not question.strip() or base != "none" or blocker != "none":
                raise ValueError("추가 질문 판단이 올바르지 않습니다.")
            results.append({"plan": plan, "match": None})
            continue
        if question:
            raise ValueError("추가 질문이 필요하지 않은 판단에 질문이 있습니다.")
        requested = capabilities + (["request.unclassified"] if requirement.strip() else [])
        match = match_components(surface, requested, registry=items)
        if decision in ("reuse", "compose"):
            if requirement.strip() or base != "none" or blocker != "none" or match["outcome"] != decision:
                raise ValueError("등록부와 재사용 판단이 일치하지 않습니다.")
        elif decision == "extend":
            candidate = available.get(base)
            if blocker != "missing_behavior" or match["outcome"] != "gap" or candidate is None \
                    or surface not in candidate.surfaces or not set(capabilities) & set(candidate.capabilities):
                raise ValueError("확장할 수 있는 기존 부품 근거가 없습니다.")
        elif decision == "create":
            if base != "none" or blocker not in ("no_related_component", "incompatible_contract") \
                    or match["outcome"] != "gap":
                raise ValueError("새 부품 생성 근거가 올바르지 않습니다.")
            overlap = bool(match["selected_keys"] or match["candidate_reasons"])
            if blocker == "no_related_component" and overlap:
                raise ValueError("관련 후보가 있어 생성 근거를 다시 검토해야 합니다.")
            if blocker == "incompatible_contract" and not overlap:
                raise ValueError("양립 불가능한 기존 계약이 확인되지 않았습니다.")
        results.append({"plan": plan, "match": match})
    return results
