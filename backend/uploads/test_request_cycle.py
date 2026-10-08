"""One uploaded catalog can run a generic user/admin request cycle."""

import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import ServiceRequest, Upload


class RequestCycleTests(APITestCase):
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
        self.base = f"/api/uploads/{self.upload.pk}/service-requests/"
        self.row = self.upload.managed_rows.first()

    def mutate(self, path, method, body):
        return getattr(self.client, method)(self.base + path, body, format="json",
                                            HTTP_X_CSRFTOKEN=self.token)

    def test_review_request_create_approve_and_dashboard_counts(self):
        self.upload.workflow_config = {"version": 1,
            "user": {"template": "request_review", "subjectColumn": 1},
            "admin": {"template": "review_requests", "subjectColumn": 1}}
        self.upload.save(update_fields=["workflow_config"])
        created = self.mutate("", "post", {"row_id": str(self.row.id)})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["status"], "pending")
        self.assertEqual(created.data["subject"], "A")
        self.assertEqual(self.client.get(self.base + "?mine=1").data["count"], 1)
        self.assertEqual(self.client.get(self.base + "stats/").data["counts"]["pending"], 1)
        approved = self.mutate(f"{created.data['id']}/", "patch", {"status": "approved"})
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["status"], "approved")
        self.assertEqual(self.client.get(self.base + "stats/").data["counts"]["approved"], 1)
        self.assertEqual(self.mutate(f"{created.data['id']}/", "patch", {"status": "rejected"}).status_code, 400)
        self.row.delete()
        self.assertEqual(ServiceRequest.objects.get(pk=created.data["id"]).subject_snapshot, "A")

    def test_direct_request_and_browse_only_have_distinct_actions(self):
        self.upload.workflow_config = {"version": 1,
            "user": {"template": "request_auto", "subjectColumn": 1},
            "admin": {"template": "monitor_requests", "subjectColumn": 1}}
        self.upload.save(update_fields=["workflow_config"])
        created = self.mutate("", "post", {"row_id": str(self.row.id)})
        self.assertEqual(created.data["status"], "submitted")
        self.assertEqual(self.mutate(f"{created.data['id']}/", "patch", {"status": "approved"}).status_code, 400)
        self.upload.workflow_config = {"version": 1,
            "user": {"template": "browse_only", "subjectColumn": 1},
            "admin": {"template": "manage_catalog", "subjectColumn": 1}}
        self.upload.save(update_fields=["workflow_config"])
        self.assertEqual(self.mutate("", "post", {"row_id": str(self.row.id)}).status_code, 400)

    def test_requests_remain_scoped_to_upload_session(self):
        other = APIClient()
        self.assertEqual(other.get(self.base).status_code, 404)
