"""Offline notice lifecycle, isolation and feature composition checks."""
from rest_framework.test import APIClient, APITestCase

from . import test_feature_selection as fixtures
from .models import ModelCall, Notice


class NoticeApiTests(APITestCase):
    mutate = fixtures.FeatureSelectionTests.mutate
    recorded = fixtures.FeatureSelectionTests.recorded

    def setUp(self):
        fixtures.FeatureSelectionTests.setUp(self)
        self.call = self.recorded({"user_flows": [fixtures.flow("notice")],
                                   "admin_flows": [fixtures.flow("manage_notices")]})
        self.reference = {"scope": "user", "model_call_id": str(self.call.pk), "index": 0}
        self.assertEqual(self.mutate("workflow/", {"features": [self.reference]}).status_code, 200)

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
        republished = self.mutate(path, {"is_published": True}, "patch")
        self.assertIsNotNone(republished.data["published_at"])
        self.assertEqual(ModelCall.objects.count(), 1)

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

    def test_deselection_preserves_notices_and_reselection_restores_them(self):
        self.create(is_published=True)
        self.mutate("workflow/", {"features": [fixtures.reference("inquiry")]})
        self.assertEqual(self.client.get(self.base + "notices/").status_code, 400)
        self.assertEqual(Notice.objects.count(), 1)
        self.mutate("workflow/", {"features": [self.reference]})
        self.assertEqual(self.client.get(self.base + "notices/").data["count"], 1)

    def test_notice_pairs_and_composes_with_other_features(self):
        call = self.recorded({"user_flows": [fixtures.flow("reservation"), fixtures.flow("notice")],
                              "admin_flows": [fixtures.flow("manage_reservations"), fixtures.flow("manage_notices")]})
        refs = [{"scope": "admin", "model_call_id": str(call.pk), "index": index} for index in (0, 1)]
        selected = self.mutate("workflow/", {"features": [*refs, fixtures.reference("inquiry"), fixtures.reference("catalog")]})
        self.assertEqual(selected.status_code, 200)
        modules = selected.data["selected"]["modules"]
        self.assertEqual(len(modules), 4)
        self.assertEqual(modules[1]["user"]["template"], "notice")
        self.assertEqual(modules[1]["admin"]["template"], "manage_notices")
        self.assertEqual(self.create(is_published=True).status_code, 201)
