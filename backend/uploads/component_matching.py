"""Deterministic registry search before any semantic extend/create decision."""

import re
from collections import defaultdict

from .component_contract import Surface
from .models import ComponentMatch, ComponentVersion


CAPABILITY_KEY = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
MAX_REQUESTED_CAPABILITIES = 16
MAX_CANDIDATE_REASONS = 5


def _request(surface, required):
    try:
        surface = Surface(surface)
    except (TypeError, ValueError) as exc:
        raise ValueError("대상 화면이 올바르지 않습니다.") from exc
    if not isinstance(required, (list, tuple)) or not 1 <= len(required) <= MAX_REQUESTED_CAPABILITIES \
            or any(not isinstance(item, str) or len(item) > 64 or not CAPABILITY_KEY.fullmatch(item)
                   for item in required) or len(set(required)) != len(required):
        raise ValueError("필요한 기능 목록이 올바르지 않습니다.")
    return surface, tuple(sorted(required))


def _plan_score(plan, requested):
    return (len(plan), sum(len(set(item.capabilities) - requested) for item in plan),
            sum(item.version for item in plan), tuple(item.key for item in plan))


def match_components(surface, required, *, registry=None):
    """Return the smallest fitting plan or an explicit gap, never create code."""
    surface, required = _request(surface, required)
    requested = set(required)
    components = list(ComponentVersion.objects.all() if registry is None else registry)
    by_family = defaultdict(list)
    for item in components:
        if item.status == ComponentVersion.Status.AVAILABLE and surface in item.surfaces:
            mask = sum(1 << index for index, capability in enumerate(required)
                       if capability in item.capabilities)
            if mask:
                by_family[item.family].append((item, mask))

    # One version per family. Each mask retains the least complex plan after a family.
    plans = {0: ()}
    for family in sorted(by_family):
        next_plans = dict(plans)
        for covered, plan in plans.items():
            for item, mask in by_family[family]:
                combined = covered | mask
                if combined == covered:
                    continue
                candidate = plan + (item,)
                current = next_plans.get(combined)
                if current is None or _plan_score(candidate, requested) < _plan_score(current, requested):
                    next_plans[combined] = candidate
        plans = next_plans

    full_mask = (1 << len(required)) - 1
    covered, selected = min(plans.items(), key=lambda entry: (
        -entry[0].bit_count(), _plan_score(entry[1], requested))) if full_mask not in plans \
        else (full_mask, plans[full_mask])
    missing = [capability for index, capability in enumerate(required) if not covered & (1 << index)]
    outcome = (ComponentMatch.Outcome.GAP if missing else
               ComponentMatch.Outcome.REUSE if len(selected) == 1 else ComponentMatch.Outcome.COMPOSE)
    selected_keys = [item.key for item in selected]

    reasons = []
    for item in components:
        overlap = sorted(requested & set(item.capabilities))
        if not overlap or item.key in selected_keys:
            continue
        if item.status != ComponentVersion.Status.AVAILABLE:
            reason = "not_available"
        elif surface not in item.surfaces:
            reason = "wrong_surface"
        elif requested - set(item.capabilities):
            reason = "missing_capabilities"
        else:
            reason = "alternative_version"
        reasons.append({"key": item.key, "reason": reason, "covered": overlap,
                        "missing": sorted(requested - set(item.capabilities))})
    reasons.sort(key=lambda item: (-len(item["covered"]), item["reason"], item["key"]))
    return {"surface": surface.value, "requested_capabilities": list(required),
            "outcome": outcome.value, "selected_keys": selected_keys,
            "missing_capabilities": missing, "candidate_reasons": reasons[:MAX_CANDIDATE_REASONS]}


def record_component_match(surface, required, *, upload=None):
    """Search again before recording, so callers cannot forge a registry decision."""
    result = match_components(surface, required)
    record = ComponentMatch.objects.create(
        upload=upload, surface=result["surface"], requested_capabilities=result["requested_capabilities"],
        outcome=result["outcome"], selected_keys=result["selected_keys"],
        missing_capabilities=result["missing_capabilities"],
        candidate_reasons=result["candidate_reasons"])
    return record, result
