"""Offline contract checks; these tests make no Claude API calls."""

import json

from django.test import TestCase

from .component_planning import SETTINGS, planning_extension, validate_decision


class ComponentPlanningTests(TestCase):
    def test_example_and_prompt_use_registry_without_request_data(self):
        extension = planning_extension()
        self.assertIn('"key": "catalog-browser-v1"', extension["content"])
        self.assertNotIn("{{COMPONENT_CATALOG_JSON}}", extension["content"])
        self.assertIn("account.login", extension["schema"]["properties"]["plans"]["items"]
                      ["properties"]["knownCapabilities"]["items"]["enum"])
        self.assertNotIn("account.login", extension["content"])
        self.assertIn("서비스 설정 수정 응답", extension["system"])
        with (SETTINGS / "component_decision_response.example.json").open(encoding="utf-8") as source:
            example = json.load(source)
        result = validate_decision(example)
        self.assertEqual(result[0]["match"]["outcome"], "gap")

    def test_reuse_compose_and_gap_require_registry_evidence(self):
        def plan(capabilities, decision, **changes):
            item = {"surface": "user", "knownCapabilities": capabilities, "newRequirement": "",
                    "decision": decision, "baseComponent": "none", "blocker": "none",
                    "reason": "등록부 검색 결과", "question": ""}
            item.update(changes)
            return {"plans": [item]}

        self.assertEqual(validate_decision(plan(["catalog.list"], "reuse"))[0]["match"]["outcome"], "reuse")
        self.assertEqual(validate_decision(plan(["catalog.list", "catalog.search_text"], "compose"))
                         [0]["match"]["outcome"], "compose")
        with self.assertRaises(ValueError):
            validate_decision(plan(["account.login"], "reuse"))
        with self.assertRaises(ValueError):
            validate_decision(plan(["catalog.list"], "create", blocker="no_related_component"))
        self.assertEqual(validate_decision(plan(["catalog.list", "account.login"], "create",
                                                blocker="no_related_component"))[0]["match"]
                         ["missing_capabilities"], ["account.login"])
        self.assertEqual(validate_decision(plan(["catalog.list", "account.login"], "create",
                                                blocker="incompatible_contract"))[0]["match"]["outcome"], "gap")
        with self.assertRaises(ValueError):
            validate_decision(plan(["account.login"], "create", blocker="incompatible_contract"))
        self.assertEqual(validate_decision(plan(["catalog.list", "account.login"], "extend",
                                                baseComponent="catalog-browser-v1",
                                                blocker="missing_behavior"))[0]["match"]["outcome"], "gap")
        with self.assertRaises(ValueError):
            validate_decision(plan(["account.login"], "extend", baseComponent="catalog-browser-v1",
                                   blocker="missing_behavior"))

    def test_reservation_gap_can_reuse_submission_parts_without_claiming_reservation_support(self):
        plan = {"surface": "user", "knownCapabilities": ["reservation.time_slot", "reservation.capacity",
                                                       "submission.create", "submission.transition"],
                "newRequirement": "", "decision": "create", "baseComponent": "none",
                "blocker": "no_related_component", "reason": "신청 부품에는 시간대와 정원 관리가 없음", "question": ""}
        result = validate_decision({"plans": [plan]})[0]["match"]
        self.assertEqual(result["outcome"], "gap")
        self.assertEqual(result["missing_capabilities"], ["reservation.capacity", "reservation.time_slot"])
        self.assertEqual(set(result["selected_keys"]), {"submission-form-v1", "submission-status-v1"})

    def test_invalid_shape_and_unlisted_capability_are_rejected(self):
        item = {"surface": "platform", "knownCapabilities": ["account.login"], "newRequirement": "",
                "decision": "needs_input", "baseComponent": "none", "blocker": "none",
                "reason": "인증 방식이 지정되지 않음", "question": "어떤 로그인 방식을 원하시나요?"}
        self.assertIsNone(validate_decision({"plans": [item]})[0]["match"])
        for changed in ({**item, "knownCapabilities": ["made.up"]},
                        {**item, "question": ""}, {**item, "unexpected": "value"}):
            with self.assertRaises(ValueError):
                validate_decision({"plans": [changed]})
        with self.assertRaises(ValueError):
            validate_decision({"plans": [item] * 5})
