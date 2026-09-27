"""API approval flow tests. Network calls are mocked."""
import json
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import ModelCall


@override_settings(ANTHROPIC_API_KEY="synthetic-test-secret")
class InferenceApiTests(APITestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        token = self.client.get("/api/session/").data["csrf_token"]
        upload = self.client.post(
            "/api/uploads/",
            {"file": SimpleUploadedFile("services.csv", b"name,kind\nA,park\nB,room\n")},
            format="multipart",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(upload.status_code, 201)
        self.upload_id = upload.data["id"]
        self.token = token

    def test_get_reports_approval_scope_without_calling_claude(self):
        response = self.client.get(f"/api/uploads/{self.upload_id}/inference/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["requires_approval"])
        self.assertEqual(response.data["planned_call_count"], 1)
        self.assertEqual(response.data["automatic_retries"], 0)
        self.assertFalse(response.data["transmitted_data"]["original_csv_file"])
        self.assertEqual(response.data["transmitted_data"]["column_count"], 2)
        self.assertEqual(response.data["transmitted_data"]["sample_count"], 2)
        self.assertEqual(ModelCall.objects.count(), 0)

    @patch("uploads.claude._post_message")
    def test_post_requires_explicit_approval_before_network(self, post_message):
        response = self.client.post(
            f"/api/uploads/{self.upload_id}/inference/",
            {"approved": False, "approval_note": "no"},
            format="json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        self.assertEqual(response.status_code, 400)
        post_message.assert_not_called()
        self.assertEqual(ModelCall.objects.count(), 0)

    @patch("uploads.claude._post_message")
    def test_approved_post_records_and_validates_result(self, post_message):
        provider = {"content": [{"type": "text", "text": json.dumps({
            "version": 2, "views": [{"template": "table", "columns": [1, 2]}],
        })}], "usage": {"input_tokens": 12, "output_tokens": 8}}
        post_message.return_value = (200, {"request-id": "req_synthetic"}, json.dumps(provider))
        response = self.client.post(
            f"/api/uploads/{self.upload_id}/inference/",
            {"approved": True, "approval_note": "테스트에서 1회 호출 승인"},
            format="json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], ModelCall.Status.SUCCEEDED)
        self.assertEqual(response.data["result"]["preview"]["views"][0]["template"], "table")
        self.assertFalse(response.data["result"]["used_fallback"])
        record = ModelCall.objects.get()
        self.assertEqual(record.provider_request_id, "req_synthetic")
        self.assertEqual(record.usage["input_tokens"], 12)
        self.assertEqual(record.request_body["output_config"]["format"]["schema"]["properties"]["version"]["enum"], [2])

    @patch("uploads.claude._post_message")
    def test_approved_post_normalizes_duplicates_before_returning_preview(self, post_message):
        preview = {
            "version": 2,
            "views": [
                {"template": "cards", "titleColumn": 1, "fields": [2, 2, 1]},
                {"template": "cards", "titleColumn": 1, "fields": [2, 1]},
            ],
        }
        provider_body = {
            "content": [{"type": "text", "text": json.dumps(preview)}],
            "usage": {"input_tokens": 12, "output_tokens": 8},
        }
        post_message.return_value = (200, {"request-id": "req_noisy"}, json.dumps(provider_body))
        response = self.client.post(
            f"/api/uploads/{self.upload_id}/inference/",
            {"approved": True, "approval_note": "noisy preview normalization test"},
            format="json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        self.assertEqual(response.status_code, 200)
        views = response.data["result"]["preview"]["views"]
        self.assertEqual(views, [{"template": "cards", "titleColumn": 1, "fields": [2]}])
        record = ModelCall.objects.get(provider_request_id="req_noisy")
        self.assertEqual(record.status, ModelCall.Status.SUCCEEDED)
        self.assertEqual(record.parsed_result["preview"]["views"], views)

    @patch("uploads.claude._post_message")
    def test_invalid_preview_uses_fallback_and_preserves_provider_response(self, post_message):
        provider = {"content": [{"type": "text", "text": '{"version":2,"views":[{"template":"table","columns":[99]}]}' }],
                    "usage": {"input_tokens": 7, "output_tokens": 3}}
        post_message.return_value = (200, {"request-id": "req_invalid"}, json.dumps(provider))
        response = self.client.post(
            f"/api/uploads/{self.upload_id}/inference/",
            {"approved": True, "approval_note": "검증 실패 보존 테스트"},
            format="json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["result"]["used_fallback"])
        self.assertEqual(response.data["result"]["preview"]["views"],
                         [{"template": "table", "columns": [1, 2]}])
        record = ModelCall.objects.get()
        self.assertEqual(record.provider_request_id, "req_invalid")
        self.assertEqual(record.http_status, 200)
        self.assertEqual(record.usage["input_tokens"], 7)
        self.assertIn("99", record.response_body)
        self.assertTrue(record.validation_error)
