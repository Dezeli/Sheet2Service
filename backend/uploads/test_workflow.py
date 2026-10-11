"""Offline checks for paired flow proposals and explicit custom-call approval."""

import json
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .analysis import analyze
from .models import ModelCall, Upload
from .preview_request_v2 import build_schema
from .preview_response_v2 import prepare_preview_response
from .workflow import normalize_flow


def user_flow(template="request_review"):
    return {"template": template, "subjectColumn": 1,
            "steps": ["항목을 살펴봅니다.", "원하는 항목에 신청합니다."]}


def admin_flow(template="review_requests"):
    return {"template": template, "subjectColumn": 1,
            "steps": ["신청 목록을 확인합니다.", "신청을 승인하거나 거절합니다."]}


class WorkflowSchemaTests(APITestCase):
    def test_contextual_titles_survive_normalization_and_reject_multiline(self):
        report = analyze(b"name,kind\nA,park\nB,room\n")
        titles = {"user": "체육시설 이용 신청", "admin": "체육시설 신청 승인"}
        flow = {**user_flow(), "titles": titles}
        result = prepare_preview_response(json.dumps({
            "version": 2, "views": [{"template": "table", "columns": [1, 2]}],
            "serviceSummary": "시설 목록을 활용한 서비스를 추천합니다. " * 12, "serviceSubject": "체육시설",
            "userFlows": [flow], "adminFlows": [{**admin_flow(), "titles": titles}],
        }), report)
        self.assertEqual(result["service_subject"], "체육시설")
        self.assertEqual(result["user_flows"][0]["titles"], titles)
        for invalid in ["신청\n접수", "a" * 49, " "]:
            with self.assertRaises(ValueError):
                normalize_flow({**flow, "titles": {**titles, "user": invalid}}, "user", report)

    def test_model_output_limits_both_flow_templates_and_validates_response(self):
        report = analyze(b"name,kind\nA,park\nB,room\n")
        schema = build_schema(report)
        self.assertEqual(schema["properties"]["userFlows"]["items"]["properties"]["template"]["enum"],
                         ["browse_only", "inquiry", "request_review", "request_auto", "notice", "reservation", "rental", "quote"])
        self.assertEqual(schema["properties"]["adminFlows"]["items"]["properties"]["subjectColumn"]["enum"],
                         [0, 1, 2])
        with self.assertRaises(ValueError):
            normalize_flow({**user_flow(), "subjectColumn": 0}, "user", report)
        raw = json.dumps({"version": 2, "views": [{"template": "table", "columns": [1, 2]}],
                          "serviceSummary": "시설을 소개하는 서비스 목록으로 보입니다.",
                          "userFlows": [user_flow()], "adminFlows": [admin_flow()]}, ensure_ascii=False)
        result = prepare_preview_response(raw, report)
        self.assertFalse(result["used_fallback"])
        self.assertEqual(result["user_flows"][0]["template"], "request_review")
        self.assertEqual(result["admin_flows"][0]["template"], "review_requests")
        with self.assertRaises(ValueError):
            normalize_flow({**user_flow(), "template": "arbitrary_code"}, "user", report)


@override_settings(ANTHROPIC_API_KEY="synthetic-test-secret")
class WorkflowApiTests(APITestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        media = override_settings(MEDIA_ROOT=temporary.name)
        media.enable()
        self.addCleanup(media.disable)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/session/").data["csrf_token"]
        uploaded = self.client.post("/api/uploads/", {
            "file": SimpleUploadedFile("items.csv", b"name,kind\nA,park\nB,room\n")},
            format="multipart", HTTP_X_CSRFTOKEN=self.token)
        self.upload = Upload.objects.get(pk=uploaded.data["id"])
        self.base = f"/api/uploads/{self.upload.pk}/workflow/"
        self.call = ModelCall.objects.create(
            upload=self.upload, purpose="preview", model="test-model", request_body={"model": "test-model"},
            approval_note="recorded approval", approved_at=timezone.now(),
            status=ModelCall.Status.SUCCEEDED,
            parsed_result={"preview": {"version": 2, "views": [{"template": "table", "columns": [1, 2]}]},
                           "service_summary": "시설 목록으로 보입니다.",
                           "user_flows": [user_flow()], "admin_flows": [admin_flow()]},
        )

    def post(self, url, value):
        return self.client.post(url, value, format="json", HTTP_X_CSRFTOKEN=self.token)

    def test_review_and_apply_pair_without_model_call(self):
        preview = self.client.get(self.base)
        self.assertEqual(preview.data["service_summary"], "시설 목록으로 보입니다.")
        self.assertEqual(len(preview.data["options"]["user"]), 1)
        reference = {"model_call_id": str(self.call.id), "index": 0}
        applied = self.post(self.base, {"user": reference, "admin": reference})
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.data["selected"]["user"]["template"], "request_review")
        self.assertEqual(ModelCall.objects.count(), 1)
        self.assertEqual(self.client.get(f"/api/uploads/{self.upload.pk}/service/").data["workflow_config"],
                         applied.data["selected"])
        self.assertEqual(APIClient().get(self.base).status_code, 404)

    @patch("uploads.claude._post_message")
    def test_custom_description_requires_preflight_and_one_approved_call(self, post_message):
        description = "사용자가 시설을 고르면 관리자가 신청을 승인합니다."
        preflight = self.post(self.base + "custom-preview/", {"scope": "user", "description": description})
        self.assertEqual(preflight.status_code, 200)
        self.assertEqual(preflight.data["planned_call_count"], 1)
        self.assertEqual(preflight.data["transmitted_data"]["sample_rows"], 0)
        post_message.assert_not_called()
        denied = self.post(self.base + "custom-run/", {"scope": "user", "description": description,
            "approved": False, "approval_note": "no", "request_fingerprint": preflight.data["request_fingerprint"]})
        self.assertEqual(denied.status_code, 400)
        post_message.assert_not_called()
        provider = {"content": [{"type": "text", "text": json.dumps({"version": 1, "flow": user_flow()})}],
                    "usage": {"input_tokens": 10, "output_tokens": 20}}
        post_message.return_value = (200, {"request-id": "req_test"}, json.dumps(provider))
        approved = self.post(self.base + "custom-run/", {"scope": "user", "description": description,
            "approved": True, "approval_note": "one call approved",
            "request_fingerprint": preflight.data["request_fingerprint"]})
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["flow"]["template"], "request_review")
        post_message.assert_called_once()
        self.assertEqual(ModelCall.objects.count(), 2)
