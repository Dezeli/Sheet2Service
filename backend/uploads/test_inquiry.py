"""Offline inquiry lifecycle, isolation and feature gating on the generated service."""
from rest_framework.test import APIClient, APITestCase

from .models import Inquiry, ModelCall, Upload
from .test_fixtures import ServiceClientMixin
from .test_reservation_understanding import BOOKINGS, model_answer


class InquiryTests(ServiceClientMixin, APITestCase):
    csv_data = BOOKINGS

    def answer(self):
        return model_answer()

    def setUp(self):
        super().setUp()
        self.base = f"/api/uploads/{self.upload.pk}/inquiries/"

    def test_general_inquiry_answer_status_and_counts_without_model_call(self):
        created = self.mutate("", {"title": "Question", "body": "Details"})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["subject"], "")
        self.assertEqual(created.data["status"], "received")
        self.assertEqual(self.client.get(self.base + "stats/").data["counts"]["received"], 1)
        url = created.data["id"] + "/"
        self.assertEqual(self.mutate(url, {"answer": "", "status": "resolved"}, "patch").status_code, 400)
        self.assertEqual(self.mutate(url, {"answer": "Checking", "status": "in_progress"}, "patch").status_code, 200)
        self.assertEqual(self.mutate(url, {"answer": "Answer", "status": "resolved"}, "patch").status_code, 200)
        mine = self.client.get(self.base + "?mine=1").data
        self.assertEqual(mine["inquiries"][0]["answer"], "Answer")
        self.assertEqual(self.client.get(self.base + "stats/").data["counts"]["resolved"], 1)
        self.assertEqual(ModelCall.objects.count(), 0)

    def test_related_item_uses_the_last_resource_column_and_survives_row_deletion(self):
        row = self.upload.managed_rows.first()
        created = self.mutate("", {"title": "Item question", "body": "Details", "row_id": str(row.id)})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["subject"], "우럭")  # 상품명, the leaf of 기관명 > 상품명
        row.delete()
        item = Inquiry.objects.get(pk=created.data["id"])
        self.assertIsNone(item.subject_row)
        self.assertEqual(item.subject_snapshot, "우럭")
        self.assertEqual(self.mutate("", {"title": "Missing", "body": "Details", "row_id": str(row.id)}).status_code, 400)

    def test_validation_csrf_and_missing_feature(self):
        for body in ({"title": " ", "body": "Details"}, {"title": "x" * 121, "body": "Details"},
                     {"title": "Title", "body": "x" * 5001}, {"title": "Title", "body": 3},
                     {"title": "Title", "body": "Details", "status": "resolved"}):
            self.assertEqual(self.mutate("", body).status_code, 400)
        self.assertEqual(self.client.post(self.base, {"title": "Title", "body": "Details"}, format="json").status_code, 403)
        answer = model_answer()
        for persona in answer["personas"]:
            persona["features"] = [f for f in persona["features"] if f not in ("inquiry", "reply_inquiries")]
        self.rebuild(answer)
        self.assertEqual(self.mutate("", {"title": "Title", "body": "Details"}).status_code, 400)
        self.upload.service_config = None
        self.upload.save(update_fields=["service_config"])
        self.assertEqual(self.client.get(self.base + "stats/").status_code, 400)

    def test_session_and_upload_isolation(self):
        created = self.mutate("", {"title": "Private", "body": "Details"})
        other = APIClient()
        self.assertEqual(other.get(self.base).status_code, 404)
        self.assertEqual(other.get(self.base + "stats/").status_code, 404)
        unrelated = Upload.objects.create(session_key=self.upload.session_key, original_name="other.csv",
                                          file_type="csv", size=1, analysis=self.upload.analysis, managed=True,
                                          service_config=self.upload.service_config)
        other_base = f"/api/uploads/{unrelated.pk}/inquiries/"
        self.assertEqual(self.client.patch(other_base + created.data["id"] + "/",
                                           {"answer": "Other", "status": "resolved"}, format="json",
                                           HTTP_X_CSRFTOKEN=self.token).status_code, 404)
        row = unrelated.managed_rows.create(row_number=1, values=["R", "기관", "방", "2026-01-01", "", "", "", "", "", ""])
        self.assertEqual(self.mutate("", {"title": "Other", "body": "Details", "row_id": str(row.id)}).status_code, 404)

    def test_pagination_and_unsupported_states(self):
        Inquiry.objects.bulk_create([Inquiry(upload=self.upload, title=str(index), body="Details",
                                             created_by_session=self.upload.session_key) for index in range(21)])
        self.assertEqual(len(self.client.get(self.base).data["inquiries"]), 20)
        second = self.client.get(self.base + "?mine=1&page=2")
        self.assertEqual(len(second.data["inquiries"]), 1)
        self.assertFalse(second.data["has_next"])
        self.assertEqual(self.client.get(self.base + "?page=0").status_code, 400)
        self.assertEqual(self.client.get(self.base + "?page=bad").status_code, 400)
        self.assertEqual(self.mutate(second.data["inquiries"][0]["id"] + "/",
                                     {"answer": "Answer", "status": "approved"}, "patch").status_code, 400)

    def test_status_filter_and_delete(self):
        first = self.mutate("", {"title": "One", "body": "Details"}).data
        second = self.mutate("", {"title": "Two", "body": "Details"}).data
        self.mutate(second["id"] + "/", {"answer": "Answer", "status": "resolved"}, "patch")
        waiting = self.client.get(self.base + "?status=received").data
        self.assertEqual([item["id"] for item in waiting["inquiries"]], [first["id"]])
        self.assertEqual(self.client.get(self.base + "?status=bad").status_code, 400)
        self.assertEqual(self.mutate(first["id"] + "/", {}, "delete").status_code, 204)
        self.assertFalse(Inquiry.objects.filter(pk=first["id"]).exists())
        self.assertEqual(self.mutate(first["id"] + "/", {}, "delete").status_code, 404)


class InquiryResourceSubjectTests(ServiceClientMixin, APITestCase):
    csv_data = BOOKINGS

    def answer(self):
        return model_answer()

    def test_a_resource_names_the_subject(self):
        from .models import Resource
        room = Resource.objects.get(upload=self.upload, path="변산 자연휴양림 / 우럭")
        created = self.mutate("inquiries/", {"title": "문의", "body": "내용", "resource_id": str(room.id)})
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["subject"], "변산 자연휴양림 / 우럭")
