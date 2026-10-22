"""End-to-end API checks with mocked provider responses; never calls Claude."""

import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import BlueprintSubmission, ComponentMatch, ModelCall, Upload


EXAMPLE = Path(__file__).resolve().parents[1] / "claude_api_settings" / "service_blueprint_response.example.json"


@override_settings(ANTHROPIC_API_KEY="synthetic-test-secret")
class BlueprintApiTests(APITestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        media = override_settings(MEDIA_ROOT=temporary.name)
        media.enable()
        self.addCleanup(media.disable)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/session/").data["csrf_token"]
        uploaded = self.client.post("/api/uploads/", {"file": SimpleUploadedFile(
            "programs.csv", "프로그램,분류,장소\n도예,문화,1층\n요가,건강,2층\n".encode())},
            format="multipart", HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(uploaded.status_code, 201)
        self.upload = Upload.objects.get(pk=uploaded.data["id"])
        self.base = f"/api/uploads/{self.upload.pk}/blueprint/"
        self.blueprint = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def post(self, suffix, data):
        return self.client.post(self.base + suffix, data, format="json", HTTP_X_CSRFTOKEN=self.token)

    def provider(self, value):
        return (200, {"request-id": "synthetic-request"}, json.dumps({
            "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
            "usage": {"input_tokens": 20, "output_tokens": 30},
        }))

    def decision(self, capabilities, decision, **changes):
        item = {"surface": "user", "knownCapabilities": capabilities, "newRequirement": "",
                "decision": decision, "baseComponent": "none", "blocker": "none",
                "reason": "등록부와 필요한 기능을 비교했습니다.", "question": ""}
        item.update(changes)
        return [item]

    @patch("uploads.service_blueprint_views._post_message")
    def test_one_approved_generation_then_catalog_and_request_cycle(self, post_message):
        approval = self.client.get(self.base + "approval/")
        self.assertEqual(approval.status_code, 200)
        self.assertEqual(approval.data["planned_call_count"], 1)
        self.assertFalse(approval.data["original_csv_file"])
        denied = self.post("generate/", {"approved": True, "request_fingerprint": "wrong",
                                         "approval_note": "test"})
        self.assertEqual(denied.status_code, 400)
        post_message.assert_not_called()
        post_message.return_value = self.provider(self.blueprint)
        created = self.post("generate/", {"approved": True,
                                           "request_fingerprint": approval.data["request_fingerprint"],
                                           "approval_note": "approved synthetic test call"})
        self.assertEqual(created.status_code, 200)
        post_message.assert_called_once()
        self.assertEqual(ModelCall.objects.get().status, ModelCall.Status.SUCCEEDED)
        self.assertEqual(self.client.get(f"/api/uploads/{self.upload.pk}/service/").data["blueprint"], self.blueprint)
        other_session = APIClient()
        self.assertEqual(other_session.get(self.base + "rows/").status_code, 404)

        filtered = self.client.get(self.base + "rows/", {"filter_column": 2, "filter_value": "문화"})
        self.assertEqual(filtered.data["row_count"], 1)
        self.assertEqual(self.client.get(self.base + "rows/", {"filter_column": 3, "filter_value": "1층"}).status_code, 400)
        row_id = filtered.data["rows"][0]["id"]
        submitted = self.post("submissions/", {"workflow_id": "flow_1", "row_id": row_id,
                                               "values": {"field_1": "참여 희망"}})
        self.assertEqual(submitted.status_code, 201)
        self.assertEqual(submitted.data["status"], "state_1")
        changed = self.client.patch(self.base + f"submissions/{submitted.data['id']}/",
                                    {"actor": "admin", "to": "state_2"}, format="json",
                                    HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.data["status"], "state_2")
        self.assertEqual(self.client.patch(self.base + f"submissions/{submitted.data['id']}/",
                                           {"actor": "owner", "to": "state_4"}, format="json",
                                           HTTP_X_CSRFTOKEN=self.token).status_code, 400)
        self.assertEqual(BlueprintSubmission.objects.count(), 1)

    @patch("uploads.service_blueprint_views._post_message")
    def test_revision_preserves_current_config_on_invalid_or_unsupported_response(self, post_message):
        self.upload.service_blueprint = self.blueprint
        self.upload.save(update_fields=["service_blueprint"])
        request = "프로그램 분류 필터를 변경해줘"
        approval = self.post("approval/", {"request": request, "current_page": "User"})
        self.assertEqual(approval.status_code, 200)
        self.assertEqual(approval.data["planned_call_count"], 1)
        self.assertIn("부품 등록부", approval.data["transmitted_data"])
        admin_approval = self.post("approval/", {"request": request, "current_page": "Admin"})
        self.assertNotEqual(approval.data["request_fingerprint"], admin_approval.data["request_fingerprint"])
        self.assertEqual(self.post("approval/", {"request": request, "current_page": "unknown"}).status_code, 400)
        body = {"request": request, "current_page": "User", "approved": True,
                "request_fingerprint": approval.data["request_fingerprint"],
                "approval_note": "approved synthetic revision"}
        self.assertEqual(self.post("revise/", {**body, "current_page": "Admin"}).status_code, 400)
        post_message.assert_not_called()
        post_message.return_value = self.provider({"status": "unsupported", "message": "재고 기능은 지원하지 않습니다.",
                                                   "blueprint": self.blueprint,
                                                   "plans": self.decision([], "create",
                                                       newRequirement="재고 수량 추적", blocker="no_related_component")})
        unsupported = self.post("revise/", body)
        self.assertEqual(unsupported.status_code, 200)
        self.assertEqual(unsupported.data["status"], "unsupported")
        self.assertEqual(unsupported.data["plans"][0]["decision"], "create")
        invalid = copy.deepcopy(self.blueprint)
        invalid["catalog"]["titleColumn"] = 99
        post_message.return_value = self.provider({"status": "applied", "message": "수정했습니다.",
                                                   "blueprint": invalid,
                                                   "plans": self.decision(["catalog.filter_exact"], "reuse")})
        self.assertEqual(self.post("revise/", body).status_code, 400)
        self.upload.refresh_from_db()
        self.assertEqual(self.upload.service_blueprint, self.blueprint)
        self.assertEqual(ModelCall.objects.filter(status=ModelCall.Status.FAILED).count(), 1)
        changed = copy.deepcopy(self.blueprint)
        changed["catalog"]["filterColumns"] = [2, 3]
        post_message.return_value = self.provider({"status": "applied", "message": "장소 필터를 추가했습니다.",
                                                   "blueprint": changed,
                                                   "plans": self.decision(["catalog.filter_exact"], "reuse")})
        applied = self.post("revise/", body)
        self.assertEqual(applied.status_code, 200)
        self.upload.refresh_from_db()
        self.assertEqual(self.upload.service_blueprint["catalog"]["filterColumns"], [2, 3])
        self.assertEqual(ComponentMatch.objects.filter(upload=self.upload).count(), 2)

    @patch("uploads.service_blueprint_views._post_message")
    def test_revision_rejects_unimplemented_feature_claimed_as_applied(self, post_message):
        self.upload.service_blueprint = self.blueprint
        self.upload.save(update_fields=["service_blueprint"])
        request = "이 서비스에 로그인 기능을 추가해줘"
        approval = self.post("approval/", {"request": request, "current_page": "User"})
        body = {"request": request, "current_page": "User", "approved": True,
                "request_fingerprint": approval.data["request_fingerprint"],
                "approval_note": "approved synthetic revision"}
        changed = copy.deepcopy(self.blueprint)
        changed["title"] = "로그인 서비스"
        post_message.return_value = self.provider({"status": "applied", "message": "로그인을 추가했습니다.",
                                                   "blueprint": changed,
                                                   "plans": self.decision(["account.login"], "create",
                                                       surface="platform", blocker="no_related_component")})
        self.assertEqual(self.post("revise/", body).status_code, 400)
        self.upload.refresh_from_db()
        self.assertEqual(self.upload.service_blueprint, self.blueprint)
        self.assertEqual(ComponentMatch.objects.count(), 0)
