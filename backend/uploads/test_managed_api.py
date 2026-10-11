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
        self.assertEqual(self.mutate(f"choices/{created_choice.data['id']}/", "patch", {"active": False}).status_code, 400)
        replacement = FieldChoice.objects.get(upload=upload, column_number=1, value="A")
        self.assertEqual(self.mutate(f"choices/{created_choice.data['id']}/", "patch", {"active": False,
            "replacement_id": str(replacement.id), "expected_usage": 1}).status_code, 200)
        self.assertEqual(self.mutate("managed-rows/", "post", {"values": ["C-new", "park"]}).status_code, 400)
        self.assertEqual(self.mutate(f"managed-rows/{row_id}/", "patch", {"values": ["A", "room"]}).status_code, 200)
        self.assertEqual(self.mutate(f"managed-rows/{row_id}/", "delete").status_code, 204)
        self.assertEqual(self.client.get(self.base + "managed-rows/").data["row_count"], 2)

    def test_managed_endpoints_keep_session_isolation(self):
        other = APIClient()
        self.assertEqual(other.get(self.base + "managed-rows/").status_code, 404)
        self.assertEqual(other.get(self.base + "choices/?column=1").status_code, 404)

    def test_choice_stop_replaces_all_usage_and_blocks_delete_bypass(self):
        source = FieldChoice.objects.get(upload_id=self.upload_id, column_number=2, value="park")
        target = FieldChoice.objects.get(upload_id=self.upload_id, column_number=2, value="room")
        self.mutate("managed-rows/", "post", {"values": ["B", "park"]})
        self.assertEqual(self.client.get(self.base + f"choices/{source.id}/").data["usage_count"], 2)
        listed = self.client.get(self.base + "choices/?column=2").data["choices"]
        self.assertEqual(next(item for item in listed if item["id"] == str(source.id))["usage_count"], 2)
        self.assertEqual(self.mutate(f"choices/{source.id}/", "delete").status_code, 400)
        result = self.mutate(f"choices/{source.id}/", "patch", {"active": False,
            "replacement_id": str(target.id), "expected_usage": 2, "expected_value": "park", "replacement_value": "room"})
        self.assertEqual(result.status_code, 200)
        self.assertFalse(FieldChoice.objects.get(pk=source.id).active)
        self.assertTrue(all(row.values[1] == "room" for row in ManagedRow.objects.filter(upload_id=self.upload_id)))
        self.assertEqual(self.mutate(f"choices/{source.id}/", "patch", {"active": True}).status_code, 200)

    def test_stop_rejects_stale_counts_and_invalid_replacements_without_data_changes(self):
        source = FieldChoice.objects.get(upload_id=self.upload_id, column_number=2, value="park")
        target = FieldChoice.objects.get(upload_id=self.upload_id, column_number=2, value="room")
        wrong_column = FieldChoice.objects.get(upload_id=self.upload_id, column_number=1, value="A")
        base = {"active": False, "replacement_id": str(target.id), "expected_usage": 1}
        for changes in ({"expected_usage": 0}, {"expected_usage": True}, {"replacement_id": str(source.id)},
                        {"replacement_id": str(wrong_column.id)}, {"replacement_id": "invalid"},
                        {"expected_value": "changed"}, {"replacement_value": "changed"}):
            self.assertEqual(self.mutate(f"choices/{source.id}/", "patch", {**base, **changes}).status_code, 400)
        target.active = False
        target.save(update_fields=["active"])
        self.assertEqual(self.mutate(f"choices/{source.id}/", "patch", base).status_code, 400)
        self.assertTrue(FieldChoice.objects.get(pk=source.id).active)
        self.assertEqual(ManagedRow.objects.get(upload_id=self.upload_id, row_number=2).values, ["A", "park"])

    def test_unused_choice_can_stop_without_replacement(self):
        added = self.mutate("choices/", "post", {"column": 2, "value": "unused"})
        self.assertEqual(self.mutate(f"choices/{added.data['id']}/", "patch", {"active": False, "expected_usage": 0}).status_code, 200)

    def test_search_and_filter_cover_rows_beyond_first_page(self):
        upload = Upload.objects.get(pk=self.upload_id)
        for number in range(4, 29):
            ManagedRow.objects.create(upload=upload, row_number=number,
                                      values=[f"target {number}", "room" if number % 2 == 0 else "park"])
        response = self.client.get(self.base + "managed-rows/", {"q": "TARGET", "filter_column": 2, "filter_value": "room"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["row_count"], 13)
        self.assertTrue(all(row["values"][1] == "room" for row in response.data["rows"]))
        self.assertIn("target 28", [row["values"][0] for row in response.data["rows"]])
        response = self.client.get(self.base + "managed-rows/", {"q": "target", "page": 2})
        self.assertEqual(len(response.data["rows"]), 5)
        self.assertEqual(response.data["row_count"], 25)
        self.assertEqual(ModelCall.objects.count(), 0)

    def test_search_handles_literal_characters_and_empty_results(self):
        upload = Upload.objects.get(pk=self.upload_id)
        ManagedRow.objects.create(upload=upload, row_number=4, values=['서울 "100%_"', "room"])
        response = self.client.get(self.base + "managed-rows/", {"q": '서울 "100%_"'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["row_count"], 1)
        response = self.client.get(self.base + "managed-rows/", {"q": "absent"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rows"], [])
        self.assertEqual(response.data["row_count"], 0)

    def test_filter_rejects_invalid_column_and_remains_session_scoped(self):
        for params in ({"filter_column": "bad"}, {"filter_column": 3}, {"filter_value": "room"}, {"q": "x" * 201}):
            self.assertEqual(self.client.get(self.base + "managed-rows/", params).status_code, 400)
        self.assertEqual(APIClient().get(self.base + "managed-rows/", {"q": "A", "filter_column": 2, "filter_value": "park"}).status_code, 404)
