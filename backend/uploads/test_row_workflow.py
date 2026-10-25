"""Row workflows operate a register sheet in place; no Claude calls."""
import json
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient, APITestCase

from .analysis import analyze
from .models import ManagedRow, RowHistory, Upload
from .row_workflow import TransitionError, apply_transition, flow_payload, row_state
from .service_blueprint import BlueprintError, validate_blueprint
from .sheet_understanding import validate_understanding
from .understanding_derivation import derive_blueprint

EXAMPLE = Path(__file__).resolve().parents[1] / "claude_api_settings" / "sheet_understanding_response.example.json"
SHEET = Path(__file__).resolve().parents[1] / "evaluation" / "sheets" / "민원접수대장.csv"
TODAY = date(2026, 10, 25)


def derived_flows():
    report = analyze(SHEET.read_bytes())
    understanding, _ = validate_understanding(json.loads(EXAMPLE.read_text(encoding="utf-8")), report)
    derived = derive_blueprint(understanding, report)
    return report, derived


class RowWorkflowUnitTests(SimpleTestCase):
    def setUp(self):
        self.report, self.derived = derived_flows()
        self.flows = self.derived["rowWorkflows"]
        self.status, self.reply = self.flows

    def test_state_is_read_from_the_row_itself(self):
        values = ["M-1", "2026-10-01", "김민수", "010", "소음", "내용", "배정", "환경과", "2026-10-08", "", "", "N", "", ""]
        self.assertEqual(row_state(self.status, values), "배정")
        self.assertEqual(row_state(self.reply, values), "회신 전")
        payload = flow_payload(self.flows, values)
        self.assertEqual((payload["row_1"]["kind"], payload["row_2"]["blocked"]), ("active", True))

    def test_transition_edits_status_closed_and_result_columns(self):
        values = ["M-1", "2026-10-01", "김민수", "010", "소음", "내용", "처리중", "환경과", "2026-10-08", "", "", "N", "", ""]
        new, changes = apply_transition(self.status, self.flows, values, to="완료", actor="admin",
                                        inputs={"11": "현장 조치 완료"}, today=TODAY)
        self.assertEqual((new[6], new[9], new[10]), ("완료", "2026-10-25", "현장 조치 완료"))
        self.assertEqual(set(changes), {"7", "10", "11"})
        with self.assertRaises(TransitionError):
            apply_transition(self.status, self.flows, values, to="배정", actor="admin", inputs={}, today=TODAY)
        with self.assertRaises(TransitionError):
            apply_transition(self.status, self.flows, values, to="완료", actor="user", inputs={}, today=TODAY)

    def test_flag_flow_waits_for_its_predecessor_then_fills_companions(self):
        values = ["M-1", "2026-10-01", "김민수", "010", "소음", "내용", "처리중", "환경과", "2026-10-08", "", "", "N", "", ""]
        with self.assertRaises(TransitionError):
            apply_transition(self.reply, self.flows, values, to="회신 완료", actor="admin", inputs={}, today=TODAY)
        values[6], values[9] = "완료", "2026-10-20"
        new, _ = apply_transition(self.reply, self.flows, values, to="회신 완료", actor="admin",
                                  inputs={"14": "처리 결과를 안내드렸습니다"}, today=TODAY)
        self.assertEqual((new[11], new[12], new[13]), ("Y", "2026-10-25", "처리 결과를 안내드렸습니다"))  # the sheet's own flag value
        self.assertEqual(row_state(self.reply, new), "회신 완료")

    def test_blueprint_validation_covers_row_workflows(self):
        blueprint = {**self.derived["blueprint"], "rowWorkflows": self.flows, "createForm": self.derived["createForm"]}
        validate_blueprint(blueprint, self.report)
        broken = json.loads(json.dumps(blueprint))
        broken["rowWorkflows"][0]["statusColumn"] = 99
        with self.assertRaises(BlueprintError):
            validate_blueprint(broken, self.report)
        broken = json.loads(json.dumps(blueprint))
        broken["rowWorkflows"][1]["after"] = "row_9"
        with self.assertRaises(BlueprintError):
            validate_blueprint(broken, self.report)


