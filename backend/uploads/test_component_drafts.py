"""Offline generated-source contract checks. Source is never imported or executed."""

import copy
import json

from django.test import TestCase

from .component_drafts import SETTINGS, draft_prompt, validate_component_draft
from .models import ComponentCandidate, ComponentVersion


class ComponentDraftTests(TestCase):
    def setUp(self):
        self.base = ComponentVersion.objects.get(key="catalog-browser-v1")
        self.candidate = ComponentCandidate.objects.create(
            signature="a" * 64, surface="user", capabilities=["catalog.list"],
            new_requirement="항목 수 배지", decision="extend", base_component=self.base,
            blocker="missing_behavior", reason="기존 목록에 배지가 없음")

    def test_prompt_and_example_are_bounded_and_offline(self):
        prompt = draft_prompt(self.candidate)
        self.assertIn("항목 수 배지", prompt["content"])
        self.assertIn("catalog-browser-v1", prompt["content"])
        self.assertEqual(prompt["schema"]["properties"]["surface"]["enum"], ["user"])
        with (SETTINGS / "component_draft_response.example.json").open(encoding="utf-8") as source:
            example = json.load(source)
        self.assertEqual(validate_component_draft(example, self.candidate), example)

    def test_invalid_claim_and_python_syntax_are_rejected(self):
        with (SETTINGS / "component_draft_response.example.json").open(encoding="utf-8") as source:
            example = json.load(source)
        changed = copy.deepcopy(example)
        changed["capabilities"] = ["account.login"]
        with self.assertRaises(ValueError):
            validate_component_draft(changed, self.candidate)
        changed = copy.deepcopy(example)
        changed["files"].append({"role": "backend", "source": "def broken(: pass"})
        with self.assertRaises(ValueError):
            validate_component_draft(changed, self.candidate)

    def test_platform_requires_backend_and_frontend_or_clear_question(self):
        platform = ComponentCandidate.objects.create(
            signature="b" * 64, surface="platform", capabilities=["account.login"],
            decision="create", blocker="no_related_component", reason="계정 구현이 없음")
        proposal = {"status": "draft", "surface": "platform", "capabilities": ["account.login"],
                    "baseComponent": "none", "summary": "로그인", "question": "",
                    "files": [{"role": "frontend", "source": "export default function Login() { return null; }"}]}
        with self.assertRaises(ValueError):
            validate_component_draft(proposal, platform)
        question = {**proposal, "status": "needs_input", "question": "어떤 인증 방식을 원하나요?", "files": []}
        self.assertEqual(validate_component_draft(question, platform), question)
