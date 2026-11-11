"""Upload -> one approved understanding call -> a built service, with the call mocked."""
import json
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import Booking, ModelCall, Resource, Upload
from .test_fixtures import isolated_media, upload_csv
from .test_reservation_understanding import BOOKINGS, model_answer


@override_settings(ANTHROPIC_API_KEY="synthetic-test-secret")
class GenerateApiTests(APITestCase):
    def setUp(self):
        isolated_media(self)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/session/").data["csrf_token"]
        self.upload = upload_csv(self.client, self.token, BOOKINGS, "휴양림 예약.csv")
        self.base = f"/api/uploads/{self.upload.pk}/"

    def post(self, path, body):
        return self.client.post(self.base + path, body, format="json", HTTP_X_CSRFTOKEN=self.token)

    @patch("uploads.claude._post_message")
    def test_generation_builds_the_service_from_one_call(self, post_message):
        summary = self.client.get(self.base + "generate/").data
        self.assertEqual((summary["planned_call_count"], summary["requires_approval"], summary["already_generated"]), (1, True, False))
        self.assertEqual(self.client.get(self.base + "service/").status_code, 404)
        self.assertEqual(self.post("generate/", {"approved": False, "approval_note": "no"}).status_code, 400)
        post_message.assert_not_called()
        provider = {"content": [{"type": "text", "text": json.dumps(model_answer(), ensure_ascii=False)}],
                    "usage": {"input_tokens": 10, "output_tokens": 20}, "stop_reason": "end_turn"}
        post_message.return_value = (200, {"request-id": "req_test"}, json.dumps(provider))
        generated = self.post("generate/", {"approved": True, "approval_note": "버튼으로 1회 승인",
                                            "request_fingerprint": summary["request_fingerprint"]})
        self.assertEqual(generated.status_code, 200, generated.data)
        post_message.assert_called_once()
        self.assertEqual(generated.data["landing"], "booker")
        self.assertEqual(generated.data["counts"], {"resources": 6, "slots": 0, "bookings": 10})
        self.assertEqual([persona["id"] for persona in generated.data["service"]["personas"]], ["booker", "operator", "field", "admin"])
        service = self.client.get(self.base + "service/").data
        self.assertEqual(service["service"]["subject"], "국립자연휴양림 객실")
        self.assertEqual(service["service"]["booking"]["timeModel"], "date")
        self.assertTrue(service["understanding"]["summary"])
        self.assertEqual(Resource.objects.filter(upload=self.upload).count(), 6)
        self.assertEqual(Booking.objects.filter(upload=self.upload, status="requested").count(), 2)
        self.assertEqual(ModelCall.objects.get().status, ModelCall.Status.SUCCEEDED)
        self.assertTrue(self.client.get(self.base + "generate/").data["already_generated"])
        self.assertEqual(APIClient().get(self.base + "service/").status_code, 404)

    @patch("uploads.claude._post_message")
    def test_failed_call_leaves_no_service(self, post_message):
        post_message.return_value = (200, {}, json.dumps({"content": [{"type": "text", "text": "oops"}], "usage": {},
                                                          "stop_reason": "end_turn"}))
        self.assertEqual(self.post("generate/", {"approved": True, "approval_note": "approved"}).status_code, 400)
        self.assertIsNone(Upload.objects.get(pk=self.upload.pk).service_config)
        self.assertEqual(self.client.get(self.base + "service/").status_code, 404)
        self.assertEqual(ModelCall.objects.get().status, ModelCall.Status.FAILED)
