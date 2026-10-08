"""Managed data and choice APIs never call the model provider."""

import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .models import FieldChoice, ManagedRow, ModelCall, Upload


class ManagedApiTests(APITestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        media = override_settings(MEDIA_ROOT=temporary.name)
        media.enable()
        self.addCleanup(media.disable)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/session/").data["csrf_token"]
        response = self.client.post("/api/uploads/", {
            "file": SimpleUploadedFile("items.csv", b"name,kind\nA,park\nB,room\n")},
            format="multipart", HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(response.status_code, 201)
        self.upload_id = response.data["id"]
        self.base = f"/api/uploads/{self.upload_id}/"

    def mutate(self, path, method, body=None):
        return getattr(self.client, method)(self.base + path, body, format="json",
                                            HTTP_X_CSRFTOKEN=self.token)

    def test_import_choices_and_select_only_record_changes(self):
        upload = Upload.objects.get(pk=self.upload_id)
        self.assertTrue(upload.managed)
        self.assertEqual(ManagedRow.objects.filter(upload=upload).count(), 2)
        self.assertEqual(FieldChoice.objects.filter(upload=upload).count(), 4)
        self.assertEqual(self.mutate("managed-rows/", "post", {"values": ["C", "park"]}).status_code, 400)

        created_choice = self.mutate("choices/", "post", {"column": 1, "value": "C"})
        self.assertEqual(created_choice.status_code, 201)
        created_row = self.mutate("managed-rows/", "post", {"values": ["C", "park"]})
        self.assertEqual(created_row.status_code, 201)
        row_id = created_row.data["id"]
        self.assertEqual(self.client.get(self.base + "managed-rows/").data["row_count"], 3)
        self.assertEqual(self.client.get(self.base + "rows/").data["rows"][-1]["values"], ["C", "park"])

        renamed = self.mutate(f"choices/{created_choice.data['id']}/", "patch", {"value": "C-new"})
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(ManagedRow.objects.get(pk=row_id).values, ["C-new", "park"])
        ModelCall.objects.create(
            upload=upload, purpose="preview", model="test-model", request_body={"model": "test-model"},
            approval_note="recorded approval", approved_at=timezone.now(),
            status=ModelCall.Status.SUCCEEDED,
            parsed_result={"preview": {"version": 2, "views": [{"template": "table", "columns": [1, 2]}]}},
        )
        service = self.client.get(self.base + "service/")
        self.assertEqual(service.data["upload"]["analysis"]["row_count"], 3)
        self.assertEqual(service.data["upload"]["analysis"]["preview"][-1]["values"], ["C-new", "park"])
        self.assertEqual(self.mutate(f"choices/{created_choice.data['id']}/", "patch", {"active": False}).status_code, 200)
        self.assertEqual(self.mutate("managed-rows/", "post", {"values": ["C-new", "park"]}).status_code, 400)
        self.assertEqual(self.mutate(f"managed-rows/{row_id}/", "patch", {"values": ["C-new", "room"]}).status_code, 200)
        self.assertEqual(self.mutate(f"managed-rows/{row_id}/", "delete").status_code, 204)
        self.assertEqual(self.client.get(self.base + "managed-rows/").data["row_count"], 2)

    def test_managed_endpoints_keep_session_isolation(self):
        other = APIClient()
        self.assertEqual(other.get(self.base + "managed-rows/").status_code, 404)
        self.assertEqual(other.get(self.base + "choices/?column=1").status_code, 404)
