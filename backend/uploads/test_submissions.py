"""Applications about catalog rows, opened by the row's own status flow; no Claude calls."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient, APITestCase

from .analysis import analyze
from .models import BlueprintSubmission, ManagedRow, Upload
from .sheet_understanding import validate_understanding
from .understanding_derivation import derive_blueprint

CSV = ("서비스ID,서비스명,서비스상태,장소명,접수시작일시\n"
       "S1,테니스장1,접수중,응봉공원,2026-01-01\nS2,테니스장2,접수종료,응봉공원,2026-01-01\n"
       "S3,농구장,안내중,중랑천,2026-02-01\nS4,풋살장,접수중,노들나루,2026-02-01\nS5,탁구장,예약마감,구민회관,2026-03-01\n"
       "S6,배드민턴장,접수중,구민회관,2026-03-01\n")
UNDERSTANDING = {
    "version": 1, "kind": "catalog", "subject": "체육시설 예약 서비스", "purpose": "시민이 예약 가능한 체육시설 서비스 목록",
    "actors": [{"id": "a1", "label": "시민", "kind": "requester"}, {"id": "a2", "label": "운영기관", "kind": "handler"}],
    "columnRoles": ["identifier", "title", "status", "location", "date_event"],
    "columnConfidence": ["high"] * 5, "columnEvidence": [""] * 5,
    "processes": [{"id": "p1", "title": "접수 상태", "basis": "status_column", "columns": [3],
                   "states": [{"value": "안내중", "kind": "start"}, {"value": "접수중", "kind": "active"},
                              {"value": "예약마감", "kind": "waiting"}, {"value": "접수종료", "kind": "done"}],
                   "transitions": ["안내중>접수중:a2", "접수중>예약마감:a2", "접수중>접수종료:a2"],
                   "evidence": "", "confidence": "high", "after": ""}],
    "lifecycle": {"rowCreated": "", "rowUpdated": "", "rowClosed": ""}, "questions": []}


class SubmissionDerivationTests(SimpleTestCase):
    def test_catalog_with_requester_gets_an_application_flow_gated_by_the_status_flow(self):
        report = analyze(CSV.encode())
        understanding, _ = validate_understanding(UNDERSTANDING, report)
        derived = derive_blueprint(understanding, report)
        workflow = derived["blueprint"]["workflows"][0]
        self.assertEqual((workflow["title"], workflow["subjectColumn"]), ("체육시설 예약 서비스 신청", 2))
        self.assertEqual(workflow["openWhen"], {"flow": "row_1", "kinds": ["active"]})
        self.assertIsNone(derived["createForm"])  # applications are records, not new facilities
        no_requester = json.loads(json.dumps(understanding))
        no_requester["actors"] = [understanding["actors"][1]]
        self.assertEqual(derive_blueprint(no_requester, report)["blueprint"]["workflows"], [])


class SubmissionApiTests(APITestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = override_settings(MEDIA_ROOT=temporary.name, ANTHROPIC_API_KEY="synthetic-test-secret")
        settings.enable()
        self.addCleanup(settings.disable)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/session/").data["csrf_token"]
        uploaded = self.client.post("/api/uploads/", {"file": SimpleUploadedFile("체육시설.csv", CSV.encode())},
                                    format="multipart", HTTP_X_CSRFTOKEN=self.token)
        self.upload = Upload.objects.get(pk=uploaded.data["id"])
        self.upload.understanding, _ = validate_understanding(UNDERSTANDING, self.upload.analysis)
        self.upload.save(update_fields=["understanding"])
        self.base = f"/api/uploads/{self.upload.pk}/blueprint/"
        self.client.post(f"/api/uploads/{self.upload.pk}/understanding/apply/", {}, format="json", HTTP_X_CSRFTOKEN=self.token)

    def _post(self, path, body):
        return self.client.post(self.base + path, body, format="json", HTTP_X_CSRFTOKEN=self.token)

    def test_only_rows_in_an_active_state_take_applications(self):
        rows = {row["values"][0]: row for row in self.client.get(self.base + "rows/").data["rows"]}
        closed = self._post("submissions/", {"workflow_id": "flow_1", "row_id": rows["S2"]["id"],
                                             "values": {"field_1": "김민수", "field_2": "010-0000-0000"}})
        self.assertEqual(closed.status_code, 400)
        self.assertIn("접수종료", closed.data["detail"])
        opened = self._post("submissions/", {"workflow_id": "flow_1", "row_id": rows["S1"]["id"],
                                             "values": {"field_1": "김민수", "field_2": "010-0000-0000"}})
        self.assertEqual(opened.status_code, 201, opened.data)
        self.assertEqual((opened.data["subject"], opened.data["status"]), ("테니스장1", "state_1"))
        # The admin opens S3 through the row flow; then it takes applications too.
        moved = self._post(f"rows/{rows['S3']['id']}/transition/", {"flow_id": "row_1", "to": "접수중", "actor": "admin"})
        self.assertEqual(moved.status_code, 200, moved.data)
        again = self._post("submissions/", {"workflow_id": "flow_1", "row_id": rows["S3"]["id"],
                                            "values": {"field_1": "이서연", "field_2": "010-1111-1111", "field_3": "주말"}})
        self.assertEqual(again.status_code, 201, again.data)

    def test_admin_approves_and_owner_cancels_only_their_own(self):
        rows = {row["values"][0]: row for row in self.client.get(self.base + "rows/").data["rows"]}
        item = self._post("submissions/", {"workflow_id": "flow_1", "row_id": rows["S1"]["id"],
                                           "values": {"field_1": "김민수", "field_2": "010-0000-0000"}}).data
        approved = self.client.patch(self.base + f"submissions/{item['id']}/", {"actor": "admin", "to": "state_2"},
                                     format="json", HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual((approved.status_code, approved.data["status"]), (200, "state_2"))
        refused = self.client.patch(self.base + f"submissions/{item['id']}/", {"actor": "owner", "to": "state_4"},
                                    format="json", HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(refused.status_code, 400)  # already approved: no owner transition from state_2
        mine = self.client.get(self.base + "submissions/?workflow=flow_1&role=owner").data["items"]
        self.assertEqual([entry["status"] for entry in mine], ["state_2"])
        stranger = APIClient(enforce_csrf_checks=True)
        stranger.get("/api/session/")
        self.assertEqual(stranger.get(self.base + "submissions/?workflow=flow_1&role=owner").status_code, 404)
        self.assertEqual(BlueprintSubmission.objects.count(), 1)
