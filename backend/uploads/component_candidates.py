"""Group validated component gaps without making them executable."""

import hashlib
import json

from django.db.models import F
from django.utils import timezone

from .models import ComponentCandidate, ComponentMatch, ComponentVersion


def related_component_candidates(plan, *, exclude_id=None, limit=5):
    """Rank nearby open drafts by explicit capabilities and lineage, without merging."""
    if not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("후보 조회 개수가 올바르지 않습니다.")
    requested = set(plan["knownCapabilities"])
    requirement = " ".join(plan["newRequirement"].split()).casefold()
    base = (ComponentVersion.objects.get(key=plan["baseComponent"])
            if plan["baseComponent"] != "none" else None)
    candidates = ComponentCandidate.objects.filter(
        surface=plan["surface"], status__in=(ComponentCandidate.Status.OPEN,
                                            ComponentCandidate.Status.IN_PROGRESS)).select_related("base_component")
    if exclude_id is not None:
        candidates = candidates.exclude(pk=exclude_id)
    ranked = []
    for candidate in candidates:
        overlap = sorted(requested & set(candidate.capabilities))
        same_base = bool(base and candidate.base_component_id == base.pk)
        same_family = bool(base and candidate.base_component and candidate.base_component.family == base.family)
        same_requirement = bool(requirement and requirement == " ".join(candidate.new_requirement.split()).casefold())
        if not (overlap or same_family or same_requirement):
            continue
        reasons = []
        if same_requirement:
            reasons.append("same_requirement")
        if same_base:
            reasons.append("same_base_version")
        elif same_family:
            reasons.append("same_lineage")
        if requested and requested == set(candidate.capabilities):
            reasons.append("same_capabilities")
        elif overlap:
            reasons.append("shared_capabilities")
        score = (int(same_requirement), int(same_base), int(same_family),
                 int(bool(requested) and requested == set(candidate.capabilities)),
                 len(overlap), candidate.seen_count)
        ranked.append((score, candidate.pk, {"id": candidate.pk, "reasons": reasons,
                                             "shared_capabilities": overlap,
                                             "base_component": candidate.base_component.key if candidate.base_component else "none"}))
    ranked.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    return [item[2] for item in ranked[:limit]]


def record_component_candidate(plan, match):
    """Keep one candidate per exact requirement and lineage; no model call occurs."""
    if plan["decision"] not in ("extend", "create") or match.outcome != ComponentMatch.Outcome.GAP:
        raise ValueError("미구현 기능 판단만 후보로 기록할 수 있습니다.")
    requirement = " ".join(plan["newRequirement"].split())
    capabilities = sorted(plan["knownCapabilities"])
    identity = {"surface": plan["surface"], "capabilities": capabilities,
                "new_requirement": requirement.casefold(), "decision": plan["decision"],
                "base_component": plan["baseComponent"], "blocker": plan["blocker"]}
    signature = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True,
                                          separators=(",", ":")).encode("utf-8")).hexdigest()
    base = (ComponentVersion.objects.get(key=plan["baseComponent"])
            if plan["decision"] == "extend" else None)
    candidate, created = ComponentCandidate.objects.get_or_create(
        signature=signature,
        defaults={"surface": plan["surface"], "capabilities": capabilities,
                  "new_requirement": requirement, "decision": plan["decision"],
                  "base_component": base, "blocker": plan["blocker"],
                  "reason": plan["reason"].strip(), "last_match": match})
    if not created:
        ComponentCandidate.objects.filter(pk=candidate.pk).update(
            seen_count=F("seen_count") + 1, last_seen_at=timezone.now(), last_match=match)
        candidate.refresh_from_db()
    return candidate
