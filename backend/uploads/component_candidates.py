"""Group validated component gaps without making them executable."""

import hashlib
import json

from django.db.models import F
from django.utils import timezone

from .models import ComponentCandidate, ComponentMatch, ComponentVersion


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
