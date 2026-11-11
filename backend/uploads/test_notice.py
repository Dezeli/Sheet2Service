"""Offline notice lifecycle, isolation and feature gating on the generated service."""
from rest_framework.test import APIClient, APITestCase

from .models import ModelCall, Notice
from .test_fixtures import ServiceClientMixin
from .test_reservation_understanding import BOOKINGS, model_answer


def notice_answer():
    answer = model_answer()
    for persona in answer["personas"]:
        if persona["id"] == "admin":
            persona["features"].append("manage_notices")
        if persona["id"] == "booker":
            persona["features"].append("notices")
    return answer


class NoticeApiTests(ServiceClientMixin, APITestCase):
    csv_data = BOOKINGS

    def answer(self):
        return notice_answer()

    def create(self, **changes):
        return self.mutate("notices/", {"title": "운영 안내", "body": "공지 내용", **changes})

    def test_draft_publish_edit_unpublish_and_republish(self):
        draft = self.create()
        self.assertEqual(draft.status_code, 201)
        self.assertFalse(draft.data["is_published"])
        self.assertIsNone(draft.data["published_at"])
        path = f"notices/{draft.data['id']}/"
        self.assertEqual(self.client.get(self.base + "notices/").data["count"], 0)
        self.assertEqual(self.client.get(self.base + path).status_code, 404)
        self.assertEqual(self.client.get(self.base + path + "?admin=1").status_code, 200)
        published = self.mutate(path, {"is_published": True}, "patch")
        self.assertEqual(published.status_code, 200)
        self.assertIsNotNone(published.data["published_at"])
        self.assertEqual(self.client.get(self.base + "notices/").data["count"], 1)
        edited = self.mutate(path, {"body": "수정된 안내"}, "patch")
        self.assertEqual(edited.data["published_at"], published.data["published_at"])
        self.assertEqual(self.client.get(self.base + path).data["body"], "수정된 안내")
        self.assertEqual(self.mutate(path, {"is_published": False}, "patch").status_code, 200)
        self.assertEqual(self.client.get(self.base + path).status_code, 404)
        self.assertEqual(self.client.get(self.base + "notices/?admin=1").data["count"], 1)
        self.assertIsNotNone(self.mutate(path, {"is_published": True}, "patch").data["published_at"])
        self.assertEqual(ModelCall.objects.count(), 0)

    def test_published_creation_pagination_and_draft_filter(self):
        self.assertEqual(self.create(is_published=True).status_code, 201)
        Notice.objects.bulk_create([Notice(upload=self.upload, title=f"공지 {index}", body="안내",
                                           is_published=False) for index in range(21)])
        user = self.client.get(self.base + "notices/").data
        self.assertEqual(user["count"], 1)
        self.assertTrue(all(item["is_published"] for item in user["notices"]))
        admin = self.client.get(self.base + "notices/?admin=1").data
        self.assertEqual(admin["count"], 22)
        self.assertEqual(len(admin["notices"]), 20)
        self.assertTrue(admin["has_next"])
        self.assertEqual(len(self.client.get(self.base + "notices/?admin=1&page=2").data["notices"]), 2)
        for page in ("bad", "0", "3"):
            self.assertEqual(self.client.get(self.base + f"notices/?admin=1&page={page}").status_code, 400)

    def test_validation_csrf_and_upload_isolation(self):
        for changes in ({"title": " "}, {"body": ""}, {"title": "x" * 121},
                        {"body": "x" * 10001}, {"is_published": 1}, {"is_published": "yes"}, {"unknown": True}):
            self.assertEqual(self.create(**changes).status_code, 400)
        notice = self.create().data
        path = f"notices/{notice['id']}/"
        for values in ({}, {"title": None}, {"is_published": 0}, {"upload": str(self.upload.pk)}):
            self.assertEqual(self.mutate(path, values, "patch").status_code, 400)
        anonymous = APIClient(enforce_csrf_checks=True)
        self.assertEqual(anonymous.get(self.base + "notices/?admin=1").status_code, 404)
        self.assertEqual(anonymous.patch(self.base + path, {"is_published": True}, format="json").status_code, 403)

    def test_service_without_the_feature_keeps_but_hides_notices(self):
        self.create(is_published=True)
        config = self.upload.service_config  # a config without the board, as only a hand-made one can be now
        for persona in config["personas"]:
            persona["features"] = [f for f in persona["features"] if f not in ("notices", "manage_notices")]
        self.upload.service_config = config
        self.upload.save(update_fields=["service_config"])
        self.assertEqual(self.client.get(self.base + "notices/").status_code, 400)
        self.assertEqual(Notice.objects.count(), 1)
        self.rebuild(notice_answer())
        self.assertEqual(self.client.get(self.base + "notices/").data["count"], 1)


class NoticeDeleteTests(ServiceClientMixin, APITestCase):
    csv_data = BOOKINGS

    def answer(self):
        return notice_answer()

    def test_an_admin_deletes_a_notice(self):
        created = self.mutate("notices/", {"title": "운영 안내", "body": "공지 내용", "is_published": True})
        self.assertEqual(self.mutate(f"notices/{created.data['id']}/", {}, "delete").status_code, 204)
        self.assertFalse(Notice.objects.filter(pk=created.data["id"]).exists())
        self.assertEqual(self.mutate(f"notices/{created.data['id']}/", {}, "delete").status_code, 404)
