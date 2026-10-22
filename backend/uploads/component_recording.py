"""Persist validated revision matches and missing-component candidates."""

from .component_candidates import record_component_candidate
from .component_matching import record_component_match


def record_revision_matches(upload, call, result):
    candidates = []
    for index, plan in enumerate(result["plans"]):
        if plan["decision"] == "needs_input":
            continue
        required = plan["knownCapabilities"] + (["request.unclassified"] if plan["newRequirement"].strip() else [])
        match, _ = record_component_match(plan["surface"], required, upload=upload)
        match.model_call = call
        if result["status"] == "unsupported" and plan["decision"] in ("extend", "create"):
            candidate = record_component_candidate(plan, match)
            match.candidate = candidate
            candidates.append({"plan_index": index, "id": candidate.pk})
        match.save(update_fields=["candidate", "model_call"])
    result["candidates"] = candidates
    return result
