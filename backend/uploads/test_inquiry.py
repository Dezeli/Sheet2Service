"""Offline inquiry lifecycle, isolation, and template-contract checks."""
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import Inquiry, ModelCall, Upload
from .workflow import normalize_flow


class InquiryTests(APITestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        media = override_settings(MEDIA_ROOT=temporary.name)
        media.enable()
        self.addCleanup(media.disable)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/session/").data["csrf_token"]
        uploaded = self.client.post("/api/uploads/", {
            "file": SimpleUploadedFile("catalog.csv", b"name,type\nA,product\nB,document\n")},
            format="multipart", HTTP_X_CSRFTOKEN=self.token)
        self.upload = Upload.objects.get(pk=uploaded.data["id"])
        self.base = f"/api/uploads/{self.upload.pk}/inquiries/"
        reference = {"model_call_id": "builtin:inquiry", "index": 0}
        selected = self.client.post(f"/api/uploads/{self.upload.pk}/workflow/",
            {"user": reference, "admin": reference}, format="json", HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(selected.status_code, 200)
        self.upload.refresh_from_db()

    def mutate(self, path, method, body):
        return getattr(self.client, method)(self.base + path, body, format="json", HTTP_X_CSRFTOKEN=self.token)

    def test_general_inquiry_answer_status_and_counts_without_model_call(self):
        created = self.mutate("", "post", {"title": "Question", "body": "Details"})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["subject"], "")
        self.assertEqual(created.data["status"], "received")
        self.assertEqual(self.client.get(self.base + "stats/").data["counts"]["received"], 1)
        url = created.data["id"] + "/"
        self.assertEqual(self.mutate(url, "patch", {"answer": "", "status": "resolved"}).status_code, 400)
        progress = self.mutate(url, "patch", {"answer": "Checking", "status": "in_progress"})
        self.assertEqual(progress.status_code, 200)
        resolved = self.mutate(url, "patch", {"answer": "Answer", "status": "resolved"})
        self.assertEqual(resolved.status_code, 200)
        mine = self.client.get(self.base + "?mine=1").data
        self.assertEqual(mine["inquiries"][0]["answer"], "Answer")
        self.assertEqual(self.client.get(self.base + "stats/").data["counts"]["resolved"], 1)
        self.assertEqual(ModelCall.objects.count(), 0)
        self.assertEqual(self.upload.managed_rows.count(), 2)

    def test_related_item_is_optional_scoped_and_snapshot_survives_deletion(self):
        self.upload.workflow_config["user"]["subjectColumn"] = 1
        self.upload.workflow_config["admin"]["subjectColumn"] = 1
        self.upload.save(update_fields=["workflow_config"])
        row = self.upload.managed_rows.first()
        created = self.mutate("", "post", {"title": "Item question", "body": "Details", "row_id": str(row.id)})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["subject"], "A")
        row.delete()
        item = Inquiry.objects.get(pk=created.data["id"])
        self.assertIsNone(item.subject_row)
        self.assertEqual(item.subject_snapshot, "A")
        self.assertEqual(self.mutate("", "post", {"title": "General", "body": "Details"}).status_code, 201)
        self.assertEqual(self.mutate("", "post", {"title": "Missing", "body": "Details", "row_id": str(row.id)}).status_code, 400)

    def test_validation_csrf_and_wrong_template(self):
        for body in ({"title": " ", "body": "Details"}, {"title": "x" * 121, "body": "Details"},
                     {"title": "Title", "body": "x" * 5001}, {"title": "Title", "body": 3},
                     {"title": "Title", "body": "Details", "status": "resolved"},
                     {"title": "Title", "body": "Details", "row_id": str(self.upload.managed_rows.first().id)}):
            self.assertEqual(self.mutate("", "post", body).status_code, 400)
        self.assertEqual(self.client.post(self.base, {"title": "Title", "body": "Details"}, format="json").status_code, 403)
        self.upload.workflow_config = None
        self.upload.save(update_fields=["workflow_config"])
        self.assertEqual(self.mutate("", "post", {"title": "Title", "body": "Details"}).status_code, 400)

    def test_session_and_upload_isolation(self):
        created = self.mutate("", "post", {"title": "Private", "body": "Details"})
        other = APIClient()
        self.assertEqual(other.get(self.base).status_code, 404)
        self.assertEqual(other.get(self.base + "stats/").status_code, 404)
        unrelated = Upload.objects.create(session_key=self.upload.session_key, original_name="other.csv",
            file_type="csv", size=1, analysis=self.upload.analysis, managed=True,
            workflow_config=self.upload.workflow_config)
        other_base = f"/api/uploads/{unrelated.pk}/inquiries/"
        self.assertEqual(self.client.patch(other_base + created.data["id"] + "/",
            {"answer": "Other", "status": "resolved"}, format="json", HTTP_X_CSRFTOKEN=self.token).status_code, 404)
        self.upload.workflow_config["user"]["subjectColumn"] = 1
        self.upload.save(update_fields=["workflow_config"])
        row = unrelated.managed_rows.create(row_number=1, values=["Other", "document"])
        self.assertEqual(self.mutate("", "post", {"title": "Other", "body": "Details", "row_id": str(row.id)}).status_code, 404)

    def test_pagination_and_unsupported_states(self):
        Inquiry.objects.bulk_create([Inquiry(upload=self.upload, title=str(index), body="Details",
            created_by_session=self.upload.session_key) for index in range(21)])
        self.assertEqual(len(self.client.get(self.base).data["inquiries"]), 20)
        second = self.client.get(self.base + "?mine=1&page=2")
        self.assertEqual(len(second.data["inquiries"]), 1)
        self.assertFalse(second.data["has_next"])
        self.assertEqual(self.client.get(self.base + "?page=0").status_code, 400)
        self.assertEqual(self.client.get(self.base + "?page=bad").status_code, 400)
        self.assertEqual(self.mutate(second.data["inquiries"][0]["id"] + "/", "patch",
            {"answer": "Answer", "status": "approved"}).status_code, 400)
        self.assertEqual(self.client.post(f"/api/uploads/{self.upload.pk}/service-requests/",
            {"row_id": str(self.upload.managed_rows.first().id)}, format="json", HTTP_X_CSRFTOKEN=self.token).status_code, 400)

    def test_template_zero_column_and_steps_are_executable(self):
        flow = normalize_flow({"template": "inquiry", "subjectColumn": 0,
                               "steps": ["Invented payment", "Invented booking"]}, "user", self.upload.analysis)
        self.assertNotIn("Invented", " ".join(flow["steps"]))
        with self.assertRaises(ValueError):
            normalize_flow({"template": "request_review", "subjectColumn": 0,
                            "steps": ["Select", "Submit"]}, "user", self.upload.analysis)
