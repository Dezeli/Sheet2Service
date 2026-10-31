"""Shared offline setup: upload a CSV through the API and build its service from a fixed understanding."""
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient

from .models import Upload
from .reservation_service import build_service
from .reservation_understanding import validate_understanding


def isolated_media(test):
    temporary = tempfile.TemporaryDirectory()
    test.addCleanup(temporary.cleanup)
    media = override_settings(MEDIA_ROOT=temporary.name)
    media.enable()
    test.addCleanup(media.disable)


def upload_csv(client, token, data, name="sheet.csv"):
    response = client.post("/api/uploads/", {"file": SimpleUploadedFile(name, data)}, format="multipart",
                           HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 201, response.data
    return Upload.objects.get(pk=response.data["id"])


def build_from_answer(upload, answer):
    understanding, _ = validate_understanding(answer, upload.analysis)
    upload.understanding = understanding
    upload.save(update_fields=["understanding"])
    return build_service(upload, understanding)


class ServiceClientMixin:
    """A CSRF-enforcing client, an uploaded sheet and a built service for API tests."""
    csv_data = b""
    csv_name = "sheet.csv"

    def answer(self):
        raise NotImplementedError

    def setUp(self):
        isolated_media(self)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/session/").data["csrf_token"]
        self.upload = upload_csv(self.client, self.token, self.csv_data, self.csv_name)
        self.config, self.counts = build_from_answer(self.upload, self.answer())
        self.upload.refresh_from_db()
        self.base = f"/api/uploads/{self.upload.pk}/"

    def mutate(self, path, body, method="post"):
        return getattr(self.client, method)(self.base + path, body, format="json", HTTP_X_CSRFTOKEN=self.token)

    def rebuild(self, answer):
        self.config, self.counts = build_from_answer(self.upload, answer)
        self.upload.refresh_from_db()
