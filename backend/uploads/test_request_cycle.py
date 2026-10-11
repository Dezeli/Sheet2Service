"""One uploaded catalog can run a generic user/admin request cycle."""

import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import ServiceRequest, Upload


class RequestCycleTests(APITestCase):
    def test_search_status_and_sort_apply_before_pagination(self):
        self.select_reception(0)
        for index in range(25):
            ServiceRequest.objects.create(upload=self.upload, subject_snapshot=f"Item {index:02d}",
                content="needle" if index == 24 else "", status="pending" if index % 2 == 0 else "approved",
                created_by_session=self.upload.session_key)
        found = self.client.get(self.base, {"q": "needle", "status": "pending"})
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.data["count"], 1)
        self.assertEqual(found.data["requests"][0]["subject"], "Item 24")
        ordered = self.client.get(self.base, {"sort": "subject", "page": 2})
        self.assertEqual(ordered.data["requests"][0]["subject"], "Item 20")
        descending = self.client.get(self.base, {"sort": "-subject"})
        self.assertEqual(descending.data["requests"][0]["subject"], "Item 24")
        for criteria in ({"status": "invalid"}, {"sort": "invalid"}, {"q": "x" * 201}):
            self.assertEqual(self.client.get(self.base, criteria).status_code, 400)

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

    def select_reception(self, index):
        reference = {"model_call_id": "builtin:reception", "index": index}
        result = self.client.post(f"/api/uploads/{self.upload.pk}/workflow/",
            {"user": reference, "admin": reference}, format="json", HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["selected"]["reception"]["approval"], "required" if index == 0 else "none")
        return result

    def test_review_lifecycle_requires_decision_then_processing(self):
        self.select_reception(0)
        created = self.mutate("", "post", {"row_id": str(self.row.id), "content": "Please review"})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["content"], "Please review")
        url = created.data["id"] + "/"
        self.assertEqual(self.mutate(url, "patch", {"status": "in_progress"}).status_code, 400)
        self.assertEqual(self.mutate(url, "patch", {"status": "rejected"}).status_code, 400)
        approved = self.mutate(url, "patch", {"status": "approved", "processing_note": "Eligible"})
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["admin_actions"], ["in_progress"])
        self.assertEqual(self.mutate(url, "patch", {"status": "completed"}).status_code, 400)
        self.assertEqual(self.mutate(url, "patch", {"status": "in_progress"}).status_code, 200)
        self.assertEqual(self.mutate(url, "patch", {"status": "cancelled"}).status_code, 400)
        completed = self.mutate(url, "patch", {"status": "completed", "processing_note": "Done"})
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.data["admin_actions"], [])
        self.assertEqual(self.client.get(self.base + "?mine=1").data["requests"][0]["processing_note"], "Done")
        self.assertEqual(self.client.get(self.base + "stats/").data["counts"]["completed"], 1)
        self.assertEqual(self.mutate(url, "patch", {"status": "approved"}).status_code, 400)

    def test_immediate_mode_cannot_approve_and_survives_config_change(self):
        self.select_reception(1)
        created = self.mutate("", "post", {"row_id": str(self.row.id), "content": "Work request"})
        self.assertEqual(created.data["status"], "submitted")
        self.assertEqual(created.data["approval_mode"], "none")
        url = created.data["id"] + "/"
        self.assertEqual(self.mutate(url, "patch", {"status": "approved"}).status_code, 400)
        self.select_reception(0)
        self.assertEqual(self.mutate(url, "patch", {"status": "in_progress"}).status_code, 200)
        self.assertEqual(self.mutate(url, "patch", {"status": "completed"}).status_code, 200)

    def test_duplicates_and_cancel_before_processing(self):
        self.select_reception(0)
        body = {"row_id": str(self.row.id), "content": "First"}
        created = self.mutate("", "post", body)
        self.assertEqual(self.mutate("", "post", body).status_code, 400)
        url = created.data["id"] + "/"
        ServiceRequest.objects.filter(pk=created.data["id"]).update(created_by_session="someone-else")
        self.assertEqual(self.mutate(url, "patch", {"status": "cancelled"}).status_code, 400)
        ServiceRequest.objects.filter(pk=created.data["id"]).update(created_by_session=self.upload.session_key)
        self.assertEqual(self.mutate(url, "patch", {"status": "cancelled"}).status_code, 200)
        self.assertEqual(self.mutate(url, "patch", {"status": "approved"}).status_code, 400)
        again = self.mutate("", "post", body)
        self.assertEqual(again.status_code, 201)
        self.assertEqual(self.mutate(again.data["id"] + "/", "patch", {"status": "approved"}).status_code, 200)
        self.assertEqual(self.mutate(again.data["id"] + "/", "patch", {"status": "cancelled"}).status_code, 200)

    def test_rejection_reason_and_input_validation(self):
        self.select_reception(0)
        for content in (None, 4, "x" * 5001):
            self.assertEqual(self.mutate("", "post", {"row_id": str(self.row.id), "content": content}).status_code, 400)
        created = self.mutate("", "post", {"row_id": str(self.row.id)})
        url = created.data["id"] + "/"
        self.assertEqual(self.mutate(url, "patch", {"status": "rejected", "processing_note": " "}).status_code, 400)
        rejected = self.mutate(url, "patch", {"status": "rejected", "processing_note": "Not eligible"})
        self.assertEqual(rejected.status_code, 200)
        self.assertFalse(rejected.data["can_cancel"])
        self.assertEqual(rejected.data["processing_note"], "Not eligible")
        self.assertEqual(self.mutate("", "post", {"row_id": str(self.row.id)}).status_code, 201)
