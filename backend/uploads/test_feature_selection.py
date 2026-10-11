"""Feature deduplication, composition, and legacy compatibility without model calls."""
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .models import ModelCall, Upload


def flow(template, column=1):
    return {"template": template, "subjectColumn": column, "steps": ["View", "Submit"]}


def reference(name, index=0, scope="user"):
    return {"model_call_id": f"builtin:{name}", "index": index, "scope": scope}


class FeatureSelectionTests(APITestCase):
    def test_ai_feature_titles_reach_catalog_and_saved_selection(self):
        titles = {"user": "교육 프로그램 수강 신청", "admin": "교육 프로그램 신청 승인"}
        self.recorded({"service_subject": "교육 프로그램",
                       "user_flows": [{**flow("request_review"), "titles": titles}],
                       "admin_flows": [{**flow("review_requests"), "titles": titles}]})
        data = self.client.get(self.base + "workflow/").data
        candidate = data["recommended"][0]
        self.assertEqual(candidate["user_title"], titles["user"])
        self.assertEqual(candidate["admin_title"], titles["admin"])
        self.assertEqual(data["templates"], [])
        self.assertEqual([item["template"] for item in data["recommended"]], ["request_review"])
        saved = self.mutate("workflow/", {"features": [candidate["reference"]]})
        self.assertEqual(saved.data["selected"]["user"]["title"], titles["user"])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        media = override_settings(MEDIA_ROOT=temporary.name)
        media.enable()
        self.addCleanup(media.disable)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/session/").data["csrf_token"]
        uploaded = self.client.post("/api/uploads/", {
            "file": SimpleUploadedFile("catalog.csv", b"name,category\nA,product\nB,document\n")},
            format="multipart", HTTP_X_CSRFTOKEN=self.token)
        self.upload = Upload.objects.get(pk=uploaded.data["id"])
        self.base = f"/api/uploads/{self.upload.id}/"

    def mutate(self, path, body, method="post"):
        return getattr(self.client, method)(self.base + path, body, format="json", HTTP_X_CSRFTOKEN=self.token)

    def recorded(self, parsed):
        return ModelCall.objects.create(upload=self.upload, purpose="offline fixture", model="offline",
            request_body={}, approval_note="offline", approved_at=timezone.now(),
            status=ModelCall.Status.SUCCEEDED, parsed_result=parsed)

    def test_latest_recommendation_only_and_no_builtin_duplicates(self):
        self.recorded({"user_flows": [flow("request_auto")], "admin_flows": [flow("monitor_requests")]})
        latest = self.recorded({"user_flows": [flow("request_review"), flow("request_review"), flow("inquiry", 0)],
                               "admin_flows": [flow("review_requests"), flow("reply_inquiries", 0)]})
        data = self.client.get(self.base + "workflow/").data
        templates = [item["template"] for item in data["recommended"] + data["templates"]]
        self.assertEqual(len(templates), len(set(templates)))
        self.assertEqual([item["template"] for item in data["recommended"]], ["request_review", "inquiry"])
        self.assertTrue(all(item["reference"]["model_call_id"] == str(latest.id) for item in data["recommended"]))
        self.assertTrue(all(len(items) == len({item["template"] for item in items}) for items in data["options"].values()))

    def test_custom_admin_recommendation_is_prioritized_and_old_custom_does_not_accumulate(self):
        self.recorded({"user_flows": [flow("request_review")], "admin_flows": [flow("review_requests")]})
        self.recorded({"admin_flows": [flow("monitor_requests")]})
        latest = self.recorded({"admin_flows": [flow("reply_inquiries", 0)]})
        data = self.client.get(self.base + "workflow/").data
        self.assertEqual(data["recommended"][0]["template"], "inquiry")
        self.assertEqual(data["recommended"][0]["reference"]["model_call_id"], str(latest.id))
        self.assertNotIn("request_auto", [item["template"] for item in data["recommended"]])
        applied = self.mutate("workflow/", {"features": [data["recommended"][0]["reference"]]})
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.data["selected"]["modules"][0]["user"]["subjectColumn"], 0)

    def test_request_inquiry_catalog_work_together_in_any_selection_order(self):
        for refs in ([reference("catalog"), reference("inquiry"), reference("reception")],
                     [reference("reception", 1), reference("inquiry"), reference("catalog")]):
            applied = self.mutate("workflow/", {"features": refs})
            self.assertEqual(applied.status_code, 200)
            self.assertEqual(len(applied.data["selected"]["modules"]), 3)
            request = self.mutate("service-requests/", {"row_id": str(self.upload.managed_rows.first().id), "content": "Details"})
            self.assertEqual(request.status_code, 201)
            self.assertEqual(self.mutate("service-requests/" + request.data["id"] + "/", {"status": "cancelled"}, "patch").status_code, 200)
            inquiry = self.mutate("inquiries/", {"title": "Question", "body": "Details"})
            self.assertEqual(inquiry.status_code, 201)
            self.assertEqual(self.mutate("inquiries/" + inquiry.data["id"] + "/", {"answer": "Answer", "status": "resolved"}, "patch").status_code, 200)
            self.assertEqual(self.client.get(self.base + "service-requests/stats/").status_code, 200)
            self.assertEqual(self.client.get(self.base + "inquiries/stats/").status_code, 200)
            self.assertEqual(self.client.get(self.base + "managed-rows/").status_code, 200)
        self.assertEqual(ModelCall.objects.count(), 0)
        restored = self.client.get(self.base + "workflow/").data["selected"]
        self.assertEqual([module["selection"] for module in restored["modules"]], refs)

    def test_duplicate_modes_invalid_references_and_empty_selection_are_rejected(self):
        for refs in ([], [reference("inquiry"), reference("inquiry")],
                     [reference("reception"), reference("reception", 1)],
                     [reference("inquiry", scope="sql")], [reference("catalog", 2)],
                     [reference("inquiry")] * 4):
            self.assertEqual(self.mutate("workflow/", {"features": refs}).status_code, 400)
        self.upload.refresh_from_db()
        self.assertIsNone(self.upload.workflow_config)

    def test_deselected_module_is_unavailable_and_other_records_remain(self):
        self.mutate("workflow/", {"features": [reference("inquiry"), reference("reception")]})
        inquiry = self.mutate("inquiries/", {"title": "Question", "body": "Details"})
        self.mutate("workflow/", {"features": [reference("reception")]})
        self.assertEqual(self.client.get(self.base + "inquiries/").status_code, 400)
        self.assertEqual(self.mutate("inquiries/", {"title": "Hidden", "body": "Details"}).status_code, 400)
        self.mutate("workflow/", {"features": [reference("inquiry")]})
        self.assertEqual(self.client.get(self.base + "inquiries/").data["inquiries"][0]["id"], inquiry.data["id"])
        self.assertEqual(self.mutate("service-requests/", {"row_id": str(self.upload.managed_rows.first().id)}).status_code, 400)

    def test_legacy_single_pair_still_works_and_foreign_reference_is_rejected(self):
        old_reference = {"model_call_id": "builtin:inquiry", "index": 0}
        self.assertEqual(self.mutate("workflow/", {"user": old_reference, "admin": old_reference}).status_code, 200)
        self.assertEqual(self.mutate("inquiries/", {"title": "Legacy", "body": "Details"}).status_code, 201)
        other = Upload.objects.create(session_key="other", file_type="csv", size=1, analysis=self.upload.analysis)
        call = self.recorded({"user_flows": [flow("request_review")]})
        call.upload = other
        call.save(update_fields=["upload"])
        self.assertEqual(self.mutate("workflow/", {"features": [{"model_call_id": str(call.id), "index": 0, "scope": "user"}]}).status_code, 400)

    def test_roles_link_only_paired_functions_and_preserve_independent_choices(self):
        result = self.mutate("workflow/", {"features": [reference("inquiry", scope="admin"), reference("catalog")],
            "roles": {"dashboard": ["inquiry_statistics"], "admin": []}})
        self.assertEqual(result.status_code, 200)
        roles = result.data["selected"]["role_selection"]
        self.assertEqual(roles["user"], ["inquiry", "browse_only"])
        self.assertEqual(roles["admin"], ["reply_inquiries"])
        self.assertEqual(roles["dashboard"], ["inquiry_statistics"])
        updated = self.mutate("workflow/", {"features": [reference("catalog")],
            "roles": {"dashboard": [], "admin": ["manage_catalog"]}})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["selected"]["role_selection"],
            {"user": ["browse_only"], "admin": ["manage_catalog"], "dashboard": []})

    def test_dashboard_or_admin_only_configs_and_invalid_role_choices(self):
        for roles in ({"dashboard": ["request_statistics", "inquiry_statistics"], "admin": []},
                      {"dashboard": [], "admin": ["manage_catalog"]}):
            result = self.mutate("workflow/", {"features": [], "roles": roles})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.data["selected"]["modules"], [])
            self.assertEqual(result.data["selected"]["role_selection"]["user"], [])
            self.assertEqual(self.client.get(self.base + "service-requests/stats/").status_code, 200)
            self.assertEqual(self.client.get(self.base + "inquiries/stats/").status_code, 200)
            self.assertEqual(self.mutate("service-requests/", {"row_id": str(self.upload.managed_rows.first().id)}).status_code, 400)
        for roles in ({"dashboard": [], "admin": []},
                      {"dashboard": ["payment"], "admin": []},
                      {"dashboard": [], "admin": ["reply_inquiries"]},
                      {"dashboard": ["csv_statistics", "csv_statistics"], "admin": []}):
            self.assertEqual(self.mutate("workflow/", {"features": [], "roles": roles}).status_code, 400)
