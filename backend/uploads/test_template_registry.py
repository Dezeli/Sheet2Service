"""Registry-driven recommendations and unsupported outcomes, entirely offline."""
import json
from unittest.mock import patch

from rest_framework.test import APITestCase
from . import test_feature_selection as fixtures
from .workflow import custom_request_body, normalize_flows, parse_custom_response
from .template_registry import IMPLEMENTED, PLANNED, TEMPLATES
from .preview_request_v2 import build_prompt


class TemplateRegistryTests(APITestCase):
    setUp = fixtures.FeatureSelectionTests.setUp
    mutate = fixtures.FeatureSelectionTests.mutate
    recorded = fixtures.FeatureSelectionTests.recorded

    def test_registry_is_not_injected_into_empty_recommendations(self):
        data = self.client.get(self.base + "workflow/").data
        candidates = data["recommended"] + data["templates"]
        self.assertEqual(candidates, [])
        for item in candidates:
            self.assertEqual("reference" in item, item["implemented"])
        for template in PLANNED:
            self.assertEqual(self.mutate("workflow/", {"features": [{"scope": "user", "model_call_id": f"builtin:{template}", "index": 0}]}).status_code, 400)

    def test_all_implemented_features_can_be_recommended_and_last_reference_applied(self):
        flows = [{"template": item["user_template"], "subjectColumn": 1, "steps": ["View", "Submit"]} for item in IMPLEMENTED]
        admins = [{"template": item["admin_template"], "subjectColumn": 1, "steps": ["View", "Process"]} for item in IMPLEMENTED]
        self.assertEqual(len(normalize_flows(flows, "user", self.upload.analysis)), len(IMPLEMENTED))
        call = self.recorded({"user_flows": flows, "admin_flows": admins})
        candidates = self.client.get(self.base + "workflow/").data["recommended"]
        self.assertEqual(len(candidates), len(IMPLEMENTED))
        selected = self.mutate("workflow/", {"features": [{"scope": "user", "model_call_id": str(call.id), "index": len(flows) - 1}]})
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(selected.data["selected"]["user"]["template"], flows[-1]["template"])

    def test_both_prompt_paths_receive_registry_and_custom_schema_can_decline(self):
        body = custom_request_body(self.upload.analysis, "user", "Please add automatic notifications")
        content = json.loads(body["messages"][0]["content"])
        self.assertEqual(len(content["template_registry"]), len(TEMPLATES))
        prompt = build_prompt(self.upload.analysis)
        for item in TEMPLATES:
            self.assertIn(item["template"], prompt["system"])
        outcomes = body["output_config"]["format"]["schema"]["properties"]["result"]["anyOf"]
        self.assertEqual([item["properties"]["status"]["enum"][0] for item in outcomes],
                         ["supported", "unimplemented", "unsupported"])

    def test_invalid_implementation_claims_and_unknown_templates_are_rejected(self):
        for result in ({"status": "unimplemented", "template": "inquiry"},
                       {"status": "unimplemented", "template": "unknown"},
                       {"status": "supported", "flow": {"template": "order", "subjectColumn": 1, "steps": ["Book", "Pay"]}},
                       {"status": "unsupported", "flow": {}}):
            with self.assertRaises(ValueError):
                parse_custom_response(json.dumps({"version": 1, "result": result}), "user", self.upload.analysis)

    @patch("uploads.claude._post_message")
    def test_supported_unimplemented_unsupported_responses_are_recorded_without_phantom_features(self, post_message):
        description = "Please add a matching feature to this service"
        for result in ({"status": "supported", "flow": {"template": "inquiry", "subjectColumn": 0, "steps": ["Write", "Read"]}},
                       {"status": "unimplemented", "template": "survey"}, {"status": "unsupported"}):
            preflight = self.mutate("workflow/custom-preview/", {"scope": "user", "description": description})
            self.assertEqual(preflight.status_code, 200)
            post_message.return_value = (200, {}, json.dumps({"content": [{"type": "text", "text": json.dumps({"version": 1, "result": result})}]}))
            response = self.mutate("workflow/custom-run/", {"scope": "user", "description": description,
                "approved": True, "approval_note": "offline mock", "request_fingerprint": preflight.data["request_fingerprint"]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["result"]["status"], result["status"])
            self.assertTrue(response.data["result"]["message"])
            candidates = self.client.get(self.base + "workflow/").data["recommended"]
            self.assertEqual([item["template"] for item in candidates], ["inquiry"])
            self.assertIsNone(self.upload.workflow_config)
        self.assertEqual(post_message.call_count, 3)
