"""Mocked provider checks for explicit draft approval; no Claude call is made."""

import json
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .call_records import finish_call, start_call
from .claude import ProviderTimeoutError, TIMEOUT_MESSAGE, _post_message
from .component_matching import record_component_match
from .models import ComponentCandidate, ComponentDraft, ComponentVersion, ModelCall, Upload


@override_settings(ANTHROPIC_API_KEY="synthetic-test-secret")
class ComponentDraftApiTests(APITestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        media = override_settings(MEDIA_ROOT=temporary.name)
        media.enable()
        self.addCleanup(media.disable)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/session/").data["csrf_token"]
        uploaded = self.client.post("/api/uploads/", {"file": SimpleUploadedFile(
            "items.csv", "상품,분류\n가방,잡화\n".encode())}, format="multipart",
            HTTP_X_CSRFTOKEN=self.token)
        self.upload = Upload.objects.get(pk=uploaded.data["id"])
        self.base = f"/api/uploads/{self.upload.pk}/component-drafts/"
        self.component = ComponentVersion.objects.get(key="catalog-browser-v1")
        self.candidate = ComponentCandidate.objects.create(
            signature="c" * 64, surface="user", capabilities=["catalog.list"],
            new_requirement="항목 수 배지", decision="extend", base_component=self.component,
            blocker="missing_behavior", reason="목록 수 표시가 없음")
        match, _ = record_component_match("user", ["catalog.list", "request.unclassified"], upload=self.upload)
        match.candidate = self.candidate
        call = start_call(upload=self.upload, purpose="synthetic revision", request_body={"model": "test"},
                          approval_note="synthetic approved", approved_at=timezone.now())
        finish_call(call, status=ModelCall.Status.SUCCEEDED, parsed_result={
            "candidates": [{"plan_index": 0, "id": self.candidate.pk}],
            "plans": [{"newRequirement": "이 업로드의 항목 수 배지", "reason": "이 업로드의 판단 근거"}]})
        match.model_call = call
        match.save(update_fields=["candidate", "model_call"])

    def post(self, endpoint, body):
        return self.client.post(self.base + endpoint, body, format="json", HTTP_X_CSRFTOKEN=self.token)

    @patch("uploads.component_draft_views._post_message")
    def test_approval_one_call_and_repeat_uses_saved_draft(self, post_message):
        approval = self.post("approval/", {"candidate_id": self.candidate.pk})
        self.assertEqual(approval.status_code, 200)
        self.assertEqual(approval.data["planned_call_count"], 1)
        self.assertFalse(approval.data["original_csv_file"])
        denied = self.post("generate/", {"candidate_id": self.candidate.pk,
                                         "approved": True, "request_fingerprint": "wrong",
                                         "approval_note": "test"})
        self.assertEqual(denied.status_code, 400)
        post_message.assert_not_called()
        draft = {"status": "draft", "surface": "user", "capabilities": ["catalog.list"],
                 "baseComponent": "catalog-browser-v1", "summary": "항목 수 배지", "question": "",
                 "files": [{"role": "frontend", "source": "export default function CountBadge() { return null; }"}]}
        post_message.return_value = (200, {"request-id": "synthetic"}, json.dumps({
            "content": [{"type": "text", "text": json.dumps(draft)}],
            "usage": {"input_tokens": 10, "output_tokens": 20}}))
        payload = {"candidate_id": self.candidate.pk, "approved": True,
                   "request_fingerprint": approval.data["request_fingerprint"],
                   "approval_note": "앱 버튼으로 1회 호출 승인"}
        created = self.post("generate/", payload)
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.data["content"], draft)
        self.assertFalse(created.data["already_generated"])
        self.assertEqual(ComponentDraft.objects.count(), 1)
        self.assertEqual(ModelCall.objects.filter(purpose="미구현 부품 소스 초안 생성").get().status,
                         ModelCall.Status.SUCCEEDED)
        self.assertIn("이 업로드의 판단 근거", post_message.call_args.args[0]["messages"][0]["content"])
        self.assertNotIn("목록 수 표시가 없음", post_message.call_args.args[0]["messages"][0]["content"])
        self.assertEqual(self.post("generate/", payload).data["already_generated"], True)
        post_message.assert_called_once()
        other_session = APIClient()
        self.assertEqual(other_session.post(self.base + "approval/",
                                            {"candidate_id": self.candidate.pk}, format="json").status_code, 404)

    @patch("uploads.component_draft_views._post_message")
    def test_invalid_draft_is_logged_and_never_saved(self, post_message):
        approval = self.post("approval/", {"candidate_id": self.candidate.pk})
        invalid = {"status": "draft", "surface": "user", "capabilities": ["account.login"],
                   "baseComponent": "catalog-browser-v1", "summary": "허위 기능", "question": "",
                   "files": [{"role": "backend", "source": "pass"}]}
        post_message.return_value = (200, {}, json.dumps({
            "content": [{"type": "text", "text": json.dumps(invalid)}], "usage": {}}))
        result = self.post("generate/", {"candidate_id": self.candidate.pk, "approved": True,
                                         "request_fingerprint": approval.data["request_fingerprint"],
                                         "approval_note": "앱 버튼으로 1회 호출 승인"})
        self.assertEqual(result.status_code, 400)
        self.assertEqual(ComponentDraft.objects.count(), 0)
        self.assertEqual(ModelCall.objects.filter(purpose="미구현 부품 소스 초안 생성").get().status,
                         ModelCall.Status.FAILED)

    @patch("uploads.component_draft_views._post_message", side_effect=ProviderTimeoutError(TIMEOUT_MESSAGE))
    def test_timeout_is_reported_and_logged_as_unknown(self, post_message):
        approval = self.post("approval/", {"candidate_id": self.candidate.pk})
        result = self.post("generate/", {"candidate_id": self.candidate.pk, "approved": True,
                                         "request_fingerprint": approval.data["request_fingerprint"],
                                         "approval_note": "단일 호출 승인"})
        self.assertEqual(result.status_code, 400)
        self.assertIn("응답 대기 시간", result.data["detail"])
        self.assertEqual(ComponentDraft.objects.count(), 0)
        call = ModelCall.objects.filter(purpose="미구현 부품 소스 초안 생성").get()
        self.assertEqual(call.status, ModelCall.Status.UNKNOWN)
        self.assertEqual(call.error_type, "ProviderTimeoutError")
        post_message.assert_called_once()
        self.assertEqual(post_message.call_args.kwargs["timeout_seconds"], 180)

    @patch("uploads.claude.urllib.request.urlopen", side_effect=TimeoutError("read timed out"))
    def test_transport_read_timeout_is_classified(self, urlopen):
        with self.assertRaises(ProviderTimeoutError):
            _post_message({"model": "test", "messages": []})
        urlopen.assert_called_once()
