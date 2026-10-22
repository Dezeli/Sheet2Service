"""Offline candidate grouping; no generated code or Claude call."""

from django.test import TestCase

from .component_candidates import record_component_candidate
from .component_matching import record_component_match
from .models import ComponentCandidate


class ComponentCandidateTests(TestCase):
    def test_same_gap_reuses_candidate_and_keeps_latest_evidence(self):
        plan = {"surface": "platform", "knownCapabilities": ["account.login"],
                "newRequirement": "", "decision": "create", "baseComponent": "none",
                "blocker": "no_related_component", "reason": "계정 구현이 없음", "question": ""}
        first_match, _ = record_component_match("platform", ["account.login"])
        first = record_component_candidate(plan, first_match)
        second_match, _ = record_component_match("platform", ["account.login"])
        second = record_component_candidate({**plan, "reason": "다른 표현의 같은 근거"}, second_match)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ComponentCandidate.objects.count(), 1)
        self.assertEqual(second.seen_count, 2)
        self.assertEqual(second.last_match, second_match)
        self.assertEqual(second.reason, "계정 구현이 없음")

    def test_extension_candidate_keeps_base_version_and_is_not_available(self):
        plan = {"surface": "user", "knownCapabilities": ["catalog.list", "account.login"],
                "newRequirement": "", "decision": "extend", "baseComponent": "catalog-browser-v1",
                "blocker": "missing_behavior", "reason": "계정 기능 부족", "question": ""}
        match, _ = record_component_match("user", plan["knownCapabilities"])
        candidate = record_component_candidate(plan, match)
        self.assertEqual(candidate.base_component.key, "catalog-browser-v1")
        self.assertEqual(candidate.status, ComponentCandidate.Status.OPEN)
        self.assertEqual(candidate.capabilities, sorted(plan["knownCapabilities"]))