class RowWorkflowApiTests(APITestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings = override_settings(MEDIA_ROOT=temporary.name, ANTHROPIC_API_KEY="synthetic-test-secret")
        settings.enable()
        self.addCleanup(settings.disable)
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/session/").data["csrf_token"]
        uploaded = self.client.post("/api/uploads/", {"file": SimpleUploadedFile("민원접수대장.csv", SHEET.read_bytes())},
                                    format="multipart", HTTP_X_CSRFTOKEN=self.token)
        self.upload = Upload.objects.get(pk=uploaded.data["id"])
        self.base = f"/api/uploads/{self.upload.pk}/"
        with patch("uploads.sheet_understanding_views._post_message") as post_message:
            post_message.return_value = (200, {"request-id": "synthetic"}, json.dumps({
                "content": [{"type": "text", "text": EXAMPLE.read_text(encoding="utf-8")}],
                "usage": {"input_tokens": 1, "output_tokens": 1}}))
            approval = self.client.get(self.base + "understanding/approval/").data
            self.client.post(self.base + "understanding/", {"approved": True, "request_fingerprint": approval["request_fingerprint"],
                                                            "approval_note": "synthetic"}, format="json", HTTP_X_CSRFTOKEN=self.token)

    def _post(self, path, body):
        return self.client.post(self.base + path, body, format="json", HTTP_X_CSRFTOKEN=self.token)

    def test_apply_makes_the_service_without_a_call_and_rows_carry_their_states(self):
        applied = self._post("understanding/apply/", {})
        self.assertEqual(applied.status_code, 200, applied.data)
        self.assertEqual([flow["id"] for flow in applied.data["blueprint"]["rowWorkflows"]], ["row_1", "row_2"])
        self.upload.refresh_from_db()
        self.assertEqual(self.upload.service_blueprint["catalog"]["titleColumn"], 1)
        rows = self.client.get(self.base + "blueprint/rows/").data["rows"]
        self.assertIn(rows[0]["flows"]["row_1"]["state"], {"접수", "배정", "처리중", "완료", "반려"})

    def test_admin_transition_user_create_and_history(self):
        self._post("understanding/apply/", {})
        received = next(row for row in self.client.get(self.base + "blueprint/rows/?filter_column=7&filter_value=접수").data["rows"])
        moved = self._post(f"blueprint/rows/{received['id']}/transition/",
                           {"flow_id": "row_1", "to": "배정", "actor": "admin", "inputs": {"8": "도로과"}})
        self.assertEqual(moved.status_code, 200, moved.data)
        self.assertEqual((moved.data["values"][6], moved.data["values"][7], moved.data["flows"]["row_1"]["state"]), ("배정", "도로과", "배정"))
        refused = self._post(f"blueprint/rows/{received['id']}/transition/", {"flow_id": "row_1", "to": "완료", "actor": "admin"})
        self.assertEqual(refused.status_code, 400)
        created = self._post("blueprint/rows/mine/", {"values": {"3": "박지훈", "4": "010-1234-5678", "5": "소음", "6": "밤에 공사 소음이 심합니다"}})
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual((created.data["values"][6], created.data["values"][2], created.data["mine"]), ("접수", "박지훈", True))
        self.assertEqual(ManagedRow.objects.get(pk=created.data["id"]).created_by_session, self.client.session.session_key)
        mine = self.client.get(self.base + "blueprint/rows/mine/").data["items"]
        self.assertEqual([item["id"] for item in mine], [created.data["id"]])
        history = self.client.get(self.base + f"blueprint/rows/{received['id']}/history/").data["items"]
        self.assertEqual([(item["from"], item["to"], item["actor"]) for item in history], [("접수", "배정", "admin")])
        self.assertEqual(RowHistory.objects.filter(row_id=created.data["id"], to_state="created").count(), 1)
