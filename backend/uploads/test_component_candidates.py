"""Offline candidate grouping; no generated code or Claude call."""

from django.test import TestCase

from .component_candidates import record_component_candidate, related_component_candidates
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

    def test_related_candidates_rank_lineage_and_explicit_capabilities(self):
        def add(capabilities, decision, base, blocker):
            plan = {"surface": "user", "knownCapabilities": capabilities, "newRequirement": "",
                    "decision": decision, "baseComponent": base, "blocker": blocker,
                    "reason": "구현 부족", "question": ""}
            match, _ = record_component_match("user", capabilities)
            return record_component_candidate(plan, match)

        same_base = add(["catalog.list", "account.login"], "extend", "catalog-browser-v1", "missing_behavior")
        shared = add(["account.login", "map.markers"], "create", "none", "incompatible_contract")
        unrelated = add(["reservation.capacity"], "create", "none", "no_related_component")
        requested = {"surface": "user", "knownCapabilities": ["catalog.detail", "account.login"],
                     "newRequirement": "", "baseComponent": "catalog-browser-v1"}
        related = related_component_candidates(requested)
        self.assertEqual([item["id"] for item in related], [same_base.pk, shared.pk])
        self.assertIn("same_base_version", related[0]["reasons"])
        self.assertNotIn(unrelated.pk, [item["id"] for item in related])
        self.assertEqual(related_component_candidates(requested, exclude_id=same_base.pk)[0]["id"], shared.pk)
        shared.status = ComponentCandidate.Status.RESOLVED
        shared.save(update_fields=["status"])
        self.assertEqual(len(related_component_candidates(requested)), 1)

    def test_unclassified_requirement_matches_only_identical_text(self):
        def add(requirement):
            plan = {"surface": "user", "knownCapabilities": [], "newRequirement": requirement,
                    "decision": "create", "baseComponent": "none", "blocker": "no_related_component",
                    "reason": "새 동작", "question": ""}
            match, _ = record_component_match("user", ["request.unclassified"])
            return record_component_candidate(plan, match)

        first = add("바코드  스캔")
        add("QR 스캔")
        related = related_component_candidates({"surface": "user", "knownCapabilities": [],
                                                "newRequirement": " 바코드 스캔 ", "baseComponent": "none"})
        self.assertEqual([item["id"] for item in related], [first.pk])
        self.assertEqual(related[0]["reasons"], ["same_requirement"])
