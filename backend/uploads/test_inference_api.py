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
        post_message.return_value = (200, {"request-id": "req_synthetic"}, """
        {"content":[{"type":"text","text":"{\\"schema_version\\":1,\\"summary\\":\\"목록 Preview\\",\\"preview\\":{\\"version\\":1,\\"title\\":\\"서비스\\",\\"pages\\":[{\\"id\\":\\"services\\",\\"template\\":\\"table\\",\\"title\\":\\"서비스\\",\\"bindings\\":{\\"fields\\":[\\"column_1\\",\\"column_2\\"]}}]},\\"questions\\":[]}"}],
         "usage":{"input_tokens":12,"output_tokens":8}}
        """)
        response = self.client.post(
            f"/api/uploads/{self.upload_id}/inference/",
            {"approved": True, "approval_note": "테스트에서 1회 호출 승인"},
            format="json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], ModelCall.Status.SUCCEEDED)
        self.assertEqual(response.data["result"]["preview"]["pages"][0]["template"], "table")
        record = ModelCall.objects.get()
        self.assertEqual(record.provider_request_id, "req_synthetic")
        self.assertEqual(record.usage["input_tokens"], 12)

    @patch("uploads.claude._post_message")
    def test_approved_post_normalizes_provider_noise_before_returning_preview(self, post_message):
        preview = {
            "schema_version": 1,
            "summary": "Preview candidate",
            "preview": {
                "version": 1,
                "title": "Services",
                "pages": [
                    {
                        "id": "services",
                        "template": "grouped",
                        "title": "Groups",
                        "bindings": {
                            "title": "column_1",
                            "group": "column_2,",
                            "phone": "column_2",
                        },
                    },
                    {
                        "id": "detail",
                        "template": "detail",
                        "title": "Detail",
                        "bindings": {"title": "column_1", "group": "column_2"},
                    },
                ],
            },
            "questions": [],
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
        pages = response.data["result"]["preview"]["pages"]
        self.assertEqual(pages[0]["bindings"], {"title": "column_1", "group": "column_2"})
        self.assertEqual(pages[1]["bindings"], {"title": "column_1"})
        record = ModelCall.objects.get(provider_request_id="req_noisy")
        self.assertEqual(record.status, ModelCall.Status.SUCCEEDED)
        self.assertEqual(record.parsed_result["preview"]["pages"], pages)

    @patch("uploads.claude._post_message")
    def test_validation_failure_preserves_provider_response(self, post_message):
        post_message.return_value = (200, {"request-id": "req_invalid"}, """
        {"content":[{"type":"text","text":"{\\"schema_version\\":1,\\"summary\\":\\"broken"}],
         "usage":{"input_tokens":7,"output_tokens":3}}
        """)
        response = self.client.post(
            f"/api/uploads/{self.upload_id}/inference/",
            {"approved": True, "approval_note": "검증 실패 보존 테스트"},
            format="json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        self.assertEqual(response.status_code, 400)
        record = ModelCall.objects.get()
        self.assertEqual(record.provider_request_id, "req_invalid")
        self.assertEqual(record.http_status, 200)
        self.assertEqual(record.usage["input_tokens"], 7)
        self.assertIn("broken", record.response_body)
        self.assertEqual(record.error_type, "InferenceError")
